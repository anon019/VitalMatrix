"""
健康报告模型 - 用于MCP预生成报告
"""
import uuid
from datetime import date, datetime
from sqlalchemy import ForeignKey, Date, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database.base import Base


class HealthReport(Base):
    """
    每日健康报告

    预生成的综合健康报告，供MCP快速查询
    """
    __tablename__ = "health_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # 报告日期
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # 报告类型
    report_type: Mapped[str] = mapped_column(
        nullable=False, default="daily"
    )  # daily, weekly

    # 综合数据（JSON格式存储）
    training_data: Mapped[dict] = mapped_column(JSON, nullable=True)
    sleep_data: Mapped[dict] = mapped_column(JSON, nullable=True)
    readiness_data: Mapped[dict] = mapped_column(JSON, nullable=True)
    activity_data: Mapped[dict] = mapped_column(JSON, nullable=True)
    stress_data: Mapped[dict] = mapped_column(JSON, nullable=True)

    # 风险评估
    risk_flags: Mapped[list] = mapped_column(JSON, nullable=True)
    overall_status: Mapped[str] = mapped_column(nullable=True)  # good, caution, warning

    # 周趋势数据（仅周报告）
    weekly_trends: Mapped[dict] = mapped_column(JSON, nullable=True)

    # 摘要
    summary: Mapped[str] = mapped_column(Text, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # 关联
    user: Mapped["User"] = relationship("User", back_populates="health_reports")

    def __repr__(self):
        return f"<HealthReport {self.report_date} ({self.report_type})>"
