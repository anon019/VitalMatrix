"""
Polar常量定义
"""

# Polar API端点
POLAR_AUTH_URL = "https://flow.polar.com/oauth2/authorization"
POLAR_TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
POLAR_BASE_URL = "https://www.polaraccesslink.com/v3"

# API资源端点
EXERCISES_ENDPOINT = f"{POLAR_BASE_URL}/exercises"
PHYSICAL_INFO_ENDPOINT = f"{POLAR_BASE_URL}/users/physical-information"
DAILY_ACTIVITY_ENDPOINT = f"{POLAR_BASE_URL}/users/activity-transactions"

# OAuth Scopes
POLAR_SCOPES = [
    "accesslink.read_all",  # 读取所有数据
]

# 心率区间定义（基于最大心率百分比）
HEART_RATE_ZONES = {
    "zone1": {"min": 0.50, "max": 0.60, "name": "极轻强度"},
    "zone2": {"min": 0.60, "max": 0.70, "name": "燃脂区间"},
    "zone3": {"min": 0.70, "max": 0.80, "name": "有氧区间"},
    "zone4": {"min": 0.80, "max": 0.90, "name": "无氧阈值"},
    "zone5": {"min": 0.90, "max": 1.00, "name": "最大强度"},
}

# 运动类型映射
SPORT_TYPE_MAP = {
    1: "running",  # 跑步
    2: "cycling",  # 骑行
    3: "swimming",  # 游泳
    6: "strength_training",  # 力量训练
    27: "walking",  # 步行
    # 可根据需要扩展
}
