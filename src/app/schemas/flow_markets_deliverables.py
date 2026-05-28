"""FlowMarkets 顺序研究链：各 Task 的 Pydantic 交付契约（契约驱动，对齐 08 模块 Task 课）。

与 ``flow_markets_api.py``（HTTP 入参/出参）区分：本模块仅描述 Crew 内部各步结构化交付物。
YAML 任务说明见 ``crews/config/flow_markets_tasks.yaml``。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, model_validator


Confidence3 = Literal["低", "中", "高"]
SourceCredibility = Literal["高", "中", "低", "未证实"]
DataStatus = Literal["有足够K线", "待K线数据"]
TradingStance = Literal["偏多思路", "偏空思路", "观望", "情景驱动"]

_DISCLAIMER_HINT = "必须明确不构成投资建议，加密资产波动极高。"


# -----------------------------------------------------------------------------
# 各阶段交付物（里程碑契约）
# -----------------------------------------------------------------------------


class MarketStructureBrief(BaseModel):
    """市场分析师交付物：《市场结构简报》。"""

    symbol: str = Field(..., description="标的或交易对；未指定时写「未指定」。")
    facts: list[str] = Field(
        ...,
        min_length=1,
        description="【事实】可公开验证的信息，每条独立一句，不编造具体价格/成交量。",
    )
    inferences: list[str] = Field(
        ...,
        min_length=1,
        description="【推断】基于事实的逻辑推演，须能对应到上文事实。",
    )
    assumptions: list[str] = Field(
        ...,
        min_length=1,
        description="【假设】待未来数据验证的命题，须写清何种数据可证伪。",
    )
    liquidity_and_market_phase: str = Field(
        ...,
        description="流动性状况与市场阶段判断；无链上/行情工具时标「待数据」并列出缺什么。",
    )
    key_drivers: list[str] = Field(
        ...,
        min_length=3,
        description="关键驱动因子清单，每条含「因子 + 影响机制 + 近期关注节点」。",
    )
    disclaimer: str = Field(..., description=_DISCLAIMER_HINT)
    not_investment_advice: Literal[False] = Field(
        False,
        description="必须为 false，强调不构成投资建议。",
    )


class NarrativeItem(BaseModel):
    """单条叙事条目。"""

    theme: str = Field(..., description="叙事主题，一句话。")
    source_tags: list[str] = Field(
        ...,
        min_length=1,
        description="信息源类型标签，如 official、media、community、KOL。",
    )
    credibility: SourceCredibility = Field(..., description="可信度：高/中/低/未证实。")
    summary: str = Field(..., description="叙事要点；与价格/成交量仅谈可能关联，不偷换因果。")


class NarrativeBrief(BaseModel):
    """舆情分析师交付物：《舆情与叙事摘要》。"""

    symbol: str = Field(..., description="标的。")
    narratives: list[NarrativeItem] = Field(..., min_length=1, description="主要叙事列表。")
    unverified_rumors: list[str] = Field(
        default_factory=list,
        description="未证实传言单独列出；无则空列表。",
    )
    pending_search_keywords: list[str] = Field(
        default_factory=list,
        description="无实时检索工具时，建议检索的关键词（3-8 个）。",
    )
    pending_channels: list[str] = Field(
        default_factory=list,
        description="建议关注的信息渠道类型，如官方公告、持牌媒体、链上监测。",
    )
    disclaimer: str = Field(..., description=_DISCLAIMER_HINT)


class SentimentSignal(BaseModel):
    """单条情绪/行为观察。"""

    signal: str = Field(..., description="观察项，如资金费率、拥挤度、恐惧贪婪等。")
    reading: str = Field(..., description="当前解读（概率语言，非确定性预言）。")
    invalidation: str = Field(..., description="何种数据或现象出现则该解读失效。")


class SentimentAssessment(BaseModel):
    """情绪分析师交付物：《情绪与行为评估》。"""

    symbol: str = Field(..., description="标的。")
    overall_tone: str = Field(..., description="整体情绪基调，2-4 句。")
    signals: list[SentimentSignal] = Field(..., min_length=2, description="结构化情绪信号列表。")
    tail_risks: list[str] = Field(..., min_length=1, description="极端情绪下的尾部风险。")
    disclaimer: str = Field(..., description=_DISCLAIMER_HINT)


class TechnicalBrief(BaseModel):
    """技术分析师交付物：《技术分析摘要》或待数据框架。"""

    symbol: str = Field(..., description="标的。")
    interval: str = Field(
        default="1h",
        description="get_chan_structure 使用的 K 线周期，如 1h、4h。",
    )
    data_status: DataStatus = Field(..., description="有足够K线 或 待K线数据。")
    summary: str = Field(
        ...,
        description=(
            "2～3 句执行摘要（趋势、位置、主推方向）；不得重复 analysis_markdown 全文。"
            "失效条件可在此简要列出。"
        ),
    )
    analysis_markdown: str = Field(
        default="",
        description=(
            "交易者可读 Markdown 长文（六节：形态概述、市场状态、技术信号、走势概率、操作建议、风险提示）；"
            "data_status=有足够K线 时必填，章节见 chan-analysis Skill markdown-report-template；"
            "无数据时留空。"
        ),
    )
    structure_quickview: str = Field(
        default="",
        description=(
            "缠论结构快览（仅 data_status=有足够K线 时必填，事实来自 get_chan_structure）："
            "按固定小节列出当前价、中枢(ZG/ZD)、最新笔、近期信号、笔/线段统计；"
            "无数据时留空字符串。"
        ),
    )
    missing_data_checklist: list[str] = Field(
        default_factory=list,
        description="待接入的数据项清单；有 K 线时可留空。",
    )
    disclaimer: str = Field(..., description="须含：历史形态不保证未来表现；不构成投资建议。")


# --- 策略状态机 v2.0（TechnicalAnalysisDeliverable.chanlun_v2，JSON 字段名保留）---

StateMachineState = Literal["STRATEGY_ACTIVE", "WAIT_CONFIRMATION", "OBSERVE_ONLY"]
StrategyDirection = Literal["up", "down"]
StrategyStatus = Literal["WAIT", "READY", "ACTIVE", "INVALIDATED"]
EntryType = Literal["market", "limit", "split"]
StandbyDirection = Literal["up", "down", "range"]


class ChanlunEntryGate(BaseModel):
    price_zone: list[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="入场区间 [低, 高]。",
    )
    structure_required: list[str] = Field(
        ...,
        min_length=1,
        description="缠论结构触发条件，如 price_hold_dd、15m_break_zd。",
    )


class ChanlunExecution(BaseModel):
    entry_type: EntryType = Field(..., description="market / limit / split。")
    stop_loss: float = Field(..., description="止损价。")
    target: float = Field(..., description="目标价。")
    rr: float = Field(..., gt=0, description="盈亏比，如 1.5。")


class ChanlunActiveStrategy(BaseModel):
    direction: StrategyDirection = Field(
        ...,
        description="仅允许 up 或 down；震荡主推勿填 range，应使用 standby_strategies.direction=range。",
    )
    status: StrategyStatus
    entry_gate: ChanlunEntryGate
    execution: ChanlunExecution


class ChanlunInvalidation(BaseModel):
    invalidate_active_if: list[str] = Field(
        ...,
        min_length=1,
        description="否决当前策略的条件（缠论术语）。",
    )
    next_state: str = Field(
        ...,
        description="否决后切换状态，如 OBSERVE_ONLY、RANGE_STRATEGY。",
    )


class ChanlunStandbyStrategy(BaseModel):
    direction: StandbyDirection
    activate_if: list[str] = Field(..., min_length=1)


class ChanlunStateMachine(BaseModel):
    current_state: StateMachineState
    active_strategy: ChanlunActiveStrategy
    invalidation: ChanlunInvalidation
    standby_strategies: list[ChanlunStandbyStrategy] = Field(default_factory=list)


class ChanlunAnalysisMeta(BaseModel):
    symbol: str
    interval: str
    price: float
    timestamp: str


class ChanlunStructureJudgementZs(BaseModel):
    zg: float
    zd: float
    gg: float
    dd: float


class ChanlunStructureJudgement(BaseModel):
    trend: str = Field(..., description="up_trend / down_trend / consolidation。")
    price_position: str = Field(..., description="above_zs / below_zs / inside_zs。")
    zs: ChanlunStructureJudgementZs


class ChanlunStateMachineOutput(BaseModel):
    """策略状态机 v2.0 结构化输出（version 2.0, output_mode=state_machine）。"""

    meta: ChanlunAnalysisMeta
    version: Literal["2.0"] = "2.0"
    output_mode: Literal["state_machine"] = "state_machine"
    state_machine: ChanlunStateMachine
    structure_judgement: ChanlunStructureJudgement
    risk_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_range_off_active_strategy(cls, data: Any) -> Any:
        """LLM 常把震荡写成 active_strategy.direction=range；改入 standby 并保留 up/down 激活腿。"""
        if not isinstance(data, dict):
            return data
        sm = data.get("state_machine")
        if not isinstance(sm, dict):
            return data
        active = sm.get("active_strategy")
        if not isinstance(active, dict):
            return data
        raw_dir = str(active.get("direction", "")).strip().lower()
        if raw_dir not in ("range", "震荡", "consolidation", "横盘"):
            return data

        sj = data.get("structure_judgement") or {}
        pos = str(sj.get("price_position", "")).lower()
        trend = str(sj.get("trend", "")).lower()
        if pos == "above_zs" or "up" in trend:
            active["direction"] = "up"
        elif pos == "below_zs" or "down" in trend:
            active["direction"] = "down"
        else:
            active["direction"] = "down"

        cur = str(sm.get("current_state", "")).strip()
        if cur == "STRATEGY_ACTIVE":
            sm["current_state"] = "OBSERVE_ONLY"
        elif not cur:
            sm["current_state"] = "OBSERVE_ONLY"

        standby = list(sm.get("standby_strategies") or [])
        if not any(
            isinstance(s, dict) and str(s.get("direction", "")).lower() == "range"
            for s in standby
        ):
            standby.append(
                {
                    "direction": "range",
                    "activate_if": ["price_inside_zs", "range_primary_scenario"],
                }
            )
        sm["standby_strategies"] = standby
        return data


class TechnicalAnalysisDeliverable(BaseModel):
    """技术分析师双交付：简报 brief + 策略状态机 chanlun_v2（一次 Task 输出）。"""

    brief: TechnicalBrief = Field(..., description="研究链下游使用的技术分析摘要。")
    chanlun_v2: ChanlunStateMachineOutput | None = Field(
        default=None,
        description=(
            "策略状态机 v2.0：含 state_machine、structure_judgement、risk_notes；"
            "get_chan_structure 成功时必填，失败时为 null。"
        ),
    )


class DisagreementRow(BaseModel):
    """研究经理：多空对峙表一行。"""

    topic: str = Field(..., description="对峙议题。")
    bullish_view: str = Field(..., description="多头/多方立场摘要。")
    bearish_view: str = Field(..., description="空头/空方立场摘要。")
    manager_note: str = Field(..., description="经理评注：证据强弱，不做最终裁决口号。")


class ScenarioOutlook(BaseModel):
    """备选情景。"""

    name: str = Field(..., description="情景名称，如向上突破/向下突破/延续震荡。")
    probability_note: str = Field(
        ...,
        description="主观概率区间或相对排序（定性，不作为量化输入）。",
    )
    triggers: list[str] = Field(..., min_length=1, description="触发条件列表。")
    narrative: str = Field(..., description="可能路径与主要风险点。")


class EvidenceRating(BaseModel):
    """关键命题的证据强度。"""

    proposition: str = Field(..., description="命题。")
    strength: Literal["高", "中高", "中", "中低", "低"] = Field(..., description="证据强度。")
    confidence_pct_note: str = Field(..., description="置信度说明（定性，如「约60%」）。")


class ResearchSynthesis(BaseModel):
    """研究经理交付物：《研究经理综合摘要》。"""

    symbol: str = Field(..., description="标的。")
    main_conclusion: str = Field(
        ...,
        description="主结论；证据不足时可为「无法判定」并说明原因。",
    )
    disagreements: list[DisagreementRow] = Field(
        default_factory=list,
        description="核心分歧对峙表。",
    )
    evidence_ratings: list[EvidenceRating] = Field(
        default_factory=list,
        description="关键命题证据强度评级。",
    )
    scenarios: list[ScenarioOutlook] = Field(
        ...,
        min_length=1,
        description="主结论与备选情景。",
    )
    information_gaps: list[str] = Field(
        ...,
        min_length=1,
        description="信息缺口清单，按优先级排序。",
    )
    next_research_steps: list[str] = Field(
        ...,
        min_length=1,
        description="下一步研究任务。",
    )
    disclaimer: str = Field(..., description=_DISCLAIMER_HINT)


class TradingPlaybook(BaseModel):
    """交易员交付物：《交易思路与风控检查清单》。"""

    symbol: str = Field(..., description="标的。")
    time_horizon: str = Field(..., description="时间尺度，如日内/波段/中线。")
    stance: TradingStance = Field(..., description="整体思路类型，非具体下单指令。")
    entry_logic_types: list[str] = Field(
        ...,
        min_length=1,
        description="入场逻辑类型（抽象规则，无具体价位）。",
    )
    risk_and_position_rules: list[str] = Field(
        ...,
        min_length=1,
        description="风控与仓位上限语义（相对规则，非具体数值喊单）。",
    )
    reduce_or_exit_logic: list[str] = Field(
        ...,
        min_length=1,
        description="减仓/退出逻辑类型。",
    )
    watch_triggers: list[str] = Field(
        ...,
        min_length=1,
        description="观望或加仓的触发条件；低置信时优先写观望条件。",
    )
    execution_discipline: list[str] = Field(
        ...,
        min_length=1,
        description="执行纪律；强调模拟与回测优先。",
    )
    high_risk_warnings: list[str] = Field(
        ...,
        min_length=1,
        description="杠杆/合约等高风险警示（若相关）。",
    )
    disclaimer: str = Field(..., description=_DISCLAIMER_HINT)


class PortfolioBrief(BaseModel):
    """组合经理交付物：《组合视角与免责声明》。"""

    symbol: str = Field(..., description="标的。")
    concentration_guidance: str = Field(..., description="单一标的与主题集中度管理原则（定性）。")
    correlation_guidance: str = Field(..., description="跨资产与加密内部相关性管理。")
    risk_budget_layers: list[str] = Field(
        ...,
        min_length=2,
        description="风险预算分层（如基础/战术/机会性）及当前环境建议。",
    )
    rebalance_principles: list[str] = Field(
        ...,
        min_length=2,
        description="再平衡与事件窗口原则。",
    )
    stress_narratives: list[str] = Field(
        default_factory=list,
        description="主要情景下的组合行为定性说明。",
    )
    disclaimer: str = Field(..., description="完整免责声明与适用人群提示。")
    not_investment_advice: Literal[False] = Field(False, description="必须为 false。")


# -----------------------------------------------------------------------------
# Markdown 渲染与报告组装
# -----------------------------------------------------------------------------

_Renderer = Callable[[BaseModel], str]

# 与 flow_markets_tasks.yaml / Crew Sequential 任务顺序一致（步骤 1–7）
_SECTION_STEPS: dict[str, tuple[int, str]] = {
    "MarketStructureBrief": (1, "市场结构简报"),
    "NarrativeBrief": (2, "舆情与叙事摘要"),
    "SentimentAssessment": (3, "情绪与行为评估"),
    "TechnicalBrief": (4, "技术分析摘要"),
    "TechnicalAnalysisDeliverable": (4, "技术分析（简报 + 状态机）"),
    "ResearchSynthesis": (5, "研究经理综合摘要"),
    "TradingPlaybook": (6, "交易思路与风控检查清单"),
    "PortfolioBrief": (7, "组合视角与免责声明"),
}


def _section_heading(model_key: str) -> str:
    step, title = _SECTION_STEPS[model_key]
    return f"## 步骤 {step} · {title}"


def _bullets(items: list[str], indent: int = 0) -> str:
    pad = " " * indent
    return "\n".join(f"{pad}- {x}" for x in items)


def _render_market(m: MarketStructureBrief) -> str:
    return f"""{_section_heading("MarketStructureBrief")}

