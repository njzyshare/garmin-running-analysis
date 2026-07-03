---
name: garmin-health-analysis
description: 查询 Garmin 健康数据并生成交互式 HTML 图表。支持 20+ 指标（睡眠阶段、身体电量/Body Battery、HRV、VO₂ max、训练准备度、身体成分、血氧），下载 FIT/GPX 路线文件，查询任意时间点的海拔/配速，生成训练分析报告，并提供天气/温湿度量化分析、不适指数/DI 评估。从"这周训练怎么样？"到"深度分析我的恢复 vs 训练负荷"。
version: 2.2.0
author: EversonL & Claude
homepage: https://github.com/njzyshare/garmin-running-analysis
agent_created: true
metadata: {"clawdbot":{"emoji":"⌚","requires":{"env":["GARMIN_EMAIL","GARMIN_PASSWORD"]},"install":[{"id":"garminconnect","kind":"python","package":"garminconnect","label":"Install garminconnect (pip)"},{"id":"fitparse","kind":"python","package":"fitparse","label":"Install fitparse (pip)"},{"id":"gpxpy","kind":"python","package":"gpxpy","label":"Install gpxpy (pip)"}]}}
---

# Garmin 健康分析

从 Garmin Connect 获取运动与健康数据，生成训练分析报告。

## 快速开始

### 安装

```bash
pip3 install garminconnect fitparse gpxpy
```

### 配置与登录

```bash
mkdir -p ~/.garmin-health-analysis
cp config.example.json ~/.garmin-health-analysis/config.json
# 编辑 ~/.garmin-health-analysis/config.json 填入你的 Garmin 邮箱、密码和区域

# 首次登录
python3 scripts/garmin_auth.py login
python3 scripts/garmin_auth.py status
```

凭证格式（`~/.garmin-health-analysis/config.json`）：

```json
{"email": "your-email@example.com", "password": "your-password", "region": "cn"}
```

Token 自动存储于 `~/.garmin-health-analysis/tokens/`，自动刷新。

---

## 数据获取命令

| 脚本 | 用途 | 常用参数 |
|------|------|---------|
| `garmin_data.py` | 活动/睡眠/HRV/身体电量/心率 | `activities --days 30`、`sleep --days 14`、`hrv --days 30`、`body_battery --days 30`、`summary --days 7`、`profile` |
| `garmin_data_extended.py` | VO₂max、训练准备度 | `max_metrics`、`training_readiness` |
| `garmin_chart.py` | 交互式仪表盘 | `dashboard --days 30` |
| `garmin_query.py` | 任意时间点海拔/配速 | 指定坐标与时间 |
| `garmin_activity_files.py` | 下载 FIT/GPX/TCX | 按活动 ID 下载 |
| `garmin_report.py` | 生成训练分析报告 | `--days 30`（月报）、`--days 7`（周报） |

---

## 训练报告能力（garmin_report.py）

本 skill 的核心价值——生成包含以下维度的综合 HTML 报告。

### 训练分析
- **当日/昨日训练卡片**：距离、配速、等强配速、心率、爬升、步频、步幅
- **等强配速**：爬升 >10m 时自动将山地配速折算为等效平路配速。逐公里坡度折算 + 心率个性化修正
- **计圈分段表**：逐公里展示配速/心率/步频/步幅/海拔，最快单圈绿色高亮
- **睡眠-恢复关联**：训练日 → 次日睡眠阶段（深睡/REM/浅睡/清醒）分析

### 周/月报告
- **滚动窗口统计**：7天一段的跑量和训练频率统计
- **训练日程表**：配速/等强配速、温度、湿度、DI 不适指数一览
- **恢复与健康趋势**：HRV、身体电量(Body Battery)、静息心率变化
- **天气量化分析**：不适指数(DI)分区间统计、高温高湿 vs 舒适日配速偏差对比

### PB 与目标
- **全项 PB 提取**：1KM / 1英里 / 5K / 10K / 半马 / 全马（Garmin API → 活动记录兜底）
- **训练目标**：半马/全马目标自动推断（比赛预测 → PB → 历史最佳）

### 优化建议
- **四维评分**：跑量、长距离、配速、训练频率
- **个性化建议**：基于评分给出针对性的训练方向提示

---

## 分析规则

| 规则 | 说明 |
|------|------|
| 输出层级 | 默认当日+昨日 → 询问是否需要周/月报告 |
| 首次分析 | 并行获取 profile + 7天摘要 + 30天活动 + HRV + 训练准备度 + VO₂max + 身体电量(Body Battery) |
| 睡眠日期 | Garmin 用醒来日期记录。训练日 D 的睡眠 = daily[D+1]["sleep"] |
| 自然周规则 | 不完整周不下结论 |
| 天气来源 | Garmin API 首选（约 90%+ 活动有数据），缺失时自动用 Open-Meteo 兜底 |

---

## references/ 参考文档索引

| 文件 | 内容 |
|------|------|
| `effort_pace.md` | 等强配速计算规则：方案A（逐公里坡度折算+心率修正）、方案B（整体兜底）、方案C（Naismith参考） |
| `weather_analysis.md` | 天气数据来源（Garmin API → Open-Meteo 兜底）、DI 公式与阈值 |
| `running_methodology.md` | 丹尼尔斯 VDOT、MAF 180、汉森法、亚索 800 训练体系 |
| `metrics_reference.md` | 身体电量(Body Battery) / 睡眠评分 / HRV / 静息心率的解读参考 |
| `splits_analysis.md` | 计圈数据 API 获取方式、启发式分析算法（三种检测模式） |
| `data_processing.md` | PB 提取逻辑、睡眠日期关联规则 |
| `api_reference.md` | Garmin API 端点列表、响应结构示例、认证流程 |
| `auth_and_troubleshooting.md` | 中国区 Garmin.cn 登录 monkey-patch、Token 管理、常见错误处理 |
| `report_templates.md` | 日/周/月报告的结构模板与建议生成器 |
| `training_metrics.md` | 运动类型代码（running/hike/walk 等）、心率 Zone 对照 |
| `faq_guide.md` | 常见问题→操作映射、用户基础信息表 |

---

## 版本

v2.2.0 — HRV 保持英文缩写。其他术语中文化：身体电量(Body Battery)、不适指数(DI)、静息心率(原RHR)。依赖：garminconnect、fitparse、gpxpy。协议：MIT。
