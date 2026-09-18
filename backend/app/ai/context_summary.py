"""Deterministic, coverage-aware context compression; no medical thresholds."""
from collections import Counter
from datetime import date, timedelta
from math import isfinite
from statistics import mean, pstdev

from app.utils.datetime_helper import format_hk


CONTEXT_DAYS = 90
CONTEXT_VERSION = "health-context-v1"


def metric_summary(points, end: date, unit: str) -> dict:
    """Missing days stay missing; windows use dates, never row positions."""
    values = {
        day: float(value) for day, value in points
        if value is not None and isfinite(float(value))
        and end - timedelta(days=89) <= day <= end
    }

    def window(length, offset=0):
        last = end - timedelta(days=offset)
        first = last - timedelta(days=length - 1)
        selected = [(day, value) for day, value in sorted(values.items()) if first <= day <= last]
        nums = [value for _, value in selected]
        result = {
            "start": first.isoformat(), "end": last.isoformat(),
            "observed_days": len(nums), "expected_days": length,
            "mean": round(mean(nums), 2) if nums else None,
            "min": round(min(nums), 2) if nums else None,
            "max": round(max(nums), 2) if nums else None,
            "stddev": round(pstdev(nums), 2) if len(nums) > 1 else None,
        }
        # At least half of the window plus a reasonable calendar span.
        if len(nums) >= max(4, (length + 1) // 2) and (selected[-1][0] - selected[0][0]).days >= length // 2:
            xs = [(day - first).days for day, _ in selected]
            x_mean, y_mean = mean(xs), mean(nums)
            slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, nums)) / sum((x - x_mean) ** 2 for x in xs)
            result["slope_per_day"] = round(slope, 3)
        else:
            result["slope_per_day"] = None
        return result

    windows = {"recent_7": window(7), "previous_7": window(7, 7),
               "recent_30": window(30), "previous_30": window(30, 30),
               "recent_90": window(90)}
    comparisons = {}
    for length in (7, 30):
        current, previous = windows[f"recent_{length}"], windows[f"previous_{length}"]
        sufficient = all(w["observed_days"] >= (length + 1) // 2 for w in (current, previous))
        delta = current["mean"] - previous["mean"] if sufficient else None
        comparisons[f"{length}_vs_previous_{length}"] = {
            "status": "comparable" if sufficient else "insufficient_coverage",
            "mean_change": round(delta, 2) if delta is not None else None,
            "change_percent": round(delta / abs(previous["mean"]) * 100, 1)
            if delta is not None and previous["mean"] != 0 else None,
        }
    return {"unit": unit, "last_observed_date": max(values).isoformat() if values else None,
            "windows": windows, "comparisons": comparisons}


def meal_history_summary(meals, end: date) -> dict:
    """Frequency is per recorded meal, not servings or confirmed preferences."""
    windows = {}
    for length in (7, 30, 90):
        first = end - timedelta(days=length - 1)
        selected = [m for m in meals if first.isoformat() <= format_hk(m.meal_time, "%Y-%m-%d") <= end.isoformat()]
        counts, last_seen, recorded_dates = Counter(), {}, set()
        meal_types = Counter()
        for meal in selected:
            day = format_hk(meal.meal_time, "%Y-%m-%d")
            recorded_dates.add(day)
            meal_types[meal.meal_type.value] += 1
            for name in {item.food_name.strip()[:80] for item in meal.food_items if item.food_name and item.food_name.strip()}:
                counts[name] += 1
                last_seen[name] = max(day, last_seen.get(name, day))
        ordered = sorted(counts, key=lambda name: (-counts[name], name))[:30]
        windows[str(length)] = {
            "start": first.isoformat(), "end": end.isoformat(),
            "recorded_days": len(recorded_dates), "recorded_meals": len(selected),
            "meal_type_counts": dict(meal_types), "distinct_dish_names": len(counts),
            "top_dishes": [{"name": name, "meal_count": counts[name], "last_eaten": last_seen[name]} for name in ordered],
            "omitted_dish_names": max(0, len(counts) - len(ordered)),
        }
    return {"windows": windows, "limitations": "仅统计已记录菜名，每餐同名去重；菜名数不等于食材多样性。未记录不等于没吃，频次不代表偏好、份量或过敏信息。"}


def build_health_history(oura, nutrition, training_rows, target: date) -> dict:
    """Recovery ends today; completed-day activity, training and diet end yesterday."""
    metrics = {}
    yesterday = target - timedelta(days=1)
    recovery = {"sleep_score": "分", "total_sleep_hours": "小时", "average_hrv": "ms",
                "resting_heart_rate": "bpm", "readiness_score": "分",
                "sleep_efficiency": "%", "deep_sleep_min": "分钟（主睡眠）", "rem_sleep_min": "分钟（主睡眠）"}
    activity = {"activity_score": "分", "steps": "步", "active_calories": "kcal",
                "sedentary_min": "分钟", "stress_high_min": "分钟", "recovery_high_min": "分钟",
                "high_activity_min": "分钟", "medium_activity_min": "分钟", "low_activity_min": "分钟", "inactivity_alerts": "次"}
    days = oura.recent_days if oura else []
    for name, unit in {**recovery, **activity}.items():
        metrics[name] = metric_summary([(date.fromisoformat(d.date), getattr(d, name)) for d in days], target if name in recovery else yesterday, unit)
    for name, unit in {"total_duration_min": "分钟", "zone2_min": "分钟", "hi_min": "分钟", "trimp": "TRIMP", "sessions_count": "次"}.items():
        metrics[f"training_{name}"] = metric_summary([(r.date, getattr(r, name)) for r in training_rows], yesterday, unit)
    for name, unit in {"total_calories": "kcal", "total_protein": "g", "total_carbs": "g", "total_fat": "g", "total_fiber": "g", "meals_count": "餐"}.items():
        metrics[f"recorded_nutrition_{name}"] = metric_summary([(date.fromisoformat(d.date), getattr(d, name)) for d in nutrition.days] if nutrition else [], yesterday, unit)
    return {
        "version": CONTEXT_VERSION, "target_date": target.isoformat(), "lookback_days": CONTEXT_DAYS,
        "metrics": metrics,
        "interpretation": "均值仅按有效记录日计算，不补零；营养为已记录餐食合计，不等于全天摄入。训练缺失日不等于休息日。比较前核对覆盖率和餐次数；斜率是描述性线性趋势，不是统计显著性或诊断。高低方向不等于健康好坏，应结合目标、个体基线和恢复判断。90天基线包含最近窗口，不是独立对照。",
    }
