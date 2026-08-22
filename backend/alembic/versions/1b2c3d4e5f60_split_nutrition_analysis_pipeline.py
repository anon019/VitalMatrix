"""split nutrition image analysis and recommendation pipeline

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-08-21 12:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "1b2c3d4e5f60"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meal_records",
        sa.Column("analysis_status", sa.String(20), server_default="completed", nullable=False),
    )
    op.add_column(
        "meal_records",
        sa.Column("recommendation_status", sa.String(20), server_default="completed", nullable=False),
    )
    op.add_column("meal_records", sa.Column("analysis_error", sa.Text(), nullable=True))
    op.add_column("meal_records", sa.Column("image_sha256", sa.String(64), nullable=True))
    op.add_column(
        "meal_records", sa.Column("analysis_started_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "meal_records", sa.Column("analysis_completed_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "meal_records", sa.Column("recommendation_updated_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.create_index("ix_meal_records_analysis_status", "meal_records", ["analysis_status"])
    op.create_index(
        "ix_meal_records_recommendation_status", "meal_records", ["recommendation_status"]
    )
    op.create_index("ix_meal_records_image_sha256", "meal_records", ["image_sha256"])


def downgrade() -> None:
    op.drop_index("ix_meal_records_image_sha256", table_name="meal_records")
    op.drop_index("ix_meal_records_recommendation_status", table_name="meal_records")
    op.drop_index("ix_meal_records_analysis_status", table_name="meal_records")
    op.drop_column("meal_records", "recommendation_updated_at")
    op.drop_column("meal_records", "analysis_completed_at")
    op.drop_column("meal_records", "analysis_started_at")
    op.drop_column("meal_records", "image_sha256")
    op.drop_column("meal_records", "analysis_error")
    op.drop_column("meal_records", "recommendation_status")
    op.drop_column("meal_records", "analysis_status")
