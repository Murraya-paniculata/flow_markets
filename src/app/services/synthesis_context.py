"""Phase 6.3：研究经理 synthesis 预注入（治理后 technical + 分析库 stats + 上游三域）。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from app.analysis_store.stats_formatter import format_stats_for_prompt
from app.analysis_store.stats_service import calculate_accuracy
from app.schemas.flow_markets_deliverables import (
    MarketStructureBrief,
    NarrativeBrief,
    SentimentAssessment,
    TechnicalAnalysisDeliverable,
)

_PLACEHOLDER_NO_DATA = "（无结构化输出）"


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
