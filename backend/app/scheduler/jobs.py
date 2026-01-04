"""
定时任务调度
"""
import logging
from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models.user import User
from app.models.polar import PolarAuth
from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
from app.models.oura import (
    OuraAuth, OuraSleep, OuraDailyReadiness,
    OuraDailyActivity, OuraDailyStress
)
from app.models.health_report import HealthReport
from app.services.polar_sync import PolarSyncService
from app.services.oura_sync import OuraSyncService
from app.services.training_metrics import TrainingMetricsService
from app.services.ai_service import AIService
from app.utils.datetime_helper import today_hk, now_hk
from app.config import settings

logger = logging.getLogger(__name__)

# 创建调度器
scheduler = AsyncIOScheduler(timezone="Asia/Hong_Kong")


async def get_active_users():
    """获取所有有Polar授权的活跃用户"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User)
            .join(PolarAuth)
            .where(PolarAuth.is_active == True)
        )
        users = result.scalars().all()
        return users


async def get_oura_active_users():
    """获取所有有Oura授权的活跃用户"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User)
            .join(OuraAuth)
            .where(OuraAuth.is_active == True)
        )
        users = result.scalars().all()
        return users


@scheduler.scheduled_job(CronTrigger(hour=11, minute=0))
async def sync_polar_data_job():
    """
    定时任务: 每天11:00同步Polar数据

    同步最近2天的训练数据
    """
    logger.info("🔄 开始执行定时任务: Polar数据同步")

    try:
        users = await get_active_users()
        logger.info(f"活跃用户数: {len(users)}")

        success_count = 0
        fail_count = 0

        for user in users:
            try:
                async with AsyncSessionLocal() as db:
                    polar_sync_service = PolarSyncService(db)
                    new_count, new_duration_min = await polar_sync_service.sync_user_exercises(
                        user_id=user.id,
                        days=2
                    )
                    logger.info(f"用户{user.id}同步成功: 新增{new_count}条记录, 时长{new_duration_min}分钟")
                    success_count += 1
            except Exception as e:
                logger.error(f"用户{user.id}同步失败: {str(e)}")
                fail_count += 1

        logger.info(
            f"✅ Polar数据同步完成: 成功={success_count}, 失败={fail_count}"
        )

    except Exception as e:
        logger.error(f"❌ Polar数据同步任务失败: {str(e)}")


@scheduler.scheduled_job(CronTrigger(hour=11, minute=30))
async def sync_oura_data_job():
    """
    定时任务: 每天11:30同步Oura数据（用户起床后，获取完整睡眠数据）

    同步最近3天的睡眠、准备度、活动等数据，并强制触发AI更新（兜底机制）
    """
    logger.info("🔄 开始执行定时任务: Oura数据同步")

    try:
        users = await get_oura_active_users()
        logger.info(f"Oura活跃用户数: {len(users)}")

        success_count = 0
        fail_count = 0

        for user in users:
            try:
                async with AsyncSessionLocal() as db:
                    oura_sync_service = OuraSyncService(db)
                    # 强制更新以获取最新完整数据（用户起床后数据才完整）
                    # days=3: 避免Oura API边界bug导致的数据遗漏
                    stats = await oura_sync_service.sync_user_data(
                        user_id=user.id,
                        days=3,
                        force=True
                    )
                    total = sum(stats.values())
                    logger.info(f"用户{user.id}Oura同步成功: 更新{total}条记录")

                    # 注意：不再在此处触发AI更新
                    # AI更新统一由 11:35 的 generate_ai_recommendations_job 定时任务处理
                    # 这样确保所有数据（Polar 11:00 + 指标计算 11:15 + Oura 11:30）都完成后再生成AI建议

                    success_count += 1
            except Exception as e:
                logger.error(f"用户{user.id}Oura同步失败: {str(e)}")
                fail_count += 1

        logger.info(
            f"✅ Oura数据同步完成: 成功={success_count}, 失败={fail_count}"
        )

    except Exception as e:
        logger.error(f"❌ Oura数据同步任务失败: {str(e)}")


