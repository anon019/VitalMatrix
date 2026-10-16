"""Persist additional device dimensions without overwriting native domain tables."""

from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import or_

from app.models.research import HealthSourceRecord
from app.utils.datetime_helper import HK_TZ, date_hk, now_hk, today_hk

logger = logging.getLogger(__name__)


def parse_time(value):
    if not value or not isinstance(value, str):
        return None
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return timestamp if timestamp.tzinfo else HK_TZ.localize(timestamp)


def duration_minutes(value):
    """ISO 8601 duration; months/years are not fixed durations."""
    import re

    if not value:
        return None
    match = re.fullmatch(
        r"P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?",
        value,
    )
    if not match:
        return None
    days, hours, minutes, seconds = [float(v or 0) for v in match.groups()]
    return round(days * 1440 + hours * 60 + minutes + seconds / 60, 3)


async def save_provider_records(db, user_id, source, kind, items):
    """Idempotent upsert; no-op polls do not invalidate research snapshots."""
    values = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = dict(item)
        raw.pop("email", None)
        samples = raw.get("samples")
        day_value = (
            raw.get("day")
            or raw.get("date")
            or (samples.get("date") if isinstance(samples, dict) else None)
        )
        start = parse_time(
            raw.get("start_datetime")
            or raw.get("start_time")
            or raw.get("recording_time")
            or raw.get("timestamp")
        )
        if day_value:
            day = date.fromisoformat(str(day_value)[:10])
        elif start:
            day = date_hk(start)
        else:
            day = today_hk()
        identity = raw.get("id") or raw.get("start_datetime") or raw.get("start_time")
        if not identity:
            identity = (
                str(day)
                if kind
                in ("activity", "cardio_load", "continuous_heart_rate", "sync_status")
                else hashlib.sha256(
                    json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
            )
        source_id = str(identity)
        data = dict(raw)
        date_basis = (
            "provider_day"
            if day_value
            else ("provider_timestamp" if start else "collection_day_only")
        )
        if kind == "session":
            end = parse_time(raw.get("end_datetime"))
            data = {
                "type": raw.get("type"),
                "mood": raw.get("mood"),
                "start_datetime": start.isoformat() if start else None,
                "end_datetime": end.isoformat() if end else None,
                "duration_minutes": (
                    round((end - start).total_seconds() / 60, 3)
                    if start and end and end >= start
                    else None
                ),
            }
        elif source == "polar" and kind == "activity":
            data = {
                k: raw.get(k)
                for k in (
                    "steps",
                    "active_calories",
                    "calories",
                    "daily_activity",
                    "distance_from_steps",
                    "inactivity_alert_count",
                )
            }
            data.update(
                active_minutes=duration_minutes(raw.get("active_duration")),
                inactive_minutes=duration_minutes(raw.get("inactive_duration")),
            )
        elif kind == "physical_info":
            modified = raw.get("modified") or raw.get("created")
            if modified:
                day = date_hk(parse_time(modified))
                date_basis = "provider_modified_at"
            source_id = hashlib.sha256(
                json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        data["_date_basis"] = date_basis
        values.append(
            {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "source": source,
                "kind": kind,
                "source_id": source_id,
                "day": day,
                "data": data,
                "raw_json": raw,
                "updated_at": now_hk(),
            }
        )
    if not values:
        return 0
    values = list({v["source_id"]: v for v in values}.values())
    stmt = insert(HealthSourceRecord).values(values)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["user_id", "source", "kind", "source_id"],
            set_={
                "day": stmt.excluded.day,
                "data": stmt.excluded.data,
                "raw_json": stmt.excluded.raw_json,
                "updated_at": stmt.excluded.updated_at,
            },
            where=or_(
                HealthSourceRecord.raw_json.is_distinct_from(stmt.excluded.raw_json),
                HealthSourceRecord.data.is_distinct_from(stmt.excluded.data),
            ),
        )
    )
    return len(values)


async def sync_polar_research(service, user_id, days=7):
    """Independent optional channels; missing permissions never erase saved data."""
    token = await service.get_access_token(user_id)
    if not token:
        return {}
    await service.db.commit()
    client = service.polar_client
    start = today_hk() - timedelta(days=days - 1)
    end = today_hk()
    status = {}
    calls = {
        "activity": lambda: client.get_daily_activity(token, start, end),
        "physical_info": lambda: client.get_physical_info(token),
        "cardio_load": lambda: client.get_research_collection(
            "cardio_load", token, start, end
        ),
        "continuous_heart_rate": lambda: client.get_research_collection(
            "continuous_heart_rate", token, start, end
        ),
    }
    for kind in (
        "alertness",
        "circadian_bedtime",
        "body_temperature",
        "skin_temperature",
        "skin_contacts",
        "ecg",
        "spo2_test",
    ):
        calls[kind] = lambda kind=kind: client.get_research_collection(
            kind, token, start, end
        )
    for kind, call in calls.items():
        try:
            result = await call()
            if result is None:
                raise ValueError("provider request did not complete")
            items = [result] if isinstance(result, dict) else result
            count = await save_provider_records(
                service.db, user_id, "polar", kind, items
            )
            status[kind] = {
                "status": "observed" if count else "no_records",
                "records": count,
            }
            await service.db.commit()
        except Exception as exc:
            await service.db.rollback()
            status[kind] = {
                "status": "unavailable_or_failed",
                "error_type": type(exc).__name__,
            }
            logger.warning(
                "Polar research channel %s unavailable (%s)", kind, type(exc).__name__
            )
    for kind, call in (
        ("sleep", service.sync_sleep_data),
        ("nightly_recharge", service.sync_nightly_recharge_data),
    ):
        try:
            count = await call(user_id, days=min(days, 28), force=True)
            status[kind] = {"status": "attempted", "new_records": count}
            await service.db.commit()
        except Exception as exc:
            await service.db.rollback()
            status[kind] = {
                "status": "unavailable_or_failed",
                "error_type": type(exc).__name__,
            }
    await save_provider_records(
        service.db,
        user_id,
        "polar",
        "sync_status",
        [{"day": str(end), "channels": status}],
    )
    await service.db.commit()
    return status
