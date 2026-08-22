"""expand Oura v2 data coverage

Revision ID: c7a8d9e0f1b2
Revises: f3a1b2c4d5e6
Create Date: 2026-07-27 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c7a8d9e0f1b2"
down_revision = "f3a1b2c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("oura_auth", sa.Column("oura_user_id", sa.String(100), nullable=True))
    op.add_column("oura_auth", sa.Column("personal_info", postgresql.JSONB(), nullable=True))
    op.add_column("oura_auth", sa.Column("capabilities", postgresql.JSONB(), nullable=True))

    op.add_column("oura_sleep", sa.Column("heart_rate_samples", postgresql.JSONB(), nullable=True))
    op.add_column("oura_sleep", sa.Column("hrv_samples", postgresql.JSONB(), nullable=True))
    op.add_column("oura_sleep", sa.Column("sleep_phase_30_sec", sa.Text(), nullable=True))
    op.add_column("oura_sleep", sa.Column("sleep_phase_5_min", sa.Text(), nullable=True))
    op.add_column("oura_sleep", sa.Column("app_sleep_phase_5_min", sa.Text(), nullable=True))
    op.add_column("oura_sleep", sa.Column("movement_30_sec", sa.Text(), nullable=True))
    op.add_column("oura_sleep", sa.Column("low_battery_alert", sa.Boolean(), nullable=True))
    op.add_column("oura_sleep", sa.Column("period", sa.Integer(), nullable=True))
    op.add_column("oura_sleep", sa.Column("sleep_algorithm_version", sa.String(50), nullable=True))
    op.add_column("oura_sleep", sa.Column("sleep_analysis_reason", sa.String(100), nullable=True))

    op.add_column(
        "oura_daily_sleep",
        sa.Column("source_timestamp", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "oura_daily_readiness",
        sa.Column("source_timestamp", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "oura_daily_activity",
        sa.Column("source_timestamp", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column("oura_daily_activity", sa.Column("class_5_min", sa.Text(), nullable=True))
    op.add_column("oura_daily_activity", sa.Column("met_samples", postgresql.JSONB(), nullable=True))
    op.add_column(
        "oura_daily_activity",
        sa.Column("high_activity_met_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "oura_daily_activity",
        sa.Column("medium_activity_met_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "oura_daily_activity",
        sa.Column("low_activity_met_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "oura_daily_activity",
        sa.Column("sedentary_met_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "oura_cardiovascular_age",
        sa.Column("pulse_wave_velocity", sa.DECIMAL(6, 3), nullable=True),
    )
    op.add_column(
        "oura_vo2_max",
        sa.Column("source_timestamp", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "oura_workouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("oura_id", sa.String(100), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("activity", sa.String(100), nullable=True),
        sa.Column("calories", sa.DECIMAL(10, 2), nullable=True),
        sa.Column("distance", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("start_datetime", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_datetime", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("intensity", sa.String(50), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "oura_id", name="uq_oura_workouts_user_oura"),
    )
    op.create_index("idx_oura_workouts_user_day", "oura_workouts", ["user_id", "day"])
    op.create_index(
        "idx_oura_workouts_user_start", "oura_workouts", ["user_id", "start_datetime"]
    )

    op.create_table(
        "oura_enhanced_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("oura_id", sa.String(100), nullable=False),
        sa.Column("tag_type_code", sa.String(100), nullable=True),
        sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("start_day", sa.Date(), nullable=True),
        sa.Column("end_day", sa.Date(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("custom_name", sa.String(200), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "oura_id", name="uq_oura_enhanced_tags_user_oura"),
    )
    op.create_index(
        "idx_oura_enhanced_tags_user_day", "oura_enhanced_tags", ["user_id", "start_day"]
    )
    op.create_index(
        "idx_oura_enhanced_tags_user_time", "oura_enhanced_tags", ["user_id", "start_time"]
    )

    op.create_table(
        "oura_rest_mode_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("oura_id", sa.String(100), nullable=False),
        sa.Column("start_day", sa.Date(), nullable=True),
        sa.Column("end_day", sa.Date(), nullable=True),
        sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("episodes", postgresql.JSONB(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "oura_id", name="uq_oura_rest_mode_user_oura"),
    )
    op.create_index(
        "idx_oura_rest_mode_user_day", "oura_rest_mode_periods", ["user_id", "start_day"]
    )

    op.create_table(
        "oura_heart_rate_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("producer_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("bpm", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "timestamp", name="uq_oura_hr_user_timestamp"),
    )
    op.create_index(
        "idx_oura_hr_user_timestamp",
        "oura_heart_rate_samples",
        ["user_id", "timestamp"],
    )

    # Existing rows already retain the official payload, so normalize them
    # locally without another API download.
    op.execute(
        """
        UPDATE oura_sleep
        SET heart_rate_samples = raw_json #> '{detail,heart_rate}',
            hrv_samples = raw_json #> '{detail,hrv}',
            sleep_phase_30_sec = raw_json #>> '{detail,sleep_phase_30_sec}',
            sleep_phase_5_min = raw_json #>> '{detail,sleep_phase_5_min}',
            app_sleep_phase_5_min = raw_json #>> '{detail,app_sleep_phase_5_min}',
            movement_30_sec = raw_json #>> '{detail,movement_30_sec}',
            low_battery_alert = NULLIF(raw_json #>> '{detail,low_battery_alert}', '')::boolean,
            period = NULLIF(raw_json #>> '{detail,period}', '')::integer,
            sleep_algorithm_version = raw_json #>> '{detail,sleep_algorithm_version}',
            sleep_analysis_reason = raw_json #>> '{detail,sleep_analysis_reason}'
        WHERE raw_json IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE oura_daily_sleep
        SET source_timestamp = NULLIF(raw_json ->> 'timestamp', '')::timestamptz
        WHERE raw_json ? 'timestamp'
        """
    )
    op.execute(
        """
        UPDATE oura_daily_readiness
        SET source_timestamp = NULLIF(raw_json ->> 'timestamp', '')::timestamptz
        WHERE raw_json ? 'timestamp'
        """
    )
    op.execute(
        """
        UPDATE oura_daily_activity
        SET source_timestamp = NULLIF(raw_json ->> 'timestamp', '')::timestamptz,
            class_5_min = raw_json ->> 'class_5_min',
            met_samples = raw_json -> 'met',
            high_activity_met_minutes =
                NULLIF(raw_json ->> 'high_activity_met_minutes', '')::integer,
            medium_activity_met_minutes =
                NULLIF(raw_json ->> 'medium_activity_met_minutes', '')::integer,
            low_activity_met_minutes =
                NULLIF(raw_json ->> 'low_activity_met_minutes', '')::integer,
            sedentary_met_minutes =
                NULLIF(raw_json ->> 'sedentary_met_minutes', '')::integer
        WHERE raw_json IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE oura_cardiovascular_age
        SET pulse_wave_velocity = NULLIF(raw_json ->> 'pulse_wave_velocity', '')::numeric
        WHERE raw_json ? 'pulse_wave_velocity'
        """
    )
    op.execute(
        """
        UPDATE oura_vo2_max
        SET source_timestamp = NULLIF(raw_json ->> 'timestamp', '')::timestamptz
        WHERE raw_json ? 'timestamp'
        """
    )


def downgrade() -> None:
    op.drop_index("idx_oura_hr_user_timestamp", table_name="oura_heart_rate_samples")
    op.drop_table("oura_heart_rate_samples")
    op.drop_index("idx_oura_rest_mode_user_day", table_name="oura_rest_mode_periods")
    op.drop_table("oura_rest_mode_periods")
    op.drop_index("idx_oura_enhanced_tags_user_time", table_name="oura_enhanced_tags")
    op.drop_index("idx_oura_enhanced_tags_user_day", table_name="oura_enhanced_tags")
    op.drop_table("oura_enhanced_tags")
    op.drop_index("idx_oura_workouts_user_start", table_name="oura_workouts")
    op.drop_index("idx_oura_workouts_user_day", table_name="oura_workouts")
    op.drop_table("oura_workouts")

    op.drop_column("oura_vo2_max", "source_timestamp")
    op.drop_column("oura_cardiovascular_age", "pulse_wave_velocity")
    op.drop_column("oura_daily_activity", "sedentary_met_minutes")
    op.drop_column("oura_daily_activity", "low_activity_met_minutes")
    op.drop_column("oura_daily_activity", "medium_activity_met_minutes")
    op.drop_column("oura_daily_activity", "high_activity_met_minutes")
    op.drop_column("oura_daily_activity", "met_samples")
    op.drop_column("oura_daily_activity", "class_5_min")
    op.drop_column("oura_daily_activity", "source_timestamp")
    op.drop_column("oura_daily_readiness", "source_timestamp")
    op.drop_column("oura_daily_sleep", "source_timestamp")
    op.drop_column("oura_sleep", "sleep_analysis_reason")
    op.drop_column("oura_sleep", "sleep_algorithm_version")
    op.drop_column("oura_sleep", "period")
    op.drop_column("oura_sleep", "low_battery_alert")
    op.drop_column("oura_sleep", "movement_30_sec")
    op.drop_column("oura_sleep", "app_sleep_phase_5_min")
    op.drop_column("oura_sleep", "sleep_phase_5_min")
    op.drop_column("oura_sleep", "sleep_phase_30_sec")
    op.drop_column("oura_sleep", "hrv_samples")
    op.drop_column("oura_sleep", "heart_rate_samples")
    op.drop_column("oura_auth", "capabilities")
    op.drop_column("oura_auth", "personal_info")
    op.drop_column("oura_auth", "oura_user_id")
