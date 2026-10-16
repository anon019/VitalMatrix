"""Personal health dataset: key-protected reads, owner-JWT journal writes."""

from datetime import date, timedelta
import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.openapi.utils import get_openapi
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_user,
    resolve_default_user,
    verify_mcp_api_key,
    api_key_header,
)
from app.database.session import get_db
from app.config import settings
from app.models.oura import OuraAuth
from app.models.nutrition import FoodItem
from app.models.research import HealthDirtyDay, HealthJournalEntry, HealthSourceRecord
from app.models.user import User
from app.schemas.research import JournalEntryCreate
from app.services.research_schema import TIMEZONE
from app.services.research_service import (
    ResearchService,
    json_value,
    nutrition_basis_hash,
)
from app.utils.datetime_helper import date_hk, now_hk, today_hk

router = APIRouter()


@router.get("/openapi.json", include_in_schema=False)
async def research_openapi(request: Request):
    """Public contract only; no records, identifiers or credentials."""
    prefix = "/api/v1/research"
    paths = {
        prefix + suffix
        for suffix in (
            "/catalog",
            "/profile",
            "/records/{dataset}",
            "/days",
            "/context",
            "/patterns",
        )
    }
    spec = get_openapi(
        title="Personal Health Dataset",
        version="1.0.0",
        description="Read-only personal health research. Missing values remain null; inspect quality and source evidence.",
        routes=[r for r in request.app.routes if getattr(r, "path", None) in paths],
        servers=[{"url": str(request.base_url).rstrip("/")}],
    )
    for path, item in spec["paths"].items():
        operation = item["get"]
        operation["x-openai-isConsequential"] = False
        operation["parameters"] = [
            p for p in operation.get("parameters", []) if p.get("in") != "header"
        ]
        operation["security"] = [{"HTTPBearer": []}]
        operation["responses"]["200"]["content"]["application/json"]["schema"] = {
            "type": "object",
            "properties": {"schema_version": {"type": "string"}},
            "additionalProperties": True,
        }
    return spec