@scheduler.scheduled_job(CronTrigger(hour=11, minute=15))
async def calculate_metrics_job():
    """
    定时任务: 每天11:15计算训练指标

    计算昨天的训练指标和本周汇总
    """
    logger.info("📊 开始执行定时任务: 训练指标计算")

    try:
        users = await get_active_users()
        yesterday = today_hk() - timedelta(days=1)

        success_count = 0
        fail_count = 0

        for user in users:
            try:
                async with AsyncSessionLocal() as db:
                    metrics_service = TrainingMetricsService(db)

                    # 计算昨日总结
                    daily_summary = await metrics_service.calculate_daily_summary(
                        user.id, yesterday
                    )

                    # 计算周总结
                    weekly_summary = await metrics_service.calculate_weekly_summary(
                        user.id
                    )

                    if daily_summary or weekly_summary:
                        logger.info(f"用户{user.id}指标计算成功")
                        success_count += 1
                    else:
                        logger.info(f"用户{user.id}无训练数据")

            except Exception as e:
                logger.error(f"用户{user.id}指标计算失败: {str(e)}")
                fail_count += 1

        logger.info(
            f"✅ 训练指标计算完成: 成功={success_count}, 失败={fail_count}"
        )

    except Exception as e:
        logger.error(f"❌ 训练指标计算任务失败: {str(e)}")


@scheduler.scheduled_job(CronTrigger(hour=11, minute=45))
async def generate_ai_recommendations_job():
    """
    定时任务: 每天11:45生成AI建议（唯一的AI更新入口）

    时序设计：
    - 11:00 Polar数据同步
    - 11:15 训练指标计算
    - 11:30 Oura数据同步
    - 11:45 AI建议生成 ← 当前任务

    确保所有数据都同步完成后，统一生成当天的AI建议。
    使用 force_update=True 强制更新，确保使用最新的完整数据。
    """
    logger.info("🤖 开始执行定时任务: AI建议生成")

    try:
        users = await get_active_users()
        today = today_hk()

        success_count = 0
        fail_count = 0

        for user in users:
            try:
                async with AsyncSessionLocal() as db:
                    ai_service = AIService(db)

                    # 强制更新今日建议，确保使用最新的完整数据
                    recommendation = await ai_service.generate_daily_recommendation(
                        user_id=user.id,
                        target_date=today,
                        force_update=True  # 强制更新，使用最新同步的数据
                    )

                    logger.info(
                        f"用户{user.id}AI建议生成成功: "
                        f"{recommendation.summary[:30]}..."
                    )
                    success_count += 1

            except Exception as e:
                logger.error(f"用户{user.id}AI建议生成失败: {str(e)}")
                fail_count += 1

        logger.info(
            f"✅ AI建议生成完成: 成功={success_count}, 失败={fail_count}"
        )

    except Exception as e:
        logger.error(f"❌ AI建议生成任务失败: {str(e)}")


@scheduler.scheduled_job(IntervalTrigger(minutes=15))
async def poll_polar_notifications_job():
    """
    定时任务: 每15分钟轮询Polar新数据

    检查是否有新的训练数据可同步
    """
    logger.info("🔔 开始执行定时任务: Polar新数据轮询")

    try:
        # 简单实现：检查最近1天的数据
        users = await get_active_users()

        for user in users:
            try:
                async with AsyncSessionLocal() as db:
                    polar_sync_service = PolarSyncService(db)

                    # 同步最近1天的数据（增量）
                    new_count, new_duration_min = await polar_sync_service.sync_user_exercises(
                        user_id=user.id,
                        days=1
                    )

                    if new_count > 0:
                        logger.info(f"用户{user.id}发现新训练数据: {new_count}条, 时长: {new_duration_min}分钟")

                        # 重新计算指标
                        yesterday = today_hk() - timedelta(days=1)
                        metrics_service = TrainingMetricsService(db)
                        await metrics_service.calculate_daily_summary(user.id, yesterday)
                        await metrics_service.calculate_weekly_summary(user.id)

                        # 注意：不再在轮询时触发AI更新
                        # AI更新统一由 11:35 的 generate_ai_recommendations_job 定时任务处理
                        logger.info(f"训练数据已同步，AI将在定时任务中统一更新: user={user.id}")

            except Exception as e:
                logger.error(f"用户{user.id}轮询失败: {str(e)}")

        logger.info("✅ Polar新数据轮询完成")

    except Exception as e:
        logger.error(f"❌ Polar新数据轮询任务失败: {str(e)}")


