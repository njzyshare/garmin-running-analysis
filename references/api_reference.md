# Garmin API 参考

> garminconnect 库核心端点与响应结构。

---

## 技术方案说明

Garmin 运动数据通过 **社区维护的开源库 `python-garminconnect` (v0.3.3)** 获取，底层链路如下：

```
Python 脚本 (garmin_data.py)
    ↓ 调用
garminconnect 库 — 社区维护的开源库 (https://github.com/cyberjunky/python-garminconnect)
    ↓ 发送 HTTPS 请求 + 携带 OAuth token
Garmin Connect 官方 REST API (connect.garmin.cn)
    ↓
Garmin 服务器 → Garmin 手表数据云端同步
```

**关键特点：**

| 特性 | 说明 |
|:----|:------|
| 认证方式 | OAuth1 + OAuth2 token，首次需邮箱密码，后续自动复用 |
| Token 存储 | `~/.clawdbot/garmin-tokens.json`，自动刷新 |
| 中国区适配 | 通过 monkey-patch 兼容 `garmin.cn` 的 DI token 端点 |
| 计圈数据 | ✅ **直接通过 `/splits` 端点获取完整逐圈数据**，含配速/心率/步频/触地时间/垂直振幅/功率/温度 |
| 浏览器自动化 | ❌ **不必要** — 所有数据均通过 REST API 直接获取，无需 Playwright 爬网页 |

> **与高驰对比**：高驰 MCP 不提供逐圈 API，需用 Playwright 爬网页端计圈表。Garmin 的 REST API 更开放，计圈字段也更全。## 认证流程

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
