"""Local health research records, features and transactional invalidation.

Revision ID: 4e5f60718293
Revises: 3d4e5f607182
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "4e5f60718293"
down_revision = "3d4e5f607182"
branch_labels = None
depends_on = None

# Every source write, including historical corrections and deletes, invalidates
# its old and new calendar day. Dense samples share the same dirty-day row.
SOURCES = {
    "oura_sleep": "day",
    "oura_daily_sleep": "day",
    "oura_daily_readiness": "day",
    "oura_daily_activity": "day",
    "oura_daily_stress": "day",
    "oura_daily_spo2": "day",
    "oura_cardiovascular_age": "day",
    "oura_resilience": "day",
    "oura_vo2_max": "day",
    "oura_sleep_time": "day",
    "oura_workouts": "day",
    "oura_enhanced_tags": "start_day",
    "oura_rest_mode_periods": "start_day",
    "oura_heart_rate_samples": "timestamp",
    "polar_exercises": "start_time",
    "polar_sleep": "sleep_date",
    "polar_nightly_recharge": "date",
    "meal_records": "meal_time",
    "health_source_records": "day",
    "health_journal_entries": "day",
}


def upgrade():
    def user_fk():
        return sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )

    def pk():
        return sa.Column("id", UUID(as_uuid=True), primary_key=True)

    def timestamp(name):
        return sa.Column(
            name,
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        )

    op.create_table(
        "health_source_records",
        pk(),
        user_fk(),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("raw_json", JSONB(), nullable=False),
        timestamp("created_at"),
        timestamp("updated_at"),
        sa.UniqueConstraint(
            "user_id", "source", "kind", "source_id", name="uq_health_source_record"
        ),
    )
    op.create_index(
        "idx_health_source_day", "health_source_records", ["user_id", "day"]
    )
    op.create_table(
        "health_journal_entries",
        pk(),
        user_fk(),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column(
            "supersedes_id",
            UUID(as_uuid=True),
            sa.ForeignKey("health_journal_entries.id"),
        ),
        timestamp("created_at"),
        sa.UniqueConstraint(
            "user_id", "source", "external_id", name="uq_health_journal_external"
        ),
    )
    op.create_index(
        "idx_health_journal_day", "health_journal_entries", ["user_id", "day"]
    )
    op.create_table(
        "health_daily_features",
        pk(),
        user_fk(),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metrics", JSONB(), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("quality", JSONB(), nullable=False),
        timestamp("updated_at"),
        sa.UniqueConstraint("user_id", "day", name="uq_health_daily_feature"),
    )
    op.create_table(
        "health_dirty_days",
        user_fk(),
        sa.Column("day", sa.Date(), nullable=False),
        timestamp("requested_at"),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.execute(
        """
    CREATE FUNCTION health_mark_dirty() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE item jsonb; items jsonb[] := ARRAY[]::jsonb[]; uid uuid; d date; last_day date; field_name text := TG_ARGV[0];
    BEGIN
      IF TG_OP <> 'INSERT' THEN items := array_append(items,to_jsonb(OLD)); END IF;
      IF TG_OP <> 'DELETE' THEN items := array_append(items,to_jsonb(NEW)); END IF;
      FOR item IN SELECT x FROM unnest(items) AS x
      LOOP
        uid := (item->>'user_id')::uuid;
        IF field_name IN ('timestamp','start_time','meal_time') THEN
          d := ((item->>field_name)::timestamptz AT TIME ZONE 'Asia/Hong_Kong')::date;
        ELSE d := (item->>field_name)::date; END IF;
        IF d IS NULL THEN CONTINUE; END IF;
        last_day := COALESCE((item->>'end_day')::date,
          ((item->>'ended_at')::timestamptz AT TIME ZONE 'Asia/Hong_Kong')::date, d);
        -- Ongoing intervals also touch all existing days through today.
        IF TG_TABLE_NAME = 'oura_rest_mode_periods' AND item->>'end_day' IS NULL THEN
          last_day := (now() AT TIME ZONE 'Asia/Hong_Kong')::date;
        END IF;
        INSERT INTO health_dirty_days(user_id, day, requested_at)
          SELECT uid, day::date, now() FROM generate_series(d, LEAST(GREATEST(d,last_day),(now() AT TIME ZONE 'Asia/Hong_Kong')::date), interval '1 day') day
          ON CONFLICT (user_id, day) DO UPDATE SET requested_at = EXCLUDED.requested_at;
      END LOOP;
      RETURN NULL;
    END $$;
    """
    )
    for table, field in SOURCES.items():
        op.execute(
            f"CREATE TRIGGER health_dirty AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE PROCEDURE health_mark_dirty('{field}')"
        )
    # Food changes can be written independently of the parent meal.
    op.execute(
        """
    CREATE FUNCTION health_food_dirty() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE ids uuid[] := ARRAY[]::uuid[];
    BEGIN
      IF TG_OP <> 'INSERT' THEN ids := array_append(ids,OLD.meal_id); END IF;
      IF TG_OP <> 'DELETE' THEN ids := array_append(ids,NEW.meal_id); END IF;
      INSERT INTO health_dirty_days(user_id,day,requested_at)
      SELECT user_id,(meal_time AT TIME ZONE 'Asia/Hong_Kong')::date,now() FROM meal_records
      WHERE id = ANY(ids)
      ON CONFLICT(user_id,day) DO UPDATE SET requested_at=EXCLUDED.requested_at;
      RETURN NULL;
    END $$;
    """
    )
    op.execute(
        "CREATE TRIGGER health_dirty AFTER INSERT OR UPDATE OR DELETE ON food_items FOR EACH ROW EXECUTE PROCEDURE health_food_dirty()"
    )


def downgrade():
    op.execute("DROP TRIGGER health_dirty ON food_items")
    op.execute("DROP FUNCTION health_food_dirty()")
    for table in SOURCES:
        op.execute(f"DROP TRIGGER health_dirty ON {table}")
    op.execute("DROP FUNCTION health_mark_dirty()")
    for table in (
        "health_dirty_days",
        "health_daily_features",
        "health_journal_entries",
        "health_source_records",
    ):
        op.drop_table(table)
