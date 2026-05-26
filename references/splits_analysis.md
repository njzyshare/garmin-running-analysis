# 计圈数据分析（Splits）

> 活动数据的计圈（splits/laps）启发式分析，自动识别最佳呈现方式。

---

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
    - 最佳公里高亮（绿色行）
    - 默认折叠（details/summary 标签）
    """
```

- `suspect` 模式：仅显示基本信息，提示 GPS 粒度过粗
- `auto_lap_1km` 模式：显示每公里配速表，最快公里绿色高亮
- `interval` 模式：显示快/慢段交替分布，含分类标签
