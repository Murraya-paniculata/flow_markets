# 缠论分析核心原则：结构优先

摘自 chanlun `prompt_builder.build_structured_prompt()`，供概率分配与场景排序使用。

## 1. 中枢关系 > 笔力度

| 中枢 relation / 趋势 | 概率分配倾向 |
|---------------------|--------------|
| **extend** | **震荡（range）概率最高**，通常 ≥ 40% |
| **up_trend / down_trend** | 对应 **up / down** 方向概率最高 |
| **new** | 分布更均衡，**避免单一方向 > 50%** |

## 2. 价格相对中枢（辅助）

| price_position | 倾向 |
|----------------|------|
| inside_zs | 提高震荡概率 |
| above_zs | 偏多，警惕回落 |
| below_zs | 偏空，警惕反弹 |

数据来源：输入 `structure_summary.price_position` 或最后一笔中枢 ZG/ZD 与 `latest_price` 比较。

## 3. 买卖点信号（加成，非主因）

| 信号 | 调整 |
|------|------|
| 1 类买卖点 | 对应方向约 +10% |
| 2 类买卖点 | 约 +8% |
| 3 类买卖点 | 约 +5% |

买卖点是**入场时机**提示，不应推翻结构主方向。

## 4. 背驰（预警）

- 力度背驰（weakening）提示可能反转。
- 须结合中枢 relation：extend 下的背驰可能只是**震荡内小反转**，不宜直接给单边最高概率。

## 5. 错误示例（NEVER）

| 错误 | 正确 |
|------|------|
| extend + below_zs + 向下笔加强 → 做空最高 | extend 优先 → **震荡最高** |
| 中枢 new → 单一方向 > 50% | new → **三方向更均衡** |

## 6. 与 structure_summary 的配合

优先采用输入中已有结论，再微调 scenarios：

- `trend` / `trend_description`
- `strength_comparison`
- `key_levels`（ZG/ZD/GG/DD）

若 `structure_summary` 与局部笔细节冲突，以**最近中枢 relation + 价格位置**为主，并在 `analysis` 中简要说明。
