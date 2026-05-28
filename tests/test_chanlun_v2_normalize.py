"""chanlun_v2：active_strategy.direction=range 时自动纠正。"""
from __future__ import annotations

from app.schemas.flow_markets_deliverables import (
    ChanlunStateMachineOutput,
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
)


def _minimal_chanlun_v2(*, active_direction: str = "down") -> dict:
    return {
        "meta": {
            "symbol": "BTC/USDT",
            "interval": "1h",
            "price": 73000.0,
            "timestamp": "2026-01-01T00:00:00Z",
        },
        "state_machine": {
            "current_state": "STRATEGY_ACTIVE",
            "active_strategy": {
                "direction": active_direction,
                "status": "WAIT",
                "entry_gate": {
                    "price_zone": [72000.0, 73000.0],
                    "structure_required": ["price_hold_dd"],
                },
                "execution": {
                    "entry_type": "market",
                    "stop_loss": 78000.0,
                    "target": 72000.0,
                    "rr": 1.5,
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
            "price_position": "below_zs",
            "zs": {"zg": 77500, "zd": 76400, "gg": 77900, "dd": 76100},
        },
        "risk_notes": ["测试"],
    }


def test_range_active_direction_coerced_to_up_or_down():
    out = ChanlunStateMachineOutput.model_validate(_minimal_chanlun_v2(active_direction="range"))
    assert out.state_machine.active_strategy.direction in ("up", "down")
    assert out.state_machine.current_state == "OBSERVE_ONLY"
    dirs = [s.direction for s in out.state_machine.standby_strategies]
    assert "range" in dirs


def test_deliverable_accepts_llm_range_mistake():
    d = TechnicalAnalysisDeliverable(
        brief=TechnicalBrief(
            symbol="BTC/USDT",
            interval="1h",
            data_status="有足够K线",
            summary="震荡。",
            analysis_markdown="### 一、技术形态概述\n测试",
            disclaimer="不构成投资建议。",
        ),
        chanlun_v2=ChanlunStateMachineOutput.model_validate(
            _minimal_chanlun_v2(active_direction="range")
        ),
    )
    assert d.chanlun_v2 is not None
    assert d.chanlun_v2.state_machine.active_strategy.direction in ("up", "down")
