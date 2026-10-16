"""Versioned, source-specific metric definitions; scores never masquerade as measurements."""

from dataclasses import dataclass

from sqlalchemy import func

from app.models.oura import (
    OuraSleep,
    OuraDailySleep,
    OuraDailyReadiness,
    OuraDailyActivity,
    OuraDailyStress,
    OuraDailySpo2,
    OuraCardiovascularAge,
    OuraResilience,
    OuraVO2Max,
    OuraSleepTime,
    OuraWorkout,
    OuraEnhancedTag,
    OuraRestModePeriod,
    OuraHeartRateSample,
)
from app.models.polar import PolarExercise, PolarSleep, PolarNightlyRecharge
from app.models.nutrition import MealRecord
from app.models.research import HealthJournalEntry, HealthSourceRecord

SCHEMA_VERSION = "health-research-v1"
TIMEZONE = "Asia/Hong_Kong"


@dataclass(frozen=True)
class Dataset:
    model: type
    date_field: str
    source: str
    description: str
    timestamp: bool = False

    @property
    def day_expression(self):
        column = getattr(self.model, self.date_field)
        return func.date(func.timezone(TIMEZONE, column)) if self.timestamp else column


DATASETS = {
    "sleep": Dataset(
        OuraSleep,
        "day",
        "oura",
        "睡眠段及阶段、HRV、呼吸、设备算法元数据；按设备起床日",
    ),
    "sleep_scores": Dataset(OuraDailySleep, "day", "oura", "每日睡眠评分与贡献因子"),
    "readiness": Dataset(
        OuraDailyReadiness, "day", "oura", "准备度、体温偏差与贡献因子评分"
    ),
    "activity": Dataset(
        OuraDailyActivity, "day", "oura", "步数、能量、活动强度、久坐、未佩戴与MET序列"
    ),
    "stress": Dataset(OuraDailyStress, "day", "oura", "日间压力与恢复时长"),
    "spo2": Dataset(OuraDailySpo2, "day", "oura", "血氧与呼吸扰动"),
    "cardiovascular_age": Dataset(
        OuraCardiovascularAge, "day", "oura", "血管年龄与脉搏波速度（设备支持时）"
    ),
    "resilience": Dataset(
        OuraResilience, "day", "oura", "恢复力及贡献评分（上游可用时）"
    ),
    "vo2_max": Dataset(OuraVO2Max, "day", "oura", "Oura VO₂ Max（上游可用时）"),
    "sleep_time": Dataset(
        OuraSleepTime, "day", "oura", "最佳入睡窗口；秒偏移不是实际入睡时间"
    ),
    "oura_workouts": Dataset(
        OuraWorkout, "day", "oura", "设备自动/手动运动记录；跨设备匹配时保留原记录"
    ),
    "tags": Dataset(OuraEnhancedTag, "start_day", "oura", "习惯、症状及自定义标签"),
    "rest_mode": Dataset(OuraRestModePeriod, "start_day", "oura", "休息模式周期"),
    "heart_rate": Dataset(
        OuraHeartRateSample,
        "timestamp",
        "oura",
        "连续心率采样；稀疏采样不能解释为连续覆盖",
        True,
    ),
    "polar_exercises": Dataset(
        PolarExercise,
        "start_time",
        "polar",
        "运动、心率区间、能量、距离及原始运动采样",
        True,
    ),
    "polar_sleep": Dataset(
        PolarSleep, "sleep_date", "polar", "Polar睡眠；独立保留，不与Oura简单相加"
    ),
    "polar_recharge": Dataset(
        PolarNightlyRecharge, "date", "polar", "Polar夜间恢复与ANS指标"
    ),
    "meals": Dataset(
        MealRecord,
        "meal_time",
        "nutrition",
        "餐食和食物明细；营养为AI估算的已记录摄入",
        True,
    ),
    "journal": Dataset(
        HealthJournalEntry,
        "day",
        "owner",
        "测量、体检、用药、补剂、症状、生活事件和全天记录确认",
    ),
    "provider_records": Dataset(
        HealthSourceRecord,
        "day",
        "mixed",
        "补充设备数据：session、活动、负荷、身体资料、同步状态",
    ),
}

# field -> (output unit, multiplier); original columns remain queryable.
MAPPINGS = {
    "sleep": {
        "total_sleep_duration": ("min", 1 / 60),
        "deep_sleep_duration": ("min", 1 / 60),
        "rem_sleep_duration": ("min", 1 / 60),
        "light_sleep_duration": ("min", 1 / 60),
        "awake_time": ("min", 1 / 60),
        "time_in_bed": ("min", 1 / 60),
        "latency": ("min", 1 / 60),
        "average_hrv": ("ms", 1),
        "average_heart_rate": ("bpm", 1),
        "lowest_heart_rate": ("bpm", 1),
        "average_breath": ("breaths/min", 1),
        "efficiency": ("%", 1),
        "sleep_score": ("score", 1),
        "restless_periods": ("count", 1),
    },
    "readiness": {
        "score": ("score", 1),
        "temperature_deviation": ("degC", 1),
        "temperature_trend_deviation": ("degC", 1),
    },
    "activity": {
        "score": ("score", 1),
        "steps": ("count", 1),
        "active_calories": ("kcal", 1),
        "total_calories": ("kcal", 1),
        "equivalent_walking_distance": ("m", 1),
        "sedentary_time": ("min", 1),
        "high_activity_time": ("min", 1),
        "medium_activity_time": ("min", 1),
        "low_activity_time": ("min", 1),
        "resting_time": ("min", 1),
        "non_wear_time": ("min", 1 / 60),
        "inactivity_alerts": ("count", 1),
        "average_met_minutes": ("MET", 1),
        "meters_to_target": ("m", 1),
    },
    "stress": {"stress_high": ("min", 1 / 60), "recovery_high": ("min", 1 / 60)},
    "spo2": {
        "spo2_percentage": ("%", 1),
        "breathing_disturbance_index": ("device_index", 1),
        "breathing_regularity": ("score", 1),
    },
    "cardiovascular_age": {
        "vascular_age": ("years", 1),
        "pulse_wave_velocity": ("m/s", 1),
    },
    "vo2_max": {"vo2_max": ("mL/kg/min", 1)},
    "resilience": {
        "sleep_recovery": ("score", 1),
        "daytime_recovery": ("score", 1),
        "stress": ("score", 1),
    },
    "polar_recharge": {
        "ans_charge": ("device_score", 1),
        "hrv_avg": ("ms", 1),
        "heart_rate_avg": ("bpm", 1),
        "breathing_rate_avg": ("breaths/min", 1),
    },
}
# Expose all contributing scores as scores, including readiness.resting_heart_rate.
for name in ("sleep_scores", "readiness", "activity"):
    model = DATASETS[name].model
    fields = [
        c.name for c in model.__table__.columns if c.name.startswith("contributor_")
    ]
    if name == "readiness":
        fields += [
            "activity_balance",
            "sleep_balance",
            "previous_night",
            "previous_day_activity",
            "recovery_index",
            "resting_heart_rate",
            "hrv_balance",
            "body_temperature",
            "sleep_regularity",
        ]
    MAPPINGS.setdefault(name, {}).update({f: ("score", 1) for f in fields})
