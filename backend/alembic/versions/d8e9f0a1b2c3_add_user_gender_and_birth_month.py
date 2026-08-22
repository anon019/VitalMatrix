"""add user gender and birth month

Revision ID: d8e9f0a1b2c3
Revises: c7a8d9e0f1b2
Create Date: 2026-08-21 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d8e9f0a1b2c3"
down_revision = "c7a8d9e0f1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("gender", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("birth_month", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_users_birth_month_range",
        "users",
        "birth_month IS NULL OR (birth_month >= 1 AND birth_month <= 12)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_birth_month_range", "users", type_="check")
    op.drop_column("users", "birth_month")
    op.drop_column("users", "gender")
