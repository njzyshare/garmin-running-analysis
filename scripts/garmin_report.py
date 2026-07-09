#!/usr/bin/env python3
"""
生成综合训练分析 HTML 报告：基础信息、最强表现、周跑量统计、恢复与健康趋势、四维度评分。

Usage:
    python3 scripts/garmin_report.py
    python3 scripts/garmin_report.py --days 14
    python3 scripts/garmin_report.py --output ~/reports/report.html
"""

import json
import sys
import argparse
import math
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Import auth helper
sys.path.insert(0, str(Path(__file__).parent))
from garmin_auth import get_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DAYS = 30
# 扩展 fetch 周期至 120 天（确保覆盖历史 PB 活动如 1月份的5K等）
PB_HISTORY_DAYS = 120

# 输出目录（相对于项目根目录的 reports/ 文件夹）
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# DI (Discomfort Index) 计算
# 公式: DI = T - 0.55 * (1 - RH/100) * (T - 14.5)
#   T: 温度 (°C), RH: 相对湿度 (%)
# ---------------------------------------------------------------------------

def calc_di(temp_c, humidity_pct):
    """Calculate Discomfort Index from temperature (°C) and relative humidity (%)."""
    if temp_c is None or humidity_pct is None:
        return None
    try:
        t = float(temp_c)
        rh = float(humidity_pct)
        return round(t - 0.55 * (1 - rh / 100.0) * (t - 14.5), 1)
    except (ValueError, TypeError):
        return None


def di_level(di):
    """Classify DI value into a level string."""
    if di is None:
        return None
    if di < 21:
        return "舒适"
    elif di < 24:
        return "轻度不适"
    elif di < 27:
        return "中度不适"
    elif di < 29:
        return "明显不适"
    else:
        return "严重不适"


def di_pace_impact(di):
    """Estimate pace impact (s/km) from DI value."""
    if di is None:
        return None
    if di < 21:
        return (0, "无显著影响")
    elif di < 24:
        return (1, "轻微影响，配速约慢1-3 s/km")
    elif di < 27:
        return (5, "中度影响，配速约慢3-8 s/km")
    elif di < 29:
        return (10, "明显影响，配速约慢8-15 s/km")
    else:
        return (18, "严重影响，配速约慢15+ s/km")


