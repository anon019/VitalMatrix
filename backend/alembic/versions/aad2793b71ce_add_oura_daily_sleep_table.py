"""add_oura_daily_sleep_table

Revision ID: aad2793b71ce
Revises: 2a9c97d9a3da
Create Date: 2025-12-08 17:22:54.228968

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'aad2793b71ce'
down_revision = '2a9c97d9a3da'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建每日睡眠综合评分表
    op.create_table('oura_daily_sleep',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('oura_id', sa.String(100), nullable=False, comment='Oura唯一ID'),
        sa.Column('day', sa.Date(), nullable=False, comment='日期'),
        sa.Column('score', sa.Integer(), nullable=True, comment='每日综合睡眠评分(0-100)'),
        sa.Column('contributor_deep_sleep', sa.Integer(), nullable=True, comment='深睡贡献分数'),
        sa.Column('contributor_efficiency', sa.Integer(), nullable=True, comment='睡眠效率贡献分数'),
        sa.Column('contributor_latency', sa.Integer(), nullable=True, comment='入睡延迟贡献分数'),
        sa.Column('contributor_rem_sleep', sa.Integer(), nullable=True, comment='REM睡眠贡献分数'),
        sa.Column('contributor_restfulness', sa.Integer(), nullable=True, comment='睡眠安稳度贡献分数'),
        sa.Column('contributor_timing', sa.Integer(), nullable=True, comment='睡眠时间贡献分数'),
        sa.Column('contributor_total_sleep', sa.Integer(), nullable=True, comment='总睡眠时长贡献分数'),
        sa.Column('raw_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='完整原始数据'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('oura_id')
    )
    op.create_index('idx_oura_daily_sleep_user_day', 'oura_daily_sleep', ['user_id', 'day'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_oura_daily_sleep_user_day', table_name='oura_daily_sleep')
    op.drop_table('oura_daily_sleep')