MAPPINGS["sleep_scores"]["score"] = ("score", 1)

MEASUREMENTS = {
    "weight": ("kg", 1, 500),
    "height": ("cm", 30, 300),
    "waist": ("cm", 10, 300),
    "body_fat": ("%", 0, 100),
    "blood_pressure_systolic": ("mmHg", 20, 350),
    "blood_pressure_diastolic": ("mmHg", 10, 250),
    "resting_heart_rate": ("bpm", 10, 300),
    "blood_glucose": ("mmol/L", 0, 100),
    "hba1c": ("%", 0, 100),
    "total_cholesterol": ("mmol/L", 0, 30),
    "ldl_cholesterol": ("mmol/L", 0, 30),
    "hdl_cholesterol": ("mmol/L", 0, 30),
    "triglycerides": ("mmol/L", 0, 100),
    "temperature": ("degC", 25, 45),
    "spo2": ("%", 0, 100),
    "water": ("mL", 0, 20000),
    "caffeine": ("mg", 0, 5000),
    "alcohol": ("g", 0, 1000),
    "fatigue": ("score_0_10", 0, 10),
    "mood": ("score_0_10", 0, 10),
    "pain": ("score_0_10", 0, 10),
    "perceived_stress": ("score_0_10", 0, 10),
}


def metric_definitions():
    result = {}
    for dataset, fields in MAPPINGS.items():
        for field, (unit, _) in fields.items():
            result[f"{dataset}.{field}"] = {
                "unit": unit,
                "dataset": dataset,
                "meaning": "主睡眠" if dataset == "sleep" else "来源设备指标",
            }
    extras = {
        "sleep.total_minutes": "min",
        "sleep.nap_minutes": "min",
        "sleep.nap_count": "count",
        "sleep.bedtime_minute": "minute_of_day",
        "sleep.wake_minute": "minute_of_day",
        "training.duration_minutes": "min",
        "training.sessions": "count",
        "training.zone2_minutes": "min",
        "training.high_intensity_minutes": "min",
        "training.zone_weighted_load": "weighted_minutes",
        "training.recorded_calories": "kcal",
        "nutrition.meals": "count",
        "nutrition.calories": "kcal",
        "nutrition.protein": "g",
        "nutrition.carbs": "g",
        "nutrition.fat": "g",
        "nutrition.fiber": "g",
        "nutrition.recorded_sodium": "mg",
        "nutrition.recorded_sugar": "g",
        "nutrition.last_meal_minute": "minute_of_day",
        "heart_rate.mean": "bpm",
        "heart_rate.min": "bpm",
        "heart_rate.max": "bpm",
        "heart_rate.samples": "count",
        "sessions.duration_minutes": "min",
        "polar_activity.steps": "count",
        "polar_activity.active_calories": "kcal",
        "polar_activity.calories": "kcal",
        "polar_activity.active_minutes": "min",
        "polar_activity.inactive_minutes": "min",
        "polar_load.cardio_load": "device_load",
        "polar_load.strain": "device_load",
        "polar_load.tolerance": "device_load",
        "polar_load.cardio_load_ratio": "ratio",
    }
    for key, unit in extras.items():
        result[key] = {"unit": unit, "meaning": "派生指标；核对每日quality与evidence"}
    for key, (unit, _, _) in MEASUREMENTS.items():
        result[f"journal.{key}"] = {
            "unit": unit,
            "meaning": "当日最后一次有效记录；饮水/咖啡因/酒精为记录合计",
        }
    return result


LIMITATIONS = [
    "sleep/readiness按设备起床日；活动/训练/饮食按发生日，时区Asia/Hong_Kong（UTC+8）。",
    "当天为未完成日；无数据不补零，缺失训练不代表休息。",
    "营养为已记录餐食的AI估算，只有用户明确确认全天记录完整才可标为完整。",
    "Oura准备度的resting_heart_rate是贡献评分；实际bpm见sleep.lowest_heart_rate。",
    "运动仅在唯一且高重叠的跨设备候选间自动关联；疑义保留并标记。",
    "连续心率样本数不等于佩戴覆盖；未将稀疏样本补成连续曲线。",
    "相关性与滞后关系用于探索，不是因果、诊断或健康/不健康的医学判定。",
]
