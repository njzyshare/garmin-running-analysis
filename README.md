# Garmin Running Analysis

从 Garmin Connect 查询跑步健康数据，生成交互式训练分析报告。支持中国区和国际区账号。

适用于 WorkBuddy / Codex 等 AI 工具平台。

## 核心能力

| 功能 | 说明 |
|------|------|
| **训练报告** | 自动分析当日/昨日训练，输出配速、心率、爬升、天气影响评估 |
| **分段分析** | 自动识别间歇跑、节奏跑等训练模式，间歇训练时展示恢复段心率下降评估 |
| **等强配速** | 基于坡度数据自动折算等效平路配速，准确评估真实训练强度 |
| **睡眠分析** | 睡眠时长、评分、睡眠阶段分布、身体电量(Body Battery)充放电趋势 |
| **恢复评估** | HRV 趋势、静息心率、训练准备度 |
| **天气量化** | 自动获取训练地点天气，计算不适指数(DI)量化配速影响 |
| **周/月报告** | 按周或月维度汇总跑量、训练强度、恢复状态 |
| **科学训练法** | 丹尼尔斯 VDOT / MAF 180 / 汉森累积疲劳 / 亚索 800 |
| **活动文件** | 下载 FIT/GPX/TCX 格式的活动记录 |

## 等强配速（坡度调整配速）

将山地/坡路训练折算为等效平路配速，更准确评估真实训练强度。

### 触发条件

| 场景 | 坡度调整配速？| 说明 |
|:---|:---:|:---|
| 🏔️ 越野跑 / 爬升 >10m | ✅ **显示** | 坡度调整配速才有意义 |
| 🏃 路跑轻微起伏（<10m）| ❌ 不显示 | 原始配速就是等效配速 |

### 计算规则（优先级）

1. **🥇 Garmin `avgGradeAdjustedSpeed`（平均坡度调整配速）**
   - Garmin 手表内置算法，基于 GPS 海拔和计圈数据自动计算
   - 字段位置：`summaryDTO.avgGradeAdjustedSpeed`（活动级）、lap 级也有逐圈值
   - 优势：算法成熟可靠，覆盖 90%+ 含 GPS 轨迹的活动
   - **优先使用**此字段，有就直接取

2. **🥈 手动逐公里坡度折算（兜底）**
   - 仅当 `avgGradeAdjustedSpeed` 字段为空或不存在时启用
   - 基于计圈海拔升降逐公里折算，公式见 `references/effort_pace.md`

> 注意：Garmin 的坡度调整配速在下坡路段的调整偏保守，不会过度"奖励"下坡速度，更适合评估真实训练负荷。

## 快速开始

### 1. 安装依赖

```bash
pip3 install garminconnect fitparse gpxpy
```

### 2. 配置凭证

```bash
mkdir -p ~/.garmin-health-analysis
cp config.example.json ~/.garmin-health-analysis/config.json
# 编辑 ~/.garmin-health-analysis/config.json 填入你的 Garmin 邮箱和密码
```

### 3. 登录认证

```bash
python3 scripts/garmin_auth.py login
python3 scripts/garmin_auth.py status
```

Token 自动存储于 `~/.garmin-health-analysis/tokens/`。

## 目录结构

```
skill/
├── SKILL.md                       # 主技能文件（WorkBuddy 入口）
├── README.md                      # 本文件
├── config.example.json            # 配置模板
├── references/                    # 参考文件（按需加载）
│   ├── effort_pace.md             # 等强配速计算规则
│   ├── running_methodology.md     # 训练法（丹尼尔斯 / MAF / 汉森 / 亚索 800）
│   ├── weather_analysis.md        # 天气与不适指数(DI)分析
│   ├── metrics_reference.md       # 身体电量/睡眠/HRV 详解
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

## 安装方式

### 方式一：作为 WorkBuddy/Codex Skill 安装

1. 将本目录放入 AI 工具的 skills 目录（如 `~/.workbuddy/skills/`）
2. 确保已安装 Python 依赖：`pip3 install garminconnect fitparse gpxpy`
3. 配置凭证并登录（见下方指引）

### 方式二：独立命令行使用

```bash
git clone https://github.com/njzyshare/garmin-running-analysis.git
cd garmin-running-analysis
pip3 install garminconnect fitparse gpxpy
# 配置凭证
mkdir -p ~/.garmin-health-analysis
cp config.example.json ~/.garmin-health-analysis/config.json
# 编辑配置文件，然后登录
python3 scripts/garmin_auth.py login
python3 scripts/garmin_auth.py status
# 生成报告
python3 scripts/garmin_report.py --days 7
```

## 隐私说明

- 凭据和 token 存于 `~/.garmin-health-analysis/`，**不在 skill 目录内**
- 技能目录本身不含任何个人数据，可安全共享
- Token 会自动刷新

## 更新日志

### v2.3.0 — 间歇训练恢复段心率评估 (2026-07-09)
- **新增** 间歇训练恢复段最低心率评估（取最后5秒平均），O(1)快速计算
- **新增** `render_splits_table()` 支持传入逐秒心率流，动态映射列索引
- **新增** 冷身段过滤（>300m恢复段不参与评估）
- **优化** 分段拆解模板通用化：热身→核心→恢复→冷身
- **修复** 等强配速在间歇训练短计圈上失真的问题

### v2.2.1 — 坡度调整配速 & 睡眠规则 (2026-06-17)
- **新增** 优先使用 Garmin 内置 `avgGradeAdjustedSpeed` 字段
- **新增** README 中等强配速触发条件说明（爬升>10m触发）
- **修复** 睡眠日期分析规则：D日睡眠差 → 先查D日清晨是否有早起训练
- **修复** HRV 保持英文缩写，其他术语中文化
- **清理** 移除 COROS/高驰残留引用

### v2.2.0 — 术语中文化 (2026-05-20)
- **修改** 指标全部使用中文表述（HRV除外）
- **优化** 报告内容本地化适配

### v2.0.x — 基础设施完善 (2026-05-19)
- **新增** 等强配速三级计算方案（逐公里坡度折算+心率修正+Naismith参考）
- **新增** PB 从活动记录提取功能（Garmin API fallback）
- **新增** 天气量化分析：不适指数(DI)分区间统计
- **新增** 权重评分系统（跑量/长距离/配速/频率四维评分）
- **新增** 中国区 Garmin.cn monkey-patch 登录支持
- **重构** SKILL.md 结构化，新增 references/ 参考文件体系
- **修复** PB 字典映射修复，周跑量改为滚动7天窗口
- **清理** 脱敏处理，移除硬编码路径和高驰残留

### v2.0.0 — 重大重构 (2026-04-12)
- **新增** 丹尼尔斯 VDOT / MAF 180 / 汉森法 / 亚索 800 训练体系
- **新增** 计圈启发式分析（自动识别间歇/计圈/异常模式）
- **重构** SKILL.md 轻量化，分离技术细节到 references/
- **清理** 示例数据脱敏

### v1.0.0 — 初始版本 (2026-03-26)
- **新增** Garmin Connect 数据获取（活动/睡眠/HRV/身体电量）
- **新增** 训练分析报告 HTML 生成
- **新增** 天气数据自动获取
- **新增** 交互式仪表盘
- **新增** FIT/GPX 文件下载与解析

## 许可证

MIT