@scheduler.scheduled_job(IntervalTrigger(minutes=15))
async def poll_oura_data_job():
    """
    定时任务: 每15分钟轮询Oura新数据

    同步最新的睡眠、准备度、活动等数据
    注意：对今天的数据强制更新，确保活动数据实时更新
    """
    logger.info("🔔 开始执行定时任务: Oura新数据轮询")

    try:
        users = await get_oura_active_users()

        for user in users:
            try:
                async with AsyncSessionLocal() as db:
                    oura_sync_service = OuraSyncService(db)

                    # 轮询任务：只获取今天和昨天的数据
                    # force_recent_days=2: 强制更新这2天（处理API数据延迟）
                    # days=2: 减少API调用量，第3天由11:30定时任务兜底
                    stats = await oura_sync_service.sync_user_data(
                        user_id=user.id,
                        days=2,
                        force_recent_days=2
                    )

                    total = sum(stats.values())
                    if total > 0:
                        logger.info(f"用户{user.id}Oura发现新数据: {total}条 {stats}")

                        # AI触发逻辑已经在oura_sync_service内部处理（只在睡眠数据更新时触发）
                        # 不在这里重复触发，避免活动数据频繁更新导致的无意义AI调用

            except Exception as e:
                logger.error(f"用户{user.id}Oura轮询失败: {str(e)}")

        logger.info("✅ Oura新数据轮询完成")

    except Exception as e:
        logger.error(f"❌ Oura新数据轮询任务失败: {str(e)}")


