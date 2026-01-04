"""
Oura Ring集成API
"""
import logging
import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional

from app.database.session import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.oura import (
    OuraAuth, OuraSleep, OuraDailyReadiness,
    OuraDailyActivity, OuraDailyStress, OuraDailySpo2,
    OuraCardiovascularAge, OuraResilience, OuraVO2Max
)
from app.integrations.oura.client import OuraClient
from app.services.oura_sync import OuraSyncService
from app.utils.datetime_helper import now_hk, today_hk

router = APIRouter()
logger = logging.getLogger(__name__)


# 辅助函数：秒转分钟（标准四舍五入，与Oura App一致）
# 注意：Python的round()使用银行家舍入，这里用int(x+0.5)实现标准四舍五入
def sec_to_min(seconds: Optional[int]) -> Optional[int]:
    """将秒转换为分钟（标准四舍五入）"""
    return int(seconds / 60 + 0.5) if seconds is not None else None


class AuthUrlResponse(BaseModel):
    """授权URL响应"""
    auth_url: str
    state: str


class OuraStatusResponse(BaseModel):
    """Oura连接状态响应"""
    connected: bool
    message: str


@router.get("/auth-url", response_model=AuthUrlResponse)
async def get_oura_auth_url(
    current_user: User = Depends(get_current_user)
):
    """
    获取Oura授权URL

    用于小程序跳转到Oura授权页面

    Returns:
        授权URL和state参数
    """
    try:
        from app.config import settings

        # 使用user_id作为state（防CSRF）
        state = str(current_user.id)

        # 构建Oura OAuth授权URL
        # Oura OAuth文档: https://cloud.ouraring.com/docs/authentication
        # Scope说明:
        # - personal: 个人信息（年龄、体重、身高）
        # - daily: 每日活动、准备度、睡眠评分
        # - heartrate: 心率数据
        # - workout: 训练记录
        # - session: 冥想/呼吸练习
        # - tag: 用户标签
        # - sleep: 详细睡眠数据（睡眠阶段、HRV等）
        # - spo2: 血氧饱和度
        # - stress: 压力指标（日间压力、恢复）
        # - ring_configuration: 戒指配置
        scopes = [
            "personal",
            "daily",
            "heartrate",
            "workout",
            "session",
            "tag",
            "sleep",
            "spo2",
            "stress",
            "ring_configuration",
        ]
        scope_str = "+".join(scopes)

        auth_url = (
            f"https://cloud.ouraring.com/oauth/authorize"
            f"?response_type=code"
            f"&client_id={settings.OURA_CLIENT_ID}"
            f"&redirect_uri={settings.OURA_REDIRECT_URI}"
            f"&scope={scope_str}"
            f"&state={state}"
        )

        logger.info(f"生成Oura授权URL: user_id={current_user.id}")

        return AuthUrlResponse(
            auth_url=auth_url,
            state=state
        )

    except Exception as e:
        logger.error(f"生成Oura授权URL失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取授权URL失败"
        )


