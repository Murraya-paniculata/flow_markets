# get_chan_structure 输入契约

契约源码：`flow_markets/src/app/schemas/chan_structure.py`  
生成逻辑：`flow_markets/src/app/services/chan/structure.py`

## 顶层信封

```json
{
  "ok": true,
  "partial": false,
  "data": { }
}
```

失败示例：

```json
{
  "ok": false,
  "partial": false,
  "error_code": "INSUFFICIENT_DATA | UPSTREAM_ERROR | ENGINE_ERROR",
  "message": "...",
  "hint": "..."
}
```

**`ok=false` 时不得进行缠论推演。**

## data.meta

| 字段 | 说明 |
|------|------|
| symbol | 如 `BTC/USDT` |
| interval | 如 `1h`、`4h` |
| timestamp | ISO 时间 |
| engine | 固定 `chanpy` |
| data_size.kline | 参与计算的 K 线根数 |
| data_size.bi | 引擎识别笔总数 |
| data_size.segment | 线段总数 |
| data_size.center | 中枢总数（非仅导出条数） |
| trim | 常为 `null`；若有则表示 bi/segment 曾裁剪 |

## data.market

| 字段 | 说明 |
|------|------|
| latest_price | 最新收盘价 |
| trend_hint | range / up / down（提示用） |
| volatility_hint | low / medium / high |

## data.bi[]（最近最多 15 条）

| 字段 | 说明 |
|------|------|
| index | 笔序号 |
| direction | up / down |
| is_done | 是否完成 |
| start_time / end_time | ISO |
| start_price / end_price | 端点价 |
| buy_sell_point | 如 1buy、2sell，可 null |
| divergence | 背驰类型，可 null |
| strength / macd_strength / price_strength | 力度，有则引用 |

## data.segment[]（最近最多 5 条）

与 bi 类似，通常无 `buy_sell_point`。

## data.center[]

| 字段 | 说明 |
|------|------|
| type | bi / segment |
| zg / zd | 中枢区间 |
| gg / dd | 极值 |
| high / low | 兼容字段 |
| relation | new / extend 等 |
| level | 级别，默认 1 |
| bi_count | 笔中枢内笔数 |

## data.signal

```json
{
  "buy_sell_points": ["1buy", "2sell"],
  "divergences": [],
  "last_signal_time": null
}
```

## data.structure_summary（优先引用）

| 字段 | 典型值 |
|------|--------|
| trend | up_trend / down_trend / consolidation / unknown |
| price_position | above_zs / below_zs / inside_zs / unknown |
| latest_bi_direction | up / down |
| strength_comparison | weakening / strengthening / similar / unknown |
| key_levels | zg, zd, gg, dd |
| trend_description | 中文描述 |
| position_description | 中文描述 |

## data.context

```json
{
  "analysis_goal": "predict_next_move",
  "market_type": "crypto",
  "allowed_strategy": ["trend_follow", "range_trade"]
}
```

## 读取顺序建议

1. `structure_summary` + `market.latest_price`
2. 最后一笔 `bi[-1]`、最后一个 `center[-1]`（若有）
3. `signal` 汇总
4. 需要细节时再展开 `bi` / `segment` 列表
