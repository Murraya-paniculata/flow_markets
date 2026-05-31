# `history` 块契约（get_chan_structure）

与 `data` 并列；**结构事实仍在 `data`**，`history` 仅用于置信度与状态机降级。

## 顶层

```json
{
  "ok": true,
  "partial": false,
  "data": { },
  "history": {
    "available": true,
    "db_samples_evaluated": 12,
    "context_match": { },
    "system_stats": { },
    "state_machine_hints": { },
    "similar_cases": { "has_data": false },
    "learning_feedback": { "has_data": false }
  }
}
```

## `similar_cases`（Phase 2.5）

| 字段 | 说明 |
|------|------|
| `has_data` | 是否检索到 ≥1 条相似已评估案例 |
| `threshold_used` | 相似度阈值（默认 40，不足 3 条时降至 20） |
| `count` / `win_rate` / `avg_score` | 相似案例聚合 |
| `avg_favorable_move_pct` / `avg_adverse_move_pct` | 平均有利/不利变动 |
| `confidence` / `suggestion` | 历史建议与置信度档位 |
| `by_direction` | 按预测方向分组胜率 |
| `top_cases` | 最相似 5 条（含 `similarity_score`） |
| `prompt_text` | 中文摘要（对齐 chanlun history_context） |

相似度维度：symbol、interval、signal_type、trend、price_position、strength_comparison；可选方向匹配 +10；30 天半衰期时间衰减。

## `system_stats`（Phase 2.4）

| 字段 | 说明 |
|------|------|
| `has_data` | 是否有可计分已评估样本 |
| `total` / `hit_rate` / `avg_score` | 全库聚合 |
| `for_symbol` | 当前 `meta.symbol` 桶 |
| `for_interval` | 当前 `meta.interval` 桶 |
| `prompt_text` | 中文摘要（对齐 chanlun stats_formatter） |

## `state_machine_hints`

| 字段 | 说明 |
|------|------|
| `recommended_floor` | `OBSERVE_ONLY` / `WAIT_CONFIRMATION` / null |
| `system_floor` | 仅由全库 `system_stats` 推导的下限 |
| `similar_cases_floor` | 仅由 `similar_cases.win_rate` 推导的下限（≥3 条） |
| `basis_hit_rate` | 0～1，用于降级的胜率 |
| `basis` | `for_symbol` / `for_interval` / `overall` |
| `min_win_rate_observe_only` | 0.25 |
| `min_win_rate_wait_confirmation` | 0.35 |

样本不足（&lt;5）时不设 `recommended_floor`。

**Phase 2.7**：`recommended_floor` 非空时，服务端在 AI 输出后强制降级 `chanlun_v2.state_machine.current_state`，并在 `risk_notes` 追加 `[历史约束]` 条目。

## `learning_feedback`（Phase 2.6）

| 字段 | 说明 |
|------|------|
| `has_data` | 最近窗口内可计分样本 ≥5 |
| `lookback_days` | 默认 30 天 |
| `total_predictions` / `overall_win_rate` / `overall_avg_score` | 整体表现 |
| `by_direction` / `by_signal_type` | 分桶胜率与目标偏差 |
| `error_patterns` | 系统性错误模式（如目标过高、某方向偏弱） |
| `strengths` / `weaknesses` / `recommendations` | 强项、弱项、改进建议 |
| `confidence_adjustments` | 方向/信号置信度系数（0.5～1.15） |
| `prompt_text` | 自我认知中文摘要（对齐 chanlun learning_feedback） |

与 `similar_cases` 区别：`learning_feedback` 看**整体 AI 表现**；`similar_cases` 看**结构相似**子集。

## 数据来源

仅统计 `analysis_snapshot` 中 `evaluated=1` 且 outcome 可计分（排除 `insufficient_data` 等错误回填）。
