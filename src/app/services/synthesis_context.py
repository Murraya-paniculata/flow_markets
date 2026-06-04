"""Phase 6.3–6.4：下游 Task 预注入（synthesis / trader / portfolio）。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from app.analysis_store.stats_formatter import format_stats_for_prompt
from app.analysis_store.stats_service import calculate_accuracy
from app.schemas.flow_markets_deliverables import (
    MarketStructureBrief,
    NarrativeBrief,
    ResearchSynthesis,
    SentimentAssessment,
    TechnicalAnalysisDeliverable,
    TradingPlaybook,
)

_PLACEHOLDER_NO_DATA = "（无结构化输出）"

_OBSERVE_ONLY_STATES = frozenset({"OBSERVE_ONLY"})
_WAIT_STATES = frozenset({"WAIT_CONFIRMATION"})
_AGGRESSIVE_STANCES = frozenset({"偏多思路", "偏空思路"})


def _model_to_json_text(model: BaseModel | None) -> str:
    if model is None:
        return _PLACEHOLDER_NO_DATA
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2)


def resolve_symbol_interval(
    deliverable: TechnicalAnalysisDeliverable | None,
    *,
    symbol_hint: str | None,
    timeframe: str,
) -> tuple[str, str]:
    sym = (symbol_hint or "").strip()
    interval = (timeframe or "1h").strip()
    if deliverable is not None:
        if deliverable.brief.symbol:
            sym = sym or deliverable.brief.symbol.strip()
        if deliverable.brief.interval:
            interval = deliverable.brief.interval.strip() or interval
        if deliverable.chanlun_v2 is not None:
            if deliverable.chanlun_v2.meta.symbol:
                sym = sym or deliverable.chanlun_v2.meta.symbol.strip()
            if deliverable.chanlun_v2.meta.interval:
                interval = deliverable.chanlun_v2.meta.interval.strip() or interval
    return sym or "（未指定）", interval


def build_analysis_stats_context(*, symbol: str, interval: str) -> str:
    """与 technical history 同源：全库 ``calculate_accuracy`` + 标的/周期格式化。"""
    try:
        stats = calculate_accuracy()
        return format_stats_for_prompt(stats, symbol, interval)
    except Exception as exc:
        return (
            "【系统历史表现】\n"
            f"统计查询失败（{exc}），研究经理请勿编造胜率数字。\n"
        )


def build_synthesis_injection_fields(
    *,
    governed_technical: TechnicalAnalysisDeliverable | None,
    market: MarketStructureBrief | None = None,
    narrative: NarrativeBrief | None = None,
    sentiment: SentimentAssessment | None = None,
    symbol_hint: str | None = None,
    timeframe: str = "1h",
) -> dict[str, str]:
    """
    供 ``task_fm_synthesis`` 模板使用的注入字段（均为字符串）。

    技术事实以 ``governed_technical_context`` 为准（服务端 enforcement + signal_quality 之后）。
    """
    sym, interval = resolve_symbol_interval(
        governed_technical,
        symbol_hint=symbol_hint,
        timeframe=timeframe,
    )
    return {
        "governed_technical_context": _model_to_json_text(governed_technical),
        "analysis_stats_context": build_analysis_stats_context(
            symbol=sym,
            interval=interval,
        ),
        "upstream_market_context": _model_to_json_text(market),
        "upstream_narrative_context": _model_to_json_text(narrative),
        "upstream_sentiment_context": _model_to_json_text(sentiment),
    }


def build_state_machine_summary(
    governed_technical: TechnicalAnalysisDeliverable | None,
) -> str:
    """从治理后交付物提取状态机快览（供 trader / portfolio Task）。"""
    if governed_technical is None or governed_technical.chanlun_v2 is None:
        return (
            "【缠论状态机快览】\n"
            "无有效 chanlun_v2。Playbook 应以观望/情景驱动为主，禁止编造入场区与止损价位。\n"
        )

    cv2 = governed_technical.chanlun_v2
    sm = cv2.state_machine
    active = sm.active_strategy
    gate = active.entry_gate
    exe = active.execution
    inv = sm.invalidation
    sj = cv2.structure_judgement
    lines = [
        "【缠论状态机快览】（治理后终稿，优先级高于 synthesis  prose 中的激进表述）",
        f"current_state: {sm.current_state}",
        f"active_strategy: direction={active.direction}, status={active.status}",
        f"entry_gate.price_zone: {gate.price_zone}",
        f"execution: stop_loss={exe.stop_loss}, target={exe.target}, rr={exe.rr}",
        f"invalidation.next_state: {inv.next_state}",
        f"structure_judgement: trend={sj.trend}, price_position={sj.price_position}",
        f"ZG/ZD: {sj.zs.zg}/{sj.zs.zd}",
    ]
    if inv.invalidate_active_if:
        lines.append("invalidate_active_if: " + "; ".join(inv.invalidate_active_if[:5]))
    if sm.standby_strategies:
        bits = [
            f"{s.direction}({'; '.join(s.activate_if[:2])})"
            for s in sm.standby_strategies[:3]
        ]
        lines.append("standby_strategies: " + ", ".join(bits))
    if cv2.risk_notes:
        notes = [n for n in cv2.risk_notes if n.strip()][:6]
        lines.append("risk_notes: " + " | ".join(notes))
    return "\n".join(lines) + "\n"


def build_signal_quality_summary(
    governed_technical: TechnicalAnalysisDeliverable | None,
) -> str:
    """六维信号质量（治理后写入 deliverable.signal_quality）。"""
    if governed_technical is None:
        return "【信号质量】无技术交付物。"
    sq = governed_technical.signal_quality
    if sq is None:
        return (
            "【信号质量】未写入评分（结构不足或跳过分）。"
            "Playbook 默认偏保守，execution_discipline 须强调模拟/回测。\n"
        )
    return (
        f"【信号质量】grade={sq.grade}（{sq.grade_name}） "
        f"action={sq.action}（{sq.action_name}） "
        f"score={sq.total_score:.1f}/100\n"
        f"signal_type={sq.signal_type} direction={sq.direction}\n"
        f"advice: {sq.advice or '（无）'}\n"
    )


def build_execution_context_fields(
    governed_technical: TechnicalAnalysisDeliverable | None,
    *,
    symbol_hint: str | None = None,
    timeframe: str = "1h",
) -> dict[str, str]:
    """Phase 6.4：trader / portfolio 与状态机、stats、signal_quality 对齐。"""
    sym, interval = resolve_symbol_interval(
        governed_technical,
        symbol_hint=symbol_hint,
        timeframe=timeframe,
    )
    return {
        "state_machine_summary": build_state_machine_summary(governed_technical),
        "signal_quality_summary": build_signal_quality_summary(governed_technical),
        "execution_stats_context": build_analysis_stats_context(
            symbol=sym,
            interval=interval,
        ),
    }


def build_full_downstream_injection_fields(
    *,
    governed_technical: TechnicalAnalysisDeliverable | None,
    market: MarketStructureBrief | None = None,
    narrative: NarrativeBrief | None = None,
    sentiment: SentimentAssessment | None = None,
    symbol_hint: str | None = None,
    timeframe: str = "1h",
) -> dict[str, str]:
    """synthesis + trader + portfolio 共用下游 kickoff inputs。"""
    return {
        **build_synthesis_injection_fields(
            governed_technical=governed_technical,
            market=market,
            narrative=narrative,
            sentiment=sentiment,
            symbol_hint=symbol_hint,
            timeframe=timeframe,
        ),
        **build_execution_context_fields(
            governed_technical,
            symbol_hint=symbol_hint,
            timeframe=timeframe,
        ),
    }


def check_trading_playbook_alignment(
    playbook: TradingPlaybook,
    governed_technical: TechnicalAnalysisDeliverable | None,
    *,
    synthesis: ResearchSynthesis | None = None,
) -> list[str]:
    """
    轻量一致性检查（仅返回警告文案，不阻断流程）。
    不接入回测引擎；供日志与测试使用。
    """
    warnings: list[str] = []
    if governed_technical is None or governed_technical.chanlun_v2 is None:
        if playbook.stance in _AGGRESSIVE_STANCES:
            warnings.append("无 chanlun_v2 但 playbook 为单边思路，建议改为观望")
        return warnings

    state = governed_technical.chanlun_v2.state_machine.current_state
    if state in _OBSERVE_ONLY_STATES and playbook.stance in _AGGRESSIVE_STANCES:
        warnings.append(
            f"state_machine={state} 与 stance={playbook.stance} 不一致，应以 watch_triggers 为主",
        )
    if state in _WAIT_STATES and playbook.stance in _AGGRESSIVE_STANCES:
        warnings.append(
            f"state_machine={state} 不宜直接偏多/偏空思路，优先情景驱动或观望",
        )

    sq = governed_technical.signal_quality
    if sq is not None and sq.action in ("skip", "wait") and playbook.stance in _AGGRESSIVE_STANCES:
        warnings.append(
            f"signal_quality.action={sq.action} 与 stance={playbook.stance} 偏激进",
        )

    if synthesis is not None:
        main = (synthesis.main_conclusion or "").lower()
        if "无法判定" in main or "观望" in main:
            if playbook.stance in _AGGRESSIVE_STANCES:
                warnings.append("synthesis 主结论偏谨慎但 playbook 为单边思路")

    return warnings
