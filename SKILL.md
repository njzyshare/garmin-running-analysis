---
name: garmin-health-analysis
description: 查询 Garmin 健康数据并生成交互式 HTML 图表。支持 20+ 指标（睡眠阶段、Body Battery、HRV、VO₂ max、训练准备度、身体成分、血氧），下载 FIT/GPX 路线文件，查询任意时间点的海拔/配速，生成训练分析报告，并提供天气/温湿度量化分析、DI 不适指数评估。从"这周训练怎么样？"到"深度分析我的恢复 vs 训练负荷"。
version: 2.0.0
author: EversonL & Claude
homepage: https://github.com/njzyshare/garmin-running-analysis
agent_created: true
metadata: {"clawdbot":{"emoji":"⌚","requires":{"env":["GARMIN_EMAIL","GARMIN_PASSWORD"]},"install":[{"id":"garminconnect","kind":"python","package":"garminconnect","label":"Install garminconnect (pip)"},{"id":"fitparse","kind":"python","package":"fitparse","label":"Install fitparse (pip)"},{"id":"gpxpy","kind":"python","package":"gpxpy","label":"Install gpxpy (pip)"}]}}
---

# Garmin 健康分析

从 Garmin Connect 查询健康指标，生成训练分析报告。
集成天气量化分析、不适指数（DI）评估、科学训练方法论参考。

> **详细参考**：天气分析、指标解读、训练方法论、问答指南等分支逻辑已拆分到 `references/` 目录。
> - `references/running_methodology.md` — 丹尼尔斯 / MAF / 汉森 / 亚索 800 等训练法
> - `references/weather_analysis.md` — DI 公式、阈值、采集流程
> - `references/metrics_reference.md` — Body Battery / 睡眠 / HRV / 静息心率详解
> - `references/faq_guide.md` — 问答映射表 + 用户基础信息表
> - `references/report_templates.md` — 报告结构模板
> - `docs/技术参考.md` — 代码实现细节、API 参考、计圈启发式分析

---

## 安装（首次使用）

### 依赖安装

```bash
pip3 install garminconnect fitparse gpxpy
```

### 配置凭证

凭据文件独立存放在 `~/.clawdbot/garmin-config/config.json`：

```json
{
  "email": "your-email@example.com",
  "password": "your-password",
  "region": "cn"
}
```

`region` 可选 `"cn"`（中国区，默认）或 `"intl"`（国际区）。切换区域需重新登录。

### 登录认证

```bash
# 首次登录
python3 scripts/garmin_auth.py login --email YOUR_EMAIL --password YOUR_PASSWORD

# 查看状态
python3 scripts/garmin_auth.py status
```

Token 存储在 `~/.clawdbot/garmin-tokens.json`，自动刷新。

---

## 获取数据

| 命令 | 功能 |
|------|------|
| `garmin_data.py sleep --days 14` | 睡眠数据 |
| `garmin_data.py body_battery --days 30` | Body Battery |
| `garmin_data.py hrv --days 30` | HRV 数据 |
| `garmin_data.py heart_rate --days 7` | 静息/最大/最小心率 |
| `garmin_data.py activities --days 30` | 活动记录（仅跑步类） |
| `garmin_data.py stress --days 7` | 压力水平 |
| `garmin_data.py summary --days 7` | 综合摘要（含均值） |
| `garmin_data.py profile` | 用户基本信息 |
| `garmin_data_extended.py training_readiness` | 训练准备度 |
| `garmin_data_extended.py max_metrics` | VO₂max 等体能指标 |
| `garmin_data_extended.py body_composition --date YYYY-MM-DD` | 身体成分 |
| `garmin_activity_files.py download --activity-id N --format fit` | 下载 FIT 文件 |

> 更多扩展命令见 `docs/技术参考.md`。

### 图表生成

```bash
python3 scripts/garmin_chart.py dashboard --days 30 --output ~/report.html
```

---

## 分析报告流程

### 输出层级

| 用户请求 | 数据范围 | 输出方式 |
|---------|---------|---------|
| 默认/当日 | 今日 + 昨日 | 对话框完整报告 |
| "这周训练怎么样？" | 本周 + 历史 7 天 | 周报告 |
| "上个月训练分析" | 近 30 天 | 月报告 |

### 首次分析流程

并行获取以下数据构建用户画像：profile、summary(7d)、activities(30d)、hrv(7d)、training_readiness、max_metrics、body_battery(30d)。

从上述数据提取：VO₂max、预测成绩、PB、静息心率、HRV 基线、训练准备度、近 7/30 天跑量。

**PB 双来源**：Garmin API 优先，`extract_pb_from_activities()` 活动记录补充。

### 睡眠日期规则

Garmin 用**醒来日期**记录睡眠。18号入睡→19号醒来→Garmin 记为 19 号→关联 18 号训练分析。

代码：`_sleep_for_training(date_D)` → `daily[D+1]["sleep"]`

### 训练时间排序

一日多练时按 `startTimeLocal` GPS 时间顺序排列，不标注"第一次/第二次"。

### 自然周跑量规则

**不完整周不下结论**。周三查本周 30km → "预计全周 60-70km，暂无法判断是否达标"。

---

## 天气与 DI 分析

详见 `references/weather_analysis.md`。

### 核心要点

- DI = T - 0.55 × (1 - 0.01 × H) × (T - 14.5)
- DI < 17 最佳，> 19 明显影响
- **分析优先级**：前 3 天跑量 > 睡眠质量 > 训练意图 > 天气

---

## 训练建议参考

详见 `references/running_methodology.md`。

分析报告中的训练建议从以下维度生成：
1. **E 跑占比**：是否达周跑量 70%+
2. **SOS 节奏**：一周 2-3 次关键课是否均匀分布
3. **累积疲劳**：是否连续 3+ 天训练未安排休息
4. **长距离**：4 周内是否有 20km+ 长跑
5. **亚索验证**：间歇成绩与目标匹配度

---

## 报告模板

详见 `references/report_templates.md`。

---

## 核心指标速查

详见 `references/metrics_reference.md`。

---

## 问答指南

详见 `references/faq_guide.md`。

---

## 故障排除

- **"无效凭证"**：检查邮箱/密码，在 Garmin Connect 网页端验证
- **"Token 过期"**：重新 `garmin_auth.py login`
- **"请求频繁"**：Garmin 限频，稍等几分钟
- **区域切换**：`config.json` 改 `region` 字段，重新登录
- **数据缺失**：部分指标需特定设备支持

### 频率限制

Garmin API 约每 10 分钟 50-100 次请求。**最佳实践**：本地缓存数据、勿频繁轮询、使用日期范围查询而非逐日循环。

---

## 版本信息

- **版本**：2.0.0
- **创建时间**：2026-01-25
- **最后更新**：2026-05-26
- **主要变更**：
  - v2.0.0: 重大重构
    - 新增 `references/` 目录：科学训练方法论、天气/DI 分析、指标参考、问答指南、报告模板
    - SKILL.md 轻量化：移除详细分支逻辑，改引用 `references/` 文件
    - 全技能清理个人数据，确保可共享
    - 新增科学训练建议框架（丹尼尔斯/MAF/汉森/亚索 800）
  - v1.8.3: 修复当日+睡眠分析显示过多天数
  - v1.8.2: 报告去乱标 + 天气评估强化
  - v1.8.1: PB 策略"API 优先 + 校验 + 分段修复"
  - v1.8.0: PB 数据源重构
  - v1.7.0: 默认完整报告到对话框
- **依赖**：garminconnect、fitparse、gpxpy
- **协议**：MIT
