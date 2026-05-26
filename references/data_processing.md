# 数据处理逻辑

> PB 提取、睡眠日期关联等关键数据处理函数实现。

---

## 一、PB 提取函数

### extract_pb_from_activities()

从历史活动记录按距离区间提取个人最佳成绩：

```python
def extract_pb_from_activities(activities):
    """
    距离区间定义：
    - 5K: [4.5, 5.5] km
    - 10K: [9.0, 11.0] km
    - 半马: [20.0, 22.0] km
    - 全马: [40.0, 45.0] km

    关键词匹配（用于识别比赛）：
    - 半马: ["半马", "21km", "21.1", "half", "hm"]
    - 全马: ["全马", "42km", "42.2", "full", "fm", "marathon"]
    """
    pb_by_distance = {
        "5k": {"distance": None, "time": float('inf')},
        "10k": {"distance": None, "time": float('inf')},
        "half_marathon": {"distance": None, "time": float('inf')},
        "marathon": {"distance": None, "time": float('inf')},
    }

    for activity in activities:
        distance_km = activity["distance"] / 1000
        duration_sec = activity["duration"]

        if 4.5 <= distance_km <= 5.5 and duration_sec < pb_by_distance["5k"]["time"]:
            pb_by_distance["5k"] = {"distance": distance_km, "time": duration_sec}
        elif 9.0 <= distance_km <= 11.0 and duration_sec < pb_by_distance["10k"]["time"]:
            pb_by_distance["10k"] = {"distance": distance_km, "time": duration_sec}
        elif 20.0 <= distance_km <= 22.0:
            name = activity.get("activityName", "").lower()
            if any(kw in name for kw in ["半马", "21km", "half", "hm"]):
                if duration_sec < pb_by_distance["half_marathon"]["time"]:
                    pb_by_distance["half_marathon"] = {"distance": distance_km, "time": duration_sec}
        elif 40.0 <= distance_km <= 45.0:
            name = activity.get("activityName", "").lower()
            if any(kw in name for kw in ["全马", "42km", "full", "fm", "marathon"]):
                if duration_sec < pb_by_distance["marathon"]["time"]:
                    pb_by_distance["marathon"] = {"distance": distance_km, "time": duration_sec}

    return pb_by_distance
```

### PB 合并展示逻辑

```python
def merge_personal_records(api_pb, activity_pb):
    """合并 Garmin API PB 和活动记录 PB"""
    merged = {}
    # API PB 优先
    for key, value in api_pb.items():
        if value and value != "--":
            merged[key] = {"value": value, "source": "Garmin API"}
    # 活动 PB 补充缺失项
    for key, value in activity_pb.items():
        if key not in merged and value["time"] != float('inf'):
            merged[key] = {"value": value["time"], "source": "活动记录"}
    return merged
```

---

## 二、睡眠日期关联

Garmin 用醒来日期记录睡眠。训练日 D 的睡眠 = Garmin 记录中 D+1 日期的睡眠。

```python
def _sleep_for_training(training_date, daily_sleep_data):
    """训练日 D 的睡眠 = Garmin D+1 的睡眠记录"""
    next_day = training_date + datetime.timedelta(days=1)
    next_day_str = next_day.strftime("%Y-%m-%d")
    return daily_sleep_data.get(next_day_str, None)
```

| 入睡 | 醒来 | Garmin 记录日期 | 关联训练日 |
|------|------|----------------|-------------|
| 18号晚 | 19号早 | **19号** | 18号 |
| 19号晚 | 20号早 | **20号** | 19号 |
