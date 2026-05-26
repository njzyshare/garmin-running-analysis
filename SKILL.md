---
name: garmin-health-analysis
description: 查询 Garmin 健康数据并生成交互式 HTML 图表。支持 20+ 指标（睡眠阶段、Body Battery、HRV、VO₂ max、训练准备度、身体成分、血氧），下载 FIT/GPX 路线文件，查询任意时间点的海拔/配速，生成训练分析报告，并提供天气/温湿度量化分析、DI 不适指数评估。从"这周训练怎么样？"到"深度分析我的恢复 vs 训练负荷"。
version: 2.0.2
author: EversonL & Claude
homepage: https://github.com/njzyshare/garmin-running-analysis
agent_created: true
metadata: {"clawdbot":{"emoji":"⌚","requires":{"env":["GARMIN_EMAIL","GARMIN_PASSWORD"]},"install":[{"id":"garminconnect","kind":"python","package":"garminconnect","label":"Install garminconnect (pip)"},{"id":"fitparse","kind":"python","package":"fitparse","label":"Install fitparse (pip)"},{"id":"gpxpy","kind":"python","package":"gpxpy","label":"Install gpxpy (pip)"}]}}
---

# Garmin 健康分析

从 Garmin Connect 查询健康指标，生成训练分析报告。集成天气量化分析、DI 评估、科学训练方法论。

> 所有分支逻辑和技术细节已拆分到 `references/` 目录，使用时按需加载：
> - **训练法**：`references/running_methodology.md` — 丹尼尔斯 / MAF / 汉森 / 亚索 800
> - **天气**：`references/weather_analysis.md` — DI 公式、阈值、采集流程
> - **指标**：`references/metrics_reference.md` — Body Battery / 睡眠 / HRV
> - **问答**：`references/faq_guide.md` — 问答映射 + 用户信息表
> - **模板**：`references/report_templates.md` — 报告结构模板
> - **日志**：`references/splits_analysis.md` — 计圈启发式分析
> - **API**：`references/api_reference.md` — Garmin API 端点与响应结构
> - **认证**：`references/auth_and_troubleshooting.md` — 中国区登录 / 错误处理
> - **数据处理**：`references/data_processing.md` — PB 提取 / 睡眠关联

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

v2.0.2 — 2026-05-26。依赖：garminconnect、fitparse、gpxpy。协议：MIT。
