# 多级别联立模式（analysis_mode=multi_timeframe）

与 chanlun `multi_level_analyzer.py` + `build_multi_level_prompt` 对齐：**服务端预计算 4h/1h/15m**，JSON 写入 Task 变量 `multi_timeframe_context`，AI 必须联立三级别分析。

单周期模式见 [input-envelope.md](input-envelope.md)。

---

## 何时进入本模式

- CLI：`scripts/multi_timeframe_analyze.py BTCUSDT`
- 程序：`run_technical_analyst_only(..., analysis_mode="multi_timeframe")`
- Task 中 `analysis_mode=multi_timeframe`

---

## 预注入 JSON 结构

```json
{
  "meta": { "symbol", "latest_price", "analysis_type": "multi_timeframe", ... },
  "partial": false,
  "combined_judgment": {
    "main_trend", "trend_strength", "resonance",
    "prompt_text", "suggestion", ...
  },
  "levels": {
    "large":  { "timeframe": "4h",  "summary": { ... } },
    "medium": { "timeframe": "1h",  "summary": { ... }, "snapshot": { ... } },
    "small":  { "timeframe": "15m", "summary": { ... } }
  }
}
```

- **大/小级别**：以 `summary` 为主（趋势、位置、信号、关键中枢）
- **中级别**：额外含完整 `snapshot`（与单周期 `data` 同构），作操作主周期
- **`combined_judgment.prompt_text`**：优先引用到 Markdown「二、当前市场状态」

---

## 与 get_chan_structure 的分工

| 来源 | 用途 |
|------|------|
| 预注入 JSON | 三级别结构事实、共振、概率分配依据 |
| `get_chan_structure` @ **1h** | **仅** `history`（胜率、相似案例、learning_feedback、state_machine_hints） |

禁止：用 1h 工具 `data` 覆盖预注入的大/小级别结构。

---

## 三级联立原则

1. **4h 定方向**：`combined_judgment.main_trend` 与 `levels.large.summary.trend` 一致表述
2. **1h 找买卖点**：`levels.medium` 的信号与中枢决定 `chanlun_v2` 主策略
3. **15m 精入场**：`levels.small` 用于细化 entry/stop，不单独推翻 4h

---

## 共振 → 状态机

| `combined_judgment.resonance` | 建议 |
|-------------------------------|------|
| `aligned` | 可 STRATEGY_ACTIVE（仍受 history 硬约束） |
| `partial` | 倾向 WAIT_CONFIRMATION |
| `mixed` | 倾向 OBSERVE_ONLY 或 WAIT_CONFIRMATION |

`partial=true`（某级别失败）时：brief 说明缺失级别，概率更保守。

---

## 交付要求（multi_timeframe）

- `brief.interval` / `chanlun_v2.meta.interval`：**1h**
- `analysis_markdown` 须含**多级别**段落（不可只写 1h）
- `structure_judgement` 与 **medium** 级别 summary 一致
- history 硬约束与单周期相同（见 [history-envelope.md](history-envelope.md)）

---

## 检查清单

- [ ] 已读预注入 JSON 三级 summary + combined_judgment
- [ ] 已调 get_chan_structure@1h 取 history
- [ ] Markdown 体现级别一致/分歧
- [ ] 未编造预注入 JSON 中不存在的笔/中枢
