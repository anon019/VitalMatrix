"""add_oura_sleep_time_table

Revision ID: f3a1b2c4d5e6
Revises: aad2793b71ce
Create Date: 2026-02-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f3a1b2c4d5e6'
down_revision = 'aad2793b71ce'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'oura_sleep_time',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('oura_id', sa.String(100), nullable=False, comment='Oura唯一ID'),
        sa.Column('day', sa.Date(), nullable=False, comment='日期'),
        sa.Column('optimal_bedtime_start', sa.Integer(), nullable=True, comment='最佳入睡开始时间(秒偏移，负值=午夜前)'),
        sa.Column('optimal_bedtime_end', sa.Integer(), nullable=True, comment='最佳入睡结束时间(秒偏移，负值=午夜前)'),
        sa.Column('day_tz', sa.Integer(), nullable=True, comment='时区偏移(秒)'),
        sa.Column('recommendation', sa.String(100), nullable=True, comment='推荐类型'),
        sa.Column('status', sa.String(50), nullable=True, comment='状态'),
        sa.Column('raw_json', postgresql.JSONB(), nullable=True, comment='完整原始数据'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('oura_id'),
    )
    op.create_index('idx_oura_sleep_time_user_day', 'oura_sleep_time', ['user_id', 'day'])


def downgrade() -> None:
    op.drop_index('idx_oura_sleep_time_user_day', table_name='oura_sleep_time')
    op.drop_table('oura_sleep_time')
