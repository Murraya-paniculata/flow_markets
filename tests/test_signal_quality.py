"""signal_quality：六维评分与 deliverable 集成。"""

from __future__ import annotations

from typing import Any

import pytest

from app.analysis_store.signal_quality import (
    apply_signal_quality_to_deliverable,
    calculate_signal_quality,
    format_quality_report,
    reset_history_stats_cache,
)
from app.schemas.chan_structure import (
    ChanDataSize,
    ChanMarket,
    ChanMeta,
    ChanSignal,
    ChanStructureSnapshot,
    ChanStructureSummary,
)
from app.schemas.flow_markets_deliverables import (
    ChanlunStateMachineOutput,
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
)
from app.schemas.technical_analysis_display import (
    format_signal_quality_one_liner,
    format_trader_display,
)


def _chanlun_json(*, signal: list[str] | None = None, divergences: list[str] | None = None) -> dict[str, Any]:
    return {
        "signal": {
            "buy_sell_points": signal or ["1sell"],
            "divergences": divergences or ["bi"],
        },
        "structure_summary": {
            "trend": "consolidation",
            "price_position": "above_zs",
            "strength_comparison": "similar",
        },
    }


def _deliverable(direction: str = "down") -> TechnicalAnalysisDeliverable:
    return TechnicalAnalysisDeliverable(
        brief=TechnicalBrief(
            symbol="BTC/USDT",
            interval="1h",
            data_status="有足够K线",
            summary="测试摘要",
            analysis_markdown="# 一、技术形态概述\n测试",
            disclaimer="历史形态不保证未来表现；不构成投资建议。",
        ),
        chanlun_v2=ChanlunStateMachineOutput.model_validate(
            {
                "meta": {
                    "symbol": "BTC/USDT",
                    "interval": "1h",
                    "price": 70000.0,
                    "timestamp": "2026-01-01T00:00:00+00:00",
                },
                "state_machine": {
                    "current_state": "WAIT_CONFIRMATION",
                    "active_strategy": {
                        "direction": direction,
                        "status": "WAIT",
                        "entry_gate": {
                            "price_zone": [69500.0, 70100.0],
                            "structure_required": ["price_hold_zd"],
                        },
                        "execution": {
                            "entry_type": "limit",
                            "stop_loss": 71500.0,
                            "target": 66500.0,
                            "rr": 2.0,
                        },
                    },
                    "invalidation": {
                        "invalidate_active_if": ["price_break_zg"],
                        "next_state": "OBSERVE_ONLY",
                    },
                    "standby_strategies": [],
                },
                "structure_judgement": {
                    "trend": "consolidation",
                    "price_position": "above_zs",
                    "zs": {"zg": 71000, "zd": 69000, "gg": 71500, "dd": 68500},
                },
            }
        ),
    )


def test_calculate_signal_quality_from_deliverable() -> None:
    reset_history_stats_cache()
    ai = _deliverable("down").model_dump(mode="json")
    quality = calculate_signal_quality(_chanlun_json(), ai)
    assert 0 <= quality["total_score"] <= 100
    assert quality["grade"] in ("A", "B", "C", "D")
    assert quality["direction"] == "down"
    assert quality["signal_type"] == "1sell"
    assert "scores" in quality and len(quality["scores"]) == 6


def test_apply_signal_quality_to_deliverable() -> None:
    reset_history_stats_cache()
    d = _deliverable("down")
    updated = apply_signal_quality_to_deliverable(d, _chanlun_json())
    assert updated.signal_quality is not None
    assert updated.signal_quality.total_score == pytest.approx(
        sum(updated.signal_quality.scores.values()), abs=0.2
    )


def test_format_signal_quality_one_liner_in_trader_display() -> None:
    reset_history_stats_cache()
    d = apply_signal_quality_to_deliverable(_deliverable("down"), _chanlun_json())
    line = format_signal_quality_one_liner(d.signal_quality)  # type: ignore[arg-type]
    assert "信号质量" in line
    assert d.signal_quality.grade in line  # type: ignore[union-attr]

    text = format_trader_display(d)
    assert "信号质量" in text
    assert d.signal_quality.grade in text  # type: ignore[union-attr]


def test_format_quality_report_contains_dimensions() -> None:
    reset_history_stats_cache()
    quality = calculate_signal_quality(_chanlun_json(), _deliverable("down").model_dump(mode="json"))
    report = format_quality_report(quality)
    assert "信号质量评分" in report
    assert "信号类型" in report
    assert "盈亏比" in report


def test_apply_skips_without_chanlun_v2() -> None:
    d = _deliverable("down").model_copy(update={"chanlun_v2": None})
    assert apply_signal_quality_to_deliverable(d, _chanlun_json()) is d


def test_legacy_primary_scenario_still_works() -> None:
    reset_history_stats_cache()
    ai = {
        "primary_scenario": {
            "direction": "down",
            "target_pct": 2.5,
            "stop_pct": 1.5,
        }
    }
    quality = calculate_signal_quality(_chanlun_json(), ai)
    assert quality["direction"] == "down"