**标的**：{m.symbol}

### 事实
{_bullets(m.facts)}

### 推断
{_bullets(m.inferences)}

### 假设
{_bullets(m.assumptions)}

### 流动性与市场阶段
{m.liquidity_and_market_phase}

### 关键驱动因子
{_bullets(m.key_drivers)}

### 声明
{m.disclaimer}
"""


def _render_narrative(m: NarrativeBrief) -> str:
    lines = [_section_heading("NarrativeBrief"), f"**标的**：{m.symbol}", ""]
    for i, n in enumerate(m.narratives, 1):
        tags = "、".join(n.source_tags)
        lines.append(
            f"### {i}. {n.theme}\n"
            f"- 来源：{tags} | 可信度：{n.credibility}\n"
            f"- {n.summary}\n"
        )
    if m.unverified_rumors:
        lines.append("### 未证实传言\n" + _bullets(m.unverified_rumors))
    if m.pending_search_keywords:
        lines.append("### 待检索关键词\n" + _bullets(m.pending_search_keywords))
    if m.pending_channels:
        lines.append("### 建议渠道\n" + _bullets(m.pending_channels))
    lines.append(f"\n### 声明\n{m.disclaimer}")
    return "\n".join(lines)


def _render_sentiment(m: SentimentAssessment) -> str:
    sig_lines = []
    for s in m.signals:
        sig_lines.append(
            f"- **{s.signal}**：{s.reading}（失效条件：{s.invalidation}）"
        )
    return f"""{_section_heading("SentimentAssessment")}

