---
name: garmin-health-analysis
description: 查询 Garmin 健康数据并生成交互式 HTML 图表。支持 20+ 指标（睡眠阶段、Body Battery、HRV、VO₂ max、训练准备度、身体成分、血氧），下载 FIT/GPX 路线文件，查询任意时间点的海拔/配速，生成训练分析报告，并提供天气/温湿度量化分析、DI 不适指数评估。从"这周训练怎么样？"到"深度分析我的恢复 vs 训练负荷"。
version: 1.8.3
author: EversonL & Claude
homepage: https://github.com/eversonl/ClawdBot-garmin-health-analysis
agent_created: true
metadata: {"clawdbot":{"emoji":"⌚","requires":{"env":["GARMIN_EMAIL","GARMIN_PASSWORD"]},"install":[{"id":"garminconnect","kind":"python","package":"garminconnect","label":"Install garminconnect (pip)"},{"id":"fitparse","kind":"python","package":"fitparse","label":"Install fitparse (pip)"},{"id":"gpxpy","kind":"python","package":"gpxpy","label":"Install gpxpy (pip)"}]}}
---

# Garmin 健康分析

从 Garmin Connect 查询健康指标，生成交互式 HTML 图表和训练分析报告。
集成天气量化分析（Open-Meteo）、不适指数（DI）评估、训练表现综合诊断。

本 Skill 支持**两种部署方式**：

