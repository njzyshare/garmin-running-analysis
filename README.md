# Garmin Running Analysis

从 Garmin Connect 查询跑步健康数据，生成交互式训练分析报告。支持中国区和国际区账号。

适用于 WorkBuddy / Clawdbot 平台。

## 核心能力

| 功能 | 说明 |
|------|------|
| **训练报告** | 自动分析当日/昨日训练，输出配速、心率、爬升、天气影响评估 |
| **等强配速** | 基于坡度数据自动折算等效平路配速，准确评估真实训练强度 |
| **睡眠分析** | 睡眠时长、评分、睡眠阶段分布、Body Battery 充放电趋势 |
| **恢复评估** | HRV 趋势、静息心率、训练准备度 |
| **天气量化** | 自动获取训练地点天气，计算 DI（不适指数）量化配速影响 |
| **周/月报告** | 按周或月维度汇总跑量、训练强度、恢复状态 |
| **科学训练法** | 丹尼尔斯 VDOT / MAF 180 / 汉森累积疲劳 / 亚索 800 |
| **活动文件** | 下载 FIT/GPX/TCX 格式的活动记录 |

## 等强配速（Effort Pace）

基于 Garmin 计圈数据（splits）实现的坡度调整配速，用于将山地/坡路训练折算为等效平路配速。

> 完整计算规则（方案A/B/C、坡度因子、心率修正、Naismith参考）见 `references/effort_pace.md`。

## 快速开始

### 1. 安装依赖

```bash
pip3 install garminconnect fitparse gpxpy
```

### 2. 配置凭证

```bash
mkdir -p ~/.clawdbot/garmin-config
cp config.example.json ~/.clawdbot/garmin-config/config.json
# 编辑 ~/.clawdbot/garmin-config/config.json 填入你的 Garmin 邮箱和密码
```

### 3. 登录认证

```bash
python3 scripts/garmin_auth.py login
python3 scripts/garmin_auth.py status
```

## 目录结构

```
skill/
├── SKILL.md                       # 主技能文件（WorkBuddy 入口）
├── README.md                      # 本文件
├── config.example.json            # 配置模板
├── references/                    # 参考文件（按需加载）
│   ├── effort_pace.md             # 等强配速计算规则
│   ├── running_methodology.md     # 训练法（丹尼尔斯 / MAF / 汉森 / 亚索 800）
│   ├── weather_analysis.md        # 天气与 DI 分析
│   ├── metrics_reference.md       # Body Battery / 睡眠 / HRV 详解
│   ├── faq_guide.md               # 问答映射 + 用户信息表
│   ├── report_templates.md        # 报告结构模板
│   ├── splits_analysis.md         # 计圈启发式分析
│   ├── api_reference.md           # Garmin API 参考
│   ├── auth_and_troubleshooting.md # 认证与故障排查
│   ├── data_processing.md         # PB 提取 / 睡眠关联
│   ├── training_metrics.md        # 心率 Zone / 运动类型代码
│   └── weather_analysis.md        # 天气与 DI 分析
└── scripts/                       # Python 脚本
    ├── garmin_auth.py             # 认证管理
    ├── garmin_data.py             # 数据获取
    ├── garmin_data_extended.py    # 扩展指标
    ├── garmin_chart.py            # 图表生成
    ├── garmin_report.py           # 报告生成
    ├── garmin_query.py            # 时间点查询
    └── garmin_activity_files.py   # 活动文件下载/解析
```

## 隐私说明

- 凭据和 token 存于 `~/.clawdbot/garmin-config/`，**不在 skill 目录内**
- 技能目录本身不含任何个人数据，可安全共享
- Token 会自动刷新

## 许可证

MIT