**标的**：{m.symbol}

### 整体基调
{m.overall_tone}

### 信号
{chr(10).join(sig_lines)}

### 尾部风险
{_bullets(m.tail_risks)}

### 声明
{m.disclaimer}
"""


def _render_chanlun_state_machine(sm: ChanlunStateMachineOutput) -> str:
    gate = sm.state_machine.active_strategy.entry_gate
    exe = sm.state_machine.active_strategy.execution
    inv = sm.state_machine.invalidation
    zs = sm.structure_judgement.zs
    zone = gate.price_zone
    standby_lines = []
    for s in sm.state_machine.standby_strategies:
        standby_lines.append(
            f"- **{s.direction}**：{'；'.join(s.activate_if)}"
        )
    standby_block = ""
    if standby_lines:
        standby_block = "\n### 待命策略\n" + "\n".join(standby_lines) + "\n"
    risk_block = ""
    if sm.risk_notes:
        risk_block = f"\n### 风险提示\n{_bullets(sm.risk_notes)}\n"
    return f"""
### 策略状态机（v2.0）

**meta**：{sm.meta.symbol} | {sm.meta.interval} | 价 {sm.meta.price} | {sm.meta.timestamp}

**current_state**：{sm.state_machine.current_state}

**active_strategy**（{sm.state_machine.active_strategy.direction} / {sm.state_machine.active_strategy.status}）
- 入场区间：{zone[0]} – {zone[1]}
- 结构条件：{_bullets(gate.structure_required, indent=2)}
- 执行：{exe.entry_type} | SL {exe.stop_loss} | TP {exe.target} | RR {exe.rr}

