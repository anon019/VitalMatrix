"""normalize Oura activity durations to minutes

Revision ID: 0a1b2c3d4e5f
Revises: f0a1b2c3d4e5
Create Date: 2026-08-21 20:40:00.000000
"""

from alembic import op


revision = "0a1b2c3d4e5f"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


FIELDS = (
    "high_activity_time",
    "medium_activity_time",
    "low_activity_time",
    "sedentary_time",
    "resting_time",
)


def upgrade() -> None:
    for field in FIELDS:
        op.execute(
            f"UPDATE oura_daily_activity SET {field} = ROUND({field} / 60.0) "
            f"WHERE {field} IS NOT NULL"
        )


def downgrade() -> None:
    for field in FIELDS:
        op.execute(
            f"UPDATE oura_daily_activity SET {field} = {field} * 60 "
            f"WHERE {field} IS NOT NULL"
        )
