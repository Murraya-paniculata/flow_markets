"""Phase 6.3：full 模式两段 Crew + 治理后注入 synthesis。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.crews.flows.flow_markets import (
    FlowMarketsCrew,
    _kickoff_full_flow_markets_split,
    _merge_kickoff_results,
)
from app.schemas.flow_markets_deliverables import (
    MarketStructureBrief,
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
)


def _technical_raw() -> TechnicalAnalysisDeliverable:
    return TechnicalAnalysisDeliverable(
        brief=TechnicalBrief(
            symbol="BTCUSDT",
            interval="1h",
            data_status="有足够K线",
            summary="raw",
            structure_quickview="qv",
            analysis_markdown="# md",
            disclaimer="不构成投资建议",
        ),
        chanlun_v2=None,
    )


def _task_out(pydantic) -> SimpleNamespace:
    return SimpleNamespace(pydantic=pydantic, raw="")


def test_merge_kickoff_results_order() -> None:
    up = SimpleNamespace(tasks_output=[_task_out("a")])
    down = SimpleNamespace(tasks_output=[_task_out("b")])
    merged = _merge_kickoff_results(up, down)
    assert len(merged.tasks_output) == 2
    assert merged.tasks_output[0].pydantic == "a"
    assert merged.tasks_output[1].pydantic == "b"


@patch("app.crews.flows.flow_markets._create_downstream_crew")
@patch("app.crews.flows.flow_markets._create_upstream_crew")
@patch("app.crews.flows.flow_markets._govern_technical_deliverable")
def test_kickoff_full_split_injects_synthesis_fields(
    mock_govern: MagicMock,
    mock_upstream_crew: MagicMock,
    mock_downstream_crew: MagicMock,
) -> None:
    governed = _technical_raw()
    governed.brief.summary = "governed"
    mock_govern.return_value = governed

    market = MarketStructureBrief(
        symbol="BTCUSDT",
        facts=["f1"],
        inferences=["i1"],
        assumptions=["a1"],
        liquidity_and_market_phase="x",
        key_drivers=["d1", "d2", "d3"],
        disclaimer="不构成投资建议",
    )
    upstream_result = SimpleNamespace(
        tasks_output=[
            _task_out(market),
            _task_out(_technical_raw()),
        ],
    )
    downstream_result = SimpleNamespace(tasks_output=[_task_out("synthesis")])

    up_crew = MagicMock()
    up_crew.kickoff.return_value = upstream_result
    mock_upstream_crew.return_value = up_crew

    down_crew = MagicMock()
    down_crew.kickoff.return_value = downstream_result
    mock_downstream_crew.return_value = down_crew

    flow = MagicMock(spec=FlowMarketsCrew)
    inputs = {
        "user_query": "测试",
        "symbol": "BTCUSDT",
        "notes": "无",
        "analysis_mode": "single",
        "multi_timeframe_context": "",
        "primary_timeframe": "1h",
        "lookback": "300",
    }

    merged, deliverable = _kickoff_full_flow_markets_split(
        flow,
        inputs,
        persist_tf="1h",
        lookback=300,
        symbol_hint="BTCUSDT",
    )

    assert deliverable is governed
    assert len(merged.tasks_output) == 3
    down_inputs = down_crew.kickoff.call_args.kwargs["inputs"]
    assert "state_machine_summary" in down_inputs
    assert "signal_quality_summary" in down_inputs
    assert "execution_stats_context" in down_inputs
    assert "governed" in down_inputs["governed_technical_context"]
    assert "upstream_market_context" in down_inputs
