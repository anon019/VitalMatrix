"""
Polar集成API
"""
import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.polar import PolarSleep, PolarNightlyRecharge
from app.integrations.polar.client import PolarClient
from app.integrations.polar.provider import PolarProvider
from app.services.polar_sync import PolarSyncService
from app.services.training_metrics import TrainingMetricsService
from app.utils.datetime_helper import today_hk
from sqlalchemy import select, desc
from typing import List, Optional

router = APIRouter()
logger = logging.getLogger(__name__)


class AuthUrlResponse(BaseModel):
    """授权URL响应"""
    auth_url: str
    state: str


class SyncResponse(BaseModel):
    """同步响应"""
    success: bool
    new_count: int
    message: str


@router.get("/auth-url", response_model=AuthUrlResponse)
async def get_polar_auth_url(
    current_user: User = Depends(get_current_user)
):
    """
    获取Polar授权URL

    用于小程序跳转到Polar授权页面

    Returns:
        授权URL和state参数
    """
    try:
        polar_client = PolarClient()

        # 使用user_id作为state（防CSRF）
        state = str(current_user.id)

        auth_url = polar_client.get_authorization_url(state)

        logger.info(f"生成Polar授权URL: user_id={current_user.id}")

        return AuthUrlResponse(
            auth_url=auth_url,
            state=state
        )

    except Exception as e:
        logger.error(f"生成Polar授权URL失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取授权URL失败"
        )


@router.get("/callback")
async def polar_oauth_callback(
    code: str = Query(..., description="授权码"),
    state: str = Query(..., description="state参数"),
    db: AsyncSession = Depends(get_db)
):
    """
    Polar OAuth回调端点

    处理Polar授权后的回调

    Args:
        code: Polar授权码
        state: state参数（user_id）

    Returns:
        重定向或成功消息
    """
    try:
        # state参数即为user_id
        import uuid
        user_id = uuid.UUID(state)

        logger.info(f"处理Polar OAuth回调: user_id={user_id}")

        # 执行授权流程
        polar_provider = PolarProvider()
        auth_result = await polar_provider.authorize(user_id, code)

        if not auth_result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Polar授权失败: {auth_result.error_message}"
            )

        logger.info(f"Polar授权成功: user_id={user_id}")

        # 返回成功消息（实际使用中可重定向到小程序）
        return {
            "success": True,
            "message": "Polar授权成功，可以开始同步数据"
        }

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的state参数"
        )
    except Exception as e:
        logger.error(f"Polar OAuth回调失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"授权处理失败: {str(e)}"
        )


