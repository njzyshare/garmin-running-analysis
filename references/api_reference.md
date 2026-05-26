# Garmin API 参考

> garminconnect 库核心端点与响应结构。

---

## 认证流程

```python
from garminconnect import Garmin

# 首次登录
client = Garmin(email, password)
client.login()

# 保存 token
oauth1 = client.garth.oauth1_token
oauth2 = client.garth.oauth2_token

# 恢复会话
client = Garmin()
client.garth.oauth1_token = oauth1
client.garth.oauth2_token = oauth2
```

---

## 核心端点

| 功能 | 调用 | 说明 |
|------|------|------|
| 用户信息 | `get_full_name()` | 用户全名 |
| 日摘要 | `get_user_summary("YYYY-MM-DD")` | 步数、卡路里等 |
| 睡眠 | `get_sleep_data("YYYY-MM-DD")` | 睡眠阶段、评分、HRV |
| HRV | `get_hrv_data("YYYY-MM-DD")` | 夜间均值、周均值、状态 |
| Body Battery | `get_body_battery("YYYY-MM-DD")` | 充放电时间序列 |
| 心率 | `get_heart_rates("YYYY-MM-DD")` | 静息/最大/最小 |
| 活动 | `get_activities_by_date("start", "end")` | 活动列表 |
| 比赛预测 | profile 数据中 `race_predictions` | 5K/10K/半马/全马 |

---

## 响应结构

### 睡眠

```json
{
  "dailySleepDTO": {
    "sleepTimeSeconds": 28800,
    "deepSleepSeconds": 7200,
    "lightSleepSeconds": 14400,
    "remSleepSeconds": 7200,
    "awakeSleepSeconds": 1800,
    "sleepScores": {"overall": {"value": 85}},
    "restlessMoments": 12,
    "avgSleepHeartRate": 52,
    "avgSleepHRV": 45,
    "avgSleepRespiration": 14
  }
}
```

### HRV

```json
{
  "hrvSummary": {
    "lastNightAvg": 45,
    "weeklyAvg": 42,
    "baselineBalancedLow": 38,
    "baselineBalancedHigh": 48,
    "status": "BALANCED"
  }
}
```

### Body Battery

```json
[
  {"timestamp": 1737849600000, "value": 85, "charged": 45, "drained": 15}
]
```

### 心率

```json
{
  "restingHeartRate": 52,
  "maxHeartRate": 165,
  "minHeartRate": 48
}
```

### 活动记录

```json
{
  "activityId": 123456789,
  "activityType": {"typeKey": "running"},
  "activityName": "晨跑",
  "startTimeLocal": "2026-01-25 07:30:00",
  "duration": 3600,
  "distance": 10000,
  "calories": 650,
  "averageHR": 152,
  "maxHR": 178,
  "elevationGain": 120,
  "averageSpeed": 2.78,
  "averageRunningCadence": 165,
  "startLatitude": 26.07,
  "startLongitude": 119.30
}
```

### 比赛预测

键名为驼峰格式：`time5K`、`time10K`、`timeHalfMarathon`、`timeMarathon`，值单位为秒。

```python
# 双键名 fallback 映射
def get_race_time(race_preds, distance_key):
    camel_key = f"time{distance_key.upper()}" if distance_key != "5k" else "time5K"
    if camel_key in race_preds:
        return race_preds[camel_key]
    # 旧格式 fallback
    old_keys = {"5k": "5k", "10k": "10k", "half": "hm", "full": "fm"}
    old_key = old_keys.get(distance_key)
    if old_key and old_key in race_preds:
        return race_preds[old_key]
    return None
```
