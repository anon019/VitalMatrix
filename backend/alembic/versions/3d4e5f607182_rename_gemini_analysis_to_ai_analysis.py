"""rename gemini analysis to provider-neutral ai analysis

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
Create Date: 2026-09-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "3d4e5f607182"
down_revision: Union[str, None] = "2c3d4e5f6071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "meal_records",
        "gemini_analysis",
        new_column_name="ai_analysis",
        existing_type=postgresql.JSONB(),
        existing_nullable=True,
        comment="AI完整输出（包含分析、建议等）",
    )


def downgrade() -> None:
    op.alter_column(
        "meal_records",
        "ai_analysis",
        new_column_name="gemini_analysis",
        existing_type=postgresql.JSONB(),
        existing_nullable=True,
        comment="AI完整输出（包含分析、建议等）",
    )