1. **Clawdbot Skill（本指南）** — 配合 WorkBuddy/Clawdbot 实现自动化和主动健康监控
2. **MCP 服务器**（[见附录 D：MCP 服务器配置](#附录-dmcp-服务器配置)）— 配合标准 Claude Desktop 作为 MCP 服务器使用

---

## 安装（首次使用）

### 1. 安装依赖

```bash
pip3 install garminconnect fitparse gpxpy
```

### 2. 配置凭证

有三种方式提供 Garmin Connect 账号凭证：

#### 方式 A：WorkBuddy 配置

在 WorkBuddy 的 Skill 设置中配置 `GARMIN_EMAIL` 和 `GARMIN_PASSWORD` 环境变量。

#### 方式 B：本地配置文件（推荐）

凭据文件已移出 skill 目录，保存在独立路径：

```bash
# 创建配置文件目录
mkdir -p ~/.clawdbot/garmin-config

# 复制模板并编辑
cp config.example.json ~/.clawdbot/garmin-config/config.json

# 编辑 ~/.clawdbot/garmin-config/config.json 填入邮箱和密码
```

**~/.clawdbot/garmin-config/config.json：**
```json
{
  "email": "your-email@example.com",
  "password": "your-password",
  "region": "cn"
}
```

**region** 字段说明：
- `"cn"` — 中国区 (`connect.garmin.cn`)，适用于中国大陆 Garmin 账号
- `"intl"` — 国际区 (`connect.garmin.com`)，适用于海外 Garmin 账号
- 默认为 `"cn"`

**注意**：`config.json` 包含凭据，已存放在独立目录 `~/.clawdbot/garmin-config/`，与 skill 分离，请勿提交到 Git。

#### 方式 C：命令行参数

```bash
python3 scripts/garmin_auth.py login \
  --email YOUR_EMAIL@example.com \
  --password YOUR_PASSWORD
```

### 3. 登录认证

```bash
python3 scripts/garmin_auth.py login
```

凭证读取优先级（从高到低）：
1. 命令行参数（`--email`、`--password`）
2. 本地配置文件（`~/.clawdbot/garmin-config/config.json`）
3. 环境变量（`GARMIN_EMAIL`、`GARMIN_PASSWORD`）

会话 Token 存储在 `~/.clawdbot/garmin-tokens.json`，会自动刷新。

查看认证状态：

```bash
python3 scripts/garmin_auth.py status
```

## 获取数据

使用 `scripts/garmin_data.py` 获取 JSON 格式数据：

```bash
# 睡眠数据（默认近7天）
python3 scripts/garmin_data.py sleep --days 14

# Body Battery（Garmin 恢复指标）
python3 scripts/garmin_data.py body_battery --days 30

# HRV 数据
python3 scripts/garmin_data.py hrv --days 30

# 心率数据（静息、最大、最小）
python3 scripts/garmin_data.py heart_rate --days 7

# 活动/训练记录（仅跑步类）
python3 scripts/garmin_data.py activities --days 30

# 压力水平
python3 scripts/garmin_data.py stress --days 7

# 综合摘要（含平均值）
python3 scripts/garmin_data.py summary --days 7

# 自定义日期范围
python3 scripts/garmin_data.py sleep --start 2026-01-01 --end 2026-01-15

# 用户信息
python3 scripts/garmin_data.py profile
```

输出为 JSON 格式到 stdout，可用于程序化解析。

## 生成图表

使用 `scripts/garmin_chart.py` 生成交互式 HTML 可视化图表：

```bash
# 睡眠分析（时长 + 评分）
python3 scripts/garmin_chart.py sleep --days 30

# Body Battery 恢复图表（色标）
python3 scripts/garmin_chart.py body_battery --days 30

# HRV 与静息心率趋势
python3 scripts/garmin_chart.py hrv --days 90

# 活动摘要（按类型、卡路里，仅跑步类）
python3 scripts/garmin_chart.py activities --days 30

# 完整仪表盘（全部4张图表）
python3 scripts/garmin_chart.py dashboard --days 30

# 保存到指定文件
python3 scripts/garmin_chart.py dashboard --days 90 --output ~/Desktop/garmin-health.html
```

图表会自动在默认浏览器中打开。使用 Chart.js 实现，采用渐变设计风格、统计卡片和交互式提示。

## 扩展能力

### 时间点查询

使用 `scripts/garmin_query.py` 查询任意时间点的健康数据：

```bash
# 查询特定时间的心率
python3 scripts/garmin_query.py heart_rate "3:00 PM" --date 2026-01-24

# 压力水平
python3 scripts/garmin_query.py stress "14:30"

# Body Battery
python3 scripts/garmin_query.py body_battery "10:00 AM" --date 2026-01-23

# 步数
python3 scripts/garmin_query.py steps "17:00"
```

**支持的时间格式：**
- `3:00 PM`、`3 PM`（12小时制）
- `15:00`、`15:30:45`（24小时制）
- `2026-01-24 15:30`（完整日期时间）

### 扩展指标

使用 `scripts/garmin_data_extended.py` 获取更多健康指标：

```bash
# 训练准备度
python3 scripts/garmin_data_extended.py training_readiness

# 训练状态（负荷、VO₂ max 趋势）
python3 scripts/garmin_data_extended.py training_status

# 耐力评分
python3 scripts/garmin_data_extended.py endurance_score

# 爬坡评分
python3 scripts/garmin_data_extended.py hill_score

# 最大摄氧量等
python3 scripts/garmin_data_extended.py max_metrics

# 身体成分（体重、体脂率、肌肉量、BMI）
python3 scripts/garmin_data_extended.py body_composition --date 2026-01-24

# 体重历史
python3 scripts/garmin_data_extended.py weigh_ins --start 2026-01-01 --end 2026-01-24

# 血氧（SPO2）
python3 scripts/garmin_data_extended.py spo2 --date 2026-01-24

# 呼吸率
python3 scripts/garmin_data_extended.py respiration

# 详细步数（时间序列）
python3 scripts/garmin_data_extended.py steps --date 2026-01-24

# 爬楼层数
python3 scripts/garmin_data_extended.py floors

# 强度分钟
python3 scripts/garmin_data_extended.py intensity_minutes

# 水分摄入
python3 scripts/garmin_data_extended.py hydration

# 详细压力（全天时间序列）
python3 scripts/garmin_data_extended.py stress_detailed

# 日内心率（所有采样点）
python3 scripts/garmin_data_extended.py hr_intraday

# 体能年龄
python3 scripts/garmin_data_extended.py fitness_age
```

### 活动文件分析（FIT/GPX）

使用 `scripts/garmin_activity_files.py` 下载和分析活动文件：

```bash
# 下载 FIT 文件
python3 scripts/garmin_activity_files.py download --activity-id 12345678 --format fit

# 下载 GPX 文件（GPS 路线可视化）
python3 scripts/garmin_activity_files.py download --activity-id 12345678 --format gpx

# 下载 TCX 文件
python3 scripts/garmin_activity_files.py download --activity-id 12345678 --format tcx

# 解析 FIT 文件（详细指标）
python3 scripts/garmin_activity_files.py parse --file /tmp/activity_12345678.fit

# 解析 GPX 文件（GPS 轨迹）
python3 scripts/garmin_activity_files.py parse --file /tmp/activity_12345678.gpx
```

**FIT 文件包含的内容：**
- GPS 坐标（经纬度）
- 海拔
- 心率
- 步频 / 踏频
- 功率（骑行）
- 速度与配速
- 温度
- 分段数据

---

## 分析报告流程

### 报告输出层级（重要）

**默认行为**：直接输出当日+昨日的训练分析报告到对话框，不写本地文件。

| 用户请求 | 数据范围 | 获取内容 |
|---------|---------|---------|
| 默认/当日 | 今天 + 昨天 | 当日训练 + 睡眠 + 简要周概况 |
| 周报告 | 本周 + 历史7天 | 周训练质量 + 天气 + 负荷评估 |
| 月报告 | 本月 + 近30天 | 月度趋势 + 天气变化 + 优化建议 |

**询问策略**：
- 当用户请求"分析训练"但未指定范围时，先输出当日/昨日分析，然后询问：「需要输出本周/本月的详细报告吗？」
- 当用户明确说"这周训练怎么样"，直接输出周报告
- 当用户明确说"上个月训练分析"，直接输出月报告

### 一、首次分析（用户基础信息收集）

**首次分析时**，必须先并行拉取以下数据，再生成报告：

```bash
# 用户基本信息
python3 scripts/garmin_data.py profile

# 综合摘要（近7天健康数据）
python3 scripts/garmin_data.py summary --days 7

# 活动记录（近30天，仅跑步类）
python3 scripts/garmin_data.py activities --days 30

# HRV 趋势（近7天）
python3 scripts/garmin_data.py hrv --days 7

# 训练准备度（扩展指标）
python3 scripts/garmin_data_extended.py training_readiness

# 最大摄氧量与体能指标
python3 scripts/garmin_data_extended.py max_metrics

# Body Battery 趋势（近30天，恢复分析核心）
python3 scripts/garmin_data.py body_battery --days 30
```

从上述数据提取用户基础信息：

| 字段 | 来源 | 用途 |
|------|------|------|
| VO₂max | max_metrics | 体能级别 |
| 预测成绩（5K/10K/半马/全马）| profile 或历史活动推算 | **默认目标** |
| 个人 PB（历史最佳） | Garmin `personal_record` API + 历史活动记录双来源 | **训练目标参考** |
| 静息心率 | summary | 心血管适能基准 |
| HRV 均值 | hrv | 恢复状态基线 |
| 训练准备度 | training_readiness | **当前恢复状态** |
| 近7天跑量 | activities | 短期训练负荷 |
| 近30天跑量 | activities | 中期训练负荷 |

**PB 双来源说明**：
- **优先**：Garmin `get_personal_record()` API（官方记录，最权威）
- **补充/fallback**：`extract_pb_from_activities()` 从历史活动记录中按距离区间提取最快成绩
- 两个来源合并展示，API PB 若已存在则不被活动 PB 覆盖
- 活动 PB 在报告中带有 `(活动记录)` 标注以区分来源

### 睡眠日期规则（重要）

**Garmin 用"醒来日期"记录睡眠**，而非"入睡日期"。

| 入睡 | 醒来 | Garmin 记录日期 | 对应的训练日 |
|------|------|----------------|-------------|
| 18号晚 | 19号早 | **19号** | 18号 |
| 19号晚 | 20号早 | **20号** | 19号 |

因此在报告中，**18号的训练分析**关联的睡眠数据来自 Garmin **19号**的睡眠记录（即 18号入睡、19号醒来的那一夜）。

代码实现：`_sleep_for_training(training_date_D)` 返回 `daily[D+1]["sleep"]`。

> **为什么这样设计**：18号训练后，当晚是否休息充分，直接反映在"19号醒来"的睡眠质量上。将睡眠与训练日关联（而非第二天），有助于评估该日训练的恢复状况。

### 训练时间顺序规则

**一天多练时，不主观判断训练顺序**。按以下规则处理：

1. **GPS 时间优先**：若有 GPS 数据，使用活动的 `startTimeLocal` 字段判断先后
2. **若无 GPS**：按心率/配速等数据特征推断（早训多为 E 跑，晚训多为强度课）
3. **同类型训练**：按活动开始时间排序
4. **报告呈现**：不标注"第一次/第二次"，直接按时间顺序列出所有训练

### 二、天气数据采集流程

**每次分析关键训练（节奏跑/长距离/间歇）时，必须采集训练当天的天气数据。**

Garmin API 不直接提供历史天气数据，可通过以下流程获取：

1. **从活动记录提取坐标**：每个活动包含 GPS 坐标（经纬度），从 `activities` 输出的 `startLatitude` / `startLongitude` 字段获取
2. **用坐标查询开源天气 API**（推荐 Open-Meteo Archive API，免费、无需 API Key）：
   ```
   https://archive-api.open-meteo.com/v1/archive?
     latitude={lat}&longitude={lon}&
     start_date={YYYY-MM-DD}&end_date={YYYY-MM-DD}&
     hourly=temperature_2m,relative_humidity_2m,precipitation,weather_code&
     timezone=Asia/Shanghai
   ```
3. **WMO 天气代码→中文映射**：
   ```python
   wmo = {0:"晴",1:"晴间多云",2:"多云",3:"阴",
          45:"雾",51:"小毛毛雨",53:"中毛毛雨",61:"小雨",
          63:"中雨",80:"阵雨",81:"中阵雨",95:"雷暴"}
   ```
4. **训练时段取数**：按训练时长估算时段（如 30K≈5-9am，20K≈5-8am，10K≈5-7am）
5. **若无坐标可用**：询问用户训练大致位置，用城市名拼坐标查询

**分析原则**：
- **疲劳 > 天气 > 训练意图**：温湿度影响表现是合理推断，但同温湿度的两场训练表现可能截然不同（主因通常是累积疲劳而非天气变化）。关键课（MP/长距离）前的 1-3 天跑量和休息日安排是更重要的变量。
- 同时考虑累积疲劳、训练意图、睡眠因素进行综合解读
- 不将单次表现差异全部归因于天气——优先核查：①前3天跑量 ②睡眠质量 ③训练意图

### 三、温湿度与不适指数（DI）量化分析

> 本节提供温湿度量化分析框架，基于夏季晨间训练数据推导。其他气候区域需根据本地条件重新校准阈值。

#### 不适指数（Discomfort Index）公式

```
DI = T - 0.55 × (1 - 0.01 × H) × (T - 14.5)
其中 T = 温度(°C), H = 相对湿度(%)
```

DI 越低越舒适，>=21 时即使短距离也会明显感知。

#### DI 参考阈值（基于实际训练数据）

| DI 范围 | 影响级别 | 典型表现 |
|---------|---------|---------|
| **< 17** | ✅ 最佳区 | 15-17°C + 60-80%RH → 正常发挥，可冲刺Best |
| **17 - 19** | ⚠️ 轻度影响 | 配速惩罚约+5~10s/km |
| **> 19** | 🔴 明显影响 | 配速惩罚可感知，但训练意图可部分抵消（如MP跑时意志可覆盖天气劣势） |

#### 温度量化影响（粗估公式）

```
基准温度: 17°C（晨间低温基准线）
  ≤18°C: 基准表现区
  20°C:  配速惩罚 +5s/km vs 17°C
  22°C:  配速惩罚 +10s/km vs 17°C（训练意图强时可忽略此惩罚）
```

#### 湿度量化影响（粗估公式）

```
同温下每+10%RH ≈ +3-5s/km 配速惩罚（中度可信，6-10场数据推导）
湿度 60-70% ≈ 最舒适，80-95% ≈ 可感知但非致命
```

#### 关键分析原则：疲劳 > 天气

典型例子（两场同温湿度 30K 对比）：
- 训练 A（前1天休息）→ 均配速较佳，完成质量高
- 训练 B（前3天连续跑~30km 累积疲劳）→ 均配速断崖下降

**结论**：纯温湿度解释力 < 10%，疲劳累积解释力 > 80%。**查天气前，先查前3天跑量。**

---

## 分析报告模板

### 输出行为约定

> **默认：直接输出完整分析报告到对话框，不写本地文件。**
>
> 报告末尾询问用户：「需要保存为本地 HTML 文件吗？」若用户确认，走以下流程。

**保存文件流程**：
1. 用户确认后，先问：「分析报告将保存在工作区下的 佳明数据分析 目录，是否确认？」
2. 用户可能回答：
   - 确认（直接使用默认目录）
   - 自定义（提供其他路径）
   - 拒绝保存

**核心规则**：
1. **不往 C 盘写文件。** 所有分析结果文件统一输出到用户指定的目录。
2. **不重新拉取数据。** 直接复用当前会话已有的分析结论和数据，整理成文件。
3. **保存 HTML 格式。** HTML 在手机、电脑、平板上均能直接打开查看，兼容性最好。包含 CSS 内联样式，不依赖外链。

**默认目录**：工作区根目录下的 `佳明数据分析\` 文件夹

**文件名规范**：
- 主文件：`训练分析报告_YYYYMMDD.html`（HTML 格式，CSS 内联）

### 报告结构概览

#### 简短报告（当日/昨日，默认）

```
## 📊 训练摘要
【一句话概括今日+昨日训练质量】

## 🏃 今日训练分析（YYYY-MM-DD）
【单次或多次训练详情 + 睡眠 + 天气】

## 😴 睡眠分析
【昨晚到今早的睡眠数据】

## 📈 昨日训练回顾（如有）
【昨日训练简要点评】

---
💡 需要输出本周/本月的详细报告吗？
```

#### 周报告（指定周报告时）

```
## 📊 训练摘要
【本周一句话概括 + 与历史均值对比】

## 🏃 本周训练详情
【各次训练详细分析 + 天气 + 配速/心率解读】

## 😴 睡眠与恢复
【Body Battery + HRV + 训练准备度趋势】

## 📈 周维度分析
【跑量统计 + 训练质量评分】

## 💡 优化建议
```

#### 月报告（指定月报告时）

```
## 📊 月度训练摘要
【本月一句话概括 + 与上月对比】

## 🏃 本月训练详情
【关键训练回顾 + 天气变化轨迹】

## 📈 月维度分析
【跑量趋势 + 训练质量评分 + 天气分布】

## 😴 恢复状态月度评估
【Body Battery + HRV + 训练准备度月度趋势】

## 💡 优化建议
```

### 用户基础信息表

```
## 用户基础信息

| 类别 | 参数 | 当前值 | 说明 |
|------|------|--------|------|
| 体能 | VO₂max | XX ml/kg/min | — |
| 阈值 | 阈值配速（MP） | X:XX/km | 对应阈值心率 |
| 阈值 | 乳酸阈心率 | XXX bpm | ≈ 最大心率×0.89 |
| 预估 | Garmin 预测全马 | X:XX:XX | **默认目标** |
| 预估 | Garmin 预测半马 | X:XX:XX | **默认目标** |
| 🎯 目标 | 半马目标 | X:XX | 训练参考目标 |
| 🎯 目标 | 全马目标 | X:XX | 训练参考目标 |
| 📌 PB | 5K/10K/半马/全马最佳 | — | 见 PB 数据 |
| 健康 | 安静心率 | XX bpm | 近7天均值 |
| 健康 | HRV 均值 | XX ms | 近7天均值 |
| 健康 | 训练准备度 | X/100 | 扩展指标 |
| 训练 | 近7天跑量 | XX km | — |
| 训练 | 近30天跑量 | XXX km | — |
| 训练 | 历史周均跑量 | XX.X km | 近8–12周均值 |
| 配速 | E跑 配速 | X:XX/km | HR ≤ LT×0.78 |
| 配速 | MP 配速 | X:XX/km | 阈值配速 |
| 配速 | T跑 配速 | X:XX/km | 乳酸阈值配速 |

> **默认目标说明**：本报告以 Garmin 预测全马/半马为默认目标进行评估。
> **PB 来源优先级**：Garmin API → 历史活动记录（标注"活动记录"）
```

### 单次训练分析格式

```
🏃 Running — YYYY-MM-DD 训练类型（XX.XXkm / XX:XX）
========================================
均配速: X:XX/km | 最佳1km: X:XX/km
均心率: XXX bpm | 最高心率: XXX bpm
均步频: XXX spm | 均步幅: X.XX m
海拔升降: +Xm / -Xm | 热量: XXX kcal

▶ 均配速解读：
  - 均配速 X:XX/km vs 阈值 X:XX/km → 差 XX秒/km
  - HR XXX bpm 对应的心率区间分析

▶ 温湿度影响量化：
  - 训练日天气：温度 XX°C / 湿度 XX% / DI=X.X
  - 本次 DI vs 基准 DI 16.5 → 预估配速影响 ±X s/km
```

### 计圈数据分析

Garmin 活动数据的计圈（splits/laps）需要启发式分析来识别最合适的呈现方式。详见 `docs/技术参考.md`。

---

## 自然周跑量规则

**核心原则：不完整周不下结论，等周末数据补齐后再判断。**

| 场景 | 处理方式 |
|------|---------|
| 周三查本周，30km | "周三仅3天，预计全周可达60-70km，**暂时无法判断是否达标**" |
| 周日查本周，68km | "周日最终68km，距目标差2km，**未达标**" |

---

## 问答指南

| 用户提问 | 操作 |
|---------|------|
| "分析训练" / "看看训练" | 当日+昨日分析 → 询问是否需要周/月报告 |
| "这周训练怎么样？" | 直接输出周报告 |
| "上个月训练分析" | 直接输出月报告 |
| "昨晚睡得怎么样？" | `summary --days 1`，报告睡眠时长 + 评分 |
| "这周恢复得如何？" | `body_battery --days 7`，报告平均值 + 趋势 |
| "看看我上个月的健康数据" | `chart.py dashboard --days 30` |
| "我的 HRV 在改善吗？" | `hrv --days 30`，分析趋势 |
| "这周做了哪些训练？" | `activities --days 7`，列出活动详情 |
| "我的静息心率怎么样？" | `heart_rate --days 7`，报告平均值 + 趋势 |
| "我的周跑量怎么样？" | 历史周跑量统计 |
| "昨天的训练受天气影响吗？" | 天气数据采集 + DI 量化分析 |

---

## 核心指标说明

### Body Battery 身体电量（0-100）

Garmin 基于 HRV、压力、睡眠和活动的专有恢复指标。身体电量在休息/睡眠期间"充电"，在活动/压力期间"放电"。

| 等级 | 范围 | 含义 | 建议 |
|------|------|------|------|
| **高** | 75-100 | 充分恢复，能量充沛 | 适合高强度训练 |
| **中** | 50-74 | 能量适中 | 适合常规训练 |
| **低** | 25-49 | 能量有限 | 轻量活动，注重恢复 |
| **极低** | 0-24 | 能量耗尽 | 优先休息与恢复 |

**需要关注的模式：**
- **每日峰值**（睡眠后的最高值）：反映夜间恢复质量
- **充电速度**（睡眠期间增长量）：充电慢 = 睡眠/恢复不佳
- **放电速度**（消耗速度）：快速放电 = 高压力/高强度
- **峰值持续 <50**：慢性恢复不足
- **连续 3+ 天峰值 <75**：累积疲劳

### 睡眠评分（0-100）

| 评分 | 质量 | 解读 |
|------|------|------|
| 90-100 | 优秀 | 最佳恢复性睡眠 |
| 80-89 | 良好 | 质量良好，有小问题 |
| 60-79 | 一般 | 足够但可改善 |
| 0-59 | 差 | 睡眠明显不足 |

### HRV 心率变异性

通常越高越好。反映自主神经系统平衡和恢复能力。

**按年龄的正常范围（腕式穿戴设备）：**

| 年龄 | 偏低 | 正常 | 偏高 |
|------|------|------|------|
| 30-39 | <20ms | 20-80ms | >80ms |
| 40-49 | <15ms | 15-60ms | >60ms |
| 50-59 | <12ms | 12-45ms | >45ms |

> 腕式 HRV 通常比胸带偏低。**个人基线比人群标准更重要。**

**解读要点：**
- **趋势比绝对值更重要** — 比较个人周/月平均值
- **HRV 下降趋势**（连续 3+ 天低于基线 10%）：累积压力、恢复差、疾病前兆或过度训练
- **急性下降**：睡眠差、饮酒、疾病、高强度训练、情绪压力

### 静息心率（bpm）

通常越低表示心血管适能越好。

| 体能水平 | 静息心率 |
|----------|----------|
| 运动员 | 40-55 bpm |
| 活跃成人 | 55-65 bpm |
| 普通成人 | 60-80 bpm |

**解读要点：**
- **趋势最重要**：连续几天升高 3-5+ bpm 提示累积疲劳、压力、生病或脱水
- **长期下降**：心血管适能提升

### 警示信号

- **连续低 HRV**（<15ms）→ 建议就医
- **睡眠呼吸率 >20 次/分** → 可能的呼吸问题
- **静息心率连续 3+ 天升高 5+ bpm** → 注意疾病/过度训练
- **Body Battery 连续 5+ 天峰值 <75** → 慢性恢复不足

---

## 故障排除

### 认证问题

- **"无效凭证"**：检查邮箱/密码，尝试在 Garmin Connect 网页端登录
- **"Token 已过期"**：重新登录：`python3 scripts/garmin_auth.py login`
- **"请求过于频繁"**：Garmin 有频率限制，稍等几分钟再试

### 区域选择（中国区 / 国际区）

在 `~/.clawdbot/garmin-config/config.json` 中设置 `region` 字段：

```json
{
  "email": "your-email@example.com",
  "password": "your-password",
  "region": "cn"
}
```

- `"cn"` — 中国区（默认），使用 `connect.garmin.cn`
- `"intl"` — 国际区，使用 `connect.garmin.com`

切换区域后需要**重新登录**，不同区域的 token 不互通。

### 中国区（garmin.cn）技术说明

本 Skill 通过 monkey-patch 支持中国区 Garmin 账号登录。具体实现见 `docs/技术参考.md`。

### 数据缺失

- 部分指标需要特定 Garmin 设备（Body Battery 需要支持 HRV 的设备）
- 历史数据可能因未佩戴设备而出现空白

### 频率限制

Garmin 对 API 实施频率限制：
- 大约每 10 分钟 50-100 次请求
- 过量请求可能触发临时 IP/账号封锁（通常 15-60 分钟）

**最佳实践：**
- 本地缓存数据
- 勿频繁轮询（每小时最多一次）
- 使用日期范围查询而非逐日循环

---

## 隐私说明

- 凭证本地存储在 `~/.clawdbot/garmin-tokens.json`
- 会话 Token 会自动刷新
- 数据仅发送至 Garmin 官方服务器
- 可随时删除 Token 文件以撤销访问权限
- **切勿提交凭据文件到 Git 仓库**
- **注意：获取的用户信息请过滤或匿名化处理后再使用**

---

## 版本信息

- **创建时间**：2026-01-25
- **最后更新**：2026-05-20
- **版本**：1.8.3
- **主要变更**：
  - v1.8.3: 修复「一、当日训练+睡眠分析」显示过多天数
    - **Bug**：`render_report` 中 section 一遍历了 `run_activities`（全周期30天），而非只显示今天+昨天
    - **修复**：新增 `recent_cutoff = today - 2 days` 过滤，只渲染 `date >= recent_cutoff` 的活动
    - **自检其他章节**：二章节（当周整体评估，current+last week）→ 正常；三章节（天气数据，全周期）→ 正常；四章节（DI分析，全周期）→ 正常
  - v1.8.2: 报告去乱标 + 天气评估强化 + 结尾追问
    - **重要：活动卡片不再自作主张分类**。删除"训练强度"标签（之前按配速硬编码为"高强度/中高强度/中等强度/有氧强度/恢复强度"），只展示原始数据（配速、心率、距离、爬升）
    - 天气DI评估已内置于每条训练卡片中
    - 报告末尾新增「六、💬 后续分析选项」，引导用户选择分段分析或周/月维度分析
    - 对话框概览同步清理，不写未经核实的训练类型标签
  - v1.8.1: PB 策略改为"API 优先 + 校验 + 分段修复兜底"
    - **新策略**：半马/全马直接信任 API；5K/10K 先取 API，再校验，异常时用分段插值修复
    - `extract_personal_records()`: 提取所有 typeId（2=5K, 3=10K, 5=半马, 6=全马），每条记录附带 `validated` 布尔值和 `validation_reason` 说明
    - `_validate_api_pb()`: 新增 PB 校验函数，基于合理范围 + 已知错误值（5K=387秒, 10K=1313秒）双重检测
    - PB 合并策略反转：API PB 为初值 → 校验 → 无效时用分段插值替换，并在报告中显示 🔧分段修复 标签
    - 报告中 PB 行显示数据来源标签：(API) / 🔧分段修复 / ⚠️待核
  - v1.8.0: PB 数据源重构——活动分段插值为主，API 为兜底
    - **根因发现**：中国区 Garmin API typeId 2（5K）/3（10K）/4（15K）的 value 字段存储了错误的时间戳（prStartTimeGMT 异常），仅 typeId 6（全马）可靠
    - `extract_personal_records()`: 仅信任 typeId 6（全马），其余 typeId 全部跳过
    - `extract_pb_from_activities()`: 新增 `_interp_at_target()` 分段插值函数，从 lap splits 精确提取 5K/10K/半马/全马终点时间（通过跨目标距离的 lap 线性插值）
    - PB 历史活动额外 fetch：默认从 120 天历史中获取 PB 活动的 splits（解决 30 天周期内缺失历史 PB 的问题）
    - `fetch_all_data`: max_splits_activities 从 20 → 100，splits 获取门槛从 ≥3km → ≥5km（确保关键比赛活动被获取）
    - 全马 PB 合并策略：分段插值 PB 作为初值，API 全马 PB（终点计时毯，更精确）覆盖
  - v1.7.1: 修复 VO₂max/比赛预测/PB 无法获取问题
    - `extract_personal_records()`: 支持数组格式（中国区 Garmin API 返回 typeId+value）
    - `_format_race_predictions()`: 修复半马/全马时间格式化（支持 >60 分钟）
    - `_seconds_to_time_str()`: 新增通用时间格式化函数
    - 渲染层: 优化比赛预测去重逻辑
  - v1.7.0: 默认直接输出完整报告到对话框（不再只有摘要）
  - 报告开头包含训练摘要信息
  - 优化报告输出层级：默认当日/昨日 → 询问是否需要周/月报告
  - 一日多练时不主观判断顺序，按 GPS 时间排序
  - 去除个人信息，可共享给其他电脑
  - 代码详细逻辑分离到 `docs/技术参考.md`
- **依赖**：garminconnect、fitparse、gpxpy（Python 库）
- **协议**：MIT

---

# 附录

## 附录 A：API 参考

详见 `docs/技术参考.md`。

## 附录 B：活动文件分析详解

详见 `docs/技术参考.md`。

## 附录 C：Garmin vs Whoop 详细对比

| 功能 | Garmin | Whoop |
|------|--------|-------|
| **恢复指标** | Body Battery（0-100） | Recovery Score（0-100%） |
| **HRV 追踪** | 是（夜间平均值） | 是（详细数据） |
| **睡眠阶段** | 浅睡、深睡、REM、清醒 | 浅睡、深睡、REM、清醒 |
| **活动追踪** | 内置 GPS，多种运动模式 | 负荷评分（0-21） |
| **API** | 非官方（garminconnect） | 官方 OAuth |
| **设备类型** | 手表、健身追踪器 | 腕带（仅此一款） |

## 附录 D：MCP 服务器配置

> 如果你使用的是 **标准 Claude Desktop**（非 WorkBuddy/Clawdbot），可以使用独立的 MCP 服务器。

**[garmin-health-mcp-server](https://github.com/eversonl/garmin-health-mcp-server)**

### 快速开始

```bash
git clone https://github.com/eversonl/garmin-health-mcp-server.git
cd garmin-health-mcp-server

npm install
pip3 install garminconnect fitparse gpxpy
cp .env.example .env
# 编辑 .env 填写凭证

# 登录认证
npm run auth

# 配置 Claude Desktop（添加到 claude_desktop_config.json）
```

### 同时使用两种方式

WorkBuddy Skill 和 MCP 服务器可以同时使用！它们共享认证 token，只需登录一次。

**推荐搭配：**
- **WorkBuddy**：晨间健康摘要、周报、自动追踪
- **Claude Desktop**：日常快速查询

认证 token 共享于 `~/.clawdbot/garmin-tokens.json`。
