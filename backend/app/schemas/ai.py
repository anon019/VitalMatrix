"""
AI相关Schemas
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Literal, List
from pydantic import BaseModel, ConfigDict, Field, model_validator


class YesterdayReview(BaseModel):
    """昨日数据回顾"""
    title: str = Field(..., min_length=1, max_length=60, description="标题")
    emoji: str = Field(..., min_length=1, max_length=8, description="图标emoji")
    items: List[str] = Field(..., min_length=1, max_length=8, description="要点列表")


class TodayRecommendation(BaseModel):
    """今日训练建议"""
    title: str = Field(..., min_length=1, max_length=60, description="标题")
    emoji: str = Field(..., min_length=1, max_length=8, description="图标emoji")
    items: List[str] = Field(..., min_length=1, max_length=8, description="要点列表")


class HealthEducationItem(BaseModel):
    """健康教育知识点"""
    label: str = Field(..., description="标签")
    content: str = Field(..., description="内容")


class HealthEducationSection(BaseModel):
    """健康教育章节"""
    subtitle: str = Field(..., description="章节小标题")
    highlight: bool = Field(default=True, description="是否高亮显示")
    items: List[HealthEducationItem] = Field(..., min_length=1, description="知识点列表")


class HealthEducation(BaseModel):
    """健康科普"""
    title: str = Field(..., description="标题")
    emoji: str = Field(..., description="图标emoji")
    sections: List[HealthEducationSection] = Field(..., min_length=1, description="科普章节列表")


class RecommendationResponse(BaseModel):
    """AI建议响应（新结构）"""

    id: str
    date: date
    provider: str
    model: Optional[str]
    summary: str
    yesterday_review: YesterdayReview = Field(..., description="昨日评价")
    today_recommendation: TodayRecommendation = Field(..., description="今日建议")
    health_education: HealthEducation = Field(..., description="健康科普")
    created_at: str
    requested_date: Optional[date] = Field(None, description="客户端请求的日期")
    source_date: Optional[date] = Field(None, description="实际建议所属日期")
    is_stale: bool = Field(False, description="是否为今日接口回退的历史建议")
    generation_metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class ChatMessage(BaseModel):
    """聊天消息"""

    role: Literal["user", "assistant"] = Field(..., description="角色")
    content: str = Field(..., min_length=1, max_length=4000, description="内容")


class ChatRequest(BaseModel):
    """聊天请求"""

    messages: List[ChatMessage] = Field(..., min_length=1, max_length=20, description="消息历史")
    context: Optional[dict] = Field(None, description="上下文数据")

    @model_validator(mode="after")
    def validate_request_size(self):
        if sum(len(message.content) for message in self.messages) > 12_000:
            raise ValueError("消息总长度不能超过 12000 个字符")
        if self.context and len(str(self.context)) > 4_000:
            raise ValueError("上下文数据过大")
        return self


class ChatResponse(BaseModel):
    """聊天响应"""

    message: str = Field(..., description="AI回复")
    usage: Optional[dict] = Field(None, description="Token使用情况")