**invalidation**
- 否决：{_bullets(inv.invalidate_active_if, indent=2)}
- 下一状态：{inv.next_state}

**structure_judgement**：{sm.structure_judgement.trend} | {sm.structure_judgement.price_position} | ZG/ZD/GG/DD {zs.zg}/{zs.zd}/{zs.gg}/{zs.dd}
{standby_block}{risk_block}""".strip()


def _render_technical_analysis(m: TechnicalAnalysisDeliverable) -> str:
    inner = _render_technical(m.brief)
    body_start = 0
    for i, line in enumerate(inner.split("\n")):
        if line.startswith("**标的**"):
            body_start = i
            break
    body = "\n".join(inner.split("\n")[body_start:])
    chanlun = ""
    if m.chanlun_v2 is not None:
        chanlun = "\n\n" + _render_chanlun_state_machine(m.chanlun_v2)
    return f"""{_section_heading("TechnicalAnalysisDeliverable")}

#### FlowMarkets 简报

{body}{chanlun}"""


def _render_technical(m: TechnicalBrief) -> str:
    extra = ""
    if m.missing_data_checklist:
        extra = f"\n### 待接入数据\n{_bullets(m.missing_data_checklist)}\n"

    quickview_block = ""
    if (m.structure_quickview or "").strip():
        quickview_block = f"""
