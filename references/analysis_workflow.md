---
title: "分析工作流参考"
summary: "首次分析流程、配速区间识别、周跑量统计方法"
---

# 分析工作流参考

> **关于时间精度**：MCP 返回的日期不含时间戳，无法区分晨跑/夜跑/一天多次。
> 如需精确时间或时段天气，参见 `time-weather-refinement.md`。

## 一、首次分析流程

首次分析用户时，并行拉取以下数据：

```javascript
fitness  = call('queryFitnessAssessmentOverview', {})
health   = call('queryDailyHealthData', { days: 7, timezone: 'Asia/Shanghai' })
records  = call('querySportRecords', { startDate:'YYYYMMDD', endDate:'YYYYMMDD', sportTypeCodes:[100], limit:100, timezone:'Asia/Shanghai' })
recovery = call('queryRecoveryStatus', {})
load     = call('queryTrainingLoadAssessment', { days: 30 })
hrv      = call('queryHrvAssessment', { days: 7, timezone: 'Asia/Shanghai' })
```

### Fitness 字段提取

| 字段 | 含义 | 用途 |
|------|------|------|
| vo2max | 最大摄氧量 | 体能级别 |
| predictedFullMarathon | 高驰预估全马 | **默认目标** |
| predictedHalfMarathon | 高驰预估半马 | **默认目标** |
| thresholdPace | 阈值配速（MP） | 主课段参考 |
| thresholdHeartRate | 阈值心率 | 强度参考 |
| anaerobicThresholdHeartRate | 乳酸阈心率 | 间歇/MP 上限 |

## 二、配速区间识别

⚠️ `getActivityDetail` 不返回逐km分段，配速区间从汇总数据推断。

| 类型 | 心率 | 配速来源 |
|------|------|---------|
| **轻松跑（E）** | ≤ LT心率×0.78 | 均速中偏低且HR稳定 |
| **MP** | 阈值心率 ±5 | thresholdPace |
| **乳酸阈值（T）** | LT心率 ±3 | fitness 数据 |
| **间歇（I）** | LT心率+5~15 | 最高均HR段 |

## 三、历史周跑量统计

```javascript
// 查询近8-12周
records = call('querySportRecords', {
  startDate: START, endDate: END,
  sportTypeCodes: [100], limit: 200,
  timezone: 'Asia/Shanghai'
})
// 按自然周（周一→周日）汇总，仅统计 SportType: [100,101,102,103]
```

输出模板：

| 周次 | 跑量(km) | 训练天数 | 备注 |
|------|---------|--------|------|
| W-1 | 72.3 | 5 | 完整周 |
| W-2 | 68.5 | 4 | 缺1天 |
| ... | ... | ... | ... |
| **均值** | XX.X | X.X | — |
| **峰值** | XX.X | — | W-N |
