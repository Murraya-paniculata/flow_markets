"""Phase 6.3：synthesis 预注入字段。"""

from __future__ import annotations

from unittest.mock import patch

from app.schemas.flow_markets_deliverables import (
    MarketStructureBrief,
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
)
from app.services.synthesis_context import (
    build_analysis_stats_context,
    build_synthesis_injection_fields,
)


def _minimal_deliverable() -> TechnicalAnalysisDeliverable:
    return TechnicalAnalysisDeliverable(
        brief=TechnicalBrief(
            symbol="BTCUSDT",
            interval="1h",
            data_status="有足够K线",
            summary="测试",
            structure_quickview="qv",
            analysis_markdown="# 六节",
            disclaimer="不构成投资建议",
        ),
        chanlun_v2=None,
    )


def test_build_synthesis_injection_fields_contains_governed_and_upstream() -> None:
    market = MarketStructureBrief(
        symbol="BTCUSDT",
        facts=["宏观事实"],
        inferences=["推断"],
        assumptions=["假设"],
        liquidity_and_market_phase="震荡",
        key_drivers=["驱动1", "驱动2", "驱动3"],
        disclaimer="不构成投资建议",
    )
    fields = build_synthesis_injection_fields(
        governed_technical=_minimal_deliverable(),
        market=market,
        symbol_hint="BTCUSDT",
        timeframe="1h",
    )
    assert "governed_technical_context" in fields
    assert "BTCUSDT" in fields["governed_technical_context"]
    assert "upstream_market_context" in fields
    assert "宏观事实" in fields["upstream_market_context"]
    assert "analysis_stats_context" in fields
    assert "【系统历史表现】" in fields["analysis_stats_context"]


@patch("app.services.synthesis_context.calculate_accuracy")
def test_build_analysis_stats_context(mock_calc) -> None:
    mock_calc.return_value = {"total": 10, "hit_count": 6, "avg_score": 0.5, "by_direction": []}
    text = build_analysis_stats_context(symbol="BTCUSDT", interval="1h")
    assert "10" in text
    assert "60.0%" in text or "60%" in text