### 缠论结构快览

{m.structure_quickview.strip()}
"""

    analysis_block = ""
    if (m.analysis_markdown or "").strip():
        analysis_block = f"""
### AI 缠论分析（Markdown）

{m.analysis_markdown.strip()}
"""

    return f"""{_section_heading("TechnicalBrief")}

**标的**：{m.symbol} | **周期**：{m.interval or "—"} | **数据状态**：{m.data_status}

### 分析推断

{m.summary}
{quickview_block}{analysis_block}{extra}
### 声明
{m.disclaimer}
"""


def _render_synthesis(m: ResearchSynthesis) -> str:
    rows = []
    for d in m.disagreements:
        rows.append(
            f"| {d.topic} | {d.bullish_view} | {d.bearish_view} | {d.manager_note} |"
        )
    table = ""
    if rows:
        table = (
            "\n| 议题 | 多方 | 空方 | 经理评注 |\n|------|------|------|----------|\n"
            + "\n".join(rows)
            + "\n"
        )
    ratings = _bullets(
        [f"{e.proposition} — {e.strength}（{e.confidence_pct_note}）" for e in m.evidence_ratings]
    )
    scenarios = []
    for s in m.scenarios:
        scenarios.append(
            f"### {s.name}（{s.probability_note}）\n"
            f"- 触发：{_bullets(s.triggers)}\n"
            f"- 路径：{s.narrative}\n"
        )
    return f"""{_section_heading("ResearchSynthesis")}

