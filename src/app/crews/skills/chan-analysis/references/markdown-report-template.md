# 交易者 Markdown 报告（`brief.analysis_markdown`）

写入 **`brief.analysis_markdown`**（非 `summary`）。`summary` 仅 2～3 句执行摘要。

## 必须使用的标题（顺序不可打乱）

```markdown
### 一、技术形态概述
（1～2 段：基于工具 data 的缠论结构总览，禁止编造笔/中枢）

### 二、当前市场状态
- 最新价格：[来自 market.latest_price]
- 处于什么级别的中枢内/外
- 中枢范围变化情况
- 最后一笔的状态（向上/向下，是否完成）

### 三、关键技术信号
- 买卖点信号：[来自 signal.buy_sell_points，无则写「无」]
- 背驰信号：[来自 signal.divergences，无则写「无」]
- 中枢关系：[来自 center[].relation 等]

### 四、可能走势分析（概率排序）

#### 走势一：[描述]（概率：X%）
**技术依据**：
- …
**预期走势**：
- …

#### 走势二：[描述]（概率：Y%）
…

#### 走势三：[描述]（概率：Z%）
…

（至少 2 种、至多 3 种走势；概率为整数百分比，总和约 100%）

### 五、操作建议

**多头策略**：
- 入场点位区间：…
- 止损位：…
- 目标位：…

**空头策略**：
- 入场点位区间：…
- 止损位：…
- 目标位：…

**震荡策略**：
- 上沿做空：…
- 下沿做多：…
- 止损止盈设置：…

（三项策略须各给概率，与第四节走势概率逻辑一致）

### 六、风险提示
- …
- 请结合其他分析工具和市场消息综合判断，不建议单纯依据本分析进行交易决策。
```

## 约束

- 禁止均线、MACD、KDJ、RSI、消息面、情绪舆论作为依据。
- 价位须与 `structure_summary.key_levels`（ZG/ZD/GG/DD）及 `bi[]` 一致，不得虚构。
- 不得输出 JSON 代码块包裹本 Markdown；字段值为纯 Markdown 字符串。

---

## 多级别联立模式（`analysis_mode=multi_timeframe`）

Task 已预注入 `multi_timeframe_context`（4h / 1h / 15m）。**六节标题顺序不变**，但 **第二节必须写级别共振**；结构事实以预注入 JSON 的 `levels.*.summary` 为准，中级别 `snapshot` 作操作主周期（与 `chanlun_v2.meta.interval=1h` 一致）。详见 [multi-timeframe-mode.md](multi-timeframe-mode.md)。

### 第二节额外要求（当前市场状态）

在单周期四条 bullet 之后（或之中），**必须**增加一段 **「多级别联立」** 小节，至少包含：

- **大级别（4h）**：趋势 + 相对中枢位置（引用 `levels.large.summary`）
- **中级别（1h）**：趋势 + 买卖点/中枢（引用 `levels.medium.summary`）
- **小级别（15m）**：最新笔/入场时机（引用 `levels.small.summary`）
- **共振结论**：引用 `combined_judgment.resonance`（aligned / partial / mixed）与 `prompt_text` 或 `suggestion` 一句

示例句式（勿照抄数字，须替换为工具/预注入 JSON 中的实际字段）：

```markdown
### 二、当前市场状态
- 最新价格：…
- …（单周期四条可保留，价位以中级别为准）

**多级别联立**
- 4h：上升趋势，价格在中枢上方（大级别定方向：偏多）
- 1h：震荡盘整，价格在中枢内部（等待方向选择，关注 ZG/ZD）
- 15m：…（精入场：…）
- 共振：partial；大/中偏多、小级别待确认，主策略宜 WAIT_CONFIRMATION 而非激进追单
```

### 第四节、第五节与共振的衔接

| `combined_judgment.resonance` | 对走势概率 / 状态机的提示 |
|-------------------------------|---------------------------|
| `aligned` | 主推方向可与 `main_trend` 一致；单边走势概率可略高，仍受 history 硬约束 |
| `partial` | 两级别同向、一级别分歧；**避免任一方向 >50%**；第五节与 `chanlun_v2` 宜 WAIT_CONFIRMATION |
| `mixed` | 三级别分歧；**震荡概率通常最高（宜 ≥40%）**；`current_state` 宜 OBSERVE_ONLY 或 WAIT_CONFIRMATION |

`partial=true`（某周期计算失败）时，须在第二节说明缺失级别，第四节概率整体下调、表述保守。

### 多级别检查（写入前）

- [ ] 第二节含大/中/小 + 共振一句
- [ ] 第四节概率与 `resonance` / `main_trend` 不矛盾
- [ ] 第五节止损/目标与中级别 `levels.medium` 中枢价位一致
- [ ] 未用 1h 工具 `data` 覆盖预注入的大/小级别结构描述
