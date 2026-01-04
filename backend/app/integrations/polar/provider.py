"""
Polar数据源Provider实现
"""
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.base import DataSourceProvider, AuthResult, TrainingSession, SleepSession
from app.integrations.polar.client import PolarClient
from app.models.polar import PolarAuth
from app.database.session import AsyncSessionLocal
from app.config import settings

logger = logging.getLogger(__name__)


class PolarProvider(DataSourceProvider):
    """Polar数据源Provider"""

    def __init__(self):
        self.client = PolarClient()

    @property
    def name(self) -> str:
        return "polar"

    async def authorize(self, user_id: uuid.UUID, auth_code: str) -> AuthResult:
        """
        授权流程

        Args:
            user_id: 用户ID
            auth_code: OAuth授权码

        Returns:
            授权结果
        """
        try:
            # 1. 用授权码换取令牌
            token_data = await self.client.exchange_code_for_token(auth_code)

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)
            polar_user_id = token_data.get("x_user_id")

            if not access_token or not polar_user_id:
                return AuthResult(
                    success=False, error_message="获取访问令牌失败"
                )

            # 2. 注册用户（首次使用）
            await self.client.register_user(access_token, int(polar_user_id))

            # 3. 计算过期时间
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # 4. 保存授权信息到数据库
            async with AsyncSessionLocal() as db:
                # 查询是否已存在
                result = await db.execute(
                    select(PolarAuth).where(PolarAuth.user_id == user_id)
                )
                polar_auth = result.scalar_one_or_none()

                if polar_auth:
                    # 更新
                    polar_auth.polar_user_id = str(polar_user_id)
                    polar_auth.access_token = access_token
                    polar_auth.refresh_token = refresh_token
                    polar_auth.token_expires_at = expires_at
                    polar_auth.is_active = True
                    polar_auth.updated_at = datetime.now(timezone.utc)
                else:
                    # 新建
                    polar_auth = PolarAuth(
                        user_id=user_id,
                        polar_user_id=str(polar_user_id),
                        access_token=access_token,
                        refresh_token=refresh_token,
                        token_expires_at=expires_at,
                        is_active=True,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    db.add(polar_auth)

                await db.commit()

            logger.info(f"Polar授权成功: user_id={user_id}, polar_user_id={polar_user_id}")

            return AuthResult(
                success=True,
                user_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )

        except Exception as e:
            logger.error(f"Polar授权失败: {str(e)}")
            return AuthResult(success=False, error_message=str(e))

    async def refresh_token(self, user_id: uuid.UUID) -> AuthResult:
        """
        刷新访问令牌

        Args:
            user_id: 用户ID

        Returns:
            新的授权结果
        """
        try:
            async with AsyncSessionLocal() as db:
                # 获取授权信息
                result = await db.execute(
                    select(PolarAuth).where(PolarAuth.user_id == user_id)
                )
                polar_auth = result.scalar_one_or_none()

                if not polar_auth or not polar_auth.refresh_token:
                    return AuthResult(success=False, error_message="未找到授权信息")

                # 刷新令牌
                token_data = await self.client.refresh_access_token(polar_auth.refresh_token)

                access_token = token_data.get("access_token")
                refresh_token = token_data.get("refresh_token")
                expires_in = token_data.get("expires_in", 3600)

                if not access_token:
                    return AuthResult(success=False, error_message="刷新令牌失败")

                # 更新数据库
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                polar_auth.access_token = access_token
                if refresh_token:
                    polar_auth.refresh_token = refresh_token
                polar_auth.token_expires_at = expires_at
                polar_auth.updated_at = datetime.now(timezone.utc)

                await db.commit()

                logger.info(f"Polar令牌刷新成功: user_id={user_id}")

                return AuthResult(
                    success=True,
                    user_id=user_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                )

        except Exception as e:
            logger.error(f"Polar令牌刷新失败: {str(e)}")
            return AuthResult(success=False, error_message=str(e))

    async def _get_access_token(self, user_id: uuid.UUID) -> str:
        """
        获取有效的访问令牌（自动刷新）

        Args:
            user_id: 用户ID

        Returns:
            访问令牌

        Raises:
            ValueError: 未找到授权信息
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PolarAuth).where(PolarAuth.user_id == user_id)
            )
            polar_auth = result.scalar_one_or_none()

            if not polar_auth:
                raise ValueError("未找到Polar授权信息")

            # 检查是否过期（提前5分钟刷新）
            if polar_auth.token_expires_at and (
                polar_auth.token_expires_at - timedelta(minutes=5) < datetime.now(timezone.utc)
            ):
                logger.info(f"Polar令牌即将过期，自动刷新: user_id={user_id}")
                refresh_result = await self.refresh_token(user_id)
                if not refresh_result.success:
                    raise ValueError("令牌刷新失败")
                return refresh_result.access_token

            return polar_auth.access_token

    async def fetch_training_data(
        self, user_id: uuid.UUID, start_date: date, end_date: date
    ) -> List[TrainingSession]:
        """
        拉取训练数据

        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            训练会话列表
        """
        try:
            access_token = await self._get_access_token(user_id)

            # 获取训练列表（包含心率区间数据）
            exercises = await self.client.get_exercises(access_token, start_date, end_date)

            # 转换为通用格式
            training_sessions = []
            for exercise in exercises:
                try:
                    # 提取基础信息
                    exercise_id = exercise.get("id")
                    start_time_str = exercise.get("start_time") or exercise.get("start-time")
                    duration_str = exercise.get("duration")  # 格式: PT1H2M3S

                    if not exercise_id or not start_time_str or not duration_str:
                        logger.warning(f"训练记录缺少必要字段: id={exercise_id}")
                        continue

                    # 解析时间（处理不同格式）
                    if "Z" in start_time_str or "+" in start_time_str:
                        start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    else:
                        # 如果没有时区信息，假设是本地时间（香港时区）
                        import pytz
                        hk_tz = pytz.timezone('Asia/Hong_Kong')
                        naive_dt = datetime.fromisoformat(start_time_str)
                        start_time = hk_tz.localize(naive_dt).astimezone(timezone.utc)

                    # 解析时长（ISO 8601格式）
                    duration_sec = self._parse_duration(duration_str)

                    end_time = start_time + timedelta(seconds=duration_sec)

                    # 直接从 Polar API 获取心率区间（第一手数据）
                    zones = self._parse_heart_rate_zones(exercise.get("heart_rate_zones", []))

                    # 解析运动类型（支持字符串和数字ID）
                    sport = exercise.get("sport")
                    if isinstance(sport, str):
                        # 字符串格式，如 "RUNNING"
                        sport_type = sport.lower()
                    elif isinstance(sport, int):
                        # 数字ID格式
                        sport_type = self.client.parse_sport_type(sport)
                    else:
                        sport_type = exercise.get("detailed_sport_info") or "unknown"

                    # 心率数据（支持两种字段名）
                    hr_data = exercise.get("heart_rate") or exercise.get("heart-rate", {})
                    avg_hr = hr_data.get("average")
                    max_hr = hr_data.get("maximum")

                    # 其他数据
                    calories = exercise.get("calories")
                    distance = exercise.get("distance")

                    training_session = TrainingSession(
                        external_id=str(exercise_id),
                        start_time=start_time,
                        end_time=end_time,
                        sport_type=sport_type,
                        duration_sec=duration_sec,
                        avg_hr=avg_hr,
                        max_hr=max_hr,
                        zone1_sec=zones["zone1_sec"],
                        zone2_sec=zones["zone2_sec"],
                        zone3_sec=zones["zone3_sec"],
                        zone4_sec=zones["zone4_sec"],
                        zone5_sec=zones["zone5_sec"],
                        # Zone boundaries
                        zone1_lower=zones["zone1_lower"],
                        zone1_upper=zones["zone1_upper"],
                        zone2_lower=zones["zone2_lower"],
                        zone2_upper=zones["zone2_upper"],
                        zone3_lower=zones["zone3_lower"],
                        zone3_upper=zones["zone3_upper"],
                        zone4_lower=zones["zone4_lower"],
                        zone4_upper=zones["zone4_upper"],
                        zone5_lower=zones["zone5_lower"],
                        zone5_upper=zones["zone5_upper"],
                        calories=calories,
                        distance_meters=distance,
                        raw_data=exercise,
                    )

                    training_sessions.append(training_session)

                except Exception as e:
                    logger.error(f"解析Polar训练数据失败: {str(e)}")
                    continue

            logger.info(f"成功解析{len(training_sessions)}条Polar训练记录")
            return training_sessions

        except Exception as e:
            logger.error(f"拉取Polar训练数据失败: {str(e)}")
            return []

    async def fetch_sleep_data(
        self, user_id: uuid.UUID, start_date: date, end_date: date
    ) -> List[SleepSession]:
        """
        拉取睡眠数据（Polar不支持）

        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            空列表
        """
        logger.warning("Polar不支持睡眠数据，请使用Oura")
        return []

    async def check_connection(self, user_id: uuid.UUID) -> bool:
        """
        检查连接状态

        Args:
            user_id: 用户ID

        Returns:
            是否连接正常
        """
        try:
            access_token = await self._get_access_token(user_id)
            # 尝试获取体能信息（轻量级请求）
            physical_info = await self.client.get_physical_info(access_token)
            return physical_info is not None
        except Exception as e:
            logger.error(f"Polar连接检查失败: {str(e)}")
            return False

    async def _get_user_max_hr(self, access_token: str) -> int:
        """
        获取用户最大心率

        Args:
            access_token: 访问令牌

        Returns:
            最大心率（bpm）
        """
        try:
            # 获取用户信息
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(PolarAuth).where(PolarAuth.access_token == access_token)
                )
                polar_auth = result.scalar_one_or_none()

                if not polar_auth:
                    # 默认最大心率
                    return 187

                # 通过API获取用户信息
                import httpx
                user_url = f"{settings.POLAR_BASE_URL}/users/{polar_auth.polar_user_id}"
                async with httpx.AsyncClient(timeout=30.0, trust_env=False) as http_client:
                    response = await http_client.get(
                        user_url,
                        headers={"Authorization": f"Bearer {access_token}"}
                    )

                    if response.status_code == 200:
                        user_data = response.json()
                        birthdate = user_data.get('birthdate')

                        if birthdate:
                            # 计算最大心率: 220 - 年龄
                            birth_year = int(birthdate.split('-')[0])
                            age = datetime.now().year - birth_year
                            max_hr = 220 - age
                            logger.info(f"根据生日计算最大心率: {birthdate} -> {max_hr} bpm")
                            return max_hr

        except Exception as e:
            logger.warning(f"获取用户最大心率失败: {str(e)}")

        # 默认值
        return 187

    def _parse_duration(self, duration_str: str) -> int:
        """
        解析ISO 8601时长格式

        Args:
            duration_str: 时长字符串，如 "PT1H2M3S" 或 "PT3755.609S"

        Returns:
            总秒数（整数）
        """
        # 简单解析，格式: PT[hours]H[minutes]M[seconds]S
        duration_str = duration_str.replace("PT", "")

        hours = 0
        minutes = 0
        seconds = 0

        if "H" in duration_str:
            parts = duration_str.split("H")
            hours = int(float(parts[0]))
            duration_str = parts[1]

        if "M" in duration_str:
            parts = duration_str.split("M")
            minutes = int(float(parts[0]))
            duration_str = parts[1]

        if "S" in duration_str:
            # 支持小数秒，如 "3755.609S"
            seconds = int(float(duration_str.replace("S", "")))

        return hours * 3600 + minutes * 60 + seconds

    def _parse_heart_rate_zones(self, heart_rate_zones: list) -> dict:
        """
        解析 Polar API 返回的 heart_rate_zones 数据

        Polar 返回 5 个区间 (index 0-4)，我们的数据库使用 zone1-5
        映射关系：Polar index 0 -> zone1, index 1 -> zone2, ...

        Polar API 返回格式：
        {
            "index": 1,
            "lower-limit": 111,    # Zone下限心率
            "upper-limit": 130,    # Zone上限心率
            "in-zone": "PT45M20S"  # 在该区间的时长
        }

        Args:
            heart_rate_zones: Polar API 返回的心率区间数组

        Returns:
            字典 {
                zone1_sec: int, zone2_sec: int, ...,
                zone1_lower: int, zone1_upper: int, ...
            }
        """
        zones = {
            "zone1_sec": 0,
            "zone2_sec": 0,
            "zone3_sec": 0,
            "zone4_sec": 0,
            "zone5_sec": 0,
            # Zone boundaries (heart rate limits)
            "zone1_lower": None,
            "zone1_upper": None,
            "zone2_lower": None,
            "zone2_upper": None,
            "zone3_lower": None,
            "zone3_upper": None,
            "zone4_lower": None,
            "zone4_upper": None,
            "zone5_lower": None,
            "zone5_upper": None,
        }

        for zone_data in heart_rate_zones:
            index = zone_data.get("index")
            # 支持两种字段名格式（带连字符和下划线）
            in_zone = zone_data.get("in-zone") or zone_data.get("in_zone", "PT0S")
            lower_limit = zone_data.get("lower-limit") or zone_data.get("lower_limit")
            upper_limit = zone_data.get("upper-limit") or zone_data.get("upper_limit")

            # 解析时长（ISO 8601格式）
            duration_sec = self._parse_duration(in_zone)

            # Polar index 0-4 映射到 zone1-5
            if index is not None and 0 <= index <= 4:
                zone_num = index + 1
                zones[f"zone{zone_num}_sec"] = duration_sec
                if lower_limit is not None:
                    zones[f"zone{zone_num}_lower"] = int(lower_limit)
                if upper_limit is not None:
                    zones[f"zone{zone_num}_upper"] = int(upper_limit)

        return zones
