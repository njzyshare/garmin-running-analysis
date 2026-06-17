---
name: garmin-health-analysis
description: 查询 Garmin 健康数据并生成交互式 HTML 图表。支持 20+ 指标（睡眠阶段、Body Battery、HRV、VO₂ max、训练准备度、身体成分、血氧），下载 FIT/GPX 路线文件，查询任意时间点的海拔/配速，生成训练分析报告，并提供天气/温湿度量化分析、DI 不适指数评估。从"这周训练怎么样？"到"深度分析我的恢复 vs 训练负荷"。
version: 2.1.0
author: EversonL & Claude
homepage: https://github.com/njzyshare/garmin-running-analysis
agent_created: true
metadata: {"clawdbot":{"emoji":"⌚","requires":{"env":["GARMIN_EMAIL","GARMIN_PASSWORD"]},"install":[{"id":"garminconnect","kind":"python","package":"garminconnect","label":"Install garminconnect (pip)"},{"id":"fitparse","kind":"python","package":"fitparse","label":"Install fitparse (pip)"},{"id":"gpxpy","kind":"python","package":"gpxpy","label":"Install gpxpy (pip)"}]}}
---

# Garmin 健康分析

从 Garmin Connect 查询健康指标，生成训练分析报告。集成天气量化分析、DI 评估、科学训练方法论。

> 各模块的详细技术文档见 `references/` 目录。

---

## 核心功能

### 1. 训练报告（garmin_report.py）
- **当日/昨日训练分析**：自动识别最近两次跑步活动，展示距离、配速、心率、爬升、天气影响
- **等强配速**：基于计圈爬升数据，将山地/坡路训练折算为等效平路配速，>10m爬升自动计算
- **计圈分段分析**：逐公里展示配速/心率/步频/步幅/海拔，标记最快单圈
- **睡眠-恢复关联**：训练日 → 次日睡眠阶段分析（深睡/REM/浅睡/清醒）
- **周/月报告**：滚动7天窗口跑量统计、周训练日程表、恢复与健康趋势
- **天气量化**：自动获取训练地点天气，计算 DI（不适指数）量化配速影响
- **DI 配速偏差分析**：高温高湿日 vs 舒适日的配速差异对比
- **PB 展示**：Garmin API 全项 PB 提取 + 历史活动记录兜底
- **目标参考**：半马/全马训练目标，自动从比赛预测/PB/历史最佳推断
- **多维度评分**：跑量、长距离、配速、训练频率四维评分，生成个性化优化建议

### 2. 健康数据查询（garmin_data.py）
- 活动记录列表、睡眠数据、HRV、Body Battery、心率区间分布、压力/呼吸等

### 3. 扩展指标（garmin_data_extended.py）
- VO₂max 趋势、训练准备度、最大耗氧量等

### 4. 数据可视化（garmin_chart.py）
- 交互式仪表盘：HRV/睡眠/BB/心率区间/配速趋势/周跑量/训练准备度

### 5. 时间点查询（garmin_query.py）
- 任意时间点海拔/配速查询，活动轨迹详情

### 6. 活动文件（garmin_activity_files.py）
- FIT/GPX/TCX 格式活动文件下载与本地解析

---

## 安装

```bash
pip3 install garminconnect fitparse gpxpy
```

凭证存于 `~/.clawdbot/garmin-config/config.json`（`region` 可选 `"cn"`/`"intl"`）：

```json
{"email": "your-email@example.com", "password": "your-password", "region": "cn"}
```

```bash
python3 scripts/garmin_auth.py login --email YOUR_EMAIL --password YOUR_PASSWORD
python3 scripts/garmin_auth.py status
```

Token 自动存储于 `~/.clawdbot/garmin-tokens.json`。

---

## 基础命令

| 脚本 | 常用参数 |
|------|---------|
| `garmin_data.py activities --days 30` | 活动记录 |
| `garmin_data.py summary --days 7` | 综合摘要 |
| `garmin_data.py hrv --days 30` | HRV 数据 |
| `garmin_data.py body_battery --days 30` | Body Battery |
| `garmin_data.py sleep --days 14` | 睡眠数据 |
| `garmin_data.py profile` | 用户信息 |
| `garmin_data_extended.py max_metrics` | VO₂max |
| `garmin_data_extended.py training_readiness` | 训练准备度 |
| `garmin_chart.py dashboard --days 30` | 图表仪表盘 |

---

## 分析流程

**输出层级**：默认当日+昨日 → 询问是否需要周/月报告。周/月直接输出。

**首次分析**：并行 profile + summary(7d) + activities(30d) + hrv(7d) + training_readiness + max_metrics + body_battery(30d)。

**睡眠日期规则**：Garmin 用醒来日期记录。训练日 D 的睡眠 `= daily[D+1]["sleep"]`。

**自然周规则**：不完整周不下结论。

---

## 版本

v2.1.0 — 配置：garminconnect、fitparse、gpxpy。协议：MIT。

---

## 安装

```bash
pip3 install garminconnect fitparse gpxpy
```

凭证存于 `~/.clawdbot/garmin-config/config.json`（`region` 可选 `"cn"`/`"intl"`）：

```json
{"email": "your-email@example.com", "password": "your-password", "region": "cn"}
```

```bash
python3 scripts/garmin_auth.py login --email YOUR_EMAIL --password YOUR_PASSWORD
python3 scripts/garmin_auth.py status
```

Token 自动存储于 `~/.clawdbot/garmin-tokens.json`。

---

## 基础命令

| 脚本 | 常用参数 |
|------|---------|
| `garmin_data.py activities --days 30` | 活动记录 |
| `garmin_data.py summary --days 7` | 综合摘要 |
| `garmin_data.py hrv --days 30` | HRV 数据 |
| `garmin_data.py body_battery --days 30` | Body Battery |
| `garmin_data.py sleep --days 14` | 睡眠数据 |
| `garmin_data.py profile` | 用户信息 |
| `garmin_data_extended.py max_metrics` | VO₂max |
| `garmin_data_extended.py training_readiness` | 训练准备度 |
| `garmin_chart.py dashboard --days 30` | 图表仪表盘 |

---

## 分析流程

**输出层级**：默认当日+昨日 → 询问是否需要周/月报告。周/月直接输出。

**首次分析**：并行 profile + summary(7d) + activities(30d) + hrv(7d) + training_readiness + max_metrics + body_battery(30d)。

**睡眠日期规则**：Garmin 用醒来日期记录。训练日 D 的睡眠 `= daily[D+1]["sleep"]`。

**自然周规则**：不完整周不下结论。

---

## 版本

v2.1.0 — 2026-06-17。依赖：garminconnect、fitparse、gpxpy。协议：MIT。
