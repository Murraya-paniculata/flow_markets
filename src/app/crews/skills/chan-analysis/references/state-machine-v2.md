# Chanlun state_machine v2.0（FlowMarkets `chanlun_v2` 字段）

对齐 `chanlun/ai_output_schema.py` 的 `get_state_machine_schema_template()`。

## 顶层（嵌在 TechnicalAnalysisDeliverable.chanlun_v2）

| 字段 | 说明 |
|------|------|
| `meta` | symbol, interval, price, timestamp |
| `version` | 固定 `"2.0"` |
| `output_mode` | 固定 `"state_machine"` |
| `state_machine` | 见下 |
| `structure_judgement` | trend, price_position, zs{zg,zd,gg,dd} |
| `risk_notes` | 字符串数组 |

## state_machine

- `current_state`: `STRATEGY_ACTIVE` | `WAIT_CONFIRMATION` | `OBSERVE_ONLY`
- `active_strategy.direction`: `up` | `down`
- `active_strategy.status`: `WAIT` | `READY` | `ACTIVE` | `INVALIDATED`
- `active_strategy.entry_gate.price_zone`: `[低, 高]`
- `active_strategy.entry_gate.structure_required`: 非空缠论条件列表
- `active_strategy.execution`: entry_type, stop_loss, target, rr
- `invalidation.invalidate_active_if`: 至少 1 条
- `invalidation.next_state`: 如 `OBSERVE_ONLY`
- `standby_strategies`: 可选数组

工具 `ok=false` 时整段 `chanlun_v2` 为 `null`，仅填 `brief`。
