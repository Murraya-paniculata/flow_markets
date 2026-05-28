# 缠论研判输出 JSON Schema

对齐 chanlun `ai_output_schema.get_schema_template()`，供 **chan-analysis** Skill 单次 LLM 输出使用。  
校验逻辑可参考 `chanlun/ai_output_schema.py` 的 `validate_ai_output()`（flow_markets 侧可后续加 Pydantic 模型）。

## 完整模板

```json
{
  "meta": {
    "symbol": "string",
    "interval": "string",
    "price": "number",
    "timestamp": "string"
  },
  "analysis": "string（交易者可读长文，见 SKILL.md analysis 模板）",
  "structure_judgement": {
    "current_state": "string",
    "trend": "up_trend | down_trend | consolidation",
    "latest_bi": {
      "direction": "up | down",
      "is_done": true,
      "strength_vs_prev": "weakening | strengthening | similar"
    },
    "latest_xd": {
      "direction": "up | down",
      "is_done": true
    },
    "zs": {
      "level": 1,
      "zg": 0,
      "zd": 0,
      "gg": 0,
      "dd": 0,
      "range": [0, 0],
      "relation": "new | extend | ..."
    },
    "price_position": "above_zs | below_zs | inside_zs"
  },
  "signals": {
    "buy_sell_points": ["1buy"],
    "divergences": []
  },
  "primary_scenario": {
    "direction": "up",
    "target_pct": 3.0,
    "stop_pct": 1.5,
    "probability": 0.55,
    "trigger": "突破 ZG 且回踩不破",
    "reasoning": "string"
  },
  "scenarios": [
    {
      "rank": 1,
      "probability": 0.55,
      "direction": "up",
      "trigger": "string",
      "target_range": [91000, 92000],
      "entry_range": [90500, 91200],
      "logic": "string"
    },
    {
      "rank": 2,
      "probability": 0.25,
      "direction": "down",
      "trigger": "string",
      "target_range": [89000, 90000],
      "entry_range": [90800, 91200],
      "logic": "string"
    },
    {
      "rank": 3,
      "probability": 0.2,
      "direction": "range",
      "trigger": "string",
      "target_range": [90500, 91500],
      "entry_range": [90600, 91400],
      "logic": "string"
    }
  ],
  "risk_notes": ["string"]
}
```

## 必填与约束

| 规则 | 说明 |
|------|------|
| 顶层必填 | `meta`, `structure_judgement`, `primary_scenario`, `scenarios` |
| scenarios | 非空数组；每项含 rank, probability, direction, trigger, logic |
| 概率 | 0–1 小数；总和 ≤ 1.05 |
| primary_scenario.direction | 仅 `up` 或 `down` |
| entry_range | 每个 scenario 必填 `[低, 高]` |
| target_range 方向 | up 高于现价；down 低于现价；range 包含现价 |
| analysis | 含做多/做空/震荡策略与概率，与 scenarios 一致 |

## meta.price

使用输入 `data.market.latest_price`，勿与工具 JSON 外的行情混用。

## 无中枢时

`structure_judgement.zs` 可填 0 或省略极值含义；`analysis` 中注明「无中枢参考」，震荡/趋势判断更多依赖 `bi` 与 `structure_summary.trend`。
