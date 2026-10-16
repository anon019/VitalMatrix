"""Initialize/rebuild local research features; no model calls, exports or backups.

Run from backend: venv/bin/python scripts/build_research_dataset.py [--sync-devices]
"""
# ruff: noqa: E402

import argparse
import asyncio
from datetime import date, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

# Token encryption reads os.environ; Settings' env_file alone does not populate it.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.api.dependencies import resolve_default_user
from app.database.session import AsyncSessionLocal, engine
from app.models.research import HealthDirtyDay
from app.services.research_schema import DATASETS
from app.services.research_service import process_dirty_days
from app.utils.datetime_helper import now_hk, today_hk


async def main(args):
    try:
        async with AsyncSessionLocal() as db:
            user = await resolve_default_user(db)
            uid = user.id
            earliest = []
            for spec in DATASETS.values():
                day = await db.scalar(
                    select(func.min(spec.day_expression)).where(
                        spec.model.user_id == uid
                    )
                )
                if day:
                    earliest.append(day)
            start = args.start or min(earliest, default=today_hk())
            end = args.end or today_hk()
            if start > end or end > today_hk():
                raise ValueError("invalid date range")
            await db.commit()
        if args.sync_devices:
            from app.services.oura_sync import OuraSyncService
            from app.services.polar_sync import PolarSyncService
            from app.services.provider_research import (
                save_provider_records,
                sync_polar_research,
            )

            async with AsyncSessionLocal() as db:
                async with OuraSyncService(db) as service:
                    stats = await service.sync_user_data(
                        uid, days=28, force_recent_days=3
                    )
                    print(json.dumps({"oura_processed": stats}), flush=True)
                    token = await service.get_access_token(uid)
                    await db.commit()
                    if token:
                        try:
                            sessions = await service.oura_client.get_sessions(
                                token, start, end + timedelta(days=1)
                            )
                            await save_provider_records(
                                db, uid, "oura", "session", sessions
                            )
                            await db.commit()
                            print(
                                json.dumps({"oura_historical_sessions": len(sessions)}),
                                flush=True,
                            )
                        except Exception as exc:
                            await db.rollback()
                            print(
                                json.dumps(
                                    {"oura_sessions_unavailable": type(exc).__name__}
                                ),
                                flush=True,
                            )
            async with AsyncSessionLocal() as db:
                async with PolarSyncService(db) as service:
                    channels = await sync_polar_research(service, uid, days=28)
                    print(json.dumps({"polar_channels": channels}), flush=True)
                    exercises = await service.sync_user_exercises(
                        uid, days=28, force=True
                    )
                    print(
                        json.dumps({"polar_exercises_processed": exercises}), flush=True
                    )
        async with AsyncSessionLocal() as db:
            total = (end - start).days + 1
            # Source triggers plus the explicit full historical queue cover old records.
            for offset in range(0, total, 100):
                dates = [
                    start + timedelta(days=i)
                    for i in range(offset, min(total, offset + 100))
                ]
                stmt = insert(HealthDirtyDay).values(
                    [
                        {"user_id": uid, "day": d, "requested_at": now_hk()}
                        for d in dates
                    ]
                )
                await db.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["user_id", "day"],
                        set_={"requested_at": stmt.excluded.requested_at},
                    )
                )
            await db.commit()
            completed = 0
            while count := await process_dirty_days(db, limit=31):
                completed += count
                print(
                    json.dumps(
                        {
                            "materialized_days": completed,
                            "requested_start": str(start),
                            "requested_end": str(end),
                        }
                    ),
                    flush=True,
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument(
        "--sync-devices",
        action="store_true",
        help="Collect currently available device channels; never calls AI",
    )
    asyncio.run(main(parser.parse_args()))