@router.get("/callback")
async def oura_oauth_callback(
    code: str = Query(..., description="授权码"),
    state: str = Query(..., description="state参数"),
    db: AsyncSession = Depends(get_db)
):
    """
    Oura OAuth回调端点

    处理Oura授权后的回调

    Args:
        code: Oura授权码
        state: state参数（user_id）

    Returns:
        成功页面或错误信息
    """
    try:
        # state参数即为user_id
        user_id = uuid.UUID(state)

        logger.info(f"处理Oura OAuth回调: user_id={user_id}")

        # 使用OuraClient换取token
        oura_client = OuraClient()
        token_data = await oura_client.exchange_code_for_token(code)
        await oura_client.close()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 86400)

        # 保存token到数据库
        result = await db.execute(
            select(OuraAuth).where(OuraAuth.user_id == user_id)
        )
        existing_auth = result.scalar_one_or_none()

        current_time = now_hk()
        token_expires_at = current_time + timedelta(seconds=expires_in)

        if existing_auth:
            # 更新现有记录
            existing_auth.access_token = access_token
            existing_auth.refresh_token = refresh_token
            existing_auth.token_expires_at = token_expires_at
            existing_auth.is_active = True
            existing_auth.updated_at = current_time
            logger.info(f"更新Oura授权信息: user_id={user_id}")
        else:
            # 创建新记录
            oura_auth = OuraAuth(
                user_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                is_active=True,
                created_at=current_time,
                updated_at=current_time,
            )
            db.add(oura_auth)
            logger.info(f"创建Oura授权信息: user_id={user_id}")

        await db.commit()
        logger.info(f"Oura授权成功: user_id={user_id}")

        # 返回成功页面
        success_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>授权成功</title>
            <meta charset="utf-8">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .card {
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    text-align: center;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                }
                .success-icon {
                    font-size: 48px;
                    margin-bottom: 20px;
                }
                h1 { color: #333; margin-bottom: 10px; }
                p { color: #666; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="success-icon">✅</div>
                <h1>Oura 授权成功</h1>
                <p>您可以关闭此页面，返回小程序</p>
            </div>
        </body>
        </html>
        """

        return HTMLResponse(content=success_html)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的state参数"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Oura OAuth回调失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"授权处理失败: {str(e)}"
        )


@router.get("/status", response_model=OuraStatusResponse)
async def check_oura_connection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    检查Oura连接状态

    Returns:
        连接状态信息
    """
    try:
        oura_sync_service = OuraSyncService(db)
        is_connected = await oura_sync_service.check_connection(current_user.id)

        return OuraStatusResponse(
            connected=is_connected,
            message="Oura连接正常" if is_connected else "Oura未连接或连接异常"
        )

    except Exception as e:
        logger.error(f"检查Oura连接失败: {str(e)}")
        return OuraStatusResponse(
            connected=False,
            message=f"检查失败: {str(e)}"
        )


class SyncResponse(BaseModel):
    """同步响应"""
    success: bool
    stats: dict
    message: str


@router.post("/sync", response_model=SyncResponse)
async def sync_oura_data(
    days: int = Query(7, ge=1, le=30, description="同步最近几天的数据"),
    force: bool = Query(False, description="强制重新同步已存在的数据"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    手动触发Oura数据同步

    Args:
        days: 同步最近几天的数据（1-30天）
        force: 强制重新同步已存在的数据

    Returns:
        同步结果
    """
    try:
        logger.info(f"手动触发Oura数据同步: user_id={current_user.id}, days={days}, force={force}")

        oura_sync_service = OuraSyncService(db)
        stats = await oura_sync_service.sync_user_data(
            user_id=current_user.id,
            days=days,
            force=force
        )

        total_new = sum(stats.values())
        logger.info(f"Oura数据同步完成: user_id={current_user.id}, stats={stats}")

        return SyncResponse(
            success=True,
            stats=stats,
            message=f"成功同步{total_new}条新记录"
        )

    except Exception as e:
        logger.error(f"Oura数据同步失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据同步失败: {str(e)}"
        )


# ============ 数据查询接口 ============

class SleepContributorsResponse(BaseModel):
    """睡眠贡献因子响应"""
    total_sleep: Optional[int]
    efficiency: Optional[int]
    restfulness: Optional[int]
    rem_sleep: Optional[int]
    deep_sleep: Optional[int]
    latency: Optional[int]
    timing: Optional[int]


class EmbeddedReadinessResponse(BaseModel):
    """嵌入的准备度数据响应"""
    score: Optional[int]
    sleep_balance: Optional[int]
    previous_night: Optional[int]
    recovery_index: Optional[int]
    activity_balance: Optional[int]
    body_temperature: Optional[int]
    resting_heart_rate: Optional[int]
    hrv_balance: Optional[int]
    previous_day_activity: Optional[int]
    temperature_deviation: Optional[float]
    temperature_trend_deviation: Optional[float]


class SleepRecordResponse(BaseModel):
    """睡眠记录响应"""
    day: str
    score: Optional[int]
    total_sleep_duration: Optional[int]
    rem_sleep_duration: Optional[int]
    deep_sleep_duration: Optional[int]
    light_sleep_duration: Optional[int]
    awake_time: Optional[int]
    efficiency: Optional[int]
    average_hrv: Optional[float]
    bedtime_start: Optional[str]
    bedtime_end: Optional[str]
    average_heart_rate: Optional[int]
    lowest_heart_rate: Optional[int]
    average_breath: Optional[float]
    spo2_percentage: Optional[float]
    temperature_deviation: Optional[float]

    # 新增：睡眠贡献因子
    contributors: Optional[SleepContributorsResponse]

    # 新增：Detail字段
    sleep_type: Optional[str]
    time_in_bed: Optional[int]
    latency: Optional[int]
    restless_periods: Optional[int]

    # 新增：嵌入的准备度数据（睡眠债务关键指标）
    embedded_readiness: Optional[EmbeddedReadinessResponse]


class SleepDataResponse(BaseModel):
    """睡眠数据响应（旧格式，保持兼容）"""
    records: List[SleepRecordResponse]
    total_count: int


# ============ 新增：按天分组的睡眠数据响应 ============

class SleepSegmentResponse(BaseModel):
    """单个睡眠片段响应"""
    sleep_type: str  # long_sleep, sleep (nap)
    score: Optional[int]  # 主睡眠用summary的score，午睡用readiness.score
    sleep_score_delta: Optional[int]  # 睡眠评分增量（午睡贡献，如+9）
    readiness_score_delta: Optional[int]  # 准备度评分增量
    # 时长字段（秒）- 原始精度
    total_sleep_duration: Optional[int]  # 秒
    rem_sleep_duration: Optional[int]
    deep_sleep_duration: Optional[int]
    light_sleep_duration: Optional[int]
    awake_time: Optional[int]
    # 时长字段（分钟，四舍五入）- 与Oura App显示一致
    total_sleep_minutes: Optional[int]
    deep_sleep_minutes: Optional[int]
    rem_sleep_minutes: Optional[int]
    light_sleep_minutes: Optional[int]
    awake_minutes: Optional[int]
    time_in_bed_minutes: Optional[int]
    # 其他字段
    efficiency: Optional[int]
    average_hrv: Optional[float]
    bedtime_start: Optional[str]
    bedtime_end: Optional[str]
    average_heart_rate: Optional[int]
    lowest_heart_rate: Optional[int]
    average_breath: Optional[float]
    time_in_bed: Optional[int]
    latency: Optional[int]
    restless_periods: Optional[int]
    # 嵌入的准备度数据
    embedded_readiness: Optional[EmbeddedReadinessResponse]
    # 睡眠贡献因子（仅主睡眠有）
    contributors: Optional[SleepContributorsResponse]


class DailySleepResponse(BaseModel):
    """单日睡眠数据响应（包含所有片段）"""
    day: str
    summary_score: Optional[int]  # Daily Sleep Summary 的累计评分（主睡眠+午睡增量）
    base_score: Optional[int]  # 主睡眠基础分（summary_score - 午睡增量之和）
    total_duration: int  # 所有片段的总睡眠时长（秒）
    total_duration_minutes: int  # 总时长（分钟，四舍五入）
    segments_count: int  # 睡眠片段数量
    segments: List[SleepSegmentResponse]  # 所有睡眠片段


class GroupedSleepDataResponse(BaseModel):
    """按天分组的睡眠数据响应"""
    records: List[DailySleepResponse]
    total_days: int


@router.get("/sleep/grouped", response_model=GroupedSleepDataResponse)
async def get_grouped_sleep_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取按天分组的睡眠数据（包含所有睡眠片段）

    每天的数据包含：
    - summary_score: Daily Sleep Summary 的评分
    - total_duration: 所有片段的总睡眠时长
    - segments: 所有睡眠片段（主睡眠+午睡+小憩）

    前端可以用不同颜色叠加展示各片段的睡眠时长。

    Returns:
        按天分组的睡眠记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        # 查询所有睡眠记录
        result = await db.execute(
            select(OuraSleep)
            .where(OuraSleep.user_id == current_user.id)
            .where(OuraSleep.day >= start_date)
            .order_by(desc(OuraSleep.day), desc(OuraSleep.total_sleep_duration))
        )
        records = result.scalars().all()

        # 按天分组
        from collections import defaultdict
        day_groups = defaultdict(list)
        for r in records:
            day_groups[r.day].append(r)

        # 构建响应
        daily_records = []
        for day in sorted(day_groups.keys(), reverse=True):
            day_records = day_groups[day]

            # 按睡眠类型排序：long_sleep 优先，然后按时长降序
            day_records.sort(key=lambda x: (
                0 if x.sleep_type == 'long_sleep' else 1,
                -(x.total_sleep_duration or 0)
            ))

            # 计算当天总时长
            total_duration = sum(r.total_sleep_duration or 0 for r in day_records)

            # 获取 summary score（从主睡眠记录获取）
            summary_score = None
            for r in day_records:
                if r.sleep_type == 'long_sleep' and r.sleep_score:
                    summary_score = r.sleep_score
                    break

            # 构建片段列表（使用模块级 sec_to_min 函数）
            segments = []
            for r in day_records:
                segment = SleepSegmentResponse(
                    sleep_type=r.sleep_type or 'unknown',
                    score=r.sleep_score,
                    sleep_score_delta=r.sleep_score_delta,
                    readiness_score_delta=r.readiness_score_delta,
                    # 原始秒数
                    total_sleep_duration=r.total_sleep_duration,
                    rem_sleep_duration=r.rem_sleep_duration,
                    deep_sleep_duration=r.deep_sleep_duration,
                    light_sleep_duration=r.light_sleep_duration,
                    awake_time=r.awake_time,
                    # 四舍五入分钟（与Oura App显示一致）
                    total_sleep_minutes=sec_to_min(r.total_sleep_duration),
                    deep_sleep_minutes=sec_to_min(r.deep_sleep_duration),
                    rem_sleep_minutes=sec_to_min(r.rem_sleep_duration),
                    light_sleep_minutes=sec_to_min(r.light_sleep_duration),
                    awake_minutes=sec_to_min(r.awake_time),
                    time_in_bed_minutes=sec_to_min(r.time_in_bed),
                    # 其他字段
                    efficiency=r.efficiency,
                    average_hrv=float(r.average_hrv) if r.average_hrv else None,
                    bedtime_start=r.bedtime_start.isoformat() if r.bedtime_start else None,
                    bedtime_end=r.bedtime_end.isoformat() if r.bedtime_end else None,
                    average_heart_rate=r.average_heart_rate,
                    lowest_heart_rate=r.lowest_heart_rate,
                    average_breath=float(r.average_breath) if r.average_breath else None,
                    time_in_bed=r.time_in_bed,
                    latency=r.latency,
                    restless_periods=r.restless_periods,
                    embedded_readiness=EmbeddedReadinessResponse(
                        score=r.readiness_score_embedded,
                        sleep_balance=r.readiness_contributor_sleep_balance,
                        previous_night=r.readiness_contributor_previous_night,
                        recovery_index=r.readiness_contributor_recovery_index,
                        activity_balance=r.readiness_contributor_activity_balance,
                        body_temperature=r.readiness_contributor_body_temperature,
                        resting_heart_rate=r.readiness_contributor_resting_heart_rate,
                        hrv_balance=r.readiness_contributor_hrv_balance,
                        previous_day_activity=r.readiness_contributor_previous_day_activity,
                        temperature_deviation=float(r.readiness_temperature_deviation) if r.readiness_temperature_deviation else None,
                        temperature_trend_deviation=float(r.readiness_temperature_trend_deviation) if r.readiness_temperature_trend_deviation else None,
                    ) if r.readiness_score_embedded is not None else None,
                    contributors=SleepContributorsResponse(
                        total_sleep=r.contributor_total_sleep,
                        efficiency=r.contributor_efficiency,
                        restfulness=r.contributor_restfulness,
                        rem_sleep=r.contributor_rem_sleep,
                        deep_sleep=r.contributor_deep_sleep,
                        latency=r.contributor_latency,
                        timing=r.contributor_timing,
                    ) if r.contributor_total_sleep is not None else None,
                )
                segments.append(segment)

            # 计算基础分：summary_score - 所有午睡的 sleep_score_delta 之和
            total_delta = sum(r.sleep_score_delta or 0 for r in day_records)
            base_score = summary_score - total_delta if summary_score else None

            # 修正主睡眠的 score：应该显示基础分，而不是累加后的 summary_score
            for seg in segments:
                if seg.sleep_type == 'long_sleep' and base_score is not None:
                    # 主睡眠的实际评分 = 基础分（用户在App看到的主睡眠评分）
                    seg.score = base_score

            daily_records.append(DailySleepResponse(
                day=day.isoformat(),
                summary_score=summary_score,
                base_score=base_score,
                total_duration=total_duration,
                total_duration_minutes=int(total_duration / 60 + 0.5) if total_duration else 0,
                segments_count=len(segments),
                segments=segments
            ))

        return GroupedSleepDataResponse(
            records=daily_records,
            total_days=len(daily_records)
        )

    except Exception as e:
        logger.error(f"获取分组睡眠数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/sleep", response_model=SleepDataResponse)
async def get_sleep_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取睡眠数据

    Returns:
        指定天数内的睡眠记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(OuraSleep)
            .where(OuraSleep.user_id == current_user.id)
            .where(OuraSleep.day >= start_date)
            .order_by(desc(OuraSleep.day))
        )
        records = result.scalars().all()

        return SleepDataResponse(
            records=[
                SleepRecordResponse(
                    day=r.day.isoformat(),
                    score=r.sleep_score,
                    total_sleep_duration=r.total_sleep_duration,
                    rem_sleep_duration=r.rem_sleep_duration,
                    deep_sleep_duration=r.deep_sleep_duration,
                    light_sleep_duration=r.light_sleep_duration,
                    awake_time=r.awake_time,
                    efficiency=r.efficiency,
                    average_hrv=float(r.average_hrv) if r.average_hrv else None,
                    bedtime_start=r.bedtime_start.isoformat() if r.bedtime_start else None,
                    bedtime_end=r.bedtime_end.isoformat() if r.bedtime_end else None,
                    average_heart_rate=r.average_heart_rate,
                    lowest_heart_rate=r.lowest_heart_rate,
                    average_breath=float(r.average_breath) if r.average_breath else None,
                    spo2_percentage=float(r.spo2_percentage) if r.spo2_percentage else None,
                    temperature_deviation=float(r.temperature_deviation) if r.temperature_deviation else None,
                    # 睡眠贡献因子
                    contributors=SleepContributorsResponse(
                        total_sleep=r.contributor_total_sleep,
                        efficiency=r.contributor_efficiency,
                        restfulness=r.contributor_restfulness,
                        rem_sleep=r.contributor_rem_sleep,
                        deep_sleep=r.contributor_deep_sleep,
                        latency=r.contributor_latency,
                        timing=r.contributor_timing,
                    ) if r.contributor_total_sleep is not None else None,
                    # Detail字段
                    sleep_type=r.sleep_type,
                    time_in_bed=r.time_in_bed,
                    latency=r.latency,
                    restless_periods=r.restless_periods,
                    # 嵌入的准备度数据
                    embedded_readiness=EmbeddedReadinessResponse(
                        score=r.readiness_score_embedded,
                        sleep_balance=r.readiness_contributor_sleep_balance,
                        previous_night=r.readiness_contributor_previous_night,
                        recovery_index=r.readiness_contributor_recovery_index,
                        activity_balance=r.readiness_contributor_activity_balance,
                        body_temperature=r.readiness_contributor_body_temperature,
                        resting_heart_rate=r.readiness_contributor_resting_heart_rate,
                        hrv_balance=r.readiness_contributor_hrv_balance,
                        previous_day_activity=r.readiness_contributor_previous_day_activity,
                        temperature_deviation=float(r.readiness_temperature_deviation) if r.readiness_temperature_deviation else None,
                        temperature_trend_deviation=float(r.readiness_temperature_trend_deviation) if r.readiness_temperature_trend_deviation else None,
                    ) if r.readiness_score_embedded is not None else None,
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取睡眠数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


class ReadinessRecordResponse(BaseModel):
    """准备度记录响应"""
    day: str
    score: Optional[int]  # Daily Readiness 累计评分（含午睡增量）
    base_score: Optional[int]  # 基础分（不含午睡增量）
    nap_boost: Optional[int]  # 午睡带来的准备度增量
    temperature_deviation: Optional[float]
    temperature_trend_deviation: Optional[float]
    activity_balance: Optional[int]
    body_temperature: Optional[int]
    hrv_balance: Optional[int]
    previous_day_activity: Optional[int]
    previous_night: Optional[int]
    recovery_index: Optional[int]
    resting_heart_rate: Optional[int]
    sleep_balance: Optional[int]
    sleep_regularity: Optional[int]  # 新增：睡眠规律性


class ReadinessDataResponse(BaseModel):
    """准备度数据响应"""
    records: List[ReadinessRecordResponse]
    total_count: int


@router.get("/readiness", response_model=ReadinessDataResponse)
async def get_readiness_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取准备度数据

    准备度评分也采用累计机制：
    - Daily Readiness score = 基础分（主睡眠后的准备度）+ 午睡带来的 readiness_score_delta 之和
    - 例如：Daily Readiness 82 = 主睡眠准备度 76 + 午睡增量 6

    Returns:
        指定天数内的准备度记录，包含 base_score 和 nap_boost
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        # 查询准备度数据
        result = await db.execute(
            select(OuraDailyReadiness)
            .where(OuraDailyReadiness.user_id == current_user.id)
            .where(OuraDailyReadiness.day >= start_date)
            .order_by(desc(OuraDailyReadiness.day))
        )
        readiness_records = result.scalars().all()

        # 查询睡眠数据（获取 readiness_score_delta）
        sleep_result = await db.execute(
            select(OuraSleep)
            .where(OuraSleep.user_id == current_user.id)
            .where(OuraSleep.day >= start_date)
        )
        sleep_records = sleep_result.scalars().all()

        # 按天汇总午睡带来的 readiness_score_delta
        from collections import defaultdict
        nap_boost_by_day = defaultdict(int)
        for sleep in sleep_records:
            if sleep.readiness_score_delta:
                nap_boost_by_day[sleep.day] += sleep.readiness_score_delta

        # 构建响应
        response_records = []
        for r in readiness_records:
            nap_boost = nap_boost_by_day.get(r.day, 0) or 0
            base_score = r.score - nap_boost if r.score is not None else None

            response_records.append(ReadinessRecordResponse(
                day=r.day.isoformat(),
                score=r.score,
                base_score=base_score,
                nap_boost=nap_boost if nap_boost > 0 else None,
                temperature_deviation=float(r.temperature_deviation) if r.temperature_deviation else None,
                temperature_trend_deviation=float(r.temperature_trend_deviation) if r.temperature_trend_deviation else None,
                activity_balance=r.activity_balance,
                body_temperature=r.body_temperature,
                hrv_balance=r.hrv_balance,
                previous_day_activity=r.previous_day_activity,
                previous_night=r.previous_night,
                recovery_index=r.recovery_index,
                resting_heart_rate=r.resting_heart_rate,
                sleep_balance=r.sleep_balance,
                sleep_regularity=r.sleep_regularity
            ))

        return ReadinessDataResponse(
            records=response_records,
            total_count=len(response_records)
        )

    except Exception as e:
        logger.error(f"获取准备度数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


class ActivityContributorsResponse(BaseModel):
    """活动贡献因子响应"""
    stay_active: Optional[int]
    move_every_hour: Optional[int]
    meet_daily_targets: Optional[int]
    training_frequency: Optional[int]
    training_volume: Optional[int]
    recovery_time: Optional[int]


class ActivityRecordResponse(BaseModel):
    """活动记录响应"""
    day: str
    score: Optional[int]
    active_calories: Optional[int]
    steps: Optional[int]
    equivalent_walking_distance: Optional[int]
    high_activity_time: Optional[int]
    medium_activity_time: Optional[int]
    low_activity_time: Optional[int]
    sedentary_time: Optional[int]
    resting_time: Optional[int]
    total_calories: Optional[int]
    target_calories: Optional[int]
    target_meters: Optional[int]

    # 新增：活动贡献因子
    contributors: Optional[ActivityContributorsResponse]

    # 新增：其他活动指标
    non_wear_time: Optional[int]
    meters_to_target: Optional[int]
    inactivity_alerts: Optional[int]
    average_met_minutes: Optional[float]


class ActivityDataResponse(BaseModel):
    """活动数据响应"""
    records: List[ActivityRecordResponse]
    total_count: int


@router.get("/activity", response_model=ActivityDataResponse)
async def get_activity_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取活动数据

    Returns:
        指定天数内的活动记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(OuraDailyActivity)
            .where(OuraDailyActivity.user_id == current_user.id)
            .where(OuraDailyActivity.day >= start_date)
            .order_by(desc(OuraDailyActivity.day))
        )
        records = result.scalars().all()

        return ActivityDataResponse(
            records=[
                ActivityRecordResponse(
                    day=r.day.isoformat(),
                    score=r.score,
                    active_calories=r.active_calories,
                    steps=r.steps,
                    equivalent_walking_distance=r.equivalent_walking_distance,
                    high_activity_time=r.high_activity_time,
                    medium_activity_time=r.medium_activity_time,
                    low_activity_time=r.low_activity_time,
                    sedentary_time=r.sedentary_time,
                    resting_time=r.resting_time,
                    total_calories=r.total_calories,
                    target_calories=r.target_calories,
                    target_meters=r.target_meters,
                    # 活动贡献因子
                    contributors=ActivityContributorsResponse(
                        stay_active=r.contributor_stay_active,
                        move_every_hour=r.contributor_move_every_hour,
                        meet_daily_targets=r.contributor_meet_daily_targets,
                        training_frequency=r.contributor_training_frequency,
                        training_volume=r.contributor_training_volume,
                        recovery_time=r.contributor_recovery_time,
                    ) if r.contributor_stay_active is not None else None,
                    # 其他活动指标
                    non_wear_time=r.non_wear_time,
                    meters_to_target=r.meters_to_target,
                    inactivity_alerts=r.inactivity_alerts,
                    average_met_minutes=float(r.average_met_minutes) if r.average_met_minutes else None,
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取活动数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


class StressRecordResponse(BaseModel):
    """压力记录响应（与Oura App命名一致）"""
    day: str
    # 原始秒数
    stressed: Optional[int]  # 压力时间(秒)，Oura App称为"Stressed"
    restored: Optional[int]  # 恢复时间(秒)，Oura App称为"Restored"
    # 分钟数（便于显示）
    stressed_minutes: Optional[int]  # 压力时间(分钟)
    restored_minutes: Optional[int]  # 恢复时间(分钟)
    # 日间总结
    day_summary: Optional[str]  # normal/stressed等


class StressDataResponse(BaseModel):
    """压力数据响应"""
    records: List[StressRecordResponse]
    total_count: int


@router.get("/stress", response_model=StressDataResponse)
async def get_stress_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取压力数据

    Returns:
        指定天数内的压力记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(OuraDailyStress)
            .where(OuraDailyStress.user_id == current_user.id)
            .where(OuraDailyStress.day >= start_date)
            .order_by(desc(OuraDailyStress.day))
        )
        records = result.scalars().all()

        return StressDataResponse(
            records=[
                StressRecordResponse(
                    day=r.day.isoformat(),
                    stressed=r.stress_high,
                    restored=r.recovery_high,
                    stressed_minutes=sec_to_min(r.stress_high),
                    restored_minutes=sec_to_min(r.recovery_high),
                    day_summary=r.day_summary
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取压力数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


class Spo2RecordResponse(BaseModel):
    """血氧记录响应"""
    day: str
    spo2_percentage: Optional[float]
    breathing_disturbance_index: Optional[float]
    breathing_regularity: Optional[int]


class Spo2DataResponse(BaseModel):
    """血氧数据响应"""
    records: List[Spo2RecordResponse]
    total_count: int


@router.get("/spo2", response_model=Spo2DataResponse)
async def get_spo2_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取血氧数据

    Returns:
        指定天数内的血氧记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(OuraDailySpo2)
            .where(OuraDailySpo2.user_id == current_user.id)
            .where(OuraDailySpo2.day >= start_date)
            .order_by(desc(OuraDailySpo2.day))
        )
        records = result.scalars().all()

        return Spo2DataResponse(
            records=[
                Spo2RecordResponse(
                    day=r.day.isoformat(),
                    spo2_percentage=float(r.spo2_percentage) if r.spo2_percentage else None,
                    breathing_disturbance_index=float(r.breathing_disturbance_index) if r.breathing_disturbance_index else None,
                    breathing_regularity=r.breathing_regularity
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取血氧数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


class CardiovascularAgeRecordResponse(BaseModel):
    """心血管年龄记录响应"""
    day: str
    vascular_age: Optional[int]


class CardiovascularAgeDataResponse(BaseModel):
    """心血管年龄数据响应"""
    records: List[CardiovascularAgeRecordResponse]
    total_count: int


@router.get("/cardiovascular-age", response_model=CardiovascularAgeDataResponse)
async def get_cardiovascular_age_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取心血管年龄数据

    Returns:
        指定天数内的心血管年龄记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(OuraCardiovascularAge)
            .where(OuraCardiovascularAge.user_id == current_user.id)
            .where(OuraCardiovascularAge.day >= start_date)
            .order_by(desc(OuraCardiovascularAge.day))
        )
        records = result.scalars().all()

        return CardiovascularAgeDataResponse(
            records=[
                CardiovascularAgeRecordResponse(
                    day=r.day.isoformat(),
                    vascular_age=r.vascular_age
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取心血管年龄数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


class ResilienceRecordResponse(BaseModel):
    """韧性记录响应"""
    day: str
    level: Optional[str]
    sleep_recovery: Optional[int]
    daytime_recovery: Optional[int]
    stress: Optional[int]


class ResilienceDataResponse(BaseModel):
    """韧性数据响应"""
    records: List[ResilienceRecordResponse]
    total_count: int


@router.get("/resilience", response_model=ResilienceDataResponse)
async def get_resilience_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取韧性数据

    Returns:
        指定天数内的韧性记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(OuraResilience)
            .where(OuraResilience.user_id == current_user.id)
            .where(OuraResilience.day >= start_date)
            .order_by(desc(OuraResilience.day))
        )
        records = result.scalars().all()

        return ResilienceDataResponse(
            records=[
                ResilienceRecordResponse(
                    day=r.day.isoformat(),
                    level=r.level,
                    sleep_recovery=r.sleep_recovery,
                    daytime_recovery=r.daytime_recovery,
                    stress=r.stress
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取韧性数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


class VO2MaxRecordResponse(BaseModel):
    """VO2 Max记录响应"""
    day: str
    vo2_max: Optional[float]


class VO2MaxDataResponse(BaseModel):
    """VO2 Max数据响应"""
    records: List[VO2MaxRecordResponse]
    total_count: int


@router.get("/vo2-max", response_model=VO2MaxDataResponse)
async def get_vo2_max_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取VO2 Max数据

    Returns:
        指定天数内的VO2 Max记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(OuraVO2Max)
            .where(OuraVO2Max.user_id == current_user.id)
            .where(OuraVO2Max.day >= start_date)
            .order_by(desc(OuraVO2Max.day))
        )
        records = result.scalars().all()

        return VO2MaxDataResponse(
            records=[
                VO2MaxRecordResponse(
                    day=r.day.isoformat(),
                    vo2_max=float(r.vo2_max) if r.vo2_max else None
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取VO2 Max数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


# ============ 睡眠债务接口 ============

class SleepDebtMethodology(BaseModel):
    """睡眠债务计算方法说明"""
    definition: str
    algorithm: List[str]
    data_requirements: str
    interpretation: dict


class SleepDebtResponse(BaseModel):
    """睡眠债务响应"""
    sleep_debt_minutes: Optional[int]
    baseline_sleep_minutes: Optional[int]
    recent_14d_avg_minutes: Optional[int]
    debt_trend: str
    sleep_balance_score: Optional[int]
    data_quality: str
    methodology: SleepDebtMethodology


@router.get("/sleep-debt", response_model=SleepDebtResponse)
async def get_sleep_debt(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取睡眠债务（基于Oura sleep_balance评分）

    直接使用Oura提供的sleep_balance评分（0-100），并换算为睡眠债务时长。

    换算公式：债务时长(分钟) = (100 - sleep_balance) * 6
    - sleep_balance = 100: 无债务
    - sleep_balance = 0: 最大债务约10小时

    Returns:
        睡眠债务信息
        - sleep_debt_minutes: 估算的睡眠债务（分钟）
        - sleep_balance_score: Oura原始评分（0-100）
        - debt_trend: 趋势（improving/stable/worsening）
    """
    try:
        # 获取最近的sleep_balance数据
        result = await db.execute(
            select(OuraDailyReadiness)
            .where(OuraDailyReadiness.user_id == current_user.id)
            .where(OuraDailyReadiness.sleep_balance.isnot(None))
            .order_by(desc(OuraDailyReadiness.day))
            .limit(14)  # 获取最近14天用于趋势分析
        )
        records = result.scalars().all()

        if not records:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="暂无睡眠平衡数据"
            )

        latest = records[0]
        sleep_balance_score = latest.sleep_balance

        # 使用换算公式：debt_minutes = (100 - sleep_balance) * 6
        # 这样：100分=0债务，0分=600分钟(10小时)债务
        sleep_debt_minutes = int((100 - sleep_balance_score) * 6)

        # 计算趋势：比较最近7天和前7天的平均值
        debt_trend = "stable"
        if len(records) >= 14:
            recent_7d = [r.sleep_balance for r in records[:7] if r.sleep_balance]
            previous_7d = [r.sleep_balance for r in records[7:14] if r.sleep_balance]
            if recent_7d and previous_7d:
                recent_avg = sum(recent_7d) / len(recent_7d)
                previous_avg = sum(previous_7d) / len(previous_7d)
                if recent_avg > previous_avg + 5:
                    debt_trend = "improving"
                elif recent_avg < previous_avg - 5:
                    debt_trend = "worsening"

        # 数据质量评估
        data_quality = "good" if len(records) >= 14 else "limited"

        # 计算方法说明
        methodology = SleepDebtMethodology(
            definition="睡眠债务基于Oura提供的Sleep Balance评分（0-100）换算得出。评分越低表示睡眠债务越大。",
            algorithm=[
                "1. 获取Oura提供的sleep_balance评分（0-100）",
                "2. 换算公式：债务时长(分钟) = (100 - sleep_balance) × 6",
                "3. 趋势分析：比较最近7天与前7天的平均评分变化"
            ],
            data_requirements="至少需要1天的sleep_balance数据，建议14天以上用于趋势分析",
            interpretation={
                "sleep_balance_score": {
                    "description": "Oura睡眠平衡评分（0-100）",
                    "range": "100=完全平衡，0=严重债务",
                    "source": "Oura API直接提供"
                },
                "sleep_debt_minutes": {
                    "description": "估算的睡眠债务（分钟）",
                    "formula": "(100 - sleep_balance) × 6",
                    "note": "这是基于评分的估算值，非Oura直接提供"
                },
                "debt_trend": {
                    "improving": "评分上升，睡眠债务减少",
                    "stable": "评分稳定",
                    "worsening": "评分下降，睡眠债务增加"
                },
                "data_quality": {
                    "good": "≥14天数据，趋势分析可靠",
                    "limited": "<14天数据，仅供参考"
                }
            }
        )

        return SleepDebtResponse(
            sleep_debt_minutes=sleep_debt_minutes,
            baseline_sleep_minutes=None,
            recent_14d_avg_minutes=None,
            debt_trend=debt_trend,
            sleep_balance_score=sleep_balance_score,
            data_quality=data_quality,
            methodology=methodology
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取睡眠债务失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取失败: {str(e)}"
        )


# ============ 睡眠心率详情接口 ============

class DaytimeHRResponse(BaseModel):
    """日间心率响应"""
    # 活动心率范围 (Activity Range)
    activity_hr_min: Optional[int]  # 日间最低心率
    activity_hr_max: Optional[int]  # 日间最高心率
    activity_hr_avg: Optional[int]  # 日间平均心率

    # 日间最低平均心率 (Daytime Lowest Avg)
    # 通常是5分钟窗口的最低平均值
    daytime_lowest_avg: Optional[int]
    daytime_lowest_avg_time: Optional[str]  # 出现的时间

    # 数据统计
    data_points_count: int


class SleepHeartRateDetailResponse(BaseModel):
    """睡眠心率详情响应"""
    day: str
    # 最低心率信息
    lowest_hr: Optional[int]
    lowest_hr_time: Optional[str]  # ISO格式时间
    sleep_phase: Optional[str]  # first_half=上半夜, second_half=下半夜
    sleep_progress_percent: Optional[int]  # 在睡眠周期中的位置百分比 (0-100)

    # 睡眠心率区间
    hr_range: Optional[dict]  # {"min": 50, "avg": 55, "max": 65}

    # 恢复质量评估
    recovery_quality: Optional[str]  # optimal=理想(前50%达最低), suboptimal=次优(后50%达最低)
    recovery_note: Optional[str]  # 解释说明

    # 日间心率数据
    daytime_hr: Optional[DaytimeHRResponse]

    # 数据来源
    data_points_count: int  # 心率数据点数量
    sleep_duration_minutes: Optional[int]  # 睡眠时长(分钟)
    bedtime_start: Optional[str]
    bedtime_end: Optional[str]


@router.get("/heartrate-detail", response_model=SleepHeartRateDetailResponse)
async def get_sleep_heartrate_detail(
    day: str = Query(..., description="查询日期 (YYYY-MM-DD格式)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定日期的睡眠心率详情

    这个接口分析睡眠期间的心率数据，返回：
    - 最低心率出现的时间点
    - 最低心率在睡眠周期中的位置（上半夜/下半夜，百分比）
    - 睡眠心率区间（最低、平均、最高）
    - 恢复质量评估

    **重要指标解读**：
    - 最低心率出现在睡眠前50%（上半夜）= 理想状态，身体快速进入深度恢复
    - 最低心率出现在睡眠后50%（下半夜）= 次优状态，身体整晚都在"加班"

    Args:
        day: 查询日期，格式 YYYY-MM-DD

    Returns:
        睡眠心率详情，包含最低心率时间点和恢复质量评估
    """
    from datetime import datetime as dt
    import pytz

    hk_tz = pytz.timezone("Asia/Hong_Kong")

    try:
        # 解析日期
        try:
            query_date = dt.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="日期格式错误，请使用 YYYY-MM-DD 格式"
            )

        # 查询当天的主睡眠记录
        result = await db.execute(
            select(OuraSleep)
            .where(OuraSleep.user_id == current_user.id)
            .where(OuraSleep.day == query_date)
            .where(OuraSleep.sleep_type == 'long_sleep')  # 只取主睡眠
            .order_by(desc(OuraSleep.total_sleep_duration))
            .limit(1)
        )
        sleep_record = result.scalar_one_or_none()

        if not sleep_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{day} 没有睡眠数据"
            )

        if not sleep_record.bedtime_start or not sleep_record.bedtime_end:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{day} 睡眠数据不完整（缺少入睡/起床时间）"
            )

        # 获取Oura访问令牌
        oura_sync_service = OuraSyncService(db)
        access_token = await oura_sync_service.get_access_token(current_user.id)

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Oura未连接或令牌已失效"
            )

        # 调用Oura API获取睡眠期间的心率数据
        oura_client = OuraClient()
        try:
            heartrate_data = await oura_client.get_heartrate(
                access_token=access_token,
                start_datetime=sleep_record.bedtime_start,
                end_datetime=sleep_record.bedtime_end
            )
        finally:
            await oura_client.close()

        if not heartrate_data:
            # 没有详细心率数据，返回睡眠记录中的基础信息
            return SleepHeartRateDetailResponse(
                day=day,
                lowest_hr=sleep_record.lowest_heart_rate,
                lowest_hr_time=None,
                sleep_phase=None,
                sleep_progress_percent=None,
                hr_range={
                    "min": sleep_record.lowest_heart_rate,
                    "avg": sleep_record.average_heart_rate,
                    "max": None
                } if sleep_record.lowest_heart_rate else None,
                recovery_quality=None,
                recovery_note="无详细心率数据，仅显示睡眠记录中的汇总值",
                daytime_hr=None,
                data_points_count=0,
                sleep_duration_minutes=sec_to_min(sleep_record.total_sleep_duration),
                bedtime_start=sleep_record.bedtime_start.isoformat() if sleep_record.bedtime_start else None,
                bedtime_end=sleep_record.bedtime_end.isoformat() if sleep_record.bedtime_end else None
            )

        # 记录Oura返回的原始数据用于调试
        logger.info(f"Oura心率API返回 {len(heartrate_data)} 条数据")
        if heartrate_data:
            logger.info(f"第一条数据样本: {heartrate_data[0]}")

        # 提取有效的心率数据点
        hr_points = []
        parse_errors = []
        for item in heartrate_data:
            if item.get("bpm") and item.get("timestamp"):
                try:
                    # Oura返回的timestamp格式: 2025-11-29T02:35:00+08:00
                    ts_str = item["timestamp"]
                    # 使用dateutil解析ISO格式时间（更robust）
                    from dateutil import parser as date_parser
                    ts = date_parser.parse(ts_str)
                    hr_points.append({
                        "bpm": item["bpm"],
                        "timestamp": ts
                    })
                except Exception as e:
                    parse_errors.append(f"{ts_str}: {str(e)}")
                    continue

        if parse_errors:
            logger.warning(f"心率时间戳解析错误: {parse_errors[:3]}...")

        if not hr_points:
            return SleepHeartRateDetailResponse(
                day=day,
                lowest_hr=sleep_record.lowest_heart_rate,
                lowest_hr_time=None,
                sleep_phase=None,
                sleep_progress_percent=None,
                hr_range={
                    "min": sleep_record.lowest_heart_rate,
                    "avg": sleep_record.average_heart_rate,
                    "max": None
                } if sleep_record.lowest_heart_rate else None,
                recovery_quality=None,
                recovery_note="心率数据点解析失败",
                daytime_hr=None,
                data_points_count=0,
                sleep_duration_minutes=sec_to_min(sleep_record.total_sleep_duration),
                bedtime_start=sleep_record.bedtime_start.isoformat() if sleep_record.bedtime_start else None,
                bedtime_end=sleep_record.bedtime_end.isoformat() if sleep_record.bedtime_end else None
            )

        # 按时间排序
        hr_points.sort(key=lambda x: x["timestamp"])

        # 找出最低心率及其时间点
        min_hr_point = min(hr_points, key=lambda x: x["bpm"])
        lowest_hr = min_hr_point["bpm"]
        lowest_hr_time = min_hr_point["timestamp"]

        # 计算心率统计
        all_bpm = [p["bpm"] for p in hr_points]
        hr_min = min(all_bpm)
        hr_max = max(all_bpm)
        hr_avg = sum(all_bpm) // len(all_bpm)

        # 计算睡眠进度百分比
        sleep_start = sleep_record.bedtime_start
        sleep_end = sleep_record.bedtime_end

        # 确保时区一致
        if sleep_start.tzinfo is None:
            sleep_start = hk_tz.localize(sleep_start)
        if sleep_end.tzinfo is None:
            sleep_end = hk_tz.localize(sleep_end)
        if lowest_hr_time.tzinfo is None:
            lowest_hr_time = hk_tz.localize(lowest_hr_time)

        total_sleep_seconds = (sleep_end - sleep_start).total_seconds()
        lowest_hr_offset = (lowest_hr_time - sleep_start).total_seconds()

        if total_sleep_seconds > 0:
            sleep_progress_percent = int((lowest_hr_offset / total_sleep_seconds) * 100)
            sleep_progress_percent = max(0, min(100, sleep_progress_percent))  # 限制在0-100
        else:
            sleep_progress_percent = 0

        # 判断上半夜/下半夜
        sleep_phase = "first_half" if sleep_progress_percent <= 50 else "second_half"

        # 恢复质量评估
        if sleep_progress_percent <= 50:
            recovery_quality = "optimal"
            recovery_note = f"最低心率在睡眠前{sleep_progress_percent}%出现（上半夜），身体快速进入深度恢复状态，恢复效率高。"
        else:
            recovery_quality = "suboptimal"
            recovery_note = f"最低心率在睡眠{sleep_progress_percent}%时才出现（下半夜），身体整晚都在'加班'，可能受睡前饮食、酒精或运动影响。"

        # ========== 获取日间心率数据 ==========
        daytime_hr_response = None
        try:
            # 日间时间段：从起床时间到当天晚上23:59
            daytime_start = sleep_record.bedtime_end
            # 日间结束时间：当天23:59:59 (香港时间)
            daytime_end = dt.combine(query_date, dt.max.time())
            daytime_end = hk_tz.localize(daytime_end)

            # 确保daytime_start有时区
            if daytime_start.tzinfo is None:
                daytime_start = hk_tz.localize(daytime_start)

            # 只有当起床时间在当天时才获取日间数据
            if daytime_start.date() <= query_date:
                logger.info(f"获取日间心率数据: {daytime_start} 到 {daytime_end}")

                # 调用Oura API获取日间心率数据
                oura_client2 = OuraClient()
                try:
                    daytime_hr_data = await oura_client2.get_heartrate(
                        access_token=access_token,
                        start_datetime=daytime_start,
                        end_datetime=daytime_end
                    )
                finally:
                    await oura_client2.close()

                if daytime_hr_data:
                    logger.info(f"日间心率API返回 {len(daytime_hr_data)} 条数据")

                    # 解析日间心率数据
                    daytime_points = []
                    for item in daytime_hr_data:
                        if item.get("bpm") and item.get("timestamp"):
                            try:
                                ts_str = item["timestamp"]
                                from dateutil import parser as date_parser
                                ts = date_parser.parse(ts_str)
                                daytime_points.append({
                                    "bpm": item["bpm"],
                                    "timestamp": ts
                                })
                            except Exception:
                                continue

                    if daytime_points:
                        daytime_points.sort(key=lambda x: x["timestamp"])
                        daytime_bpm = [p["bpm"] for p in daytime_points]

                        # 计算日间心率范围
                        activity_hr_min = min(daytime_bpm)
                        activity_hr_max = max(daytime_bpm)
                        activity_hr_avg = sum(daytime_bpm) // len(daytime_bpm)

                        # 计算5分钟窗口最低平均心率
                        window_size = 5  # 5个数据点为一个窗口（约5分钟，假设每分钟1个数据点）
                        min_window_avg = None
                        min_window_time = None

                        if len(daytime_points) >= window_size:
                            for i in range(len(daytime_points) - window_size + 1):
                                window = daytime_points[i:i + window_size]
                                window_avg = sum(p["bpm"] for p in window) // window_size
                                if min_window_avg is None or window_avg < min_window_avg:
                                    min_window_avg = window_avg
                                    min_window_time = window[window_size // 2]["timestamp"]  # 窗口中间时间
                        else:
                            # 数据点不足，使用全部数据的平均值
                            min_window_avg = activity_hr_avg
                            min_window_time = daytime_points[len(daytime_points) // 2]["timestamp"]

                        daytime_hr_response = DaytimeHRResponse(
                            activity_hr_min=activity_hr_min,
                            activity_hr_max=activity_hr_max,
                            activity_hr_avg=activity_hr_avg,
                            daytime_lowest_avg=min_window_avg,
                            daytime_lowest_avg_time=min_window_time.isoformat() if min_window_time else None,
                            data_points_count=len(daytime_points)
                        )

        except Exception as e:
            logger.warning(f"获取日间心率数据失败: {str(e)}")
            # 日间数据获取失败不影响整体响应

        return SleepHeartRateDetailResponse(
            day=day,
            lowest_hr=lowest_hr,
            lowest_hr_time=lowest_hr_time.isoformat(),
            sleep_phase=sleep_phase,
            sleep_progress_percent=sleep_progress_percent,
            hr_range={
                "min": hr_min,
                "avg": hr_avg,
                "max": hr_max
            },
            recovery_quality=recovery_quality,
            recovery_note=recovery_note,
            daytime_hr=daytime_hr_response,
            data_points_count=len(hr_points),
            sleep_duration_minutes=sec_to_min(sleep_record.total_sleep_duration),
            bedtime_start=sleep_record.bedtime_start.isoformat() if sleep_record.bedtime_start else None,
            bedtime_end=sleep_record.bedtime_end.isoformat() if sleep_record.bedtime_end else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取睡眠心率详情失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取失败: {str(e)}"
        )
