"""
数据库模型
"""
from app.models.user import User
from app.models.polar import PolarAuth, PolarExercise
from app.models.oura import (
    OuraAuth, OuraSleep, OuraDailyReadiness,
    OuraDailyActivity, OuraDailyStress, OuraDailySpo2,
    OuraDailySleep, OuraCardiovascularAge, OuraResilience, OuraVO2Max
)
from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
from app.models.ai import AIRecommendation
from app.models.health_report import HealthReport
from app.models.nutrition import MealRecord, FoodItem, NutritionDailySummary

__all__ = [
    "User",
    # Polar
    "PolarAuth",
    "PolarExercise",
    # Oura
    "OuraAuth",
    "OuraSleep",
    "OuraDailyReadiness",
    "OuraDailyActivity",
    "OuraDailyStress",
    "OuraDailySpo2",
    "OuraDailySleep",
    "OuraCardiovascularAge",
    "OuraResilience",
    "OuraVo2Max",
    # 训练汇总
    "DailyTrainingSummary",
    "WeeklyTrainingSummary",
    "AIRecommendation",
    # 健康报告
    "HealthReport",
    # 营养
    "MealRecord",
    "FoodItem",
    "NutritionDailySummary",
]
