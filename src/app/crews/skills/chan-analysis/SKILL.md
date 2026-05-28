---
name: chan-analysis
description: >
  Interprets Chan structure snapshots from get_chan_structure (笔/线段/中枢/买卖点/
  structure_summary) and produces trader-facing structured analysis JSON. Use when the
  user or task provides ok=true data from GetChanStructureTool, asks for 缠论研判、
  scenarios、做多做空震荡概率、ZG/ZD/GG/DD, or wants chanlun-style analysis on
  flow_markets chan_structure output. Do not invent bi/segment/center not present in input.
---

# 缠论结构分析 Skill（chan-analysis）

## 适用场景

- 输入来自 **`GetChanStructureTool`** / `build_chan_structure_snapshot()` 的 JSON 字符串或对象。
- 需要输出 **可解析的结构化研判 JSON**（含 `scenarios`、`analysis` 等），供 API、回测或展示。
- FlowMarkets 多智能体链若只需 **`TechnicalBrief`**，可同时遵守本 Skill 的事实约束，但交付契约以任务 YAML 为准。

## 输入：如何读取工具 JSON

### 信封

```json
{ "ok": true, "partial": false, "data": { ... } }
```

- **`ok=false`**：不得编造笔/中枢；应声明数据不可用，并引用 `error_code`、`message`、`hint`。
- **只分析 `data` 块**；忽略外层 `ok`/`partial` 作为结构事实。

### `data` 各块含义

| 字段 | 用途 |
|------|------|
| `meta` | symbol、interval、timestamp、data_size |
| `market.latest_price` | 当前价 |
| `bi[]` | 最近若干笔（方向、价位、买卖点、背驰、力度） |
| `segment[]` | 线段 |
| `center[]` | 中枢 ZG/ZD/GG/DD、relation |
| `signal` | 买卖点/背驰汇总 |
| `structure_summary` | 预计算趋势、price_position、力度对比、key_levels |
| `context` | 分析目标与策略类型提示 |

字段详解见 [references/input-envelope.md](references/input-envelope.md)。

## 分析流程（按顺序执行）

1. **校验输入**：`ok=true` 且 `data.bi` 非空或 `data_size.kline` 足够；否则停止并说明缺口。
2. **复述事实**（仅引用输入）：最新价、最后一笔、最近中枢、signal 列表、`structure_summary` 中的 trend / price_position / strength_comparison。
3. **结构优先推理**：按 [references/structure-priority.md](references/structure-priority.md) 分配 up / down / range 概率；中枢 relation 优先于单笔力度。
4. **构造 scenarios**：2–4 个场景，含 `entry_range`、`target_range`、`trigger`、`logic`；概率用 **0–1 小数**，总和 ≤ 1.05。
5. **填写 analysis 字符串**：交易者可读，格式见下方「analysis 正文模板」。
6. **输出 JSON**：必须符合 [references/output-schema.md](references/output-schema.md)；**仅输出 JSON**，无 Markdown 外壳、无前言。

## 角色与边界（CRITICAL）

- 你是 **缠论结构分析引擎**，不是泛化行情评论员。
- **NEVER** 使用均线、MACD、KDJ、RSI、消息面、情绪舆论作为依据。
- **NEVER** 虚构输入中不存在的笔、线段、中枢或买卖点。
- **ALWAYS** 用缠论术语（笔、线段、中枢、ZG/ZD、买卖点、背驰、inside_zs / above_zs / below_zs）。
- **ALWAYS** 让 `analysis` 中的概率与 `scenarios` 数组一致（做多/做空/震荡可合并同方向场景概率）。

## 缠论术语（精简）

- **笔（bi）**：方向 up/down，可有 buy_sell_point、divergence、strength。
- **线段（segment）**：笔的更高一级组合。
- **中枢（center）**：ZG 中枢高、ZD 中枢低、GG/DD 极值；`relation` 如 new / extend。
- **买卖点**：如 1buy、2buy、3buy、1sell…；**背驰**：力度减弱等提示。
- **structure_summary.price_position**：above_zs / below_zs / inside_zs。

## 结构优先原则（摘要）

完整规则见 [references/structure-priority.md](references/structure-priority.md)。

1. 中枢 **extend** → 震荡概率通常最高（≥40%）。
2. 明确 **up_trend / down_trend** → 对应方向概率最高。
3. 中枢 **new** → 概率分布更均衡，避免单一方向 >50%。
4. 买卖点、背驰只做 **±5%～10% 微调**，不推翻结构主判断。

## analysis 正文模板（写入 JSON 的 `analysis` 字段）

必须包含以下小节（中文，给交易者阅读）：

1. **当前结构判断**：笔、线段、中枢状态，力度对比（引用 `structure_summary` 与最近 bi/center）。
2. **可能走势**：2–3 种场景，各含方向、概率、触发条件。
3. **关键价位**：ZG、ZD、GG、DD（无中枢时写明「无中枢参考」）。
4. **【做多策略】（概率 XX%）**：入场区间、目标、止损。
5. **【做空策略】（概率 XX%）**：入场区间、目标、止损。
6. **【震荡策略】（概率 XX%）**：区间、高抛低吸。

注：三项策略概率之和约 100%，与 `scenarios` 中 up/down/range 合并概率一致。

## 输出格式（CRITICAL）

- 输出 **单一 JSON 对象**，字段定义见 [references/output-schema.md](references/output-schema.md)。
- `primary_scenario.direction` 必须是 **`"up"` 或 `"down"`**（主推方向）。
- `scenarios[].probability` 为 **0–1**（勿用 55 表示 55%）。
- 做多：`target_range` 两端均 **高于** `meta.price` / `latest_price`。
- 做空：`target_range` 两端均 **低于** 当前价。
- 震荡：`target_range` **包含** 当前价；`direction` 为 `"range"`。
- 每个 scenario 必须有 **`entry_range`**：`[低, 高]`。

## 与 FlowMarkets Crew 的关系

| 场景 | 交付物 |
|------|--------|
| 本 Skill 默认 | 缠论研判 JSON（`output-schema.md`） |
| `task_fm_technical` | `TechnicalAnalysisDeliverable`：`brief` + `chanlun_v2`（`flow_markets_deliverables.py`） |

使用本 Skill 时：**结构事实仍只来自 get_chan_structure**；FlowMarkets 任务须一次输出：
- `brief`：研究链用的 `TechnicalBrief`（`summary` + `structure_quickview`）
- `chanlun_v2`：对齐 `chanlun/ai_output_schema.py` 的 `state_machine` v2.0（工具 ok=true 时必填）

两套字段须逻辑一致，不得矛盾。

## 可选：本地试工具

项目根目录：

```bash
FM_CHAN_PROGRESS=1 uv run python scripts/run_get_chan_structure.py --symbol BTCUSDT --timeframe 1h --lookback 300
```

将 stdout JSON 作为本 Skill 的输入进行研判。

## 参考文件

- [references/input-envelope.md](references/input-envelope.md) — 输入契约
- [references/output-schema.md](references/output-schema.md) — 输出 JSON Schema
- [references/structure-priority.md](references/structure-priority.md) — 概率分配规则
- [references/state-machine-v2.md](references/state-machine-v2.md) — FlowMarkets `chanlun_v2` 字段