**标的**：{m.symbol}

### 主结论
{m.main_conclusion}

### 分歧对峙
{table}
### 证据强度
{ratings}

### 情景
{chr(10).join(scenarios)}

### 信息缺口
{_bullets(m.information_gaps)}

### 下一步研究
{_bullets(m.next_research_steps)}

### 声明
{m.disclaimer}
"""


def _render_trading(m: TradingPlaybook) -> str:
    return f"""{_section_heading("TradingPlaybook")}

**标的**：{m.symbol} | **时间尺度**：{m.time_horizon} | **思路**：{m.stance}

### 入场逻辑类型
{_bullets(m.entry_logic_types)}

### 风控与仓位规则
{_bullets(m.risk_and_position_rules)}

### 减仓/退出逻辑
{_bullets(m.reduce_or_exit_logic)}

### 观察与触发条件
{_bullets(m.watch_triggers)}

### 执行纪律
{_bullets(m.execution_discipline)}

### 高风险警示
{_bullets(m.high_risk_warnings)}

### 声明
{m.disclaimer}
"""


def _render_portfolio(m: PortfolioBrief) -> str:
    stress = ""
    if m.stress_narratives:
        stress = f"\n### 情景压力\n{_bullets(m.stress_narratives)}\n"
    return f"""{_section_heading("PortfolioBrief")}

**标的**：{m.symbol}

### 集中度
{m.concentration_guidance}

### 相关性
{m.correlation_guidance}

### 风险预算
{_bullets(m.risk_budget_layers)}

### 再平衡原则
{_bullets(m.rebalance_principles)}
{stress}
### 免责声明
{m.disclaimer}
"""


_RENDERERS: dict[type[BaseModel], _Renderer] = {
    MarketStructureBrief: _render_market,
    NarrativeBrief: _render_narrative,
    SentimentAssessment: _render_sentiment,
    TechnicalBrief: _render_technical,
    TechnicalAnalysisDeliverable: _render_technical_analysis,
    ResearchSynthesis: _render_synthesis,
    TradingPlaybook: _render_trading,
    PortfolioBrief: _render_portfolio,
}


def render_task_deliverable(model: BaseModel) -> str:
    """将单步 Pydantic 交付物渲染为 Markdown 小节。"""
    renderer = _RENDERERS.get(type(model))
    if renderer:
        return renderer(model).strip()
    return model.model_dump_json(indent=2, ensure_ascii=False)


def assemble_flow_markets_report(
    result: Any,
    *,
    user_query: str = "",
    symbol: str = "",
) -> str | None:
    """
    从 Crew kickoff 结果组装完整 Markdown 报告（各 Task 结构化输出按序拼接）。
    """
    if result is None:
        return None

    sections: list[str] = []
    tasks_output = getattr(result, "tasks_output", None)
    if tasks_output:
        for task_out in tasks_output:
            pyd = getattr(task_out, "pydantic", None)
            if pyd is not None:
                sections.append(render_task_deliverable(pyd))
                continue
            raw = getattr(task_out, "raw", None)
            if isinstance(raw, str) and raw.strip():
                sections.append(raw.strip())

    if not sections:
        return None

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    single_technical = False
    if len(sections) == 1 and tasks_output:
        pyd0 = getattr(tasks_output[0], "pydantic", None)
        single_technical = isinstance(pyd0, TechnicalAnalysisDeliverable)
    title = (
        "# FlowMarkets 技术分析师报告"
        if single_technical
        else "# FlowMarkets 研究报告"
    )
    header = [
        title,
        "",
        f"- **研究问题**：{user_query or '（未提供）'}",
        f"- **标的**：{symbol or '（未指定）'}",
        f"- **生成时间**：{ts}",
        "",
        "---",
        "",
    ]
    return "\n".join(header) + "\n\n---\n\n".join(sections)
