"""
Polar AccessLink API客户端
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import httpx
from app.config import settings
from app.integrations.polar.constants import (
    POLAR_AUTH_URL,
    POLAR_TOKEN_URL,
    EXERCISES_ENDPOINT,
    PHYSICAL_INFO_ENDPOINT,
    DAILY_ACTIVITY_ENDPOINT,
    POLAR_SCOPES,
    SPORT_TYPE_MAP,
)

logger = logging.getLogger(__name__)


class PolarAPIError(Exception):
    """Polar API错误"""

    pass


class PolarClient:
    """Polar AccessLink API客户端"""

    def __init__(self):
        self.client_id = settings.POLAR_CLIENT_ID
        self.client_secret = settings.POLAR_CLIENT_SECRET
        self.redirect_uri = settings.POLAR_REDIRECT_URI
        # trust_env=False: 忽略代理环境变量，直连Polar API
        self.http_client = httpx.AsyncClient(timeout=30.0, trust_env=False)

    async def close(self):
        """关闭HTTP客户端"""
        await self.http_client.aclose()

    def get_authorization_url(self, state: str) -> str:
        """
        获取授权URL

        Args:
            state: 状态参数（用于防CSRF）

        Returns:
            授权URL
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(POLAR_SCOPES),
            "state": state,
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{POLAR_AUTH_URL}?{query_string}"

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        用授权码换取访问令牌

        Args:
            code: 授权码

        Returns:
            令牌信息 {access_token, refresh_token, expires_in, x_user_id}

        Raises:
            PolarAPIError: API调用失败
        """
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        try:
            response = await self.http_client.post(
                POLAR_TOKEN_URL,
                data=data,
                auth=(self.client_id, self.client_secret),
            )
            response.raise_for_status()
            token_data = response.json()

            logger.info(f"成功获取Polar访问令牌，用户ID: {token_data.get('x_user_id')}")
            return token_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Polar令牌交换失败: {e.response.status_code} {e.response.text}")
            raise PolarAPIError(f"令牌交换失败: {e.response.text}")
        except Exception as e:
            logger.error(f"Polar令牌交换异常: {str(e)}")
            raise PolarAPIError(f"令牌交换异常: {str(e)}")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        刷新访问令牌

        Args:
            refresh_token: 刷新令牌

        Returns:
            新的令牌信息

        Raises:
            PolarAPIError: API调用失败
        """
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        try:
            response = await self.http_client.post(
                POLAR_TOKEN_URL,
                data=data,
                auth=(self.client_id, self.client_secret),
            )
            response.raise_for_status()
            token_data = response.json()

            logger.info("成功刷新Polar访问令牌")
            return token_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Polar令牌刷新失败: {e.response.status_code} {e.response.text}")
            raise PolarAPIError(f"令牌刷新失败: {e.response.text}")
        except Exception as e:
            logger.error(f"Polar令牌刷新异常: {str(e)}")
            raise PolarAPIError(f"令牌刷新异常: {str(e)}")

    async def _make_request(
        self, method: str, url: str, access_token: str, **kwargs
    ) -> Dict[str, Any]:
        """
        发送API请求

        Args:
            method: HTTP方法
            url: 请求URL
            access_token: 访问令牌
            **kwargs: 其他请求参数

        Returns:
            响应数据

        Raises:
            PolarAPIError: API调用失败
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = await self.http_client.request(
                method, url, headers=headers, **kwargs
            )
            response.raise_for_status()
            return response.json() if response.content else {}

        except httpx.HTTPStatusError as e:
            logger.error(f"Polar API请求失败: {url} - {e.response.status_code}")
            raise PolarAPIError(f"API请求失败: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Polar API请求异常: {url} - {str(e)}")
            raise PolarAPIError(f"API请求异常: {str(e)}")

    async def register_user(self, access_token: str, user_id: int) -> bool:
        """
        注册用户（首次使用需要注册）

        Args:
            access_token: 访问令牌
            user_id: Polar用户ID

        Returns:
            是否注册成功
        """
        try:
            url = f"{settings.POLAR_BASE_URL}/users"
            data = {"member-id": str(user_id)}
            await self._make_request("POST", url, access_token, json=data)
            logger.info(f"Polar用户注册成功: {user_id}")
            return True
        except PolarAPIError:
            # 用户可能已注册，忽略错误
            logger.info(f"Polar用户可能已注册: {user_id}")
            return True

    async def get_exercises(
        self, access_token: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        获取训练列表

        使用Polar AccessLink API v3直接访问endpoint:
        GET /v3/exercises - 直接获取所有训练记录

        Args:
            access_token: 访问令牌
            start_date: 开始日期（可选，用于过滤）
            end_date: 结束日期（可选，用于过滤）

        Returns:
            训练列表
        """
        try:
            # 直接通过 /v3/exercises 获取训练列表
            exercises_url = f"{settings.POLAR_BASE_URL}/exercises"

            logger.info(f"获取Polar训练列表: {exercises_url}")

            # 获取训练列表（返回的是简要信息的数组）
            # 添加 zones=true 参数以获取心率区间数据
            exercises_summary = await self._make_request("GET", f"{exercises_url}?zones=true", access_token)

            if not exercises_summary or not isinstance(exercises_summary, list):
                logger.info("未获取到训练记录")
                return []

            logger.info(f"找到{len(exercises_summary)}条训练记录")

            exercises = []

            # 遍历每条训练，获取完整详情
            for summary in exercises_summary:
                try:
                    exercise_id = summary.get("id")
                    if not exercise_id:
                        continue

                    # 日期过滤（基于 start_time）
                    if start_date or end_date:
                        start_time_str = summary.get("start_time")
                        if start_time_str:
                            # 注意：这里的格式可能不带时区，需要处理
                            try:
                                # 尝试解析不同格式
                                if "Z" in start_time_str or "+" in start_time_str:
                                    exercise_date = datetime.fromisoformat(start_time_str.replace("Z", "+00:00")).date()
                                else:
                                    exercise_date = datetime.fromisoformat(start_time_str).date()

                                if start_date and exercise_date < start_date:
                                    logger.debug(f"跳过训练（早于开始日期）: {exercise_id}")
                                    continue
                                if end_date and exercise_date > end_date:
                                    logger.debug(f"跳过训练（晚于结束日期）: {exercise_id}")
                                    continue
                            except Exception as e:
                                logger.warning(f"解析训练日期失败: {start_time_str} - {str(e)}")

                    # 获取完整的训练详情
                    # 添加 zones=true 参数以获取心率区间数据
                    detail_url = f"{exercises_url}/{exercise_id}?zones=true"
                    exercise_detail = await self._make_request("GET", detail_url, access_token)

                    if exercise_detail:
                        exercises.append(exercise_detail)
                        logger.debug(f"成功获取训练详情: {exercise_id}")

                except PolarAPIError as e:
                    logger.warning(f"获取训练详情失败: {summary.get('id')} - {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"处理训练记录异常: {str(e)}")
                    continue

            logger.info(f"成功获取{len(exercises)}条Polar训练记录（含详情）")
            return exercises

        except PolarAPIError as e:
            logger.error(f"获取Polar训练数据失败: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"获取Polar训练数据异常: {str(e)}")
            return []

    async def get_physical_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        获取用户体能信息

        Args:
            access_token: 访问令牌

        Returns:
            体能信息
        """
        try:
            info = await self._make_request("GET", PHYSICAL_INFO_ENDPOINT, access_token)
            logger.info("成功获取Polar体能信息")
            return info
        except PolarAPIError as e:
            logger.error(f"获取Polar体能信息失败: {str(e)}")
            return None

    async def get_daily_activity(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取日常活动数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            活动数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            activities = await self._make_request(
                "GET", DAILY_ACTIVITY_ENDPOINT, access_token, params=params
            )
            logger.info(f"成功获取Polar日常活动数据")
            return activities.get("activity-log", [])
        except PolarAPIError as e:
            logger.error(f"获取Polar日常活动数据失败: {str(e)}")
            return []

    async def get_exercise_zones_from_tcx(
        self, access_token: str, exercise_id: str, max_hr: int
    ) -> Dict[str, int]:
        """
        从TCX文件中提取心率区间数据

        Args:
            access_token: 访问令牌
            exercise_id: 训练ID
            max_hr: 最大心率

        Returns:
            {zone1_sec, zone2_sec, zone3_sec, zone4_sec, zone5_sec}
        """
        import xml.etree.ElementTree as ET

        try:
            # 获取TCX文件
            tcx_url = f"{settings.POLAR_BASE_URL}/exercises/{exercise_id}/tcx"
            response = await self.http_client.get(
                tcx_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if response.status_code != 200:
                logger.warning(f"获取TCX失败: {exercise_id} - {response.status_code}")
                return self._empty_zones()

            # 解析TCX XML
            root = ET.fromstring(response.text)
            namespaces = {'tcx': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'}

            # 提取所有心率采样点
            trackpoints = root.findall('.//tcx:Trackpoint', namespaces)

            # 计算心率区间边界
            zones_def = {
                1: (int(max_hr * 0.50), int(max_hr * 0.60)),
                2: (int(max_hr * 0.60), int(max_hr * 0.70)),
                3: (int(max_hr * 0.70), int(max_hr * 0.80)),
                4: (int(max_hr * 0.80), int(max_hr * 0.90)),
                5: (int(max_hr * 0.90), max_hr),
            }

            # 统计各区间秒数
            zone_counts = {i: 0 for i in range(1, 6)}

            for tp in trackpoints:
                hr_elem = tp.find('.//tcx:HeartRateBpm/tcx:Value', namespaces)
                if hr_elem is not None:
                    hr = int(hr_elem.text)

                    # 分配到对应区间
                    for zone_num, (min_hr, max_hr_zone) in zones_def.items():
                        if min_hr <= hr < max_hr_zone:
                            zone_counts[zone_num] += 1
                            break
                    else:
                        # 超出范围，分配到zone5或zone1
                        if hr >= zones_def[5][1]:
                            zone_counts[5] += 1
                        else:
                            zone_counts[1] += 1

            result = {f"zone{i}_sec": zone_counts[i] for i in range(1, 6)}
            logger.info(f"从TCX计算心率区间: {exercise_id} - Zone2={result['zone2_sec']}秒")
            return result

        except Exception as e:
            logger.error(f"解析TCX失败: {exercise_id} - {str(e)}")
            return self._empty_zones()

    def _empty_zones(self) -> Dict[str, int]:
        """返回空的心率区间"""
        return {f"zone{i}_sec": 0 for i in range(1, 6)}

    def parse_exercise_zones(self, exercise: Dict[str, Any]) -> Dict[str, int]:
        """
        解析训练心率区间数据

        Args:
            exercise: Polar训练原始数据

        Returns:
            {zone1_sec, zone2_sec, zone3_sec, zone4_sec, zone5_sec}
        """
        zones = {
            "zone1_sec": 0,
            "zone2_sec": 0,
            "zone3_sec": 0,
            "zone4_sec": 0,
            "zone5_sec": 0,
        }

        # 从心率区间数据中提取（支持不同的字段名）
        hr_data = exercise.get("heart_rate") or exercise.get("heart-rate", {})
        hr_zones = hr_data.get("zones", [])

        if hr_zones and isinstance(hr_zones, list):
            for idx, zone_data in enumerate(hr_zones, start=1):
                if idx <= 5:
                    # Polar返回的可能是秒数或毫秒
                    in_zone = zone_data.get("in-zone") or zone_data.get("in_zone", 0)
                    zones[f"zone{idx}_sec"] = int(in_zone)
        else:
            # 如果没有zones数据，记录日志
            logger.debug(f"训练记录缺少心率区间数据: {exercise.get('id')}")

        return zones

    def parse_sport_type(self, sport_id: int) -> str:
        """
        解析运动类型

        Args:
            sport_id: Polar运动类型ID

        Returns:
            运动类型名称
        """
        return SPORT_TYPE_MAP.get(sport_id, f"sport_{sport_id}")

    async def get_sleep_data(
        self, access_token: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        获取睡眠数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            睡眠数据列表
        """
        try:
            # GET /v3/users/nights
            nights_url = f"{settings.POLAR_BASE_URL}/users/nights"

            logger.info(f"获取Polar睡眠列表: {nights_url}")

            # 获取睡眠列表
            nights_data = await self._make_request("GET", nights_url, access_token)

            if not nights_data or "nights" not in nights_data:
                logger.info("未获取到睡眠记录")
                return []

            nights = nights_data.get("nights", [])
            logger.info(f"找到{len(nights)}条睡眠记录")

            sleep_records = []

            # 遍历每条睡眠记录，获取详情
            for night_summary in nights:
                try:
                    night_id = night_summary.get("polar-user") + "/" + night_summary.get("date")
                    if not night_id:
                        continue

                    # 日期过滤
                    if start_date or end_date:
                        night_date_str = night_summary.get("date")
                        if night_date_str:
                            try:
                                night_date = date.fromisoformat(night_date_str)
                                if start_date and night_date < start_date:
                                    logger.debug(f"跳过睡眠（早于开始日期）: {night_id}")
                                    continue
                                if end_date and night_date > end_date:
                                    logger.debug(f"跳过睡眠（晚于结束日期）: {night_id}")
                                    continue
                            except Exception as e:
                                logger.warning(f"解析睡眠日期失败: {night_date_str} - {str(e)}")

                    # 获取睡眠详情
                    # 使用polar-user和date组合作为ID
                    detail_url = f"{nights_url}/{night_id}"
                    sleep_detail = await self._make_request("GET", detail_url, access_token)

                    if sleep_detail:
                        sleep_records.append(sleep_detail)
                        logger.debug(f"成功获取睡眠详情: {night_id}")

                except PolarAPIError as e:
                    logger.warning(f"获取睡眠详情失败: {night_summary.get('date')} - {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"处理睡眠记录异常: {str(e)}")
                    continue

            logger.info(f"成功获取{len(sleep_records)}条Polar睡眠记录（含详情）")
            return sleep_records

        except PolarAPIError as e:
            logger.error(f"获取Polar睡眠数据失败: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"获取Polar睡眠数据异常: {str(e)}")
            return []

    async def get_nightly_recharge_data(
        self, access_token: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        获取夜间恢复数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            夜间恢复数据列表
        """
        try:
            # GET /v3/users/nightly-recharge
            recharge_url = f"{settings.POLAR_BASE_URL}/users/nightly-recharge"

            logger.info(f"获取Polar夜间恢复列表: {recharge_url}")

            # 获取夜间恢复列表
            recharge_data = await self._make_request("GET", recharge_url, access_token)

            if not recharge_data or "recharges" not in recharge_data:
                logger.info("未获取到夜间恢复记录")
                return []

            recharges = recharge_data.get("recharges", [])
            logger.info(f"找到{len(recharges)}条夜间恢复记录")

            recharge_records = []

            # 遍历每条记录，获取详情
            for recharge_summary in recharges:
                try:
                    # 使用polar-user和date组合作为ID
                    recharge_id = recharge_summary.get("polar-user") + "/" + recharge_summary.get("date")
                    if not recharge_id:
                        continue

                    # 日期过滤
                    if start_date or end_date:
                        recharge_date_str = recharge_summary.get("date")
                        if recharge_date_str:
                            try:
                                recharge_date = date.fromisoformat(recharge_date_str)
                                if start_date and recharge_date < start_date:
                                    logger.debug(f"跳过夜间恢复（早于开始日期）: {recharge_id}")
                                    continue
                                if end_date and recharge_date > end_date:
                                    logger.debug(f"跳过夜间恢复（晚于结束日期）: {recharge_id}")
                                    continue
                            except Exception as e:
                                logger.warning(f"解析夜间恢复日期失败: {recharge_date_str} - {str(e)}")

                    # 获取夜间恢复详情
                    detail_url = f"{recharge_url}/{recharge_id}"
                    recharge_detail = await self._make_request("GET", detail_url, access_token)

                    if recharge_detail:
                        recharge_records.append(recharge_detail)
                        logger.debug(f"成功获取夜间恢复详情: {recharge_id}")

                except PolarAPIError as e:
                    logger.warning(f"获取夜间恢复详情失败: {recharge_summary.get('date')} - {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"处理夜间恢复记录异常: {str(e)}")
                    continue

            logger.info(f"成功获取{len(recharge_records)}条Polar夜间恢复记录（含详情）")
            return recharge_records

        except PolarAPIError as e:
            logger.error(f"获取Polar夜间恢复数据失败: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"获取Polar夜间恢复数据异常: {str(e)}")
            return []
