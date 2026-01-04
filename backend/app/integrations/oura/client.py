"""
Oura Ring API客户端
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

# Oura API v2 基础URL
OURA_API_BASE = "https://api.ouraring.com/v2"

# Oura OAuth URLs
OURA_AUTH_URL = "https://cloud.ouraring.com/oauth/authorize"
OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"


class OuraAPIError(Exception):
    """Oura API错误"""
    pass


class OuraClient:
    """Oura Ring API客户端"""

    def __init__(self):
        self.client_id = settings.OURA_CLIENT_ID
        self.client_secret = settings.OURA_CLIENT_SECRET
        self.redirect_uri = settings.OURA_REDIRECT_URI
        # trust_env=False: 忽略代理环境变量，直连Oura API
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
            f"{OURA_AUTH_URL}"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scope_str}"
            f"&state={state}"
        )
        return auth_url

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        用授权码换取访问令牌

        Args:
            code: 授权码

        Returns:
            令牌信息 {access_token, refresh_token, expires_in, token_type}

        Raises:
            OuraAPIError: API调用失败
        """
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = await self.http_client.post(OURA_TOKEN_URL, data=data)
            response.raise_for_status()
            token_data = response.json()

            logger.info("成功获取Oura访问令牌")
            return token_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Oura令牌交换失败: {e.response.status_code} {e.response.text}")
            raise OuraAPIError(f"令牌交换失败: {e.response.text}")
        except Exception as e:
            logger.error(f"Oura令牌交换异常: {str(e)}")
            raise OuraAPIError(f"令牌交换异常: {str(e)}")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        刷新访问令牌

        Args:
            refresh_token: 刷新令牌

        Returns:
            新的令牌信息

        Raises:
            OuraAPIError: API调用失败
        """
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = await self.http_client.post(OURA_TOKEN_URL, data=data)
            response.raise_for_status()
            token_data = response.json()

            logger.info("成功刷新Oura访问令牌")
            return token_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Oura令牌刷新失败: {e.response.status_code} {e.response.text}")
            raise OuraAPIError(f"令牌刷新失败: {e.response.text}")
        except Exception as e:
            logger.error(f"Oura令牌刷新异常: {str(e)}")
            raise OuraAPIError(f"令牌刷新异常: {str(e)}")

    async def _make_request(
        self, method: str, endpoint: str, access_token: str, **kwargs
    ) -> Dict[str, Any]:
        """
        发送API请求

        Args:
            method: HTTP方法
            endpoint: API端点（不包含基础URL）
            access_token: 访问令牌
            **kwargs: 其他请求参数

        Returns:
            响应数据

        Raises:
            OuraAPIError: API调用失败
        """
        url = f"{OURA_API_BASE}{endpoint}"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = await self.http_client.request(
                method, url, headers=headers, **kwargs
            )
            response.raise_for_status()
            return response.json() if response.content else {}

        except httpx.HTTPStatusError as e:
            logger.error(f"Oura API请求失败: {endpoint} - {e.response.status_code}")
            raise OuraAPIError(f"API请求失败: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Oura API请求异常: {endpoint} - {str(e)}")
            raise OuraAPIError(f"API请求异常: {str(e)}")

    async def get_personal_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        获取个人信息

        Args:
            access_token: 访问令牌

        Returns:
            个人信息（年龄、体重、身高等）
        """
        try:
            info = await self._make_request("GET", "/usercollection/personal_info", access_token)
            logger.info("成功获取Oura个人信息")
            return info
        except OuraAPIError as e:
            logger.error(f"获取Oura个人信息失败: {str(e)}")
            return None

    async def get_daily_sleep(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取睡眠数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            睡眠数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/daily_sleep", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura睡眠数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura睡眠数据失败: {str(e)}")
            return []

    async def get_sleep_details(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取详细睡眠数据（包含HRV等）

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            详细睡眠数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/sleep", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura详细睡眠数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura详细睡眠数据失败: {str(e)}")
            return []

    async def get_daily_readiness(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取准备度数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            准备度数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/daily_readiness", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura准备度数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura准备度数据失败: {str(e)}")
            return []

    async def get_daily_activity(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取活动数据

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
            response = await self._make_request(
                "GET", "/usercollection/daily_activity", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura活动数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura活动数据失败: {str(e)}")
            return []

    async def get_daily_stress(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取压力数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            压力数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/daily_stress", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura压力数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura压力数据失败: {str(e)}")
            return []

    async def get_daily_spo2(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取血氧数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            血氧数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/daily_spo2", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura血氧数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura血氧数据失败: {str(e)}")
            return []

    async def get_daily_cardiovascular_age(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取心血管年龄数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            心血管年龄数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/daily_cardiovascular_age", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura心血管年龄数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura心血管年龄数据失败: {str(e)}")
            return []

    async def get_daily_resilience(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取韧性/恢复力数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            韧性数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/daily_resilience", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura韧性数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura韧性数据失败: {str(e)}")
            return []

    async def get_vo2_max(
        self, access_token: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取VO2 Max数据

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            VO2 Max数据列表
        """
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/vo2_max", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura VO2 Max数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura VO2 Max数据失败: {str(e)}")
            return []

    async def get_heartrate(
        self, access_token: str, start_datetime: datetime, end_datetime: datetime
    ) -> List[Dict[str, Any]]:
        """
        获取心率数据

        Args:
            access_token: 访问令牌
            start_datetime: 开始时间
            end_datetime: 结束时间

        Returns:
            心率数据列表
        """
        try:
            params = {
                "start_datetime": start_datetime.isoformat(),
                "end_datetime": end_datetime.isoformat(),
            }
            response = await self._make_request(
                "GET", "/usercollection/heartrate", access_token, params=params
            )
            data = response.get("data", [])
            logger.info(f"成功获取{len(data)}条Oura心率数据")
            return data
        except OuraAPIError as e:
            logger.error(f"获取Oura心率数据失败: {str(e)}")
            return []

    async def get_all_daily_data(
        self, access_token: str, start_date: date, end_date: date
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有每日数据（睡眠、准备度、活动、压力、血氧、心血管年龄、韧性、VO2 Max）

        Args:
            access_token: 访问令牌
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含所有数据类型的字典
        """
        results = {
            "sleep": [],
            "sleep_details": [],
            "readiness": [],
            "activity": [],
            "stress": [],
            "spo2": [],
            "cardiovascular_age": [],
            "resilience": [],
            "vo2_max": [],
        }

        # 并行获取所有数据
        import asyncio

        tasks = [
            self.get_daily_sleep(access_token, start_date, end_date),
            self.get_sleep_details(access_token, start_date, end_date),
            self.get_daily_readiness(access_token, start_date, end_date),
            self.get_daily_activity(access_token, start_date, end_date),
            self.get_daily_stress(access_token, start_date, end_date),
            self.get_daily_spo2(access_token, start_date, end_date),
            self.get_daily_cardiovascular_age(access_token, start_date, end_date),
            self.get_daily_resilience(access_token, start_date, end_date),
            self.get_vo2_max(access_token, start_date, end_date),
        ]

        data = await asyncio.gather(*tasks, return_exceptions=True)

        keys = ["sleep", "sleep_details", "readiness", "activity", "stress", "spo2", "cardiovascular_age", "resilience", "vo2_max"]
        for i, key in enumerate(keys):
            if not isinstance(data[i], Exception):
                results[key] = data[i]
            else:
                logger.error(f"获取{key}数据失败: {data[i]}")

        return results