async def research_owner(
    credentials: HTTPAuthorizationCredentials | None = Depends(api_key_header),
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    token = credentials.credentials if credentials else x_api_key
    if (
        settings.MCP_API_KEY
        and token
        and hmac.compare_digest(token.encode(), settings.MCP_API_KEY.encode())
    ):
        return await resolve_default_user(db)
    if credentials:
        return await get_current_user(credentials, db)
    await verify_mcp_api_key(credentials, x_api_key)
    return await resolve_default_user(db)


async def profile_data(user, db):
    fields = (
        "weight",
        "height",
        "gender",
        "birth_year",
        "birth_month",
        "hr_max",
        "resting_hr",
        "health_goal",
        "training_plan",
        "updated_at",
    )
    auth = (
        await db.execute(select(OuraAuth).where(OuraAuth.user_id == user.id))
    ).scalar_one_or_none()
    info = auth.personal_info if auth and auth.personal_info else {}
    polar = (
        await db.execute(
            select(HealthSourceRecord)
            .where(
                HealthSourceRecord.user_id == user.id,
                HealthSourceRecord.source == "polar",
                HealthSourceRecord.kind == "physical_info",
            )
            .order_by(
                HealthSourceRecord.day.desc(), HealthSourceRecord.updated_at.desc()
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "timezone": TIMEZONE,
        "profile": {f: json_value(getattr(user, f)) for f in fields},
        "device_profile": {
            f: info.get(f) for f in ("age", "weight", "height", "biological_sex")
        },
        "polar_profile": (
            {
                "data": polar.data,
                "source_record_id": str(polar.id),
                "updated_at": json_value(polar.updated_at),
            }
            if polar
            else None
        ),
        "profile_units": {
            "weight": "kg",
            "height": "cm",
            "hr_max": "bpm",
            "resting_hr": "bpm",
        },
        "profile_limitations": [
            "profile为当前配置，不是历史测量；身高/体重来源设备单位请查上游定义。",
            "有效的历史测量和体检结果通过journal查询；不自动覆盖用户资料。",
        ],
    }


@router.get("/catalog")
async def catalog(
    user: User = Depends(research_owner), db: AsyncSession = Depends(get_db)
):
    return await ResearchService(db).catalog(user.id)


@router.get("/profile")
async def profile(
    user: User = Depends(research_owner), db: AsyncSession = Depends(get_db)
):
    return await profile_data(user, db)


@router.get("/records/{dataset}")
async def records(
    dataset: str,
    start: date,
    end: date,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0, le=1000000),
    include_raw: bool = False,
    include_samples: bool = False,
    include_superseded: bool = False,
    user: User = Depends(research_owner),
    db: AsyncSession = Depends(get_db),
):
    return await ResearchService(db).records(
        user.id,
        dataset,
        start,
        end,
        limit,
        offset,
        include_raw,
        include_samples,
        include_superseded,
    )


@router.get("/days")
async def days(
    start: date,
    end: date,
    metrics: str | None = Query(None, max_length=5000),
    user: User = Depends(research_owner),
    db: AsyncSession = Depends(get_db),
):
    selected = [m.strip() for m in metrics.split(",") if m.strip()] if metrics else None
    return await ResearchService(db).days(user.id, start, end, selected)


@router.get("/context")
async def context(
    target_date: date | None = None,
    user: User = Depends(research_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await ResearchService(db).context(user.id, target_date or today_hk())
    result.update(await profile_data(user, db))
    return result


@router.get("/patterns")
async def patterns(
    start: date,
    end: date,
    x: str,
    y: str,
    lag: int = Query(1, ge=0, le=14),
    min_pairs: int = Query(20, ge=20, le=100),
    user: User = Depends(research_owner),
    db: AsyncSession = Depends(get_db),
):
    return await ResearchService(db).association(
        user.id, start, end, x, y, lag, min_pairs
    )


@router.post("/journal", status_code=201)
async def create_journal(
    entry: JournalEntryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Append evidence; retries are idempotent, corrections retain the original."""
    if entry.occurred_at > now_hk():
        raise HTTPException(422, "future entries are plans, not recorded health facts")
    data = entry.model_dump(
        mode="json",
        exclude={
            "source",
            "external_id",
            "kind",
            "occurred_at",
            "ended_at",
            "supersedes_id",
        },
    )
    existing = (
        await db.execute(
            select(HealthJournalEntry).where(
                HealthJournalEntry.user_id == user.id,
                HealthJournalEntry.source == entry.source,
                HealthJournalEntry.external_id == entry.external_id,
            )
        )
    ).scalar_one_or_none()

    def same(row):
        return (
            row.kind == entry.kind
            and row.occurred_at == entry.occurred_at
            and row.ended_at == entry.ended_at
            and {k: v for k, v in row.data.items() if k != "_nutrition_basis_hash"}
            == {k: v for k, v in data.items() if k != "_nutrition_basis_hash"}
            and row.supersedes_id == entry.supersedes_id
        )

    if existing:
        if not same(existing):
            raise HTTPException(409, "external_id already used with different content")
        return {"id": str(existing.id), "day": str(existing.day), "reused": True}
    if entry.kind == "nutrition_coverage" and entry.complete:
        day = date_hk(entry.occurred_at)
        meals = (
            (
                await db.execute(
                    ResearchService(db).source_query("meals", user.id, day, day)
                )
            )
            .mappings()
            .all()
        )
        foods = (
            (
                await db.execute(
                    select(*FoodItem.__table__.columns).where(
                        FoodItem.meal_id.in_([r["id"] for r in meals])
                    )
                )
            )
            .mappings()
            .all()
            if meals
            else []
        )
        data["_nutrition_basis_hash"] = nutrition_basis_hash(meals, foods)
    if entry.supersedes_id:
        old = (
            await db.execute(
                select(HealthJournalEntry)
                .where(
                    HealthJournalEntry.id == entry.supersedes_id,
                    HealthJournalEntry.user_id == user.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if old is None:
            raise HTTPException(404, "superseded entry not found")
        replaced = await db.scalar(
            select(HealthJournalEntry.id).where(
                HealthJournalEntry.supersedes_id == old.id
            )
        )
        if replaced:
            raise HTTPException(409, "correct the latest version of this entry")
        # A correction can move the observation to another day.
        last = date_hk(old.ended_at) if old.ended_at else old.day
        dates = [
            old.day + timedelta(days=i)
            for i in range((min(last, today_hk()) - old.day).days + 1)
        ]
        if dates:
            dirty = insert(HealthDirtyDay).values(
                [
                    {"user_id": user.id, "day": d, "requested_at": now_hk()}
                    for d in dates
                ]
            )
            await db.execute(
                dirty.on_conflict_do_update(
                    index_elements=["user_id", "day"],
                    set_={"requested_at": dirty.excluded.requested_at},
                )
            )
    new_id = uuid.uuid4()
    stmt = insert(HealthJournalEntry).values(
        id=new_id,
        user_id=user.id,
        source=entry.source,
        external_id=entry.external_id,
        kind=entry.kind,
        day=date_hk(entry.occurred_at),
        occurred_at=entry.occurred_at,
        ended_at=entry.ended_at,
        data=data,
        supersedes_id=entry.supersedes_id,
    )
    result = await db.execute(
        stmt.on_conflict_do_nothing(
            index_elements=["user_id", "source", "external_id"]
        ).returning(HealthJournalEntry.id)
    )
    inserted = result.scalar_one_or_none()
    if not inserted:
        row = (
            await db.execute(
                select(HealthJournalEntry).where(
                    HealthJournalEntry.user_id == user.id,
                    HealthJournalEntry.source == entry.source,
                    HealthJournalEntry.external_id == entry.external_id,
                )
            )
        ).scalar_one()
        if not same(row):
            raise HTTPException(409, "external_id already used with different content")
        new_id = row.id
    await db.commit()
    return {
        "id": str(new_id),
        "day": str(date_hk(entry.occurred_at)),
        "reused": not bool(inserted),
        "research_status": "queued",
    }
