"""
日期时间辅助函数
"""
from datetime import datetime, date, timedelta, timezone
import pytz

# 香港时区
HK_TZ = pytz.timezone("Asia/Hong_Kong")


def now_hk() -> datetime:
    """获取当前香港时间"""
    return datetime.now(HK_TZ)


def today_hk() -> date:
    """获取当前香港日期"""
    return now_hk().date()


def ensure_hk(value: datetime) -> datetime:
    """把数据库或调用方时间统一转换为香港时区。

    PostgreSQL 通常返回 UTC aware datetime；历史数据或测试数据也可能是 naive。
    naive 值按 UTC 解释，避免依赖服务器本地时区。
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(HK_TZ)


def date_hk(value: datetime) -> date:
    """返回某个时间戳在香港时区对应的自然日。"""
    return ensure_hk(value).date()


def format_hk(value: datetime, pattern: str) -> str:
    """按香港时区格式化时间。"""
    return ensure_hk(value).strftime(pattern)


def start_of_day_hk(current_date: date) -> datetime:
    """获取某日香港时区零点时间"""
    return HK_TZ.localize(datetime.combine(current_date, datetime.min.time()))


def end_of_day_hk(current_date: date) -> datetime:
    """获取某日香港时区23:59:59时间"""
    return start_of_day_hk(current_date) + timedelta(days=1) - timedelta(seconds=1)


def get_week_start(dt: date) -> date:
    """获取周起始日期（周一）"""
    return dt - timedelta(days=dt.weekday())


def get_week_end(dt: date) -> date:
    """获取周结束日期（周日）"""
    return dt + timedelta(days=6 - dt.weekday())


def format_duration(seconds: int) -> str:
    """格式化时长（秒 -> 时:分:秒）"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_duration_minutes(seconds: int) -> str:
    """格式化时长（秒 -> 分钟）"""
    return f"{seconds // 60}分{seconds % 60}秒"