@router.post("/sync", response_model=SyncResponse)
async def sync_polar_data(
    days: int = Query(7, ge=1, le=30, description="同步最近几天的数据"),
    force: bool = Query(False, description="强制更新已存在的记录"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    手动触发Polar数据同步

    Args:
        days: 同步最近几天的数据（1-30天）
        force: 强制更新已存在的记录

    Returns:
        同步结果
    """
    try:
        logger.info(f"手动触发Polar数据同步: user_id={current_user.id}, days={days}, force={force}")

        # 同步训练数据
        polar_sync_service = PolarSyncService(db)
        new_count, _ = await polar_sync_service.sync_user_exercises(
            user_id=current_user.id,
            days=days,
            force=force
        )

        # 重新计算训练指标（最近7天）
        metrics_service = TrainingMetricsService(db)
        for i in range(min(days, 7)):
            target_date = today_hk() - timedelta(days=i + 1)
            try:
                await metrics_service.calculate_daily_summary(current_user.id, target_date)
            except Exception as e:
                logger.warning(f"日指标计算失败: date={target_date} - {str(e)}")

        # 计算周指标
        try:
            await metrics_service.calculate_weekly_summary(current_user.id)
        except Exception as e:
            logger.warning(f"周指标计算失败: {str(e)}")

        logger.info(f"Polar数据同步完成: user_id={current_user.id}, new={new_count}")

        return SyncResponse(
            success=True,
            new_count=new_count,
            message=f"成功同步{new_count}条新训练记录"
        )

    except Exception as e:
        logger.error(f"Polar数据同步失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据同步失败: {str(e)}"
        )


@router.get("/status")
async def check_polar_connection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    检查Polar连接状态

    Returns:
        连接状态信息
    """
    try:
        polar_sync_service = PolarSyncService(db)
        is_connected = await polar_sync_service.check_connection(current_user.id)

        return {
            "connected": is_connected,
            "message": "Polar连接正常" if is_connected else "Polar未连接或连接异常"
        }

    except Exception as e:
        logger.error(f"检查Polar连接失败: {str(e)}")
        return {
            "connected": False,
            "message": f"检查失败: {str(e)}"
        }


# ============ Polar睡眠和夜间恢复数据查询接口 ============

class PolarSleepRecordResponse(BaseModel):
    """Polar睡眠记录响应"""
    sleep_date: str
    sleep_start_time: str
    sleep_end_time: str
    deep_sleep_duration: Optional[int]
    light_sleep_duration: Optional[int]
    rem_sleep_duration: Optional[int]
    total_interruption_duration: Optional[int]
    sleep_score: Optional[int]
    continuity: Optional[float]
    continuity_class: Optional[int]


class PolarSleepDataResponse(BaseModel):
    """Polar睡眠数据响应"""
    records: List[PolarSleepRecordResponse]
    total_count: int


@router.get("/sleep", response_model=PolarSleepDataResponse)
async def get_polar_sleep_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取Polar睡眠数据

    Returns:
        指定天数内的睡眠记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(PolarSleep)
            .where(PolarSleep.user_id == current_user.id)
            .where(PolarSleep.sleep_date >= start_date)
            .order_by(desc(PolarSleep.sleep_date))
        )
        records = result.scalars().all()

        return PolarSleepDataResponse(
            records=[
                PolarSleepRecordResponse(
                    sleep_date=r.sleep_date.isoformat(),
                    sleep_start_time=r.sleep_start_time.isoformat() if r.sleep_start_time else None,
                    sleep_end_time=r.sleep_end_time.isoformat() if r.sleep_end_time else None,
                    deep_sleep_duration=r.deep_sleep_duration,
                    light_sleep_duration=r.light_sleep_duration,
                    rem_sleep_duration=r.rem_sleep_duration,
                    total_interruption_duration=r.total_interruption_duration,
                    sleep_score=r.sleep_score,
                    continuity=float(r.continuity) if r.continuity else None,
                    continuity_class=r.continuity_class
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取Polar睡眠数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


class PolarNightlyRechargeRecordResponse(BaseModel):
    """Polar夜间恢复记录响应"""
    date: str
    ans_charge: Optional[float]
    ans_charge_status: Optional[int]
    hrv_avg: Optional[int]
    breathing_rate_avg: Optional[float]
    heart_rate_avg: Optional[int]
    rmssd: Optional[int]
    sleep_charge: Optional[float]
    sleep_charge_status: Optional[int]
    sleep_score: Optional[int]
    nightly_recharge_status: Optional[int]


class PolarNightlyRechargeDataResponse(BaseModel):
    """Polar夜间恢复数据响应"""
    records: List[PolarNightlyRechargeRecordResponse]
    total_count: int


@router.get("/nightly-recharge", response_model=PolarNightlyRechargeDataResponse)
async def get_polar_nightly_recharge_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取Polar夜间恢复数据

    Returns:
        指定天数内的夜间恢复记录
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days)

        result = await db.execute(
            select(PolarNightlyRecharge)
            .where(PolarNightlyRecharge.user_id == current_user.id)
            .where(PolarNightlyRecharge.date >= start_date)
            .order_by(desc(PolarNightlyRecharge.date))
        )
        records = result.scalars().all()

        return PolarNightlyRechargeDataResponse(
            records=[
                PolarNightlyRechargeRecordResponse(
                    date=r.date.isoformat(),
                    ans_charge=float(r.ans_charge) if r.ans_charge else None,
                    ans_charge_status=r.ans_charge_status,
                    hrv_avg=r.hrv_avg,
                    breathing_rate_avg=float(r.breathing_rate_avg) if r.breathing_rate_avg else None,
                    heart_rate_avg=r.heart_rate_avg,
                    rmssd=r.rmssd,
                    sleep_charge=float(r.sleep_charge) if r.sleep_charge else None,
                    sleep_charge_status=r.sleep_charge_status,
                    sleep_score=r.sleep_score,
                    nightly_recharge_status=r.nightly_recharge_status
                )
                for r in records
            ],
            total_count=len(records)
        )

    except Exception as e:
        logger.error(f"获取Polar夜间恢复数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )
