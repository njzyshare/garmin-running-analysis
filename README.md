# Garmin Running Analysis

从 Garmin Connect 查询跑步健康数据，生成交互式 HTML 报告。

支持中国区和国际区账号，自动获取训练记录、睡眠、HRV、Body Battery 等核心指标。

## 核心能力

| 功能 | 说明 |
|------|------|
| **训练报告** | 自动分析当日/昨日训练，输出配速、心率、爬升、天气影响评估 |
| **睡眠分析** | 睡眠时长、评分、睡眠阶段分布、Body Battery 充放电趋势 |
| **恢复评估** | HRV 趋势、静息心率、训练准备度 |
| **天气量化** | 自动获取训练地点天气，计算 DI（不适指数）量化配速影响 |
| **周/月报告** | 按周或月维度汇总跑量、训练强度、恢复状态 |
| **活动文件** | 下载 FIT/GPX/TCX 格式的活动记录 |

## 快速开始

### 1. 安装依赖

```bash
pip install garminconnect fitparse gpxpy
```

### 2. 配置凭证

```bash
# 创建配置目录
mkdir -p ~/.clawdbot/garmin-config

# 创建配置文件
# 编辑 ~/.clawdbot/garmin-config/config.json
```

```json
{
  "email": "your-email@example.com",
  "password": "your-password",
  "region": "cn"
}
```

| region 值 | 适用场景 |
|-----------|----------|
| `cn` | 中国区 Garmin 账号（默认） |
| `intl` | 国际区 Garmin 账号 |

### 3. 登录认证

```bash
python scripts/garmin_auth.py login
```

## 调用规则

### 获取健康数据

```bash
# 睡眠数据（默认近7天）
python scripts/garmin_data.py sleep --days 7

# 活动记录（仅跑步类）
python scripts/garmin_data.py activities --days 30

# HRV 数据
python scripts/garmin_data.py hrv --days 30

# 用户信息
python scripts/garmin_data.py profile
```

### 生成图表

```bash
# 睡眠分析
python scripts/garmin_chart.py sleep --days 30

# 完整仪表盘
python scripts/garmin_chart.py dashboard --days 30

# 保存到文件
python scripts/garmin_chart.py dashboard --days 30 --output ~/Desktop/report.html
```

### 查询特定时间点

```bash
# 查询心率
python scripts/garmin_query.py heart_rate "10:00 AM" --date 2026-01-24

# 查询压力水平
python scripts/garmin_query.py stress "14:30"
```

### 扩展指标

```bash
# 训练准备度
python scripts/garmin_data_extended.py training_readiness

# 身体成分
python scripts/garmin_data_extended.py body_composition --date 2026-01-24

# VO₂max 等最大摄氧量指标
python scripts/garmin_data_extended.py max_metrics
```

### 活动文件

```bash
# 下载 FIT 文件
python scripts/garmin_activity_files.py download --activity-id 12345678 --format fit

# 解析活动文件
python scripts/garmin_activity_files.py parse --file activity.fit
```

## 训练报告结构

```
一、当日训练 + 睡眠分析   # 今天 + 昨天的训练详情
二、当周整体评估          # 本周 + 上周所有训练汇总
三、天气数据              # 训练日温湿度及 DI 指数
四、DI 不适指数           # 量化天气对配速的影响
五、课表建议              # 基于当前状态的训练建议
六、后续分析选项          # 分段/周/月分析引导
```

## 指标说明

| 指标 | 正常范围 | 说明 |
|------|----------|------|
| Body Battery | 0-100 | 恢复状态，高=充足 |
| HRV | 因人而异 | 看趋势，升高=改善 |
| 静息心率 | 40-80 bpm | 越低心血管适能越好 |
| 训练准备度 | 0-100 | 综合恢复评估 |

## 注意事项

- **凭证存储**：配置在 `~/.clawdbot/garmin-config/config.json`，请勿提交到 Git
- **Token 存储**：登录后 Token 保存在 `~/.clawdbot/garmin-tokens.json`
- **频率限制**：Garmin API 有请求限制，避免频繁轮询

## 文件结构

```
.
├── scripts/
│   ├── garmin_auth.py           # 登录认证
│   ├── garmin_data.py          # 健康数据获取
│   ├── garmin_chart.py         # HTML 图表生成
│   ├── garmin_report.py        # 综合分析报告
│   ├── garmin_query.py         # 时间点查询
│   ├── garmin_data_extended.py # 扩展指标
│   └── garmin_activity_files.py # 活动文件下载/解析
├── docs/
│   └── 技术参考.md              # 详细技术文档
└── README.md
```

## License

MIT
