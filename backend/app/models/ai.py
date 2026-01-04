"""
AI推荐模型
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, Text, TIMESTAMP, ForeignKey, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.database.base import Base


class AIRecommendation(Base):
    """AI建议记录"""

    __tablename__ = "ai_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, comment="建议日期")

    # AI提供商信息
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="AI提供商(deepseek/openai/claude)"
    )
    model: Mapped[Optional[str]] = mapped_column(String(100), comment="使用的模型")

    # 建议内容（新结构：昨日评价 + 今日建议 + 健康科普）
    summary: Mapped[str] = mapped_column(Text, nullable=False, comment="一句话总结")
    yesterday_review: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="昨日评价(JSON)")
    today_recommendation: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="今日建议(JSON)")
    health_education: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="健康科普(JSON)")

    # Token使用情况
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, comment="输入Token数")
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, comment="输出Token数")

    # 用户反馈
    user_rating: Mapped[Optional[int]] = mapped_column(Integer, comment="用户评分(1-5)")
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, comment="用户反馈")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), comment="生成时间")

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="ai_recommendations")

    # 注意：不设置唯一约束，允许同一天多条记录，方便历史回溯

    def __repr__(self):
        return f"<AIRecommendation {self.date} provider={self.provider}>"
