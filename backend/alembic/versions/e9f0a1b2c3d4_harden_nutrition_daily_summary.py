"""harden nutrition daily summary

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-21 20:00:00.000000
"""

from alembic import op


revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 空汇总是可重建的派生数据；移除后不会把“未记录”误算成 0 摄入。
    op.execute("DELETE FROM nutrition_daily_summary WHERE meals_count = 0")
    op.create_unique_constraint(
        "uq_nutrition_daily_summary_user_date",
        "nutrition_daily_summary",
        ["user_id", "date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_nutrition_daily_summary_user_date",
        "nutrition_daily_summary",
        type_="unique",
    )
