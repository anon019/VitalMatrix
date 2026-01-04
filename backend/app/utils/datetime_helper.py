"""
日期时间辅助函数
"""
from datetime import datetime, date, timedelta
import pytz

# 香港时区
HK_TZ = pytz.timezone("Asia/Hong_Kong")


def now_hk() -> datetime:
    """获取当前香港时间"""
    return datetime.now(HK_TZ)


def today_hk() -> date:
    """获取当前香港日期"""
    return now_hk().date()


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
