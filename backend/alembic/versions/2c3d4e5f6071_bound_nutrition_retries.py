"""bound nutrition recommendation retries and tune lookup indexes

Revision ID: 2c3d4e5f6071
Revises: 1b2c3d4e5f60
Create Date: 2026-08-21 13:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "2c3d4e5f6071"
down_revision = "1b2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meal_records",
        sa.Column(
            "recommendation_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.drop_index("ix_meal_records_image_sha256", table_name="meal_records")
    op.create_index(
        "ix_meal_records_dedup_lookup",
        "meal_records",
        ["user_id", "image_sha256", "created_at"],
        postgresql_where=sa.text(
            "image_sha256 IS NOT NULL AND analysis_status = 'completed'"
        ),
    )
    op.create_index(
        "ix_meal_records_recommendation_queue",
        "meal_records",
        [
            "recommendation_status",
            "recommendation_attempts",
            "recommendation_updated_at",
            "created_at",
        ],
        postgresql_where=sa.text("analysis_status = 'completed'"),
    )


def downgrade() -> None:
    op.drop_index("ix_meal_records_recommendation_queue", table_name="meal_records")
    op.drop_index("ix_meal_records_dedup_lookup", table_name="meal_records")
    op.create_index(
        "ix_meal_records_image_sha256",
        "meal_records",
        ["image_sha256"],
    )
    op.drop_column("meal_records", "recommendation_attempts")
