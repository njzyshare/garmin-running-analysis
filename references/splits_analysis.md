# 计圈数据分析（Splits）

> 活动数据的计圈（splits/laps）启发式分析，自动识别最佳呈现方式。

---

## 数据获取方式

Garmin 的计圈数据通过以下 API 直接获取，无需浏览器自动化：

```python
# 通过 connectapi 直接获取全部计圈
result = client.connectapi(f'/activity-service/activity/{activity_id}/splits')
laps = result.get('lapDTOs', [])   # 每圈含：距离、时长、配速、HR、步频、
                                    # 触地时间(GCT)、步幅、垂直振幅、垂直比、功率
```

每次分析训练时，优先走以上 API 获取原始计圈数据，然后通过启发式分析判断呈现方式。

## 分析策略

`garmin_report.py` 中的 `analyze_splits_heuristic()` 依次执行 3 种检测：

### Heuristic 1: 异常大圈（suspect）

若某圈距离 > 总距离 50%，说明 GPS 粒度过粗。

```python
for i, dist in enumerate(lap_distances):
    if dist > total_distance * 0.5:
        return {"type": "suspect", "description": f"第{i+1}圈占总距离 {dist/total_distance*100:.1f}%"}
```

### Heuristic 2: 自动公里计圈（auto_lap_1km）

若 ≥60% 的圈在 0.95-1.05km 范围内，判定为自动 1km 计圈。

```python
km_laps = sum(1 for d in lap_distances if 0.95 <= d <= 1.05)
if km_laps / len(lap_distances) >= 0.6:
    return {"type": "auto_lap_1km"}
```

### Heuristic 3: 配速交替间歇（interval）

遍历计圈配速，用中位配速 ±12% 阈值分类 fast/slow/medium：
- fast: 配速 ≤ 中位 × 0.88（比中位快 ≥12%）
- slow: 配速 ≥ 中位 × 1.08（比中位慢 ≥8%）

要求：≥3 次 fast↔slow 交替、≥3 个 fast 圈、≥3 个 slow 圈。

```python
paces.sort(key=lambda p: p["pace"])
median_pace = paces[len(paces) // 2]["pace"]

transition_count = sum(
    1 for i in range(1, len(classifications))
    if classifications[i] != classifications[i-1]
    and "fast" in [classifications[i], classifications[i-1]]
)

if transition_count >= 3 and fast_count >= 3 and slow_count >= 3:
    return {"type": "interval"}
```

### Heuristic 4: 距离区间间歇（distance-based interval）
- 预置标准距离区间：200m / 400m / 600m / 800m / 1km
- 检测到≥3个匹配区间的圈 + 有恢复段（>区间上限的圈）→ 判定为间歇训练

### 恢复段最低心率评估

在检测到间歇训练模式后，额外通过 `get_activity_details()` 的逐秒心率流计算恢复段最低心率：

**算法原理**：恢复段心率呈单调递减，取最后5秒平均即为该段最低心率。

```python
# 从 metricDescriptors 动态映射列索引
col_map = {d['key']: d['metricsIndex'] for d in metric_descriptors}
hr_col = col_map['directHeartRate']           # 心率列
elapsed_col = col_map['sumElapsedDuration']   # 累计耗时（秒）

# 恢复段最后5秒平均
end_time = lap_range['end']
last_5s = [hr for t, hr in timeline if end_time - 5 <= t <= end_time]
recovery_hr = sum(last_5s) / len(last_5s)
```

**触发条件**：仅 `heuristic["pattern"] == "interval"` 时启用
**冷身过滤**：恢复段距离 > 300m 的不参与评估（视为冷身而非恢复）
**评估阈值**：

| 降幅（从间歇最高心率） | 评估 |
|:---:|:---:|
| ≥30 bpm | ✅ 充分恢复 |
| ≥20 bpm | 🟡 恢复好 |
| ≥12 bpm | ⚪ 一般 |
| <12 bpm | ⚠️ 恢复不足 |

### 兜底：native

以上均未匹配时，判定为手表原生计圈。

---

## 应用示例

| 活动 | 计圈方式 | 判定结果 |
|------|---------|---------|
| 5/16 11.25km 间歇跑 | 手表原生 18 圈 | `interval` — 8快+10慢段，9次交替 |
| 5/17 21.1km 半马 | 手表仅 3 圈 | `suspect` — 第1圈占 94.8% |
| 日常 E 跑 | Garmin 自动 1km | `auto_lap_1km` — 10/10 圈在 1km 范围 |

---

## HTML 呈现

```python
def render_splits_table(laps, heur_type):
    """
    渲染分段配速表，包含：
    - 启发式分析横幅（如：⚠️ 异常计圈 / ✅ 自动1km计圈 / 🏃 间歇训练）
    - 最快单圈高亮（绿色行）
    - 默认折叠（details/summary 标签）
    """
```

- `suspect` 模式：仅显示基本信息，提示 GPS 粒度过粗
- `auto_lap_1km` 模式：显示每公里配速表，最快公里绿色高亮
- `interval` 模式：显示快/慢段交替分布，含分类标签