# 暂时禁用：MCP查询功能未使用
# @scheduler.scheduled_job(CronTrigger(hour=11, minute=40))
async def generate_health_report_job():
    """
    定时任务: 每天11:40生成健康报告（已禁用）

    生成预生成的健康报告供MCP快速查询
    """
    logger.info("📋 开始执行定时任务: 健康报告生成")

    try:
        users = await get_active_users()
        today = today_hk()
        yesterday = today - timedelta(days=1)

        success_count = 0
        fail_count = 0

        for user in users:
            try:
                async with AsyncSessionLocal() as db:
                    # 获取昨日训练数据
                    training_result = await db.execute(
                        select(DailyTrainingSummary)
                        .where(DailyTrainingSummary.user_id == user.id)
                        .where(DailyTrainingSummary.date == yesterday)
                    )
                    daily_training = training_result.scalar_one_or_none()

                    # 获取周训练汇总
                    from sqlalchemy import desc
                    weekly_result = await db.execute(
                        select(WeeklyTrainingSummary)
                        .where(WeeklyTrainingSummary.user_id == user.id)
                        .order_by(desc(WeeklyTrainingSummary.week_start_date))
                        .limit(1)
                    )
                    weekly_training = weekly_result.scalar_one_or_none()

                    # 获取Oura数据
                    sleep_result = await db.execute(
                        select(OuraSleep)
                        .where(OuraSleep.user_id == user.id)
                        .where(OuraSleep.day == yesterday)
                    )
                    sleep = sleep_result.scalar_one_or_none()

                    readiness_result = await db.execute(
                        select(OuraDailyReadiness)
                        .where(OuraDailyReadiness.user_id == user.id)
                        .where(OuraDailyReadiness.day == yesterday)
                    )
                    readiness = readiness_result.scalar_one_or_none()

                    activity_result = await db.execute(
                        select(OuraDailyActivity)
                        .where(OuraDailyActivity.user_id == user.id)
                        .where(OuraDailyActivity.day == yesterday)
                    )
                    activity = activity_result.scalar_one_or_none()

                    stress_result = await db.execute(
                        select(OuraDailyStress)
                        .where(OuraDailyStress.user_id == user.id)
                        .where(OuraDailyStress.day == yesterday)
                    )
                    stress = stress_result.scalar_one_or_none()

                    # 构建训练数据
                    training_data = {
                        "yesterday": {
                            "has_data": daily_training is not None,
                            "duration_min": daily_training.total_duration_min if daily_training else 0,
                            "zone2_min": daily_training.zone2_min if daily_training else 0,
                            "zone4_5_min": daily_training.hi_min if daily_training else 0,
                            "sessions": daily_training.sessions_count if daily_training else 0,
                        },
                        "weekly": {
                            "has_data": weekly_training is not None,
                            "total_min": weekly_training.total_duration_min if weekly_training else 0,
                            "zone2_min": weekly_training.zone2_min if weekly_training else 0,
                            "zone4_5_min": weekly_training.hi_min if weekly_training else 0,
                        }
                    }

                    # 构建Oura数据
                    sleep_data = {
                        "has_data": sleep is not None,
                        "score": sleep.score if sleep else None,
                        "total_min": sleep.total_sleep_duration if sleep else None,
                    }

                    readiness_data = {
                        "has_data": readiness is not None,
                        "score": readiness.score if readiness else None,
                    }

                    activity_data = {
                        "has_data": activity is not None,
                        "score": activity.score if activity else None,
                        "steps": activity.steps if activity else None,
                    }

                    stress_data = {
                        "has_data": stress is not None,
                        "day_summary": stress.day_summary if stress else None,
                    }

                    # 计算风险指标
                    risk_flags = []

                    if daily_training and daily_training.zone2_min < settings.TARGET_ZONE2_MIN_RANGE:
                        risk_flags.append({
                            "flag": "zone2_low",
                            "level": "medium",
                            "message": f"昨日Zone2时长{daily_training.zone2_min:.0f}分钟，低于目标"
                        })

                    if daily_training and daily_training.hi_min > settings.TARGET_HI_MAX_RANGE:
                        risk_flags.append({
                            "flag": "hi_excessive",
                            "level": "high",
                            "message": f"昨日高强度{daily_training.hi_min:.0f}分钟，超过上限"
                        })

                    if readiness and readiness.score and readiness.score < 70:
                        risk_flags.append({
                            "flag": "low_readiness",
                            "level": "high" if readiness.score < 60 else "medium",
                            "message": f"准备度评分{readiness.score}，身体恢复不足"
                        })

                    # 判断整体状态
                    high_risks = [f for f in risk_flags if f["level"] == "high"]
                    if high_risks:
                        overall_status = "warning"
                    elif risk_flags:
                        overall_status = "caution"
                    else:
                        overall_status = "good"

                    # 生成摘要
                    if overall_status == "good":
                        summary = "身体状态良好，可以进行正常训练"
                    elif overall_status == "caution":
                        summary = "有轻微风险指标，建议适当调整训练强度"
                    else:
                        summary = "存在较高风险，建议休息或进行轻度恢复性训练"

                    # 检查是否已存在报告
                    existing_result = await db.execute(
                        select(HealthReport)
                        .where(HealthReport.user_id == user.id)
                        .where(HealthReport.report_date == today)
                        .where(HealthReport.report_type == "daily")
                    )
                    existing_report = existing_result.scalar_one_or_none()

                    current_time = now_hk()

                    if existing_report:
                        # 更新现有报告
                        existing_report.training_data = training_data
                        existing_report.sleep_data = sleep_data
                        existing_report.readiness_data = readiness_data
                        existing_report.activity_data = activity_data
                        existing_report.stress_data = stress_data
                        existing_report.risk_flags = risk_flags
                        existing_report.overall_status = overall_status
                        existing_report.summary = summary
                        existing_report.updated_at = current_time
                    else:
                        # 创建新报告
                        report = HealthReport(
                            user_id=user.id,
                            report_date=today,
                            report_type="daily",
                            training_data=training_data,
                            sleep_data=sleep_data,
                            readiness_data=readiness_data,
                            activity_data=activity_data,
                            stress_data=stress_data,
                            risk_flags=risk_flags,
                            overall_status=overall_status,
                            summary=summary,
                            created_at=current_time,
                            updated_at=current_time
                        )
                        db.add(report)

                    await db.commit()
                    logger.info(f"用户{user.id}健康报告生成成功")
                    success_count += 1

            except Exception as e:
                logger.error(f"用户{user.id}健康报告生成失败: {str(e)}")
                fail_count += 1

        logger.info(
            f"✅ 健康报告生成完成: 成功={success_count}, 失败={fail_count}"
        )

    except Exception as e:
        logger.error(f"❌ 健康报告生成任务失败: {str(e)}")


