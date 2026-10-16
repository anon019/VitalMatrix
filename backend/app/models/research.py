"""Local research records and deterministic daily features (no AI dependency)."""

from datetime import date, datetime
import uuid

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    TIMESTAMP,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class HealthSourceRecord(Base):
    """Additional provider collections, preserving the original payload and units."""

    __tablename__ = "health_source_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "kind", "source_id", name="uq_health_source_record"
        ),
        Index("idx_health_source_day", "user_id", "day"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(60))
    source_id: Mapped[str] = mapped_column(String(200))
    day: Mapped[date] = mapped_column(Date)
    data: Mapped[dict] = mapped_column(JSONB)
    raw_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class HealthJournalEntry(Base):
    """Immutable, idempotent observations/events from the owner or another channel."""

    __tablename__ = "health_journal_entries"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "external_id", name="uq_health_journal_external"
        ),
        Index("idx_health_journal_day", "user_id", "day"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    day: Mapped[date] = mapped_column(Date)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    data: Mapped[dict] = mapped_column(JSONB)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("health_journal_entries.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class HealthDailyFeature(Base):
    __tablename__ = "health_daily_features"
    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_health_daily_feature"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    day: Mapped[date] = mapped_column(Date)
    schema_version: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str] = mapped_column(String(64))
    metrics: Mapped[dict] = mapped_column(JSONB)
    evidence: Mapped[dict] = mapped_column(JSONB)
    quality: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class HealthDirtyDay(Base):
    """Transactionally invalidated by source-table triggers; consumed under row locks."""

    __tablename__ = "health_dirty_days"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