def calc_effort_pace(avg_pace_s_per_km, elevation_gain_m, distance_km, avg_hr=None, use_personalized=True):
    """计算等强配速 (Effort Pace) - 坡度调整后的等效平路配速。

    参考 Garmin 计圈数据，提供三级计算方案：

    方案 A — 每公里分段法（最优，有 splits 时使用）
        根据每公里计圈的净爬升，逐公里独立折算，再以距离加权取平均。
        公式：等效配速(s) = 实际配速(s) / (1.05 ^ 坡度%)
        其中 坡度% = (elevationGain - elevationLoss) / 1000 * 100
        指数 1.05 为通用坡度因子（接近 Daniels VDOT 坡度调整系数）。

        个性化修正（当 avg_hr 可用时）：
        如果该公里心率显著偏离训练平均心率，说明坡度-实际努力的映射
        不同于通用模型，按心率偏离比例微调等效配速。

    方案 B — 整体坡度法（兜底，无 splits 时使用）
        等强配速 = 平均配速 / (1.05 ^ avg_grade)
        avg_grade = elevation_gain / (distance_m * 0.01)

    方案 C — Naismith 法（另存参考）
        等效距离 = distance_km + elevation_gain / 100
        等强配速 = total_time / 等效距离

    Args:
        avg_pace_s_per_km: 平均配速（秒/公里）
        elevation_gain_m: 总爬升（米）
        distance_km: 距离（公里）
        avg_hr: 平均心率（可选，用于个性修正）
        use_personalized: 是否启用心率个性化修正

    Returns:
        dict: {
            "effort_pace": "4:48/km",        # 最佳估算的等强配速
            "effort_pace_s": 288.0,           # 秒数
            "scheme": "A|B|C",               # 使用的方案
            "avg_grade": 3.0,                # 平均坡度 %
            "detail": {                       # 方案A时的逐公里详情
                "km_grades": [...],
                "adjusted_grades": [...]
            },
            "personalized": True/False,      # 是否使用了心率修正
            "naismith_pace": "4:16/km",      # Naismith法参考值
        }
    """
    import math
    from collections import OrderedDict

    # === 方案 A：从活动 splits 中获取分段坡度数据 ===
    laps = None
    if hasattr(avg_pace_s_per_km, "_laps_cache"):
        laps = avg_pace_s_per_km._laps_cache

    if laps:
        km_adjusted = []
        valid_km_count = 0
        total_adjusted_s = 0
        total_dist = 0
        total_actual_s = 0

        for lap in laps:
            lap_dist = lap.get("distance", 0) or 0
            if lap_dist < 500:
                continue
            lap_dur = lap.get("duration", 0) or 0
            if lap_dur <= 0:
                continue
            lap_up = lap.get("elevationGain", 0) or 0
            lap_down = lap.get("elevationLoss", 0) or 0
            lap_hr = lap.get("averageHR", 0) or 0

            # 该公里净爬升百分比
            lap_net = lap_up - lap_down
            lap_grade = lap_net / (lap_dist / 1000 * 10)  # 净爬升/10km → %（精确）

            # 通用坡度因子：1.05^坡度
            grade_factor = 1.05 ** abs(lap_grade) if lap_grade > 0 else 1.0

            # 上坡时，等强配速 < 实际配速（坡度因子越小增益越大）
            if lap_grade > 0:
                adjusted_s = lap_dur / grade_factor
            else:
                # 下坡时，实际配速已经更快，按坡度因子放大（下坡效率有限）
                adjusted_s = lap_dur * (1.0 + 0.3 * abs(lap_grade) / 10)

            # 个性化微调：如果心率显著偏离平均，说明坡度实际努力不同
            if use_personalized and avg_hr and lap_hr > 0:
                hr_ratio = lap_hr / avg_hr
                if hr_ratio > 1.05:
                    # 该公里心率偏高5%以上 → 实际付出更多努力 → 进一步降等强配速
                    adjusted_s = adjusted_s * (1.0 - (hr_ratio - 1.0) * 0.3)
                elif hr_ratio < 0.95:
                    # 心率偏低 → 该公里较轻松
                    adjusted_s = adjusted_s * (1.0 + (1.0 - hr_ratio) * 0.2)

            adjusted_s = max(adjusted_s, lap_dur * 0.7)

            km_adjusted.append({
                "km": len(km_adjusted) + 1,
                "grade": round(lap_grade, 1),
                "actual_pace_s": lap_dur / (lap_dist / 1000) if lap_dist else 0,
                "adj_pace_s": adjusted_s / (lap_dist / 1000) if lap_dist else 0,
                "hr": lap_hr,
                "factor": round(grade_factor, 3),
                "net_elev": round(lap_net, 1),
            })

            total_adjusted_s += adjusted_s
            total_actual_s += lap_dur
            total_dist += lap_dist
            valid_km_count += 1

        if valid_km_count >= 2:
            effort_pace_s = (total_adjusted_s / total_dist) * 1000 if total_dist else avg_pace_s_per_km
            avg_g = sum(k["grade"] for k in km_adjusted) / len(km_adjusted)
            pace_m = int(effort_pace_s // 60)
            pace_s = int(effort_pace_s % 60)

            # Naismith 参考
            eq_dist = distance_km + elevation_gain_m / 100
            naismith_s = (total_actual_s / eq_dist) if eq_dist else effort_pace_s

            return {
                "effort_pace": f"{pace_m}:{pace_s:02d}/km",
                "effort_pace_s": round(effort_pace_s, 1),
                "scheme": "A",
                "avg_grade": round(avg_g, 1),
                "km_count": valid_km_count,
                "naismith_pace": f"{int(naismith_s//60)}:{int(naismith_s%60):02d}/km",
                "naismith_pace_s": round(naismith_s, 1),
                "personalized": use_personalized and avg_hr is not None,
                "km_detail": km_adjusted,
            }

    # === 方案 B：整体坡度法（兜底）===
    distance_m = distance_km * 1000
    if distance_m > 0:
        avg_grade = elevation_gain_m / (distance_m * 0.01)  # 总爬升/总距离*100
        if avg_grade < 0.5:
            # 几乎平路，等强配速 ≈ 实际配速
            pace_m = int(avg_pace_s_per_km // 60)
            pace_s = int(avg_pace_s_per_km % 60)
            return {
                "effort_pace": f"{pace_m}:{pace_s:02d}/km",
                "effort_pace_s": round(avg_pace_s_per_km, 1),
                "scheme": "B",
                "avg_grade": round(avg_grade, 1),
                "note": "基本平路，等强配速≈实际配速",
                "naismith_pace": None,
            }

        grade_factor = 1.05 ** avg_grade
        effort_pace_s = avg_pace_s_per_km / grade_factor

        pace_m = int(effort_pace_s // 60)
        pace_s = int(effort_pace_s % 60)

        # Naismith 参考
        eq_dist = distance_km + elevation_gain_m / 100
        naismith_s = (avg_pace_s_per_km * distance_km / eq_dist) if eq_dist else effort_pace_s

        return {
            "effort_pace": f"{pace_m}:{pace_s:02d}/km",
            "effort_pace_s": round(effort_pace_s, 1),
            "scheme": "B",
            "avg_grade": round(avg_grade, 1),
            "note": None,
            "naismith_pace": f"{int(naismith_s//60)}:{int(naismith_s%60):02d}/km",
            "naismith_pace_s": round(naismith_s, 1),
            "personalized": False,
        }

    return None


def di_color_class(di):
    """Return CSS class for DI display."""
    if di is None:
        return ""
    if di < 21:
        return "di-green"
    elif di < 24:
        return "di-yellow"
    elif di < 27:
        return "di-orange"
    else:
        return "di-red"


def parse_activity_weather(weather_data):
    """Extract temperature/humidity from activity weather data.
    
    Garmin weather API returns temp in °F, relativeHumidity as integer 0-100,
    and condition as weatherTypeDTO.desc.
    e.g. {"temp": 84, "relativeHumidity": 52, "weatherTypeDTO": {"desc": "Cloudy"}}
    """
    if not weather_data or not isinstance(weather_data, dict):
        return {}
    
    # Temperature: Garmin returns °F, convert to °C
    temp_f = weather_data.get("temperature")
    if temp_f is None:
        temp_f = weather_data.get("temp")
    temp_c = None
    if temp_f is not None:
        try:
            temp_c = round((float(temp_f) - 32) * 5 / 9, 1)
        except (ValueError, TypeError):
            temp_c = None
    
    # Humidity: check multiple possible field names; 0 is a valid value
    humidity = weather_data.get("humidity")
    if humidity is None:
        humidity = weather_data.get("humidityPercent")
    if humidity is None:
        humidity = weather_data.get("relativeHumidity")
    
    # Condition: check multiple possible field names
    condition = weather_data.get("condition")
    if condition is None:
        condition = weather_data.get("weatherCondition")
    if condition is None:
        wtdto = weather_data.get("weatherTypeDTO")
        if isinstance(wtdto, dict):
            condition = wtdto.get("desc")
    
    return {
        "temperature": temp_c,
        "humidity": humidity,
        "condition": condition,
        "di": calc_di(temp_c, humidity) if temp_c is not None and humidity is not None else None
    }


def fetch_weather_fallback(lat, lon, date_str):
    """Fetch historical weather from Open-Meteo API as fallback.
    
    Args:
        lat: latitude (float)
        lon: longitude (float)
        date_str: date string (YYYY-MM-DD)
    
    Returns:
        dict with keys: temperature (°C), humidity (%), condition, di
        or None if fetch fails
    """
    if not lat or not lon or not date_str:
        return None
    
    try:
        import urllib.request
        import json as json_mod
        
        # Open-Meteo archive API (free, no key needed)
        url = (
            f"https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            f"&start_date={date_str}&end_date={date_str}"
            f"&hourly=temperature_2m,relative_humidity_2m,precipitation"
            f"&timezone=auto"
        )
        
        req = urllib.request.Request(url, headers={"User-Agent": "GarminReport/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json_mod.loads(resp.read().decode("utf-8"))
        
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        humidities = hourly.get("relative_humidity_2m", [])
        
        if not times or not temps:
            return None
        
        # Find the closest hour to noon (12:00) for a representative value
        noon_idx = 0
        min_diff = float("inf")
        for i, t in enumerate(times):
            if "T" in t:
                hour_str = t.split("T")[1][:2]
                try:
                    hour = int(hour_str)
                    diff = abs(hour - 12)
                    if diff < min_diff:
                        min_diff = diff
                        noon_idx = i
                except ValueError:
                    pass
        
        temp_c = temps[noon_idx] if noon_idx < len(temps) else None
        humidity = humidities[noon_idx] if noon_idx < len(humidities) else None
        
        if temp_c is None:
            return None
        
        return {
            "temperature": round(temp_c, 1),
            "humidity": humidity,
            "condition": None,
            "di": calc_di(temp_c, humidity) if humidity is not None else None,
            "source": "open-meteo"
        }
    
    except Exception as e:
        print(f"   ⚠️ Weather fallback failed: {e}", file=sys.stderr)
        return None


def format_pb_row(records_dict, metric_key, label, unit=""):
    """Format a personal record entry into HTML row or None."""
    if not records_dict or not isinstance(records_dict, dict):
        return None
    entry = records_dict.get(metric_key)
    if not entry:
        return None
    if isinstance(entry, dict):
        val = entry.get("value") or entry.get("formattedValue")
        date = entry.get("startDate", "")[:10] if entry.get("startDate") else ""
    else:
        val = entry
        date = ""
    if val is None:
        return None
    return {"label": label, "value": f"{val}{unit}", "date": date, "metric": metric_key}


def _seconds_to_time_str(seconds):
    """Convert seconds to time string (M:SS or H:MM:SS)."""
    if not seconds or seconds <= 0:
        return None
    total_seconds = int(seconds)
    m, s = divmod(total_seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    else:
        return f"{m}:{s:02d}"


def _time_str_to_seconds(time_str):
    """Convert '22:21' or '1:35:45' to seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return None


def _estimate_1km_from_1mile(mile_seconds):
    """Estimate 1KM time from 1-mile time (rough conversion).
    
    1 mile = 1609.34 meters
    1 km = 1000 meters
    Estimate: 1km time ≈ 1-mile time * (1000/1609.34)
    """
    if not mile_seconds or mile_seconds <= 0:
        return None
    km_seconds = mile_seconds * (1000.0 / 1609.34)
    total_seconds = int(km_seconds)
    m, s = divmod(total_seconds, 60)
    return f"{m}:{s:02d}"


# Known wrong values in Chinese Garmin API (discovered empirically)
# ⚠️ DEPRECATED: Now relying on validation ranges + activity splits fallback
# Keep for reference but no longer used in validation
_KNOWN_BAD_PB = {
    "5K PB": 387,    # ~6:27, impossible
    "10K PB": 1313,  # ~21:53, impossible (unless it's actually 5K PB mislabeled by API)
}


def _validate_api_pb(label, seconds):
    """Validate API PB value. Returns True if plausible, False if obviously wrong.

    Realistic running PB ranges (seconds):
    - 1KM:     2min-6min    [120, 360]
    - 1英里:   3min-8min    [180, 480]
    - 5K:      15min-35min  [900, 2100]
    - 10K:     30min-70min  [1800, 4200]
    - 半马:    54min-2h     [3240, 7200]
    - 全马:    1h48min-4h   [6480, 14400]

    Returns: (is_valid, reason_if_invalid)
    """
    if seconds is None:
        return False, "无数据"

    ranges = {
        "1KM PB": (120, 360),
        "1英里（1.609344KM）PB": (180, 480),
        "5K PB": (900, 2100),
        "10K PB": (1800, 4200),
        "半马 PB": (3240, 7200),
        "全马 PB": (6480, 14400),
    }
    lo, hi = ranges.get(label, (0, 999999))
    if not (lo <= seconds <= hi):
        return False, f"超出合理范围[{lo},{hi}]秒"

    return True, ""


def extract_personal_records(pb_data):
    """Extract running PBs from Garmin personal_record API with validation.

    API typeId mapping (Chinese Garmin garmin.cn):
    - 1 = 1KM   (validated)
    - 2 = 1英里  (validated)
    - 3 = 5K    (validated; fixed via splits if invalid)
    - 4 = 10K   (validated; fixed via splits if invalid)
    - 5 = 半马   (generally reliable)
    - 6 = 全马   (generally reliable)

    For 1KM/1英里/5K/10K: validate and fall back to activity splits if invalid.
    For 半马/全马: use API directly (reliable per empirical testing).

    Returns: [{"label": "5K PB", "value": "22:21", "date": "2026-01-24",
               "source": "api", "validated": True}, ...]
    """
    if not pb_data:
        return []

    # typeId to label mapping (Chinese Garmin garmin.cn)
    TYPE_MAP = {
        1: "1KM PB",
        2: "1英里（1.61KM）PB",
        3: "5K PB",
        4: "10K PB",
        5: "半马 PB",
        6: "全马 PB",
    }

    records = []

    if isinstance(pb_data, list):
        for item in pb_data:
            tid = item.get("typeId")
            if tid not in TYPE_MAP:
                continue

            val = item.get("value")
            name = item.get("activityName", "") or ""

            # Skip cycling
            if "骑行" in name or "cycling" in name.lower() or "biking" in name.lower():
                continue

            label = TYPE_MAP[tid]
            is_valid, reason = _validate_api_pb(label, val)

            if val:
                time_str = _seconds_to_time_str(val)
                start_ms = item.get("activityStartDateTimeLocal")
                if start_ms:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(start_ms / 1000)
                    date_str = dt.strftime("%Y-%m-%d")
                else:
                    date_str = ""

                records.append({
                    "label": label,
                    "value": time_str,
                    "value_seconds": val,
                    "date": date_str,
                    "source": "api",
                    "validated": is_valid,
                    "validation_reason": reason,
                })
        return records

    # Dict format (International Garmin)
    if not isinstance(pb_data, dict):
        return []

    records = []
    key_map = [
        ("best5kRun", "5K PB", "min"),
        ("best10kRun", "10K PB", "min"),
        ("bestHalfMarathon", "半马 PB", "min"),
        ("bestMarathon", "全马 PB", "min"),
        ("longestRun", "最长跑 PB", "km"),
    ]

    for key, label, unit in key_map:
        entry = pb_data.get(key)
        if entry:
            if isinstance(entry, dict):
                val = entry.get("value") or entry.get("formattedValue")
                date = (entry.get("startDate") or "")[:10] if entry.get("startDate") else ""
            else:
                val = entry
                date = ""
            if val is not None:
                if unit == "min" and isinstance(val, (int, float)):
                    secs = val * 60
                    is_valid, reason = _validate_api_pb(label, secs)
                    minutes = int(secs // 60)
                    seconds = int(secs % 60)
                    if minutes >= 60:
                        display = f"{minutes // 60}:{minutes % 60:02d}:{seconds:02d}"
                    else:
                        display = f"{minutes}:{seconds:02d}"
                elif unit == "km" and isinstance(val, (int, float)):
                    display = f"{val/1000:.1f} km" if val > 100 else f"{val:.1f} km"
                    is_valid, reason = True, ""
                else:
                    display = str(val)
                    is_valid, reason = True, ""
                records.append({
                    "label": label,
                    "value": display,
                    "date": date,
                    "source": "api",
                    "validated": is_valid,
                    "validation_reason": reason,
                })

    return records


def extract_pb_from_activities(activities, activity_splits_map=None):
    """从历史活动记录中按距离分段提取个人最佳成绩 (PB)。

    数据来源优先级：
    1. 活动分段数据 (lap splits) 精确提取 - 适用于有明确终点标记的距离
    2. API prStartTimeGMT 精确时间 - 适用于半马/全马（typeId 5/6 可靠）
    3. 活动总时间 - 作为最终 fallback

    分组规则（基于活动距离 + 活动名关键词双重匹配）：
    - 5K：  距离 4.5km–5.6km，或活动名含 "5k"/"5km"/"5公里"
    - 10K： 距离 9.5km–11km，或活动名含 "10k"/"10km"/"10公里"
    - 半马：距离 20km–22.5km，或活动名含 "半马"/"half"/"21km"
    - 全马：距离 41km–43.5km，或活动名含 "全马"/"marathon"/"42km"

    对于5K/10K：从 lap splits 累计到精确距离标记（通过 lap 插值）
    对于半马/全马：直接使用 prStartTimeGMT 精确时间（来自 Garmin API PB 记录）

    返回格式：[{"label": "10K PB（分段）", "value": "45:03", "date": "2026-04-26"}, ...]
    """
    if not activities:
        return []

    if activity_splits_map is None:
        activity_splits_map = {}

    def _interp_at_target(splits, target_m):
        """Return interpolated time at exact target_meters from splits.

        Finds the lap that crosses target_m and interpolates within that lap
        for sub-meter precision. Returns (time_seconds, True) or (None, False).
        """
        cum_dist = 0
        cum_time = 0
        for lap in splits:
            lap_d = lap.get("distance", 0) or 0
            lap_t = lap.get("duration", 0) or 0
            if lap_d <= 0 or lap_t <= 0:
                continue
            prev_dist = cum_dist
            prev_time = cum_time
            cum_dist += lap_d
            cum_time += lap_t
            if prev_dist < target_m <= cum_dist:
                fraction = (target_m - prev_dist) / lap_d
                return prev_time + lap_t * fraction, True
        return None, False

    buckets = {
        "5K PB（分段）":   {"dist_lo": 4500,   "dist_hi": 5600,  "keywords": ["5k", "5km", "5公里"],     "use_splits": True,  "target": 5000,   "best": None},
        "10K PB（分段）":  {"dist_lo": 9500,   "dist_hi": 11000, "keywords": ["10k", "10km", "10公里"],   "use_splits": True,  "target": 10000,  "best": None},
        "半马 PB（分段）": {"dist_lo": 20000,  "dist_hi": 22500, "keywords": ["半马", "half", "21km", "21公里"], "use_splits": True, "target": 21097, "best": None},
        "全马 PB（分段）": {"dist_lo": 41000,  "dist_hi": 43500, "keywords": ["全马", "marathon", "42km", "42公里"], "use_splits": True, "target": 42195, "best": None},
    }

    for act in activities:
        dist_m = (act.get("distance", 0) or 0)
        dur_s  = (act.get("duration", 0) or 0)
        name   = (act.get("activityName", "") or "").lower()
        date   = (act.get("startTimeLocal", "") or "")[:10]
        act_id = act.get("activityId")

        if dist_m <= 0 or dur_s <= 0:
            continue

        for label, cfg in buckets.items():
            by_dist = cfg["dist_lo"] <= dist_m <= cfg["dist_hi"]
            by_name = any(kw in name for kw in cfg["keywords"])
            if not (by_dist or by_name):
                continue

            target = cfg["target"]
            use_splits = cfg["use_splits"]

            # Try splits-based precise extraction
            if use_splits and act_id and activity_splits_map:
                splits = activity_splits_map.get(act_id, [])
                if splits and len(splits) >= 1:
                    t_at_target, ok = _interp_at_target(splits, target)
                    if ok:
                        if cfg["best"] is None or t_at_target < cfg["best"]["dur_s"]:
                            cfg["best"] = {"dur_s": t_at_target, "dist_m": target, "date": date}
                        continue  # done with this activity for this bucket

            # Fallback: use activity total time (only if splits unavailable)
            if cfg["best"] is None or dur_s < cfg["best"]["dur_s"]:
                cfg["best"] = {"dur_s": dur_s, "dist_m": dist_m, "date": date}

        results = []
    for label, cfg in buckets.items():
        entry = cfg["best"]
        if entry is None:
            continue
        dur = entry["dur_s"]
        hours   = int(dur // 3600)
        minutes = int((dur % 3600) // 60)
        seconds = int(dur % 60)
        if hours > 0:
            display = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            display = f"{minutes}:{seconds:02d}"
        # Strip source suffix for consistent labeling with API data
        clean_label = label.replace("（分段）", "").replace("（活动）", "")
        results.append({"label": clean_label, "value": display, "date": entry["date"]})

    return results


# ---------------------------------------------------------------------------
# 1. Data Layer — 数据获取
# ---------------------------------------------------------------------------

def fetch_all_data(client, start_date, end_date, max_splits_activities=100):
    """Fetch all data needed for the report."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    data = {}
    
    # Activities (running only)
    print("📡 Fetching running activities...", file=sys.stderr)
    activities = client.get_activities_by_date(start_date, end_date)
    all_activities = list(activities) if activities else []
    data["activities"] = [a for a in all_activities if _is_running(a)]
    non_running = len(all_activities) - len(data["activities"])
    print(f"   -> {len(data['activities'])} running activities found ({non_running} non-running filtered out)", file=sys.stderr)
    
    # Race predictions
    print("📡 Fetching race predictions...", file=sys.stderr)
    try:
        data["race_predictions"] = client.get_race_predictions()
    except Exception as e:
        print(f"   ⚠️  Race predictions unavailable: {e}", file=sys.stderr)
        data["race_predictions"] = {}
    
    # Personal records
    print("📡 Fetching personal records...", file=sys.stderr)
    try:
        data["personal_record"] = client.get_personal_record()
    except Exception as e:
        print(f"   ⚠️  Personal records unavailable: {e}", file=sys.stderr)
        data["personal_record"] = {}
    
    # Training status (try today, fall back to previous days if null)
    print("📡 Fetching training status...", file=sys.stderr)
    data["training_status"] = {}
    for offset in range(7):  # try today, yesterday, ... up to 7 days ago
        try:
            probe_date = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
            ts = client.get_training_status(probe_date)
            if ts and ts.get("mostRecentVO2Max") is not None:
                data["training_status"] = ts
                if offset > 0:
                    print(f"   -> Found valid data from {probe_date} (offset={offset}d)", file=sys.stderr)
                break
        except Exception:
            continue
    
    # Training readiness
    print("📡 Fetching training readiness...", file=sys.stderr)
    try:
        data["training_readiness"] = client.get_training_readiness(today_str)
    except Exception as e:
        print(f"   ⚠️  Training readiness unavailable: {e}", file=sys.stderr)
        data["training_readiness"] = {}
    
    # 逐日健康数据 — 扩展 end_date 后多1天以覆盖睡眠数据
    # Garmin sleep date = 醒来日，训练日期 D 对应的睡眠应为 D+1
    print("📡 Fetching daily health data...", file=sys.stderr)
    daily = {}
    # 额外多取1天用于睡眠偏移（训练日 D 看 D+1 的睡眠）
    sleep_extended_end = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    dates = _date_range(sleep_extended_end, 15)  # 15天覆盖14天+1偏移
    for d in dates:
        day_data = {}
        try:
            day_data["summary"] = client.get_user_summary(d)
        except Exception:
            day_data["summary"] = {}
        try:
            day_data["sleep"] = client.get_sleep_data(d)
        except Exception:
            day_data["sleep"] = {}
        try:
            day_data["hrv"] = client.get_hrv_data(d)
        except Exception:
            day_data["hrv"] = {}
        try:
            day_data["body_battery"] = client.get_body_battery(d)
        except Exception:
            day_data["body_battery"] = {}
        try:
            day_data["heart_rates"] = client.get_heart_rates(d)
        except Exception:
            day_data["heart_rates"] = {}
        try:
            day_data["stress"] = client.get_stress_data(d)
        except Exception:
            day_data["stress"] = {}
        daily[d] = day_data
    data["daily"] = daily
    
    # 活动 Splits + Weather — 获取所有 >= 5km 的跑步活动
    # ⚠️ 注意：PB 分段插值依赖 splits 数据，必须覆盖所有关键比赛
    print("📡 Fetching activity splits and weather...", file=sys.stderr)
    splits_count = 0
    weather_count = 0
    for act in data["activities"]:
        # Remove the 20-activity cap; fetch all activities >= 5km
        if splits_count >= max_splits_activities:
            break
        act_id = act.get("activityId")
        if not act_id:
            continue
        sport_type = act.get("activityType", {}).get("typeKey", "") if isinstance(act.get("activityType"), dict) else ""
        if "running" not in sport_type.lower() and "running" not in act.get("activityName", "").lower():
            continue
        distance = (act.get("distance", 0) or 0)
        # Fetch splits for all >= 5km activities (not just >= 3km)
        # This is critical for accurate PB split interpolation
        if distance < 5000:
            continue
        
        # Splits
        try:
            splits = client.get_activity_splits(act_id)
            act["_splits"] = list(splits.get("lapDTOs", [])) if isinstance(splits, dict) else list(splits)
            splits_count += 1
        except Exception as e:
            act["_splits"] = []
            print(f"   ⚠️  Splits for activity {act_id}: {e}", file=sys.stderr)
        
        # Detail metrics (for recovery min HR in interval training)
        try:
            act["_details"] = client.get_activity_details(act_id)
        except Exception:
            act["_details"] = None
        
        # Weather — try Garmin API first, then Open-Meteo fallback
        try:
            weather = client.get_activity_weather(act_id)
            act["_weather"] = parse_activity_weather(weather)
            # If Garmin weather missing or invalid (temp <= 0°C = impossible for running), try fallback
            temp = act["_weather"].get("temperature")
            if temp is None or temp <= 0:
                lat = act.get("startLatitude")
                lon = act.get("startLongitude")
                start_time = act.get("startTimeLocal", "")[:10]  # YYYY-MM-DD
                if lat and lon and start_time:
                    fallback = fetch_weather_fallback(lat, lon, start_time)
                    if fallback and fallback.get("temperature") is not None and fallback["temperature"] > 0:
                        act["_weather"] = fallback
                        print(f"   🌤️ Weather fallback used for activity {act_id}", file=sys.stderr)
            if act["_weather"].get("temperature") is not None and act["_weather"]["temperature"] > 0:
                weather_count += 1
        except Exception as e:
            # Try fallback even on exception
            lat = act.get("startLatitude")
            lon = act.get("startLongitude")
            start_time = act.get("startTimeLocal", "")[:10]
            if lat and lon and start_time:
                fallback = fetch_weather_fallback(lat, lon, start_time)
                if fallback:
                    act["_weather"] = fallback
                    weather_count += 1
                    print(f"   🌤️ Weather fallback used for activity {act_id}", file=sys.stderr)
                    continue
            act["_weather"] = {}
            print(f"   ⚠️  Weather for activity {act_id}: {e}", file=sys.stderr)
    
    print(f"   -> Splits fetched for {splits_count} activities (>=5km), weather for {weather_count}", file=sys.stderr)
    
    return data


def _date_range(end_date_str, days):
    """Generate list of date strings going back from end_date."""
    end = datetime.strptime(end_date_str, "%Y-%m-%d") if isinstance(end_date_str, str) else end_date_str
    if isinstance(end_date_str, str):
        end = datetime.strptime(end_date_str, "%Y-%m-%d")
    else:
        end = end_date_str
    start = end - timedelta(days=days - 1)
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]


def get_date_range(days=None, start=None, end=None):
    """Calculate date range for queries."""
    if start and end:
        return start, end
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days or DEFAULT_DAYS)).strftime("%Y-%m-%d")
    return start_date, end_date


def get_pb_history_range():
    """Return date range for PB history extraction (longer period to cover all PB activities)."""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=PB_HISTORY_DAYS)).strftime("%Y-%m-%d")
    return start_date, end_date


# ---------------------------------------------------------------------------
# 2. Analysis Layer — 数据分析
# ---------------------------------------------------------------------------

def calc_pace(duration_s, distance_m):
    """Calculate pace string from duration (seconds) and distance (meters)."""
    if not distance_m or distance_m <= 0:
        return "--:--/km"
    pace_s_per_km = (duration_s or 0) / (distance_m / 1000)
    minutes = int(pace_s_per_km // 60)
    seconds = int(pace_s_per_km % 60)
    return f"{minutes}:{seconds:02d}/km"


def pace_to_seconds(pace_str):
    """Convert '4:30/km' or '4:30' to seconds per km."""
    try:
        parts = pace_str.replace("/km", "").split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def score_activity(activity, race_predictions):
    """
    Score a running activity based on pace vs predicted race pace and HR.
    Returns: "best", "good", "normal", "below"
    """
    distance = (activity.get("distance", 0) or 0)
    duration = (activity.get("duration", 0) or 0)  # 秒
    avg_hr = activity.get("averageHR", 0) or 0
    max_hr = activity.get("maxHR", 0) or 0
    
    if distance <= 0 or duration <= 0:
        return "normal"
    
    avg_pace_s = duration / (distance / 1000)
    
    # 参考配速：从比赛预测取对应距离的配速
    ref_pace = None
    dist_km = distance / 1000
    
    if dist_km >= 35:
        ref_key = "fm"
    elif dist_km >= 18:
        ref_key = "hm"
    elif dist_km >= 8:
        ref_key = "10k"
    else:
        ref_key = "5k"
    
    if race_predictions:
        pred_sec = race_predictions.get(ref_key)
        if pred_sec:
            ref_pace = pred_sec / _race_distance_km(ref_key)
    
    # 评分逻辑
    if ref_pace and ref_pace > 0:
        pace_ratio = avg_pace_s / ref_pace
        if pace_ratio <= 1.05:  # 比参考配速快5%以内
            return "best"
        elif pace_ratio <= 1.15:  # 比参考配速慢15%以内
            return "good"
        elif pace_ratio <= 1.30:
            return "normal"
        else:
            return "below"
    
    # 没有参考配速时，用绝对阈值
    if avg_pace_s <= 270:  # < 4:30/km
        return "best"
    elif avg_pace_s <= 300:  # < 5:00/km
        return "good"
    elif avg_pace_s <= 360:  # < 6:00/km
        return "normal"
    else:
        return "below"


def _race_distance_km(key):
    """Return race distance in km for prediction key."""
    return {"5k": 5.0, "10k": 10.0, "hm": 21.0975, "fm": 42.195}.get(key, 10.0)


def aggregate_weekly_mileage(activities):
    """Aggregate activities into rolling 7-day windows, last 4 windows.
    
    Windows are computed from yesterday, rolling backwards:
    - Window 1: yesterday-6d ~ yesterday
    - Window 2: yesterday-13d ~ yesterday-7d
    - Window 3: yesterday-20d ~ yesterday-14d
    - Window 4: yesterday-27d ~ yesterday-21d
    
    Returns: OrderedDict with keys like "2026-6-10~2026-6-16" (date range, no leading zeros)
             Keys are ordered oldest → newest (so table renders left→right as past→recent)
    """
    from datetime import timedelta
    from collections import OrderedDict
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    
    # Build 4 rolling 7-day windows: newest first
    windows = []  # list of (start_date, end_date)
    for i in range(4):
        end_date = yesterday - timedelta(days=i * 7)
        start_date = end_date - timedelta(days=6)
        windows.append((start_date, end_date))
    
    # windows list: [(w1_start,w1_end), (w2_start,w2_end), (w3_start,w3_end), (w4_start,w4_end)]
    # w1 = most recent, w4 = oldest
    # For display, we want oldest first (leftmost in table)
    windows.reverse()  # now w4, w3, w2, w1 order
    
    result = OrderedDict()
    
    for start_date, end_date in windows:
        # Format key: 2026-6-10~2026-6-16 (no leading zeros)
        start_str = f"{start_date.year}-{start_date.month}-{start_date.day}"
        end_str = f"{end_date.year}-{end_date.month}-{end_date.day}"
        key = f"{start_str}~{end_str}"
        
        result[key] = {"distance": 0.0, "count": 0, "activities": []}
    
    # Assign activities to windows
    for act in activities:
        start_time = act.get("startTimeLocal", "")
        if not start_time:
            continue
        try:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            try:
                dt = datetime.strptime(start_time[:10], "%Y-%m-%d")
            except (ValueError, IndexError):
                continue
        
        act_date = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Find which window this activity belongs to
        for start_date, end_date in windows:
            if start_date <= act_date <= end_date:
                start_str = f"{start_date.year}-{start_date.month}-{start_date.day}"
                end_str = f"{end_date.year}-{end_date.month}-{end_date.day}"
                key = f"{start_str}~{end_str}"
                dist = (act.get("distance", 0) or 0) / 1000  # convert to km
                result[key]["distance"] += dist
                result[key]["count"] += 1
                result[key]["activities"].append(act)
                break
    
    return result


def compute_dimension_scores(activities, race_predictions):
    """Compute 4-dimension scores: 跑量, 长距离, 配速, 训练频率."""
    scores = {}
    
    # 只考虑跑步活动
    run_acts = [a for a in activities if _is_running(a)]
    
    # 跑量评分 (weekly avg vs 70km target)
    weekly = aggregate_weekly_mileage(run_acts)
    avg_weekly = sum(w["distance"] for w in weekly.values()) / max(len(weekly), 1)
    if avg_weekly >= 80:
        scores["跑量"] = 5
    elif avg_weekly >= 60:
        scores["跑量"] = 4
    elif avg_weekly >= 40:
        scores["跑量"] = 3
    elif avg_weekly >= 20:
        scores["跑量"] = 2
    else:
        scores["跑量"] = 1
    
    # 长距离评分 (>= 20km 活动次数)
    long_runs = [a for a in run_acts if (a.get("distance", 0) or 0) >= 20000]
    if len(long_runs) >= 4:
        scores["长距离"] = 5
    elif len(long_runs) >= 3:
        scores["长距离"] = 4
    elif len(long_runs) >= 2:
        scores["长距离"] = 3
    elif len(long_runs) >= 1:
        scores["长距离"] = 2
    else:
        scores["长距离"] = 1
    
    # 配速评分 (参考比赛预测)
    if race_predictions:
        pace_score = 3  # 默认
        best_act = min(run_acts, key=lambda a: _pace_seconds(a)) if run_acts else None
        if best_act:
            best_pace = _pace_seconds(best_act)
            if best_pace and best_pace <= 270:  # 4:30
                pace_score = 5
            elif best_pace and best_pace <= 300:  # 5:00
                pace_score = 4
            elif best_pace and best_pace <= 360:
                pace_score = 3
            else:
                pace_score = 2
        scores["配速"] = pace_score
    else:
        scores["配速"] = 3
    
    # 训练频率 (每周训练天数)
    weekly_days = defaultdict(set)
    for a in run_acts:
        start_time = a.get("startTimeLocal", "")
        if start_time:
            try:
                dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                iso_year, iso_week, _ = dt.isocalendar()
                week_key = f"{iso_year}-W{iso_week:02d}"
                weekly_days[week_key].add(dt.strftime("%Y-%m-%d"))
            except (ValueError, AttributeError):
                pass
    
    avg_days = sum(len(days) for days in weekly_days.values()) / max(len(weekly_days), 1)
    if avg_days >= 5:
        scores["训练频率"] = 5
    elif avg_days >= 4:
        scores["训练频率"] = 4
    elif avg_days >= 3:
        scores["训练频率"] = 3
    elif avg_days >= 2:
        scores["训练频率"] = 2
    else:
        scores["训练频率"] = 1
    
    return scores


def _is_running(activity):
    """Check if activity is a running activity."""
    sport_type = activity.get("activityType", {})
    if isinstance(sport_type, dict):
        type_key = sport_type.get("typeKey", "")
        if "running" in type_key.lower():
            return True
    name = activity.get("activityName", "") or ""
    return "running" in name.lower()


def _pace_seconds(activity):
    """Get pace in seconds per km for an activity."""
    distance = (activity.get("distance", 0) or 0)
    duration = (activity.get("duration", 0) or 0)
    if distance <= 0:
        return None
    return duration / (distance / 1000)


def get_best_splits(splits):
    """Find the best lap split (lowest pace) from splits data."""
    if not splits:
        return None
    best = None
    best_pace = float("inf")
    for lap in splits:
        dist = (lap.get("distance", 0) or 0)
        dur = (lap.get("duration", 0) or 0)
        if dist <= 0:
            continue
        pace = dur / (dist / 1000)
        if pace < best_pace:
            best_pace = pace
            best = lap
    return best


def analyze_splits_heuristic(splits):
    """Analyze split/lap pattern to determine the type of lap data.

    Supports fast/slow paced-based alternation (pace_based interval),
    multiple interval distances (200m, 400m, 800m, 1km),
    auto 1km lap, suspect oversized-lap, and native lap detection.

    Returns a dict describing the detected pattern:
    - "interval" (pace_based=True): alternating fast↔slow pace pattern
    - "interval" (pace_based=False/absent): short fast laps (auto-detected for 200m/400m/800m/1km)
    - "auto_lap_1km": automatic 1km lap splits
    - "suspect": suspicious pattern (one giant lap covering >50% of distance)
    - "native": normal watch-native lap splits
    - "none": no lap data available
    """
    if not splits:
        return {"pattern": "none"}

    lap_distances_km = []
    for lap in splits:
        d = (lap.get("distance", 0) or 0) / 1000
        if d > 0:
            lap_distances_km.append(d)

    if not lap_distances_km:
        return {"pattern": "none"}

    total_dist = sum(lap_distances_km)
    num_laps = len(lap_distances_km)

    # --- Heuristic 1: Oversized single lap (suspect) ---
    oversized = [d for d in lap_distances_km if d > total_dist * 0.50]
    if oversized:
        ratio = oversized[0] / total_dist * 100
        return {
            "pattern": "suspect",
            "reason": f"存在异常大圈({oversized[0]:.1f}km, 占总距离{ratio:.0f}%)",
            "recommendation": "建议使用每1km自动计圈替代，当前手表计圈粒度太粗"
        }

    # --- Heuristic 2: Auto 1km lap (check BEFORE interval to avoid false positives) ---
    near_1km = [d for d in lap_distances_km if 0.95 <= d <= 1.05]
    if len(near_1km) >= num_laps * 0.6:
        return {
            "pattern": "auto_lap_1km",
            "detail": f"{len(near_1km)}/{num_laps}圈为1km自动计圈",
            "near_1km_count": len(near_1km),
            "total_laps": num_laps
        }

    # --- Heuristic 3: Pace-based interval (alternating fast/slow pattern) ---
    # Detects intervals by analyzing pace alternation, regardless of exact lap distances.
    # This catches irregular interval distances (e.g., 320m reps, 450m recoveries).
    laps_with_pace = []
    for lap in splits:
        d = (lap.get("distance", 0) or 0)
        t = (lap.get("duration", 0) or 0)
        if d > 0 and t > 0:
            laps_with_pace.append({
                "distance_km": d / 1000,
                "pace_s_per_km": t / (d / 1000),
                "duration": t
            })

    if len(laps_with_pace) >= 6:
        paces = [lp["pace_s_per_km"] for lp in laps_with_pace]
        sorted_paces = sorted(paces)
        median_pace = sorted_paces[len(sorted_paces) // 2]

        # Classify: fast < median * 0.88 (12%+ faster than median)
        #          slow > median * 1.08 (8%+ slower than median)
        #          medium = in between (excluded from alternation counting)
        classifications = []
        for lp in laps_with_pace:
            p = lp["pace_s_per_km"]
            if p <= median_pace * 0.88:
                classifications.append("fast")
            elif p >= median_pace * 1.08:
                classifications.append("slow")
            else:
                classifications.append("medium")

        # Count transitions between fast and slow (skip medium segments)
        transitions = 0
        prev = None
        for c in classifications:
            if c in ("fast", "slow"):
                if prev is not None and c != prev:
                    transitions += 1
                prev = c

        fast_count = classifications.count("fast")
        slow_count = classifications.count("slow")

        # Require: ≥3 transitions, at least 3 fast and 3 slow laps
        if transitions >= 3 and fast_count >= 3 and slow_count >= 3:
            avg_fast_pace = sum(
                laps_with_pace[i]["pace_s_per_km"]
                for i, c in enumerate(classifications) if c == "fast"
            ) / fast_count
            avg_slow_pace = sum(
                laps_with_pace[i]["pace_s_per_km"]
                for i, c in enumerate(classifications) if c == "slow"
            ) / slow_count

            def _pace_str(secs):
                m = int(secs // 60)
                s = int(secs % 60)
                return f"{m}:{s:02d}"

            return {
                "pattern": "interval",
                "interval_type": "配速交替",
                "pace_based": True,
                "detail": (f"配速交替模式：{fast_count}快段({_pace_str(avg_fast_pace)}/km)"
                           f" + {slow_count}恢复段({_pace_str(avg_slow_pace)}/km)"
                           f"，{transitions}次交替"),
                "short_laps": fast_count,
                "medium_laps": slow_count,
                "total_laps": num_laps
            }

    # --- Heuristic 4: Interval training (distance-based, multi-distance) ---
    # Requires both short fast laps AND recovery/medium segments
    interval_ranges = [
        ("200m", 0.18, 0.23),
        ("400m", 0.38, 0.43),
        ("600m", 0.58, 0.63),
        ("800m", 0.78, 0.83),
        ("1km", 0.98, 1.03),
    ]

    best_interval = None
    best_short_count = 0
    interval_matches = {}

    for label, lo, hi in interval_ranges:
        short_laps = [d for d in lap_distances_km if lo <= d <= hi]
        # Medium-to-long laps = everything longer than hi (recovery segments)
        medium_laps = [d for d in lap_distances_km if d > hi]
        count = len(short_laps)
        interval_matches[label] = {"count": count, "medium": len(medium_laps)}
        if count >= 3 and count > best_short_count:
            # Require at least some medium/recovery laps (guards against all-short patterns)
            if len(medium_laps) > 0 and count >= len(medium_laps) * 0.4:
                best_interval = label
                best_short_count = count

    if best_interval:
        info = interval_matches[best_interval]
        return {
            "pattern": "interval",
            "interval_type": best_interval,
            "detail": f"检测到{info['count']}个{best_interval}间歇段，"
                      f"{info['medium']}个恢复段",
            "short_laps": info['count'],
            "medium_laps": info['medium'],
            "total_laps": num_laps
        }

    # --- Heuristic 5: Native lap ---
    return {
        "pattern": "native",
        "detail": f"手表原生计圈，{num_laps}圈，距离范围 {min(lap_distances_km):.2f}-{max(lap_distances_km):.2f}km",
        "total_laps": num_laps
    }


def render_splits_table(splits, detail_metrics=None, metric_descriptors=None):
    """Render the splits/lap data as an HTML table with heuristic analysis.

    Args:
        splits: List of lap dicts from get_activity_splits
        detail_metrics: Optional list of metrics points from get_activity_details
        metric_descriptors: Optional list of metric descriptors (for column mapping)
    """
    if not splits:
        return "", "", ""

    # Heuristic analysis
    heuristic = analyze_splits_heuristic(splits)

    # === Recovery min HR (last 5 seconds) for interval training ===
    recovery_html_segments = []
    if heuristic["pattern"] == "interval" and detail_metrics and metric_descriptors:
        # Build column map
        col_map = {}
        for d in metric_descriptors:
            col_map[d['key']] = d['metricsIndex']
        hr_col = col_map.get('directHeartRate')
        elapsed_col = col_map.get('sumElapsedDuration')  # seconds
        
        if hr_col is not None and elapsed_col is not None:
            # Build HR timeline: [elapsed_seconds, hr]
            timeline = []
            for pt in detail_metrics:
                m = pt.get("metrics", [])
                if not m or len(m) <= max(hr_col, elapsed_col):
                    continue
                e = m[elapsed_col]
                h = m[hr_col]
                if e is not None and h is not None and h > 0:
                    timeline.append({'elapsed': e, 'hr': int(round(h))})
            
            if timeline:
                # Lap boundaries (cumulative duration)
                cumul = 0.0
                lap_ranges = []
                for lap in splits:
                    dur = lap.get("duration", 0) or 0
                    start = cumul
                    cumul += dur
                    lap_ranges.append({
                        'start': start, 'end': cumul,
                        'type': lap.get("intensityType","?"),
                        'dist': lap.get("distance",0) or 0
                    })
                
                # Recovery analysis: track interval max HRs, compute last-5s for recovery
                interval_maxes = []
                recovery_segments = []
                
                for i, lr in enumerate(lap_ranges):
                    hrs = [t['hr'] for t in timeline if lr['start'] <= t['elapsed'] <= lr['end']]
                    if not hrs:
                        continue
                    
                    intensity = lr.get("type", "?")
                    
                    if intensity == "ACTIVE":
                        interval_maxes.append(max(hrs))
                    
                    elif intensity == "RECOVERY" and interval_maxes:
                        # Only short recovery segments (≤300m) qualify for interval recovery assessment
                        # Longer segments are cool-down, not interval recovery jogs
                        if lr['dist'] > 300:
                            continue
                        prev_max = interval_maxes[-1]
                        # Last 5 seconds of recovery
                        end_time = lr['end']
                        last_5s = [t['hr'] for t in timeline 
                                   if t['elapsed'] >= end_time - 5 and t['elapsed'] <= end_time]
                        recovery_hr = sum(last_5s)/len(last_5s) if last_5s else hrs[-1]
                        if len(last_5s) >= 2:
                            avg_recovery_hr = sum(last_5s) / len(last_5s)
                        else:
                            avg_recovery_hr = hrs[-1]
                        recovery_hr = round(avg_recovery_hr)
                        drop = round(prev_max - recovery_hr)
                        
                        # Get pace from the original split data
                        orig_lap = splits[i] if i < len(splits) else {}
                        speed = orig_lap.get("averageSpeed", 0) or 0
                        pace = 1000 / speed / 60 if speed > 0 else 0
                        pace_str = f"{int(pace)}:{int((pace-int(pace))*60):02d}/km" if pace > 0 else "N/A"
                        
                        if drop >= 30: eval_s = "✅ 充分恢复"
                        elif drop >= 20: eval_s = "🟡 恢复好"
                        elif drop >= 12: eval_s = "⚪ 一般"
                        else: eval_s = "⚠️ 恢复不足"
                        
                        recovery_segments.append({
                            'interval_num': len(interval_maxes),
                            'pace': pace_str,
                            'interval_max': prev_max,
                            'recovery_hr': recovery_hr,
                            'drop': drop,
                            'eval': eval_s
                        })
                
                if recovery_segments:
                    tbl = '<div style="margin-top:10px;">'
                    tbl += '<div style="font-size:13px;font-weight:bold;color:#0f3460;margin-bottom:6px;">📉 恢复段心率下降评估</div>'
                    tbl += '<table class="splits-table" style="font-size:12px;">'
                    tbl += '<tr><th>间歇序</th><th>恢复配速</th><th>间歇最高</th><th>恢复最低</th><th>降幅</th><th>评估</th></tr>'
                    for r in recovery_segments:
                        tbl += f'<tr><td>{r["interval_num"]}</td><td>{r["pace"]}</td>'
                        tbl += f'<td>{r["interval_max"]}</td><td>{r["recovery_hr"]}</td>'
                        tbl += f'<td>{r["drop"]}</td><td>{r["eval"]}</td></tr>'
                    tbl += '</table></div>'
                    recovery_html_segments.append(tbl)

    # Heuristic analysis
    heuristic = analyze_splits_heuristic(splits)

    # Generate heuristic notice
    pattern_labels = {
        "interval": "🏃 间歇训练模式",
        "auto_lap_1km": "📏 1km 自动计圈",
        "suspect": "⚠️ 异常计圈",
        "native": "⌚ 手表原生计圈",
        "none": ""
    }
    heuristic_notice = ""
    if heuristic["pattern"] != "none":
        label = pattern_labels.get(heuristic["pattern"], "")
        detail = heuristic.get("detail", heuristic.get("reason", ""))
        if heuristic["pattern"] == "suspect":
            rec = heuristic.get("recommendation", "")
            heuristic_notice = (
                f'<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;'
                f'padding:6px 10px;margin:6px 0;font-size:13px;">'
                f'<strong>{label}</strong>：{detail}<br>'
                f'<span style="color:#856404;">💡 {rec}</span></div>'
            )
        elif heuristic["pattern"] == "interval":
            interval_label = heuristic.get("interval_type", "间歇")
            pace_based = heuristic.get("pace_based", False)

            if not pace_based:
                # Distance-based: count fast vs recovery segments
                lo_map = {"200m": 0.18, "400m": 0.38, "600m": 0.58, "800m": 0.78, "1km": 0.98}
                hi_map = {"200m": 0.23, "400m": 0.43, "600m": 0.63, "800m": 0.83, "1km": 1.03}
                i_lo = lo_map.get(interval_label, 0.18)
                i_hi = hi_map.get(interval_label, 0.23)
                fast_laps = [lap for lap in splits
                             if i_lo <= ((lap.get("distance", 0) or 0)/1000) <= i_hi]
                if fast_laps:
                    paces = []
                    for lap in fast_laps:
                        d = (lap.get("distance", 0) or 0)
                        t = (lap.get("duration", 0) or 0)
                        if d > 0:
                            paces.append(calc_pace(t, d))
                    if paces:
                        fastest = min(paces, key=lambda p: pace_to_seconds(p) if pace_to_seconds(p) else float('inf'))
                        # fastest pace stored in variable for reference
                        _ = f"最快间歇 {fastest}"

            heuristic_notice = (
                f'<div style="background:#e8f5e9;border:1px solid #4caf50;border-radius:4px;'
                f'padding:6px 10px;margin:6px 0;font-size:13px;">'
                f'<strong>🏃 {interval_label}间歇训练</strong>：{heuristic["detail"]}'
                f'</div>'
            )

    # Render table
    best_pace_val = float("inf")
    best_idx = -1
    for i, lap in enumerate(splits):
        lap_dist = (lap.get("distance", 0) or 0)
        lap_dur = (lap.get("duration", 0) or 0)
        if lap_dist <= 0:
            continue
        lap_pace = lap_dur / (lap_dist / 1000)
        if lap_pace < best_pace_val:
            best_pace_val = lap_pace
            best_idx = i

    html = '<table class="splits-table">\n<tr><th>分段</th><th>距离</th><th>配速</th><th>心率</th><th>步频</th><th>步幅</th><th>海拔</th></tr>\n'
    for i, lap in enumerate(splits):
        lap_dist = (lap.get("distance", 0) or 0)
        lap_dur = (lap.get("duration", 0) or 0)
        if lap_dist <= 0:
            continue
        lap_pace = calc_pace(lap_dur, lap_dist)
        lap_hr = lap.get("averageHR", "--") or "--"
        lap_cad = lap.get("averageRunCadence", "--") or "--"
        if isinstance(lap_cad, (int, float)) and lap_cad != "--":
            lap_cad = f"{lap_cad:.0f}"
        lap_stride = lap.get("strideLength", "--") or "--"
        if isinstance(lap_stride, (int, float)) and lap_stride != "--":
            lap_stride_m = lap_stride / 100.0
            lap_stride = f"{lap_stride_m:.2f}"
        lap_elev = lap.get("elevationGain", 0) or 0
        row_class = ' class="best-lap"' if i == best_idx else ""
        html += f'<tr{row_class}><td>{i+1}</td><td>{lap_dist/1000:.3f} km</td><td>{lap_pace}</td><td>{lap_hr} bpm</td><td>{lap_cad}</td><td>{lap_stride} m</td><td>+{lap_elev:.0f}m</td></tr>\n'
    html += '</table>\n'

    # Append recovery min HR segments if any
    for rec_html in recovery_html_segments:
        html += rec_html

    return html, heuristic_notice, recovery_html_segments


# ---------------------------------------------------------------------------
# 3. Render Layer — HTML 渲染
# ---------------------------------------------------------------------------

def render_report(data, start_date, end_date):
    """Render the full HTML report with new 5-section structure."""
    activities = data.get("activities", [])
    race_preds = data.get("race_predictions", {})
    personal_records = data.get("personal_record", {})
    training_status = data.get("training_status", {})
    training_readiness = data.get("training_readiness", {})
    daily = data.get("daily", {})

    # Extract user info
    vo2max = _get_vo2max(training_status)

    # Race predictions format
    race_texts = _format_race_predictions(race_preds)

    # Filter running activities
    run_activities = [a for a in activities if _is_running(a)]
    total_distance_km = sum((a.get("distance", 0) or 0) for a in run_activities) / 1000
    total_runs = len(run_activities)

    # Build activity splits map for PB extraction
    activity_splits_map = {}
    for act in run_activities:
        act_id = act.get("activityId")
        if act_id:
            splits = act.get("_splits", [])
            if splits:
                activity_splits_map[act_id] = splits
    
    # PB from activities (fallback/fix source - used when API PB is invalid)
    pb_from_acts = extract_pb_from_activities(run_activities, activity_splits_map)
    
    # Personal records from Garmin API (primary source, with validation)
    pb_from_api = extract_personal_records(personal_records)
    
    # Build splits-based PB lookup by label (for fallback)
    splits_pb_by_label = {}
    for pb in pb_from_acts:
        label = pb["label"]
        if label not in splits_pb_by_label:
            splits_pb_by_label[label] = pb
    
    # Merge strategy:
    # 1. Start with API PBs (now TYPE_MAP is correct for China Garmin)
    # 2. For each PB type, validate and fall back to splits if invalid
    # 3. 半马/全马: always prefer API (empirically reliable)
    # 4. 1KM/1英里/5K/10K: validate API, use splits as fallback
    pb_list_merged = []
    
    # Process all API PBs
    for pb_api in pb_from_api:
        label = pb_api["label"]
        is_valid = pb_api.get("validated", True)
        
        if label in ("半马 PB", "全马 PB"):
            # Always trust API for half/full marathon
            pb_api["fix_source"] = "api"
            pb_list_merged.append(pb_api)
        elif is_valid:
            # Valid API PB - use it
            pb_api["fix_source"] = "api"
            pb_list_merged.append(pb_api)
        else:
            # Invalid API PB - try splits fallback
            splits_pb = splits_pb_by_label.get(label)
            if splits_pb:
                splits_pb["fix_source"] = "splits"
                splits_pb["api_original"] = pb_api.get("value")
                splits_pb["api_reason"] = pb_api.get("validation_reason", "")
                pb_list_merged.append(splits_pb)
            else:
                # No splits available - keep API with warning
                pb_api["fix_source"] = "api-warn"
                pb_list_merged.append(pb_api)
    
    # Add any splits-based PB that API doesn't have
    api_labels = {pb["label"] for pb in pb_from_api}
    for label, pb_splits in splits_pb_by_label.items():
        if label not in api_labels:
            pb_splits["fix_source"] = "splits-only"
            pb_list_merged.append(pb_splits)

    # Last 7 days stats
    last_7_days = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    last_7_runs = [a for a in run_activities if (a.get("startTimeLocal", "") or "")[:10] >= last_7_days]
    week7_distance = sum((a.get("distance", 0) or 0) for a in last_7_runs) / 1000

    # Health data (last 7 days average)
    health = _summarize_health(daily)

    # Training readiness
    readiness_score = _get_readiness(training_readiness)

    # Scored activities for display
    scored_activities = _get_scored_activities(run_activities, race_preds)

    # Weekly mileage
    weekly = aggregate_weekly_mileage(run_activities)

    # 4-dimension scores
    dim_scores = compute_dimension_scores(run_activities, race_preds)

    today = datetime.now().strftime("%Y-%m-%d")

    # Helper: get training date from activity
    def _act_date(act):
        return (act.get("startTimeLocal", "") or "")[:10]

    # Helper: get sleep for a training day (sleep date = training date + 1)
    def _sleep_for_training(training_date_str):
        """Garmin sleep date = wake-up day. Training on day D → look at sleep data for D+1."""
        if not training_date_str:
            return {}
        try:
            dt = datetime.strptime(training_date_str, "%Y-%m-%d")
            sleep_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
            return daily.get(sleep_date, {}).get("sleep", {}) or {}
        except ValueError:
            return {}

    # Helper: get sleep details from sleep data
    def _extract_sleep_detail(sleep_data):
        """Extract sleep hours, score, and sleep stages from sleep data.
        
        Returns: (hours_str, score, deep_s, rem_s, light_s, awake_s, quality_text)
        """
        if not isinstance(sleep_data, dict):
            return "--", "--", 0, 0, 0, 0, ""
        
        dto = sleep_data.get("dailySleepDTO", {})
        if not isinstance(dto, dict):
            return "--", "--", 0, 0, 0, 0, ""
        
        # Sleep duration
        sleep_dur = dto.get("sleepTimeSeconds") or dto.get("sleepTime", 0) or 0
        hours = f"{sleep_dur/3600:.1f}h" if sleep_dur else "--"
        
        # Sleep score
        score = dto.get("sleepScore") or "--"
        scores = dto.get("sleepScores", {})
        if isinstance(scores, dict):
            overall = scores.get("overall", {})
            if isinstance(overall, dict):
                score = overall.get("value") or score
        
        # Sleep stages (in seconds)
        deep_s = dto.get("deepSleepSeconds") or dto.get("deepSleepDuration", 0) or 0
        rem_s = dto.get("remSleepSeconds") or dto.get("remSleepDuration", 0) or 0
        light_s = dto.get("lightSleepSeconds") or dto.get("lightSleepDuration", 0) or 0
        awake_s = dto.get("awakeSleepSeconds") or dto.get("awakeDuration", 0) or 0
        
        # Calculate percentages
        total_sleep = deep_s + rem_s + light_s
        if total_sleep > 0:
            deep_pct = deep_s / total_sleep * 100
            rem_pct = rem_s / total_sleep * 100
            light_pct = light_s / total_sleep * 100
        else:
            deep_pct = rem_pct = light_pct = 0
        
        # Quality text
        quality_parts = []
        if deep_s > 0:
            quality_parts.append(f"深睡 {deep_s/60:.0f}min ({deep_pct:.0f}%)")
        if rem_s > 0:
            quality_parts.append(f"REM {rem_s/60:.0f}min ({rem_pct:.0f}%)")
        if light_s > 0:
            quality_parts.append(f"浅睡 {light_s/60:.0f}min ({light_pct:.0f}%)")
        if awake_s > 0:
            quality_parts.append(f"清醒 {awake_s/60:.0f}min")
        
        quality_text = " | ".join(quality_parts) if quality_parts else ""
        
        return hours, score, deep_s, rem_s, light_s, awake_s, quality_text

    # Helper: get body battery max for a date
    def _extract_bb_max(date_str):
        bb = daily.get(date_str, {}).get("body_battery", []) or []
        if isinstance(bb, list):
            vals = []
            for item in bb:
                if isinstance(item, dict):
                    ch = item.get("charged")
                    if ch and isinstance(ch, (int, float)):
                        vals.append(ch)
                    arr = item.get("bodyBatteryValuesArray", [])
                    if isinstance(arr, list):
                        for pair in arr:
                            if isinstance(pair, (list, tuple)) and len(pair) >= 2 and pair[1] is not None:
                                vals.append(pair[1])
            return max(vals) if vals else "--"
        return "--"

    # Helper: get HRV for a date
    def _extract_hrv(date_str):
        hrv = daily.get(date_str, {}).get("hrv", {}) or {}
        if isinstance(hrv, dict):
            summary = hrv.get("hrvSummary", {})
            if isinstance(summary, dict):
                return summary.get("weeklyAvg") or summary.get("lastNightAvg") or "--"
        return "--"

    # Helper: get summary resting HR for a date
    def _extract_rhr(date_str):
        summary = daily.get(date_str, {}).get("summary", {}) or {}
        if isinstance(summary, dict):
            return summary.get("restingHeartRate") or "--"
        return "--"

    # Helper: DI display HTML
    def _di_html(di_val):
        if di_val is None:
            return '<span class="di-none">--</span>'
        cls = di_color_class(di_val)
        return f'<span class="{cls}">{di_val}</span>'

    # Helper: weather display
    def _weather_badge(act):
        w = act.get("_weather", {})
        if not w or w.get("temperature") is None:
            return '<span style="color:#999;">🌡️ 无天气数据</span>'
        t = w["temperature"]
        rh = w.get("humidity", "--")
        di = w.get("di")
        cond = w.get("condition", "")
        di_h = _di_html(di)
        level = di_level(di) if di is not None else ""
        cond_str = f" {cond}" if cond else ""
        return (f'<span>🌡️ {t}°C / 💧 {rh}%{cond_str} | '
                f'DI={di_h} <small style="color:#888;">({level})</small></span>')

    # Helper: pace impact text
    def _di_impact_text(act):
        w = act.get("_weather", {})
        di = w.get("di")
        if di is None:
            return ""
        _, desc = di_pace_impact(di)
        return f'<small style="color:#666;">{desc}</small>'

    # Helper: grade activity quality
    def _grade_activity(act):
        score = score_activity(act, race_preds)
        tags = {"best": '<span class="tag-best">最佳</span>',
                "good": '<span class="tag-good">好</span>',
                "normal": '<span class="tag-normal">一般</span>',
                "below": '<span class="tag-below">需改善</span>'}
        return tags.get(score, "")

    # -----------------------------------------------------------------------
    # HTML start
    # -----------------------------------------------------------------------
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>佳明综合训练分析报告 {today}</title>
<style>
body {{ font-family: -apple-system, 'Segoe UI', 'Noto Sans SC', sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; line-height: 1.7; }}
h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
h2 {{ color: #16213e; margin-top: 30px; border-left: 4px solid #0f3460; padding-left: 12px; }}
h3 {{ color: #0f3460; margin-top: 24px; font-size: 16px; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 14px; }}
th {{ background: #0f3460; color: white; padding: 10px 12px; text-align: left; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #dee2e6; }}
tr:nth-child(even) {{ background: #f1f3f5; }}
blockquote {{ border-left: 4px solid #e94560; background: #fff5f5; margin: 16px 0; padding: 12px 16px; }}
.star {{ color: #f0c040; }}
.star-dim {{ color: #ccc; }}
.footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #dee2e6; font-size: 13px; color: #666; }}
.tag-best {{ display: inline-block; background: #28a745; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
.tag-good {{ display: inline-block; background: #17a2b8; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
.tag-normal {{ display: inline-block; background: #6c757d; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
.tag-below {{ display: inline-block; background: #dc3545; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
.workout-card {{ background: white; border-radius: 8px; padding: 16px 20px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.workout-card h4 {{ margin-top: 0; color: #0f3460; }}
.workout-card .meta {{ font-size: 13px; color: #666; margin-bottom: 8px; }}
.stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.stats-item {{ display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px dashed #eee; }}
.stats-label {{ color: #666; }}
.stats-value {{ font-weight: bold; }}
.splits-table {{ margin-top: 8px; font-size: 13px; }}
.splits-table th {{ font-size: 12px; padding: 4px 8px; }}
.splits-table td {{ padding: 3px 8px; font-size: 12px; }}
.splits-table .best-lap {{ background: #d4edda; font-weight: bold; }}
.di-green {{ color: #28a745; font-weight: bold; }}
.di-yellow {{ color: #cc7a00; font-weight: bold; }}
.di-orange {{ color: #e67e22; font-weight: bold; }}
.di-red {{ color: #dc3545; font-weight: bold; }}
.di-none {{ color: #999; }}
.di-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
.pb-star {{ color: #f0c040; font-size: 16px; }}
.summary-box {{ background: white; border-radius: 8px; padding: 12px 16px; margin: 8px 0; border-left: 4px solid #0f3460; font-size: 14px; }}
.suggestion-list {{ list-style: none; padding-left: 0; }}
.suggestion-list li {{ padding: 6px 0; border-bottom: 1px dashed #eee; }}
.suggestion-list li::before {{ content: "💡 "; }}
.plan-list {{ list-style: none; padding-left: 0; }}
.plan-list li {{ padding: 6px 0; border-bottom: 1px dashed #eee; }}
.plan-list li::before {{ content: "📋 "; }}
.di-bar {{ height: 16px; border-radius: 3px; margin: 2px 0; }}
</style>
</head>
<body>

<h1>🏃 佳明综合训练分析报告</h1>
<p style="color: #666;">数据周期：{start_date} 至 {end_date} | 生成日期：{today}</p>
<p style="color: #666;">数据来源：Garmin Connect</p>

<!-- ================================================================== -->
<!-- 用户基础信息（置顶） -->
<!-- ================================================================== -->
<h2>用户基础信息</h2>
<table>
<tr><th>类别</th><th>参数</th><th>当前值</th><th>说明</th></tr>
<tr><td>体能</td><td>VO₂max</td><td><strong>{vo2max} ml/kg/min</strong></td><td>Garmin 估算</td></tr>
"""

    # 比赛预测 — raw API keys: time5K, time10K, timeHalfMarathon, timeMarathon
    pred_entries = [
        ("time5K", "5K 预测"),
        ("time10K", "10K 预测"),
        ("timeHalfMarathon", "半马预测"),
        ("timeMarathon", "全马预测"),
    ]
    added_preds = {}  # Track which predictions we've added
    for fallback in [False, True]:
        for raw_key, label in pred_entries:
            if added_preds.get(label):
                continue  # Already added
            if fallback:
                # Map to older format
                fb_map = {"time5K": "5k", "time10K": "10k", "timeHalfMarathon": "hm", "timeMarathon": "fm"}
                raw_key = fb_map.get(raw_key, raw_key)
            val = race_preds.get(raw_key) if isinstance(race_preds, dict) else None
            if isinstance(val, (int, float)) and val > 0:
                time_str = _seconds_to_time_str(val)
                if time_str:
                    html += f'<tr><td>预估</td><td>{label}</td><td><strong>{time_str}</strong></td><td>Garmin 预测</td></tr>\n'
                    added_preds[label] = True

    # 训练目标（半马 / 全马）— 优先级：Garmin 预测 → Garmin API PB → 历史活动 PB → "--"
    def _find_pb(pb_search_list, *keywords):
        """Find first PB matching any of the given keywords."""
        for pb in pb_search_list:
            if any(kw in pb.get("label", "") for kw in keywords):
                return pb["value"]
        return None

    hm_target = None
    fm_target = None
    # Race predictions (highest priority)
    for raw_key in ["timeHalfMarathon", "hm", "timeHalfMarathon", "halfMarathon"]:
        v = race_preds.get(raw_key) if isinstance(race_preds, dict) else None
        if isinstance(v, (int, float)) and v > 0:
            hm_target = _seconds_to_time_str(v)
            break
    for raw_key in ["timeMarathon", "fm", "timeMarathon", "marathon"]:
        v = race_preds.get(raw_key) if isinstance(race_preds, dict) else None
        if isinstance(v, (int, float)) and v > 0:
            fm_target = _seconds_to_time_str(v)
            break
    # Fallback: merged PB list (Garmin API PB first, then activity PB)
    if not hm_target:
        pb_hm = _find_pb(pb_list_merged, "半马")
        if pb_hm:
            hm_target = pb_hm
    if not fm_target:
        pb_fm = _find_pb(pb_list_merged, "全马")
        if pb_fm:
            fm_target = pb_fm
    # If still nothing, show "--"
    if not hm_target:
        hm_target = "--"
    if not fm_target:
        fm_target = "--"

    html += (f'<tr><td>🎯 目标</td><td>半马目标</td><td><strong>{hm_target}</strong></td>'
             f'<td>训练参考目标</td></tr>\n')
    html += (f'<tr><td>🎯 目标</td><td>全马目标</td><td><strong>{fm_target}</strong></td>'
             f'<td>训练参考目标</td></tr>\n')

    # 个人最佳 (PB) — 合并展示 Garmin API PB + 历史活动 PB
    for pb in pb_list_merged:
        date_str = f" ({pb['date']})" if pb.get("date") else ""
        fix_src = pb.get("fix_source", "api")
        
        # Badge logic
        if fix_src == "splits":
            reason = pb.get("api_reason", "")
            src_badge = ' <small style="color:#e67e22;" title="API异常: ' + reason + '">🔧分段修复</small>'
        elif fix_src == "api-warn":
            reason = pb.get("validation_reason", "")
            src_badge = ' <small style="color:#e74c3c;" title="API异常: ' + reason + '">⚠️待核</small>'
        elif fix_src == "splits-no-api":
            src_badge = ' <small style="color:#888;">(活动记录)</small>'
        else:
            src_badge = ' <small style="color:#888;">(API)</small>'
        
        # For 1英里 PB, add km equivalent in parentheses
        value_display = pb["value"]
        if "1英里" in pb["label"]:
            # Estimate 1KM equivalent time
            seconds = _time_str_to_seconds(pb["value"])
            if seconds:
                km_equivalent = _estimate_1km_from_1mile(seconds)
                if km_equivalent:
                    value_display = f'{pb["value"]} <small style="color:#666;">(约1km: {km_equivalent})</small>'
        
        html += '<tr><td>📌 PB</td><td>' + pb["label"] + '</td><td><strong>' + value_display + '</strong>' + src_badge + '</td><td>' + date_str + '</td></tr>\n'
    # 健康数据
    html += f"""<tr><td>健康</td><td>安静心率</td><td><strong>{health.get("resting_hr", "--")} bpm</strong></td><td>近7天均值</td></tr>
<tr><td>健康</td><td>HRV 基线</td><td><strong>{health.get("hrv", "--")} ms</strong></td><td>近7天均值</td></tr>
<tr><td>健康</td><td>训练准备度</td><td><strong>{readiness_score}</strong></td><td>Garmin 准备度评分</td></tr>
<tr><td>训练</td><td>近7天跑量</td><td><strong>{week7_distance:.1f} km</strong></td><td>{len(last_7_runs)} 次训练</td></tr>
<tr><td>训练</td><td>近{len(weekly)}周跑量</td><td><strong>{total_distance_km:.0f} km</strong></td><td>{total_runs} 次训练</td></tr>
</table>

"""

    # ==================================================================
    # 一、当日训练 + 睡眠分析（含温湿度影响）
    # ==================================================================
    html += '<h2>一、🏃 当日训练 + 睡眠分析</h2>\n'
    html += '<p style="color:#666;font-size:13px;">每项训练结合天气温湿度（DI不适指数）、前3天跑量、训练质量和睡眠恢复综合解读。</p>\n'

    # 筛选：只显示今天和昨天的训练（不含今日之前的）
    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    recent_cutoff = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

    sorted_acts = sorted(run_activities, key=lambda a: (a.get("startTimeLocal", "") or ""))
    recent_acts = [a for a in sorted_acts if _act_date(a) >= recent_cutoff]
    # 倒序显示：最新的训练最先展示（用户看到第一个卡片 = 昨日）
    recent_acts.reverse()
    for i, act in enumerate(recent_acts):
        act_date = _act_date(act)
        act_name = act.get("activityName") or act.get("activityType", {}).get("typeKey", "跑步") if isinstance(act.get("activityType"), dict) else "跑步"
        dist_km = (act.get("distance", 0) or 0) / 1000
        duration_s = (act.get("duration", 0) or 0)
        avg_pace = calc_pace(duration_s, dist_km * 1000)
        avg_hr = act.get("averageHR", "--") or "--"
        max_hr = act.get("maxHR", "--") or "--"
        cadence = act.get("averageRunCadence", "--") or "--"
        if isinstance(cadence, (int, float)) and cadence != "--":
            cadence = f"{cadence:.0f}"
        stride_m = act.get("strideLength", "--") or "--"
        if isinstance(stride_m, (int, float)) and stride_m != "--":
            stride_m = f"{stride_m/100:.2f} m"
        elev_gain = act.get("elevationGain", 0) or 0

        # Weather
        weather_html = _weather_badge(act)
        impact_html = _di_impact_text(act)

        # Grade
        grade = _grade_activity(act)

        # Sleep (shifted: training date D → sleep date D+1)
        sleep_data = _sleep_for_training(act_date)
        sleep_hours, sleep_score, deep_s, rem_s, light_s, awake_s, sleep_quality = _extract_sleep_detail(sleep_data)

        # HRV + BB for the sleep date (D+1 morning → reflects recovery from D's training)
        sleep_date_str = ""
        try:
            dt = datetime.strptime(act_date, "%Y-%m-%d")
            sleep_date_str = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            pass
        hrv_val = _extract_hrv(sleep_date_str) if sleep_date_str else "--"
        bb_max = _extract_bb_max(sleep_date_str) if sleep_date_str else "--"

        # Previous 3 days volume
        try:
            dt = datetime.strptime(act_date, "%Y-%m-%d")
            prev3_start = (dt - timedelta(days=3)).strftime("%Y-%m-%d")
            prev3_acts = [a for a in sorted_acts if prev3_start <= _act_date(a) < act_date]
            prev3_vol = sum((a.get("distance", 0) or 0) for a in prev3_acts) / 1000
        except ValueError:
            prev3_vol = 0

        # Splits
        splits = act.get("_splits", [])

        # Best km from splits
        best_lap = get_best_splits(splits)
        best_pace_str = ""
        if best_lap:
            bp = calc_pace(best_lap.get("duration", 0), best_lap.get("distance", 0))
            best_pace_str = f'<span style="font-weight:bold;color:#28a745;">{bp}</span>'

        # 等强配速（始终计算，爬升<10m时等强≈实际配速）
        pace_s_km = duration_s / dist_km if dist_km > 0 else 0
        hr_val = avg_hr if isinstance(avg_hr, (int, float)) else None

        if splits:
            ep = calc_effort_pace(pace_s_km, elev_gain, dist_km, avg_hr=hr_val, use_personalized=True)
        else:
            ep = calc_effort_pace(pace_s_km, elev_gain, dist_km, avg_hr=hr_val, use_personalized=False)
        
        if ep and ep.get("effort_pace"):
            ep_tag = f'<span style="color:#9c27b0;font-weight:bold;">{ep["effort_pace"]}</span>'
            avg_g = ep.get("avg_grade")
            grade_str = f'<small style="color:#888;">(坡度{avg_g}%)</small>' if avg_g and abs(avg_g) >= 0.5 else ""
            person_tag = '<small style="color:#9c27b0;">✦</small>' if ep.get("personalized") else ""
            pace_display = f'{avg_pace} | 等强{ep_tag} {grade_str}{person_tag}'
        else:
            pace_display = avg_pace

        # Card start
        html += f"""<div class="workout-card">
<h4>{act_date} {act_name} {grade}</h4>
<div class="meta">{weather_html}</div>
<div class="meta">{impact_html}</div>
<div class="stats-grid">
<div class="stats-item"><span class="stats-label">距离</span><span class="stats-value">{dist_km:.2f} km</span></div>
<div class="stats-item"><span class="stats-label">均配速</span><span class="stats-value">{pace_display}</span></div>
<div class="stats-item"><span class="stats-label">均心率</span><span class="stats-value">{avg_hr} bpm</span></div>
<div class="stats-item"><span class="stats-label">最大心率</span><span class="stats-value">{max_hr} bpm</span></div>
<div class="stats-item"><span class="stats-label">爬升</span><span class="stats-value">{elev_gain:.0f} m</span></div>
"""
        if best_pace_str:
            html += f'<div class="stats-item"><span class="stats-label">最快单圈</span><span class="stats-value">{best_pace_str}</span></div>\n'
        if cadence != "--":
            html += f'<div class="stats-item"><span class="stats-label">步频</span><span class="stats-value">{cadence} spm</span></div>\n'
        if stride_m != "--":
            html += f'<div class="stats-item"><span class="stats-label">步幅</span><span class="stats-value">{stride_m}</span></div>\n'
        html += "</div>\n"

        # 综合解读
        summary_parts = []
        summary_parts.append(f"前3天跑量 <strong>{prev3_vol:.1f} km</strong>")
        summary_parts.append(f"训练后睡眠 <strong>{sleep_hours}</strong>")
        if sleep_score != "--":
            summary_parts.append(f"睡眠评分 <strong>{sleep_score}</strong>")
        summary_parts.append(f"HRV <strong>{hrv_val}</strong>")
        summary_parts.append(f"Body Battery最高 <strong>{bb_max}</strong>")
        summary_text = " | ".join(summary_parts)
        
        html += f'<div class="summary-box">📊 {summary_text}</div>\n'
        
        # 睡眠详细分析
        if sleep_quality:
            html += f'<div class="summary-box" style="border-left-color:#9c27b0;">😴 睡眠阶段：{sleep_quality}</div>\n'
        
        # 睡眠评分分析
        if sleep_score != "--" and isinstance(sleep_score, (int, float)):
            if sleep_score >= 80:
                sleep_analysis = "睡眠优秀，恢复充分，身体已准备好下一次训练。"
            elif sleep_score >= 60:
                sleep_analysis = "睡眠良好，基本恢复，可正常训练。"
            else:
                sleep_analysis = "睡眠质量偏低，建议今天安排恢复性训练或休息。"
            html += f'<div class="summary-box" style="border-left-color:#ff9800;">💤 {sleep_analysis}</div>\n'

        # 天气DI解读
        w = act.get("_weather", {})
        di = w.get("di")
        if di is not None:
            level_name = di_level(di)
            _, impact_desc = di_pace_impact(di)
            html += f'<div class="summary-box" style="border-left-color:#e94560;">🌤️ DI <strong>{di}</strong>（{level_name}）— {impact_desc}</div>\n'

        # Splits table
        if splits:
            # Get detail metrics for recovery min HR (interval training only)
            act_details = act.get("_details")
            detail_m = None
            metric_d = None
            if act_details:
                detail_m = act_details.get("activityDetailMetrics")
                metric_d = act_details.get("metricDescriptors")
            splits_html, heuristic_notice, _rec_html = render_splits_table(splits, detail_m, metric_d)
            if heuristic_notice:
                html += heuristic_notice
            html += '<details style="margin-top:8px;"><summary style="cursor:pointer;color:#0f3460;font-weight:bold;">📊 分段配速表</summary>\n'
            html += splits_html
            html += '</details>\n'

        html += "</div>\n"

    # ==================================================================
    # 二、当周整体评估（含各训练温湿度分布）
    # ==================================================================
    html += '<h2>二、📅 当周整体评估</h2>\n'

    # 当周训练日程 + DI 一览
    html += '<h3>当周训练日程及 DI 一览</h3>\n'
    html += """<table>
<tr><th>日期</th><th>活动</th><th>距离</th><th>配速/等强</th><th>温度/湿度</th><th>DI</th><th>影响</th><th>评分</th></tr>
"""
    # Identify current/last week activities
    today_dt = datetime.now()
    current_week_start = today_dt - timedelta(days=today_dt.weekday())
    for act in sorted_acts:
        d = _act_date(act)
        try:
            act_dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        # Only show current week
        if act_dt < current_week_start - timedelta(days=7):
            continue
        if act_dt > today_dt:
            continue

        dist_km = (act.get("distance", 0) or 0) / 1000
        dur = (act.get("duration", 0) or 0)
        pace = calc_pace(dur, dist_km * 1000)

        w = act.get("_weather", {})
        t = w.get("temperature", "--")
        rh = w.get("humidity", "--")
        di_val = w.get("di")
        di_str = f"{di_val}" if di_val is not None else "--"
        di_h = _di_html(di_val)

        _, impact_desc = di_pace_impact(di_val) if di_val is not None else ("", "")
        impact_short = impact_desc[:3] if impact_desc else "—"  # first 3 chars

        grade_tag = _grade_activity(act)

        act_name = act.get("activityName") or "跑步"
        # 计算等强配速
        elev = act.get("elevationGain", 0) or 0
        ep = calc_effort_pace(dur / dist_km if dist_km > 0 else 0, elev, dist_km, avg_hr=act.get("averageHR"))
        if ep and ep.get("effort_pace"):
            pace_display = f'{pace}<br><small style="color:#9c27b0;">等强{ep["effort_pace"]}</small>'
        else:
            pace_display = pace
        html += f"<tr><td>{d}</td><td>{act_name}</td><td>{dist_km:.1f}km</td><td>{pace_display}</td><td>{t}°C/{rh}%</td><td>{di_h}</td><td>{impact_short}</td><td>{grade_tag}</td></tr>\n"

    html += "</table>\n"

    # 同周内不同天气条件表现对比
    html += '<h3>天气条件与表现对比</h3>\n'
    week_acts = [a for a in sorted_acts if
                 current_week_start - timedelta(days=7) <= datetime.strptime(_act_date(a), "%Y-%m-%d") <= today_dt
                 if _act_date(a)]
    week_acts = [a for a in sorted_acts if
                 (datetime.strptime(_act_date(a), "%Y-%m-%d") if _act_date(a) else today_dt)
                 >= current_week_start - timedelta(days=7)]

    # Filter again properly
    week_acts_clean = []
    for a in sorted_acts:
        d = _act_date(a)
        try:
            act_dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        if act_dt >= current_week_start - timedelta(days=7) and act_dt <= today_dt:
            week_acts_clean.append(a)
    
    # Compare high DI vs low DI paces
    high_di = [a for a in week_acts_clean if (a.get("_weather", {}) or {}).get("di", 0) is not None and (a.get("_weather", {}) or {}).get("di", 0) >= 24]
    low_di = [a for a in week_acts_clean if (a.get("_weather", {}) or {}).get("di", 0) is not None and (a.get("_weather", {}) or {}).get("di", 0) < 24]
    
    if high_di and low_di:
        avg_pace_high = sum((a.get("duration", 0) or 0) / max((a.get("distance", 0) or 1) / 1000, 0.001) for a in high_di) / len(high_di)
        avg_pace_low = sum((a.get("duration", 0) or 0) / max((a.get("distance", 0) or 1) / 1000, 0.001) for a in low_di) / len(low_di)
        diff = avg_pace_high - avg_pace_low
        diff_str = f"+{diff:.0f}s/km" if diff > 0 else f"{diff:.0f}s/km"
        html += f'<div class="summary-box">📊 本周低DI天均配速 <strong>{avg_pace_low:.0f}s/km</strong>，高DI天均配速 <strong>{avg_pace_high:.0f}s/km</strong>，差异 <strong style="color:{"#dc3545" if diff > 0 else "#28a745"}">{diff_str}</strong></div>\n'
    else:
        html += '<div class="summary-box">📊 本周天气条件较均匀，无显著 DI 对比差异。</div>\n'

    # 周跑量 + 周均DI
    week_total_km = sum((a.get("distance", 0) or 0) / 1000 for a in week_acts_clean)
    di_vals_week = [a.get("_weather", {}).get("di") for a in week_acts_clean if (a.get("_weather", {}) or {}).get("di") is not None]
    avg_di_week = round(sum(di_vals_week) / len(di_vals_week), 1) if di_vals_week else "—"
    html += f'<div class="summary-box">📈 本周跑量 <strong>{week_total_km:.1f} km</strong>，{len(week_acts_clean)}次训练，周均DI <strong>{avg_di_week}</strong></div>\n'

    # 周跑量统计表
    html += '<h3>周跑量统计</h3>\n'
    html += """<table>
<tr><th>周次</th><th>跑量</th><th>训练天数</th><th>关键训练</th></tr>
"""
    for week_key, week_data in weekly.items():
        dist = week_data["distance"]
        count = week_data["count"]
        longest = max(week_data["activities"], key=lambda a: a.get("distance", 0) or 0) if week_data["activities"] else None
        key_info = ""
        if longest:
            ld = (longest.get("distance", 0) or 0) / 1000
            key_info = f"{ld:.0f}K {longest.get('activityName', '跑步')}" if ld > 10 else ""
        html += f"<tr><td>{week_key}</td><td><strong>{dist:.0f} km</strong></td><td>{count}天</td><td>{key_info}</td></tr>\n"
    
    total_weeks = len(weekly)
    avg_weekly_dist = sum(w["distance"] for w in weekly.values()) / max(total_weeks, 1)
    html += f"""<tr><td colspan="2"><strong>周均</strong></td><td><strong>{avg_weekly_dist:.0f} km/周</strong></td><td>{total_runs}次训练</td></tr>
</table>
"""

    # ==================================================================
    # 三、当月整体评估（含月度天气变化轨迹）
    # ==================================================================
    html += '<h2>三、📆 当月整体评估</h2>\n'

    # 近30天温度/湿度/DI 变化趋势
    html += '<h3>月度天气变化趋势</h3>\n'
    html += '<table>\n<tr><th>日期</th><th>温度</th><th>湿度</th><th>DI</th><th>等级</th></tr>\n'
    # Collect all dates from daily data, sorted
    all_dates = sorted(daily.keys())
    for d in all_dates[-30:]:  # last 30 days
        # Try to find weather from activities on this date
        day_acts = [a for a in sorted_acts if _act_date(a) == d]
        best_w = None
        for a in day_acts:
            w = a.get("_weather", {})
            if w and w.get("temperature") is not None and w.get("di") is not None:
                best_w = w
                break
        if best_w:
            t = best_w["temperature"]
            rh = best_w.get("humidity", "--")
            di_val = best_w["di"]
            di_h = _di_html(di_val)
            lvl = di_level(di_val)
            html += f"<tr><td>{d}</td><td>{t}°C</td><td>{rh}%</td><td>{di_h}</td><td>{lvl}</td></tr>\n"
    html += "</table>\n"

    # DI区间训练分布
    html += '<h3>不同 DI 区间训练分布</h3>\n'
    di_buckets = {"<21 (舒适)": [], "21-24 (轻度)": [], "24-27 (中度)": [], "27-29 (明显)": [], "≥29 (严重)": []}
    for a in sorted_acts:
        di_val = (a.get("_weather", {}) or {}).get("di")
        if di_val is None:
            continue
        if di_val < 21:
            di_buckets["<21 (舒适)"].append(a)
        elif di_val < 24:
            di_buckets["21-24 (轻度)"].append(a)
        elif di_val < 27:
            di_buckets["24-27 (中度)"].append(a)
        elif di_val < 29:
            di_buckets["27-29 (明显)"].append(a)
        else:
            di_buckets["≥29 (严重)"].append(a)

    html += '<table>\n<tr><th>DI 区间</th><th>训练次数</th><th>占比</th><th>均配速</th></tr>\n'
    total_with_di = sum(len(v) for v in di_buckets.values())
    for bucket, acts_list in di_buckets.items():
        count = len(acts_list)
        if count == 0:
            continue
        pct = count / total_with_di * 100 if total_with_di > 0 else 0
        avg_p = sum((a.get("duration", 0) or 0) / max((a.get("distance", 0) or 1) / 1000, 0.001) for a in acts_list) / count
        avg_p_str = f"{int(avg_p//60)}:{int(avg_p%60):02d}/km"
        html += f"<tr><td>{bucket}</td><td>{count}</td><td>{pct:.0f}%</td><td>{avg_p_str}</td></tr>\n"
    html += f'<tr><td colspan="2"><strong>合计</strong></td><td><strong>{total_with_di}</strong></td><td></td></tr>\n'
    html += "</table>\n"

    # 高温高湿日 vs 低温舒适日的配速偏差
    html += '<h3>配速偏差对比</h3>\n'
    high_di_acts = [a for a in sorted_acts if (a.get("_weather", {}) or {}).get("di") is not None and (a.get("_weather", {}) or {}).get("di", 0) >= 24]
    low_di_acts = [a for a in sorted_acts if (a.get("_weather", {}) or {}).get("di") is not None and (a.get("_weather", {}) or {}).get("di", 0) < 24]
    
    def _avg_pace_of(acts):
        if not acts:
            return None
        total_dur = sum((a.get("duration", 0) or 0) for a in acts)
        total_dist = sum((a.get("distance", 0) or 0) for a in acts) / 1000
        if total_dist <= 0:
            return None
        return total_dur / total_dist

    if high_di_acts and low_di_acts:
        pace_high = _avg_pace_of(high_di_acts)
        pace_low = _avg_pace_of(low_di_acts)
        if pace_high and pace_low:
            diff = pace_high - pace_low
            html += '<table>\n<tr><th>条件</th><th>训练次数</th><th>均配速</th></tr>\n'
            html += f'<tr><td>🌤️ 舒适（DI&lt;24）</td><td>{len(low_di_acts)}</td><td>{int(pace_low//60)}:{int(pace_low%60):02d}/km</td></tr>\n'
            html += f'<tr><td>🔥 高温高湿（DI≥24）</td><td>{len(high_di_acts)}</td><td>{int(pace_high//60)}:{int(pace_high%60):02d}/km</td></tr>\n'
            diff_str = f'+{diff:.0f}s/km' if diff > 0 else f'{diff:.0f}s/km'
            color = "#dc3545" if diff > 0 else "#28a745"
            html += f'<tr><td><strong>偏差</strong></td><td></td><td><strong style="color:{color};">{diff_str}</strong></td></tr>\n'
            html += '</table>\n'
    else:
        html += '<div class="summary-box">📊 当前数据不足以进行高低温对比分析。</div>\n'

    # 恢复与健康趋势（健康数据表）
    html += '<h3>恢复与健康趋势</h3>\n'
    html += """<table>
<tr><th>日期</th><th>睡眠时长</th><th>睡眠Score</th><th>HRV</th><th>Body Battery(最高)</th><th>静息心率</th><th>压力</th></tr>
"""
    for d in sorted(daily.keys(), reverse=True):
        dd = daily[d]
        # Sleep
        sleep = dd.get("sleep", {}) or {}
        if isinstance(sleep, dict):
            sleep_hours, sleep_score, deep_s, rem_s, light_s, awake_s, sleep_quality = _extract_sleep_detail(sleep)
        else:
            sleep_hours, sleep_score = "--", "--"
            deep_s = rem_s = light_s = awake_s = 0
            sleep_quality = ""

        # HRV
        hrv_val = _extract_hrv(d)

        # Body Battery
        bb_max = _extract_bb_max(d)

        # Resting heart rate
        rhr = _extract_rhr(d)
        hr_data = dd.get("heart_rates", {}) or {}
        if isinstance(hr_data, dict) and rhr == "--":
            rhr = hr_data.get("restingHeartRate") or "--"

        # Stress
        stress = dd.get("stress", {}) or {}
        stress_val = "--"
        if isinstance(stress, dict):
            stress_val = stress.get("avgStressLevel") or stress.get("averageStressLevel") or "--"

        html += f"<tr><td>{d}</td><td>{sleep_hours}</td><td>{sleep_score}</td><td>{hrv_val}</td><td>{bb_max}</td><td>{rhr} bpm</td><td>{stress_val}</td></tr>\n"

    html += """</table>
"""

    # 四维度评分
    html += '<h3>四维度评分</h3>\n'
    html += "<table>\n<tr><th>维度</th><th>评分</th></tr>\n"
    score_labels = {
        5: "★★★★★", 4: "★★★★☆", 3: "★★★☆☆", 2: "★★☆☆☆", 1: "★☆☆☆☆"
    }
    for dim in ["跑量", "长距离", "配速", "训练频率"]:
        score = dim_scores.get(dim, 3)
        stars = score_labels.get(score, "★★★☆☆")
        html += f'<tr><td>{dim}</td><td>{stars}</td></tr>\n'
    html += "</table>\n"

    # ==================================================================
    # 四、优化建议
    # ==================================================================
    html += '<h2>四、💡 优化建议</h2>\n<ul class="suggestion-list">\n'
    
    suggestions = []
    
    # 跑量建议（基于近30天周均跑量，排除当前未完成的周）
    avg_weekly_complete = avg_weekly_dist  # 已经只取最近4周，且当前周可能未完成
    if dim_scores.get("跑量", 0) <= 2:
        suggestions.append("近30天跑量明显不足，建议循序渐进增加跑量，避免突然增量导致受伤。")
    elif dim_scores.get("跑量", 0) == 3:
        suggestions.append("近30天周均跑量中等，可根据训练目标适当调整。")
    
    # 长距离建议
    if dim_scores.get("长距离", 0) <= 2:
        suggestions.append("长距离训练不足，建议每 1-2 周安排一次 18K+ 的长距离跑，为半马/全马打下基础。")
    elif dim_scores.get("长距离", 0) == 3:
        suggestions.append("长距离训练基本达标，可继续保持或适当增加距离。")
    
    # 配速建议
    if dim_scores.get("配速", 0) <= 2:
        suggestions.append("配速训练不足，建议增加节奏跑（Tempo）和间歇训练，提升速度能力。")
    elif dim_scores.get("配速", 0) == 3:
        suggestions.append("配速训练中等，可根据比赛目标增加针对性训练。")
    
    # 训练频率建议
    if dim_scores.get("训练频率", 0) <= 2:
        suggestions.append("训练频率偏低，建议增加到每周至少 3 次训练，保持跑步习惯。")
    elif dim_scores.get("训练频率", 0) == 3:
        suggestions.append("训练频率中等，可根据身体恢复情况适当增加。")
    
    # 温湿度相关建议
    high_di_sessions = len([a for a in sorted_acts if (a.get("_weather", {}) or {}).get("di") is not None and (a.get("_weather", {}) or {}).get("di", 0) >= 27])
    if high_di_sessions >= 3:
        suggestions.append(f"近30天有 {high_di_sessions} 次训练在明显不适（DI≥27）条件下进行，注意高温高湿日的配速预期调整和补水策略。")
    
    # 恢复建议
    if dim_scores.get("训练频率", 0) >= 4 and dim_scores.get("跑量", 0) >= 4:
        suggestions.append("当前训练强度较高，注意安排恢复周（每 3-4 周减量一周），避免过度训练。")
    
    if not suggestions:
        suggestions.append("各项指标良好，继续保持当前训练节奏！注意循序渐进，避免过度训练。")
    
    for s in suggestions:
        html += f"<li>{s}</li>\n"
    html += "</ul>\n"

    # ==================================================================
    # 五、课表建议
    # ==================================================================
    html += '<h2>五、📋 课表建议</h2>\n<ul class="plan-list">\n'

    # 基于当前状态的全马备赛课表建议
    plans = []
    current_weekly = avg_weekly_dist if total_weeks > 0 else 40
    target_marathon = "3:15:00"
    has_long_run = dim_scores.get("长距离", 0) >= 3

    # 基础课表建议
    if current_weekly < 50:
        plans.append("当前跑量不足 50km/周，建议先稳定在 50-60km 持续 3 周再增量，避免受伤。")
    
    if not has_long_run:
        plans.append("建议每周末安排一次长距离：第一周 16km → 第二周 18km → 第三周 21km → 第四周 24km，逐步延长。")
    else:
        plans.append(f"长距离基础良好，建议持续周末 LSD（20-28km），每3周安排一次减量周。")

    plans.append(f"目标全马 {target_marathon}（4:44/km），建议每周至少一次 MP 配速节奏跑（8-12km @4:40-4:50/km）。")
    plans.append("每周安排1-2次间歇/速度训练（如 800m x 6-8 组 @4:05-4:15/km，组间慢跑恢复）。")
    plans.append("高强度训练次日安排恢复跑（5-8km @5:30-6:00/km），促进主动恢复、保持肌肉弹性。")
    plans.append("高温高湿日（DI≥27）建议调整训练时间至清晨或傍晚，配速预期下调 8-15 s/km。")

    for p in plans:
        html += f"<li>{p}</li>\n"
    html += "</ul>\n"

    # 追问
    html += """
<h2>六、💬 后续分析选项</h2>
<div style="background:#f8f9fa;padding:16px;border-radius:8px;margin:16px 0;">
<p style="margin:0 0 12px 0;">如需进一步分析，可选择以下选项：</p>
<ol style="margin:0;padding-left:20px;">
<li><strong>分段分析：</strong>对指定训练进行计圈分段分析，可精确识别间歇跑、节奏跑、马拉松配速段等运动表现</li>
<li><strong>周维度分析：</strong>按自然周汇总跑量、训练强度、恢复状态，评估周训练质量</li>
<li><strong>月维度分析：</strong>按月汇总趋势，评估月度训练完成度、与上月对比</li>
</ol>
<p style="margin:12px 0 0 0;color:#666;font-size:13px;">💡 如需分析，请回复「分段分析」+ 日期，或「周报告」/「月报告」</p>
</div>
"""

    # Footer
    html += f"""
<div class="footer">
<p>数据来源：Garmin Connect | 分析工具：小虎酱 🐯</p>
<p>报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
</div>

</body>
</html>
"""
    return html


# ---------------------------------------------------------------------------
# Helper functions for data extraction
# ---------------------------------------------------------------------------

def _get_display_name(data):
    """Return a generic display name (no PII)."""
    return "Garmin 用户"


def _get_vo2max(training_status):
    """Extract VO2max from training status data.
    
    Actual structure: {"mostRecentVO2Max": {"generic": {"vo2MaxPreciseValue": 54.6, "vo2MaxValue": 55}}}
    """
    if isinstance(training_status, dict):
        vo2 = training_status.get("mostRecentVO2Max", {})
        if isinstance(vo2, dict):
            generic = vo2.get("generic", {})
            if isinstance(generic, dict):
                val = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
                if val:
                    return val
        # Fallback to top-level keys
        return training_status.get("vo2Max") or training_status.get("vo2max") or training_status.get("fitnessLevel") or "--"
    return "--"


def _format_race_predictions(race_preds):
    """Format race predictions dict into readable strings.
    
    Raw API uses keys: time5K, time10K, timeHalfMarathon, timeMarathon (seconds).
    Also check older/cn format: 5k, 10k, hm, fm (fallback).
    """
    if not isinstance(race_preds, dict) or not race_preds:
        return {}
    result = {}
    # Primary: raw API keys
    api_keys = [
        ("time5K", "5K"),
        ("time10K", "10K"),
        ("timeHalfMarathon", "半马"),
        ("timeMarathon", "全马"),
    ]
    for key, label in api_keys:
        val = race_preds.get(key)
        if isinstance(val, (int, float)) and val > 0:
            result[label] = _seconds_to_time_str(val)
    # Fallback: older format keys (5k, 10k, hm, fm)
    if not result:
        fallback_keys = [
            ("5k", "5K"),
            ("10k", "10K"),
            ("hm", "半马"),
            ("fm", "全马"),
        ]
        for key, label in fallback_keys:
            val = race_preds.get(key)
            if isinstance(val, (int, float)) and val > 0:
                result[label] = _seconds_to_time_str(val)
    return result


def _summarize_health(daily):
    """Summarize health metrics from daily data."""
    resting_hrs = []
    hrvs = []
    
    for d, dd in daily.items():
        summary = dd.get("summary", {}) or {}
        if isinstance(summary, dict):
            rhr = summary.get("restingHeartRate")
            if rhr and isinstance(rhr, (int, float)):
                resting_hrs.append(rhr)
        
        # HRV: {"hrvSummary": {"weeklyAvg": 52, "lastNightAvg": 52, ...}}
        hrv = dd.get("hrv", {}) or {}
        if isinstance(hrv, dict):
            hrv_summary = hrv.get("hrvSummary", {})
            if isinstance(hrv_summary, dict):
                hrv_val = hrv_summary.get("weeklyAvg") or hrv_summary.get("lastNightAvg")
                if hrv_val and isinstance(hrv_val, (int, float)):
                    hrvs.append(hrv_val)
    
    return {
        "resting_hr": round(sum(resting_hrs) / len(resting_hrs)) if resting_hrs else "--",
        "hrv": round(sum(hrvs) / len(hrvs)) if hrvs else "--"
    }


def _get_readiness(readiness):
    """Extract readiness score.
    
    Actual structure: [{"score": 68, "level": "MODERATE", ...}]
    Returns score value, or "--" if unavailable.
    """
    if isinstance(readiness, list) and len(readiness) > 0:
        item = readiness[0]
        if isinstance(item, dict):
            return item.get("score") or item.get("readinessScore") or "--"
    if isinstance(readiness, dict):
        return readiness.get("score") or readiness.get("readinessScore") or "--"
    return "--"


def _get_scored_activities(activities, race_preds):
    """Score and sort activities, return list of (activity, score_tag) tuples."""
    scored = []
    for act in activities:
        dist = (act.get("distance", 0) or 0)
        if dist < 3000:  # 只展示 >= 3km 的活动
            continue
        score = score_activity(act, race_preds)
        scored.append((act, score))
    
    # 排序：best > good > normal > below
    score_order = {"best": 0, "good": 1, "normal": 2, "below": 3}
    scored.sort(key=lambda x: score_order.get(x[1], 99))
    return scored


# ---------------------------------------------------------------------------
# 4. CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Garmin 训练分析报告")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"分析天数 (默认: {DEFAULT_DAYS})")
    parser.add_argument("--pb-days", type=int, default=PB_HISTORY_DAYS, help=f"PB历史查询天数 (默认: {PB_HISTORY_DAYS})")
    parser.add_argument("--start", help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--output", help="输出文件路径")
    args = parser.parse_args()
    
    # 日期范围
    start_date, end_date = get_date_range(args.days, args.start, args.end)
    print(f"📅 分析周期: {start_date} ~ {end_date}", file=sys.stderr)
    
    # PB历史范围
    pb_start, pb_end = get_pb_history_range()
    print(f"📅 PB历史周期: {pb_start} ~ {pb_end}", file=sys.stderr)
    
    # 获取客户端
    print("🔐 Authenticating...", file=sys.stderr)
    client = get_client()
    if not client:
        print("❌ Authentication failed. Run: python3 scripts/garmin_auth.py login", file=sys.stderr)
        sys.exit(1)
    print("✅ Authenticated!", file=sys.stderr)
    
    # 获取数据
    data = fetch_all_data(client, start_date, end_date)
    
    # 额外获取 PB 历史活动的 splits（用于分段插值）
    # 这确保5K/10K/半马/全马PB不受分析周期限制
    print("📡 Fetching PB history activity splits...", file=sys.stderr)
    pb_activities = list(client.get_activities_by_date(pb_start, pb_end))
    pb_run_acts = [a for a in pb_activities if _is_running(a)]
    pb_splits_fetched = 0
    existing_ids = {a.get("activityId") for a in data["activities"]}
    for act in pb_run_acts:
        act_id = act.get("activityId")
        dist = act.get("distance", 0) or 0
        if not act_id or dist < 5000:
            continue
        if act_id in existing_ids:
            # Already have this activity's splits
            continue
        try:
            splits = client.get_activity_splits(act_id)
            act["_splits"] = list(splits.get("lapDTOs", [])) if isinstance(splits, dict) else list(splits)
            # Append to data activities (only for splits; not counted in main activities)
            data["activities"].append(act)
            pb_splits_fetched += 1
        except Exception:
            pass
    print(f"   -> Fetched splits for {pb_splits_fetched} additional PB activities", file=sys.stderr)
    
    # 生成报告
    print("📝 Generating report...", file=sys.stderr)
    html = render_report(data, start_date, end_date)
    
    # 输出文件
    output_path = args.output
    if not output_path:
        today = datetime.now().strftime("%Y%m%d")
        output_path = str(OUTPUT_DIR / f"佳明训练分析报告_{today}.html")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"✅ Report saved to: {output_path}", file=sys.stderr)
    print(output_path)  # stdout 输出路径供其他工具使用


if __name__ == "__main__":
    main()