def start_scheduler():
    """启动调度器"""
    try:
        scheduler.start()
        logger.info("⏰ 任务调度器启动成功")
        logger.info("📅 已注册定时任务:")
        logger.info("  【每日数据同步链】(按顺序执行，确保数据完整)")
        logger.info("  - 11:00 Polar数据同步")
        logger.info("  - 11:15 训练指标计算")
        logger.info("  - 11:30 Oura数据同步")
        logger.info("  - 11:45 AI建议生成 ← 唯一AI更新入口")
        logger.info("  【其他定时任务】")
        logger.info("  - 02:00 清理30天前营养照片")
        logger.info("  - 02:05 更新营养日汇总")
        logger.info("  【轮询任务】(仅同步数据，不触发AI)")
        logger.info("  - 每15分钟 Polar新数据轮询")
        logger.info("  - 每15分钟 Oura新数据轮询")
    except Exception as e:
        logger.error(f"❌ 任务调度器启动失败: {str(e)}")


@scheduler.scheduled_job(CronTrigger(hour=2, minute=0))
async def cleanup_old_nutrition_photos_job():
    """
    定时任务: 每天02:00清理30天前的营养照片

    释放存储空间
    """
    logger.info("🧹 开始执行定时任务: 清理旧营养照片")

    try:
        from app.services.file_storage import get_file_storage

        file_storage = get_file_storage()
        deleted_count = file_storage.cleanup_old_photos(days=30)

        logger.info(f"✅ 营养照片清理完成: 删除 {deleted_count} 个目录")

    except Exception as e:
        logger.error(f"❌ 营养照片清理任务失败: {str(e)}")


@scheduler.scheduled_job(CronTrigger(hour=2, minute=5))
async def update_nutrition_daily_summaries_job():
    """
    定时任务: 每天02:05更新前一天的营养汇总（兜底任务）

    虽然每次保存餐次时会自动更新，但这个任务确保遗漏的汇总被补充
    """
    logger.info("📊 开始执行定时任务: 更新营养日汇总")

    try:
        from app.models.user import User
        from app.services.nutrition_service import get_nutrition_service
        from datetime import timedelta

        nutrition_service = get_nutrition_service()
        yesterday = date.today() - timedelta(days=1)

        async with AsyncSessionLocal() as db:
            # 获取所有用户
            result = await db.execute(select(User))
            users = result.scalars().all()

            success_count = 0
            for user in users:
                try:
                    await nutrition_service.update_daily_summary(
                        db=db,
                        user_id=user.id,
                        target_date=yesterday
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"用户{user.id}营养汇总更新失败: {str(e)}")

            logger.info(f"✅ 营养日汇总更新完成: 成功={success_count}")

    except Exception as e:
        logger.error(f"❌ 营养日汇总更新任务失败: {str(e)}")


def shutdown_scheduler():
    """关闭调度器"""
    try:
        scheduler.shutdown()
        logger.info("⏰ 任务调度器已关闭")
    except Exception as e:
        logger.error(f"❌ 任务调度器关闭失败: {str(e)}")
