"""Source-preserving queries and durable, coverage-aware research features."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, pstdev
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from app.models.nutrition import FoodItem, MealRecord
from app.models.oura import OuraAuth, OuraHeartRateSample
from app.models.polar import PolarAuth
from app.models.research import (
    HealthDailyFeature,
    HealthDirtyDay,
    HealthJournalEntry,
)
from app.services.research_schema import (
    DATASETS,
    LIMITATIONS,
    MAPPINGS,
    SCHEMA_VERSION,
    TIMEZONE,
    metric_definitions,
)
from app.utils.datetime_helper import HK_TZ, date_hk, now_hk, start_of_day_hk, today_hk


def json_value(value):
    if isinstance(value, (date, datetime, uuid.UUID)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value"):
        return value.value
    return value


def compact_payload(value, include_samples=False):
    """Large series are opt-in, but their existence/length remains discoverable."""
    if isinstance(value, dict):
        return {k: compact_payload(v, include_samples) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > 20 and not include_samples:
            return {
                "sample_count": len(value),
                "omitted": True,
                "request": "include_samples=true",
            }
        return [compact_payload(v, include_samples) for v in value]
    if isinstance(value, str) and len(value) > 2000 and not include_samples:
        return {
            "length": len(value),
            "omitted": True,
            "request": "include_samples=true",
        }
    return json_value(value)


def validate_range(start, end, maximum=366):
    if start > end or (end - start).days >= maximum:
        raise HTTPException(
            422, f"date range must be ordered and at most {maximum} days inclusive"
        )
    if end > today_hk():
        raise HTTPException(422, "future research dates are not available")


def numeric(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def sum_known(rows, field, factor=1):
    numbers = [numeric(r.get(field)) for r in rows]
    values = [n for n in numbers if n is not None]
    return round(sum(values) * factor, 3) if values else None


def nutrition_basis_hash(meals, foods):
    """Confirmations apply to these exact intake facts, never to later corrections."""
    meal_fields = (
        "id",
        "meal_time",
        "meal_type",
        "analysis_status",
        "notes",
        "total_calories",
        "total_protein",
        "total_carbs",
        "total_fat",
        "total_fiber",
    )
    food_fields = (
        "id",
        "meal_id",
        "food_name",
        "category",
        "estimated_weight",
        "calories",
        "protein",
        "carbs",
        "fat",
        "fiber",
        "sodium",
        "sugar",
    )
    ids = {r["id"] for r in meals}
    value = {
        "meals": [
            {f: r.get(f) for f in meal_fields}
            for r in sorted(meals, key=lambda r: str(r["id"]))
        ],
        "foods": [
            {f: r.get(f) for f in food_fields}
            for r in sorted(foods, key=lambda r: str(r["id"]))
            if r["meal_id"] in ids
        ],
    }
    return hashlib.sha256(
        json.dumps(
            value, default=json_value, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def minute_of_day(value):
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    value = value.astimezone(HK_TZ)
    return value.hour * 60 + value.minute + value.second / 60


def match_workouts(polar, oura):
    """Conservative one-to-one matching; ambiguous candidates are never silently merged."""
    candidates = defaultdict(list)
    reverse = defaultdict(list)
    for i, o in enumerate(oura):
        os, oe = o.get("start_datetime"), o.get("end_datetime")
        if not os or not oe or oe <= os:
            continue
        for j, p in enumerate(polar):
            ps, pe = p.get("start_time"), p.get("end_time")
            if not ps or not pe or pe <= ps:
                continue
            overlap = max(0, (min(oe, pe) - max(os, ps)).total_seconds())
            longest = max((oe - os).total_seconds(), (pe - ps).total_seconds())
            if overlap / longest >= 0.8 and abs((os - ps).total_seconds()) <= 600:
                candidates[i].append(j)
                reverse[j].append(i)
    pairs = [
        (i, js[0])
        for i, js in candidates.items()
        if len(js) == 1 and len(reverse[js[0]]) == 1
    ]
    matched = {i for i, _ in pairs}
    return (
        [o for i, o in enumerate(oura) if i not in matched],
        [
            {
                "oura_id": str(oura[i]["id"]),
                "polar_id": str(polar[j]["id"]),
                "method": "unique_overlap_80_percent",
            }
            for i, j in pairs
        ],
        bool(set(candidates) - matched),
    )


def build_day(day, grouped, foods, hr=None):
    """Pure transformation. Preserve missing values and source-specific signals."""
    metrics = {key: None for key in metric_definitions()}
    evidence = {
        name: [str(r["id"]) for r in rows] for name, rows in grouped.items() if rows
    }
    quality = {"partial_day": day == today_hk(), "missing_datasets": [], "warnings": []}
    for name in ("sleep", "readiness", "activity", "stress", "meals"):
        if not grouped.get(name):
            quality["missing_datasets"].append(name)
    for dataset, fields in MAPPINGS.items():
        rows = grouped.get(dataset, [])
        if dataset == "sleep":
            rows = [r for r in rows if r.get("sleep_type") != "rest"]
            rows = sorted(
                rows,
                key=lambda r: (
                    r.get("sleep_type") == "long_sleep",
                    r.get("total_sleep_duration") or 0,
                ),
                reverse=True,
            )
        record = rows[0] if rows else {}
        for field, (_, factor) in fields.items():
            value = numeric(record.get(field))
            metrics[f"{dataset}.{field}"] = (
                round(value * factor, 3) if value is not None else None
            )
        if len(rows) > 1 and dataset != "sleep":
            quality["warnings"].append(f"multiple_{dataset}_records")

    sleeps = [r for r in grouped.get("sleep", []) if r.get("sleep_type") != "rest"]
    main = max(
        sleeps,
        key=lambda r: (
            r.get("sleep_type") == "long_sleep",
            r.get("total_sleep_duration") or 0,
        ),
        default={},
    )
    naps = [r for r in sleeps if r is not main]
    metrics["sleep.total_minutes"] = sum_known(sleeps, "total_sleep_duration", 1 / 60)
    metrics["sleep.nap_minutes"] = (
        sum_known(naps, "total_sleep_duration", 1 / 60)
        if naps
        else (0 if sleeps else None)
    )
    metrics["sleep.nap_count"] = len(naps) if sleeps else None
    metrics["sleep.bedtime_minute"] = minute_of_day(main.get("bedtime_start"))
    metrics["sleep.wake_minute"] = minute_of_day(main.get("bedtime_end"))
    quality["main_sleep_id"] = str(main["id"]) if main else None
    quality["sleep_algorithm_versions"] = sorted(
        {
            r["sleep_algorithm_version"]
            for r in sleeps
            if r.get("sleep_algorithm_version")
        }
    )

    polar = grouped.get("polar_exercises", [])
    unmatched, pairs, ambiguous = match_workouts(
        polar, grouped.get("oura_workouts", [])
    )
    quality["workout_matches"] = pairs
    quality["workout_match_ambiguous"] = ambiguous
    if polar or unmatched:
        duration = sum_known(polar, "duration_sec", 1 / 60) or 0
        valid_oura = [
            r
            for r in unmatched
            if r.get("start_datetime")
            and r.get("end_datetime")
            and r["end_datetime"] >= r["start_datetime"]
        ]
        metrics["training.duration_minutes"] = round(
            duration
            + sum(
                (r["end_datetime"] - r["start_datetime"]).total_seconds() / 60
                for r in valid_oura
            ),
            3,
        )
        metrics["training.sessions"] = len(polar) + len(unmatched)
        quality["workout_duration_complete"] = len(valid_oura) == len(unmatched)
        if len(valid_oura) != len(unmatched):
            quality["warnings"].append("workout_duration_partial")
        metrics["training.zone2_minutes"] = sum_known(polar, "zone2_sec", 1 / 60)
        metrics["training.high_intensity_minutes"] = sum_known(
            polar, "zone4_sec", 1 / 60
        )
        if metrics["training.high_intensity_minutes"] is not None:
            metrics["training.high_intensity_minutes"] += (
                sum_known(polar, "zone5_sec", 1 / 60) or 0
            )
        metrics["training.zone_weighted_load"] = (
            round(
                sum(
                    (numeric(r.get(f"zone{i}_sec")) or 0) * w / 60
                    for r in polar
                    for i, w in enumerate([1, 1.25, 1.5, 1.75, 2], 1)
                ),
                3,
            )
            if polar
            else None
        )
        metrics["training.recorded_calories"] = (
            (sum_known(polar, "calories") or 0)
            + (sum_known(unmatched, "calories") or 0)
            if any(r.get("calories") is not None for r in polar + unmatched)
            else None
        )
    quality["training_coverage"] = (
        "recorded_sessions_only; no-session does not confirm rest"
    )
    quality["zone_coverage"] = "polar_only"

    all_meals = grouped.get("meals", [])
    meals = [r for r in all_meals if r.get("analysis_status") == "completed"]
    quality["nutrition"] = {
        "recorded_meals": len(meals),
        "pending_or_failed_meals": len(all_meals) - len(meals),
        "complete_day_confirmed": False,
        "method": "photo_ai_estimate",
    }
    if meals:
        metrics["nutrition.meals"] = len(meals)
        for field in ("calories", "protein", "carbs", "fat", "fiber"):
            metrics[f"nutrition.{field}"] = sum_known(meals, f"total_{field}")
        metrics["nutrition.last_meal_minute"] = minute_of_day(
            max(r["meal_time"] for r in meals)
        )
        meal_ids = {r["id"] for r in meals}
        meal_foods = [f for f in foods if f["meal_id"] in meal_ids]
        for field in ("sodium", "sugar"):
            metrics[f"nutrition.recorded_{field}"] = sum_known(meal_foods, field)
            quality["nutrition"][field + "_observed_items"] = sum(
                f.get(field) is not None for f in meal_foods
            )
        quality["nutrition"]["food_items"] = len(meal_foods)
        missing = []
        base = Path(__file__).resolve().parents[2] / "uploads" / "nutrition"
        for r in meals:
            path = r.get("photo_path")
            if path:
                normalized = (
                    path.removeprefix("/uploads/nutrition/")
                    .removeprefix("uploads/nutrition/")
                    .lstrip("/")
                )
                candidate = (base / normalized).resolve()
                if (
                    not candidate.is_relative_to(base.resolve())
                    or not candidate.is_file()
                ):
                    missing.append(str(r["id"]))
            else:
                missing.append(str(r["id"]))
        quality["nutrition"]["missing_original_media"] = missing
    journal = sorted(
        grouped.get("journal", []), key=lambda r: (r["occurred_at"], str(r["id"]))
    )
    quality["events"] = [
        {
            "id": str(r["id"]),
            "kind": r["kind"],
            "label": r["data"].get("label"),
            "tags": r["data"].get("tags", []),
        }
        for r in journal
        if r["kind"] not in ("measurement", "lab", "nutrition_coverage")
    ]
    quality["measurement_methods"] = {}
    for entry in journal:
        data = entry["data"]
        if entry["day"] == day:
            for item in data.get("measurements", []):
                key = "journal." + item["code"]
                value = numeric(item["value"])
                if key in metrics:
                    metrics[key] = (
                        ((metrics[key] or 0) + value)
                        if item["code"] in ("water", "caffeine", "alcohol")
                        else value
                    )
                    quality["measurement_methods"][key] = item["method"]
    confirmations = [
        r for r in journal if r["kind"] == "nutrition_coverage" and r["day"] == day
    ]
    if confirmations:
        confirmation = max(
            confirmations,
            key=lambda r: (r.get("created_at") or r["occurred_at"], str(r["id"])),
        )
        data = confirmation["data"]
        valid = data.get("_nutrition_basis_hash") == nutrition_basis_hash(
            all_meals, foods
        )
        quality["nutrition"]["complete_day_confirmed"] = bool(
            data.get("complete") and valid
        )
        quality["nutrition"]["confirmation_outdated"] = bool(
            data.get("complete") and not valid
        )
    if hr:
        for field in ("mean", "min", "max", "samples"):
            metrics["heart_rate." + field] = numeric(hr.get(field))
        evidence["heart_rate"] = {
            "range_start": json_value(hr["first_at"]),
            "range_end": json_value(hr["last_at"]),
            "samples": hr["samples"],
        }
    records = grouped.get("provider_records", [])
    quality["provider_date_unknown"] = [
        str(r["id"])
        for r in records
        if r["kind"] != "sync_status"
        and r["data"].get("_date_basis") == "collection_day_only"
    ]
    sessions = [r for r in records if r["source"] == "oura" and r["kind"] == "session"]
    metrics["sessions.duration_minutes"] = sum_known(
        [r["data"] for r in sessions], "duration_minutes"
    )
    for r in records:
        data = r["data"]
        prefix = {
            ("polar", "activity"): "polar_activity",
            ("polar", "cardio_load"): "polar_load",
        }.get((r["source"], r["kind"]))
        if prefix:
            if (
                prefix == "polar_load"
                and data.get("cardio_load_status") == "LOAD_STATUS_NOT_AVAILABLE"
            ):
                quality["warnings"].append("polar_load_unavailable")
                continue
            for field, value in data.items():
                key = prefix + "." + field
                if key in metrics:
                    metrics[key] = numeric(value)
    return {"metrics": metrics, "evidence": evidence, "quality": quality}


class ResearchService:
    def __init__(self, db):
        self.db = db

    def source_query(
        self,
        name,
        user_id,
        start,
        end,
        *,
        include_raw=False,
        include_samples=False,
        include_superseded=False,
    ):
        if name not in DATASETS:
            raise HTTPException(422, "unknown dataset; use /catalog")
        spec = DATASETS[name]
        large = {
            "raw_json",
            "ai_analysis",
            "heart_rate_samples",
            "hrv_samples",
            "met_samples",
            "sleep_phase_30_sec",
            "sleep_phase_5_min",
            "app_sleep_phase_5_min",
            "movement_30_sec",
            "class_5_min",
        }
        cols = [
            c
            for c in spec.model.__table__.columns
            if c.name != "user_id"
            and (
                c.name not in large
                or (c.name in ("raw_json", "ai_analysis") and include_raw)
                or (c.name not in ("raw_json", "ai_analysis") and include_samples)
            )
        ]
        day_col = spec.day_expression
        query = select(*cols).where(spec.model.user_id == user_id)
        if spec.timestamp:
            col = getattr(spec.model, spec.date_field)
            query = query.where(
                col >= start_of_day_hk(start),
                col < start_of_day_hk(end + timedelta(days=1)),
            )
        elif name in ("tags", "rest_mode"):
            model = spec.model
            query = query.where(
                day_col <= end,
                func.coalesce(model.end_day, day_col if name == "tags" else today_hk())
                >= start,
            )
        elif name == "journal":
            replacement = aliased(HealthJournalEntry)
            query = query.where(
                day_col <= end,
                func.coalesce(
                    func.date(func.timezone(TIMEZONE, HealthJournalEntry.ended_at)),
                    day_col,
                )
                >= start,
            )
            if not include_superseded:
                query = query.where(
                    ~exists(
                        select(replacement.id).where(
                            replacement.supersedes_id == HealthJournalEntry.id,
                            replacement.user_id == user_id,
                        )
                    )
                )
        else:
            query = query.where(day_col >= start, day_col <= end)
        return query.order_by(getattr(spec.model, spec.date_field), spec.model.id)

    async def records(
        self,
        user_id,
        name,
        start,
        end,
        limit=100,
        offset=0,
        include_raw=False,
        include_samples=False,
        include_superseded=False,
    ):
        validate_range(start, end)
        if not 1 <= limit <= 1000 or not 0 <= offset <= 1000000:
            raise HTTPException(422, "invalid pagination")
        if include_raw or include_samples:
            limit = min(limit, 25)
        query = self.source_query(
            name,
            user_id,
            start,
            end,
            include_raw=include_raw,
            include_samples=include_samples,
            include_superseded=include_superseded,
        )
        rows = [
            dict(r)
            for r in (
                await self.db.execute(query.limit(limit + 1).offset(offset))
            ).mappings()
        ]
        more = len(rows) > limit
        rows = rows[:limit]
        if name == "meals" and rows:
            food_rows = (
                (
                    await self.db.execute(
                        select(*FoodItem.__table__.columns)
                        .where(FoodItem.meal_id.in_([r["id"] for r in rows]))
                        .order_by(FoodItem.id)
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                row["food_items"] = [
                    dict(f) for f in food_rows if f["meal_id"] == row["id"]
                ]
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset": name,
            "timezone": TIMEZONE,
            "start": str(start),
            "end": str(end),
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if more else None,
            "records": [compact_payload(r, include_samples) for r in rows],
        }

    async def catalog(self, user_id):
        datasets = []
        for name, spec in DATASETS.items():
            dc = spec.day_expression
            row = (
                await self.db.execute(
                    select(
                        func.count(),
                        func.min(dc),
                        func.max(dc),
                        func.count(func.distinct(dc)),
                    ).where(spec.model.user_id == user_id)
                )
            ).one()
            datasets.append(
                {
                    "name": name,
                    "source": spec.source,
                    "description": spec.description,
                    "records": row[0],
                    "first_day": json_value(row[1]),
                    "last_day": json_value(row[2]),
                    "recorded_days": row[3],
                    "fields": [
                        {
                            "name": c.name,
                            "storage_type": str(c.type),
                            "description": c.comment,
                        }
                        for c in spec.model.__table__.columns
                        if c.name != "user_id"
                    ],
                }
            )
        auth = (
            await self.db.execute(select(OuraAuth).where(OuraAuth.user_id == user_id))
        ).scalar_one_or_none()
        polar = (
            await self.db.execute(select(PolarAuth).where(PolarAuth.user_id == user_id))
        ).scalar_one_or_none()
        dirty = await self.db.scalar(
            select(func.count())
            .select_from(HealthDirtyDay)
            .where(HealthDirtyDay.user_id == user_id)
        )
        features = (
            await self.db.execute(
                select(
                    func.count(),
                    func.min(HealthDailyFeature.day),
                    func.max(HealthDailyFeature.day),
                ).where(HealthDailyFeature.user_id == user_id)
            )
        ).one()
        return {
            "schema_version": SCHEMA_VERSION,
            "timezone": TIMEZONE,
            "datasets": datasets,
            "metrics": metric_definitions(),
            "limitations": LIMITATIONS,
            "materialization": {
                "days": features[0],
                "first_day": json_value(features[1]),
                "last_day": json_value(features[2]),
                "dirty_days": dirty,
            },
            "connections": {
                "oura": {
                    "active": bool(auth and auth.is_active),
                    "last_sync_at": json_value(auth.last_sync_at) if auth else None,
                    "capabilities": auth.capabilities if auth else None,
                },
                "polar": {
                    "active": bool(polar and polar.is_active),
                    "last_sync_at": json_value(polar.last_sync_at) if polar else None,
                },
            },
        }

    async def refresh_range(self, user_id, start, end):
        """Caller owns transaction and dirty-row locks. Never commit the caller's work."""
        validate_range(start, end)
        grouped = {
            start + timedelta(days=i): defaultdict(list)
            for i in range((end - start).days + 1)
        }
        for name, spec in DATASETS.items():
            if name == "heart_rate":
                continue
            rows = (
                (await self.db.execute(self.source_query(name, user_id, start, end)))
                .mappings()
                .all()
            )
            for row in rows:
                row = dict(row)
                day = (
                    date_hk(row[spec.date_field])
                    if spec.timestamp
                    else row[spec.date_field]
                )
                if day is None:
                    continue
                last = day
                if name in ("tags", "rest_mode"):
                    last = row.get("end_day") or (
                        today_hk() if name == "rest_mode" else day
                    )
                elif name == "journal" and row.get("ended_at"):
                    last = date_hk(row["ended_at"])
                for d in grouped:
                    if day <= d <= last:
                        grouped[d][name].append(row)
        foods = (
            (
                await self.db.execute(
                    select(*FoodItem.__table__.columns)
                    .join(MealRecord, MealRecord.id == FoodItem.meal_id)
                    .where(
                        MealRecord.user_id == user_id,
                        MealRecord.meal_time >= start_of_day_hk(start),
                        MealRecord.meal_time < start_of_day_hk(end + timedelta(days=1)),
                    )
                )
            )
            .mappings()
            .all()
        )
        hr = OuraHeartRateSample
        hr_day = func.date(func.timezone(TIMEZONE, hr.timestamp))
        hr_rows = (
            (
                await self.db.execute(
                    select(
                        hr_day.label("day"),
                        func.avg(hr.bpm).label("mean"),
                        func.min(hr.bpm).label("min"),
                        func.max(hr.bpm).label("max"),
                        func.count().label("samples"),
                        func.min(hr.timestamp).label("first_at"),
                        func.max(hr.timestamp).label("last_at"),
                    )
                    .where(
                        hr.user_id == user_id,
                        hr.timestamp >= start_of_day_hk(start),
                        hr.timestamp < start_of_day_hk(end + timedelta(days=1)),
                    )
                    .group_by(hr_day)
                )
            )
            .mappings()
            .all()
        )
        hr_by_day = {r["day"]: dict(r) for r in hr_rows}
        for day, sources in grouped.items():
            payload = build_day(day, sources, foods, hr_by_day.get(day))
            digest = hashlib.sha256(
                json.dumps(
                    payload, default=json_value, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            stmt = insert(HealthDailyFeature).values(
                id=uuid.uuid4(),
                user_id=user_id,
                day=day,
                schema_version=SCHEMA_VERSION,
                revision=1,
                content_hash=digest,
                updated_at=now_hk(),
                **payload,
            )
            await self.db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["user_id", "day"],
                    set_={
                        "schema_version": SCHEMA_VERSION,
                        "revision": HealthDailyFeature.revision + 1,
                        "content_hash": digest,
                        "metrics": stmt.excluded.metrics,
                        "evidence": stmt.excluded.evidence,
                        "quality": stmt.excluded.quality,
                        "updated_at": stmt.excluded.updated_at,
                    },
                    where=HealthDailyFeature.content_hash != digest,
                )
            )

    async def days(self, user_id, start, end, metrics=None):
        validate_range(start, end)
        definitions = metric_definitions()
        if metrics and any(key not in definitions for key in metrics):
            raise HTTPException(422, "unknown metric; use /catalog")
        rows = (
            (
                await self.db.execute(
                    select(HealthDailyFeature)
                    .where(
                        HealthDailyFeature.user_id == user_id,
                        HealthDailyFeature.day.between(start, end),
                    )
                    .order_by(HealthDailyFeature.day)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        dirty = set(
            (
                await self.db.execute(
                    select(HealthDirtyDay.day).where(
                        HealthDirtyDay.user_id == user_id,
                        HealthDirtyDay.day.between(start, end),
                    )
                )
            ).scalars()
        )
        result = []
        by_day = {r.day: r for r in rows}
        for i in range((end - start).days + 1):
            day = start + timedelta(days=i)
            r = by_day.get(day)
            result.append(
                {
                    "day": str(day),
                    "materialized": bool(r),
                    "stale": day in dirty,
                    "revision": r.revision if r else None,
                    "updated_at": json_value(r.updated_at) if r else None,
                    "metrics": {
                        key: r.metrics.get(key) if r else None
                        for key in (metrics or definitions)
                    },
                    "quality": r.quality if r else {"missing_materialization": True},
                    "evidence": r.evidence if r else {},
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "timezone": TIMEZONE,
            "start": str(start),
            "end": str(end),
            "days": result,
            "limitations": LIMITATIONS,
        }

    async def context(self, user_id, target):
        data = await self.days(user_id, target - timedelta(days=90), target)
        trends = {}
        for key, definition in metric_definitions().items():
            # Sleep/recovery ends at target; completed-day behavior ends yesterday.
            recovery = key.startswith(
                ("sleep.", "sleep_scores.", "readiness.", "spo2.", "polar_recharge.")
            )
            cutoff = target if recovery else target - timedelta(days=1)
            windows = {}
            for n in (7, 30, 90):
                values = [
                    d["metrics"][key]
                    for d in data["days"]
                    if str(cutoff - timedelta(days=n - 1)) <= d["day"] <= str(cutoff)
                    and not d["stale"]
                    and d["metrics"][key] is not None
                ]
                windows[str(n)] = {
                    "expected_days": n,
                    "observed_days": len(values),
                    "mean": round(mean(values), 3) if values else None,
                    "min": min(values) if values else None,
                    "max": max(values) if values else None,
                    "stddev": round(pstdev(values), 3) if len(values) > 1 else None,
                }
            trends[key] = {"unit": definition["unit"], "windows": windows}
        return {
            "schema_version": SCHEMA_VERSION,
            "target_date": str(target),
            "timezone": TIMEZONE,
            "recent_days": data["days"][-8:],
            "trends": trends,
            "stale_days": sum(d["stale"] for d in data["days"]),
            "unmaterialized_days": sum(not d["materialized"] for d in data["days"]),
            "limitations": LIMITATIONS,
        }

    async def association(self, user_id, start, end, x, y, lag=1, min_pairs=20):
        if x not in metric_definitions() or y not in metric_definitions():
            raise HTTPException(422, "unknown metric")
        if not 0 <= lag <= 14 or not 20 <= min_pairs <= 100:
            raise HTTPException(422, "lag must be 0..14; min_pairs must be 20..100")
        if (
            metric_definitions()[x]["unit"] == "minute_of_day"
            or metric_definitions()[y]["unit"] == "minute_of_day"
        ):
            raise HTTPException(
                422,
                "clock times are circular; inspect records or use circular statistics",
            )
        data = await self.days(user_id, start, end, [x, y])
        valid = {
            date.fromisoformat(d["day"]): d
            for d in data["days"]
            if d["materialized"]
            and not d["stale"]
            and not d["quality"].get("partial_day")
        }
        pairs = []
        for day, d in valid.items():
            other = valid.get(day + timedelta(days=lag))
            if not other:
                continue
            a, b = d["metrics"][x], other["metrics"][y]
            if a is not None and b is not None:
                if any(
                    key.startswith("nutrition.")
                    and not row["quality"]
                    .get("nutrition", {})
                    .get("complete_day_confirmed")
                    for key, row in ((x, d), (y, other))
                ):
                    continue
                pairs.append(
                    {
                        "x_day": str(day),
                        "y_day": str(day + timedelta(days=lag)),
                        "x": a,
                        "y": b,
                    }
                )
        correlation = None
        status = "insufficient_pairs"
        if len(pairs) >= min_pairs:
            xs = [p["x"] for p in pairs]
            ys = [p["y"] for p in pairs]
            mx, my = mean(xs), mean(ys)
            denominator = math.sqrt(
                sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)
            )
            status = "constant_series" if not denominator else "exploratory"
            if denominator:
                correlation = round(
                    sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / denominator, 4
                )
        return {
            "x": x,
            "y": y,
            "lag_days": lag,
            "direction": "x on D versus y on D+lag",
            "pairs": len(pairs),
            "expected_pairs": max(0, (end - start).days + 1 - lag),
            "pearson_r": correlation,
            "status": status,
            "points": pairs,
            "limitations": [
                "观察性个人时间序列；自相关、混杂、多重比较可能导致伪相关。",
                "不输出因果、显著性或健康/不健康判定；营养仅使用确认完整日。",
            ],
        }


async def process_dirty_days(db, limit=31):
    """Serialize per day, so a simultaneous source write cannot lose invalidation."""
    rows = (
        (
            await db.execute(
                select(HealthDirtyDay)
                .order_by(HealthDirtyDay.day, HealthDirtyDay.user_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.user_id].append(row.day)
    service = ResearchService(db)
    for user_id, days in grouped.items():
        # Consecutive ranges keep queries bounded even for historical backfills.
        first = last = days[0]
        for day in days[1:] + [None]:
            if day is not None and day == last + timedelta(days=1):
                last = day
                continue
            await service.refresh_range(user_id, first, last)
            if day is not None:
                first = last = day
        await db.execute(
            delete(HealthDirtyDay).where(
                HealthDirtyDay.user_id == user_id, HealthDirtyDay.day.in_(days)
            )
        )
    await db.commit()
    return len(rows)
