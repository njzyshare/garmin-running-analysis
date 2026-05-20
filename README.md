# Garmin Running Analysis 🏃

从 Garmin Connect 获取跑步和健康数据，生成交互式 HTML 训练分析报告。

支持 **中国区 (garmin.cn)** 和 **国际区 (connect.garmin.com)** 账号。

---

## 核心能力

| 功能 | 说明 |
|------|------|
| **训练报告** | 自动分析当日/昨日训练，输出配速、心率、爬升、天气影响量化评估 |
| **周/月报告** | 按自然周或月度汇总跑量、训练强度、恢复状态、配速变化趋势 |
| **睡眠分析** | 睡眠时长、评分、睡眠阶段分布、Body Battery 充放电趋势 |
| **恢复评估** | HRV 趋势、静息心率、训练准备度、连续恢复状态监测 |
| **天气量化** | 自动获取训练地点历史天气，计算 DI（不适指数）量化温湿度对配速的影响 |
| **分段分析** | 对指定训练进行计圈分析，可识别间歇跑、节奏跑、马拉松配速段 |
| **活动文件** | 下载 FIT/GPX/TCX 格式的活动记录并解析详细指标 |
| **数据查询** | 支持对任意时间点的健康指标（心率、压力、Body Battery、步数等）进行精确查询 |
| **扩展指标** | VO₂max、身体成分、血氧、呼吸率、体能年龄、训练准备度等 |
| **图表可视化** | 睡眠、Body Battery、HRV、活动摘要的交互式 Chart.js 图表 |

---

## 快速开始

### 安装依赖

```bash
pip install garminconnect fitparse gpxpy
```

### 配置凭证

将 Garmin Connect 账号信息写入配置文件：

```bash
# 创建配置目录
mkdir -p ~/.garmin-analysis

# 复制配置模板
cp config.example.json ~/.garmin-analysis/config.json

# 编辑配置文件，填入你的邮箱和密码
vi ~/.garmin-analysis/config.json
```

配置文件格式：

```json
{
  "email": "your-email@example.com",
  "password": "your-password",
  "region": "cn"
}
```

| region 值 | 适用场景 |
|-----------|----------|
| `cn` | 中国区 Garmin 账号（`connect.garmin.cn`，默认） |
| `intl` | 国际区 Garmin 账号（`connect.garmin.com`） |

> 凭证也可通过环境变量 `GARMIN_EMAIL` / `GARMIN_PASSWORD` 或命令行参数 `--email` / `--password` 传入。

### 登录认证

```bash
python scripts/garmin_auth.py login
```

登录成功后，会话 Token 会自动保存，后续无需重复登录。

### 生成训练报告

```bash
python scripts/garmin_report.py
```

报告输出为交互式 HTML 文件，保存在 `reports/` 目录。

---

## CLI 参考

### 获取健康数据

```bash
# 睡眠数据
python scripts/garmin_data.py sleep --days 7

# 活动记录（仅跑步类）
python scripts/garmin_data.py activities --days 30

# HRV 趋势
python scripts/garmin_data.py hrv --days 30

# Body Battery
python scripts/garmin_data.py body_battery --days 30

# 综合摘要
python scripts/garmin_data.py summary --days 7

# 用户信息
python scripts/garmin_data.py profile
```

### 生成交互式图表

```bash
# 睡眠分析图表
python scripts/garmin_chart.py sleep --days 30

# Body Battery 恢复图表
python scripts/garmin_chart.py body_battery --days 30

# HRV 与静息心率趋势
python scripts/garmin_chart.py hrv --days 90

# 完整仪表盘（4张图表）
python scripts/garmin_chart.py dashboard --days 90 --output ~/Desktop/dashboard.html
```

### 特定时间点查询

```bash
python scripts/garmin_query.py heart_rate "15:00" --date 2026-01-24
python scripts/garmin_query.py stress "10:00 AM"
python scripts/garmin_query.py body_battery "2026-01-24 06:30"
```

### 训练报告

```bash
# 使用默认 30 天分析周期
python scripts/garmin_report.py

# 自定义分析周期和输出路径
python scripts/garmin_report.py --days 14 --output ~/Desktop/report.html
```

### 活动文件下载与解析

```bash
python scripts/garmin_activity_files.py download --activity-id 12345678 --format fit
python scripts/garmin_activity_files.py parse --file activity.fit
```

---

## 训练报告结构

报告包含以下章节：

```
一、当日训练 + 睡眠分析     # 今天 + 昨天的训练详情，含配速、心率、天气
二、当周整体评估             # 本周 + 上周所有训练汇总，含周跑量统计
三、天气数据                 # 训练日温湿度及 DI 不适指数分布
四、DI 不适指数              # 量化天气对配速的影响，含区间分布
五、课表建议                 # 基于当前状态的训练优化建议
六、后续分析选项              # 引导进行分段/周/月维度深入分析
```

每节训练卡片包含：
- 距离、时间、配速、心率、步频、步幅
- 海拔爬升与下降、热量消耗
- 温湿度与 DI 不适指数量化影响
- 与目标配速的偏差分析

---

## 文件结构

```
.
├── scripts/
│   ├── garmin_auth.py               # 登录认证（支持中国区）
│   ├── garmin_data.py               # 健康数据获取
│   ├── garmin_chart.py              # Chart.js 交互式图表
│   ├── garmin_report.py             # 综合训练分析报告
│   ├── garmin_query.py              # 时间点查询
│   ├── garmin_data_extended.py      # 扩展指标
│   └── garmin_activity_files.py     # FIT/GPX/TCX 文件处理
├── docs/
│   └── 技术参考.md                   # 技术实现细节
├── reports/                         # 报告输出目录（自动创建）
├── config.example.json              # 配置文件模板
├── SKILL.md                         # AI 助手技能定义
└── README.md
```

---

## 指标说明

| 指标 | 范围 | 说明 |
|------|------|------|
| Body Battery | 0-100 | Garmin 恢复指标，值越高表示恢复越充分 |
| 睡眠评分 | 0-100 | 综合睡眠质量评估 |
| HRV | 因人而异 | 跟踪趋势变化，升高通常表示恢复改善 |
| 静息心率 | 40-80 bpm | 越低通常表示心血管适能越好 |
| 训练准备度 | 0-100 | 综合恢复、睡眠、HRV 的量化评估 |
| DI 不适指数 | 量化值 | 温度+湿度综合影响，越高越不舒适 |

---

## 隐私与安全

- **凭证仅在本地存储**：配置文件位于 `~/.garmin-analysis/config.json`，请勿提交到 Git
- **令牌自动管理**：登录后 Token 保存在 `garmin_tokens/` 目录（已在 `.gitignore` 中排除）
- **数据仅发往 Garmin 官方服务器**，不经过任何第三方
- 可随时删除 Token 文件以撤销访问权限

---

## 注意事项

- Garmin API 存在请求频率限制，避免频繁轮询（建议每小时最多一次完整数据获取）
- 部分扩展指标（Body Battery、训练准备度等）需要支持 HRV 的 Garmin 设备
- 睡眠数据以"醒来日期"记录（Garmin 惯例）：18号晚入睡 → 19号早醒来 → 记录为 19号

## License

MIT
