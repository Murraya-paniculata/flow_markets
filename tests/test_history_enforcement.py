"""Phase 2.7：history_enforcement 强制降级。"""

from __future__ import annotations

import pytest

from app.analysis_store.history_enforcement import (
    enforce_chanlun_v2,
    enforce_deliverable,
    is_state_below_floor,
)
from app.schemas.flow_markets_deliverables import (
    ChanlunStateMachineOutput,
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
)


def _deliverable_with_state(state: str) -> TechnicalAnalysisDeliverable:
    return TechnicalAnalysisDeliverable(
        brief=TechnicalBrief(
            symbol="BTC/USDT",
            interval="1h",
            data_status="有足够K线",
            summary="测试",
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
                    "current_state": state,
                    "active_strategy": {
                        "direction": "up",
                        "status": "READY" if state == "STRATEGY_ACTIVE" else "WAIT",
                        "entry_gate": {
                            "price_zone": [69500.0, 70100.0],
                            "structure_required": ["price_hold_zd"],
                        },
                        "execution": {
                            "entry_type": "limit",
                            "stop_loss": 68500.0,
                            "target": 72000.0,
                            "rr": 1.5,
                        },
                    },
                    "invalidation": {
                        "invalidate_active_if": ["price_break_zd"],
                        "next_state": "OBSERVE_ONLY",
                    },
                    "standby_strategies": [],
                },
                "structure_judgement": {
                    "trend": "consolidation",
                    "price_position": "inside_zs",
                    "zs": {"zg": 71000, "zd": 69000, "gg": 71500, "dd": 68500},
                },
                "risk_notes": ["原有风险"],
            }
        ),
    )


def _hints(floor: str) -> dict:
    return {
        "recommended_floor": floor,
        "basis": "for_symbol",
        "basis_hit_rate": 0.17,
        "system_floor": floor,
    }


def test_is_state_below_floor() -> None:
    assert is_state_below_floor("STRATEGY_ACTIVE", "WAIT_CONFIRMATION") is True
    assert is_state_below_floor("STRATEGY_ACTIVE", "OBSERVE_ONLY") is True
    assert is_state_below_floor("WAIT_CONFIRMATION", "OBSERVE_ONLY") is True
    assert is_state_below_floor("WAIT_CONFIRMATION", "WAIT_CONFIRMATION") is False
    assert is_state_below_floor("OBSERVE_ONLY", "WAIT_CONFIRMATION") is False


def test_enforce_observe_only_from_strategy_active() -> None:
    d = _deliverable_with_state("STRATEGY_ACTIVE")
    enforced, result = enforce_deliverable(d, _hints("OBSERVE_ONLY"))
    assert result["applied"] is True
    assert enforced.chanlun_v2 is not None
    assert enforced.chanlun_v2.state_machine.current_state == "OBSERVE_ONLY"
    assert enforced.chanlun_v2.state_machine.active_strategy.status == "INVALIDATED"
    assert any("[历史约束]" in n for n in enforced.chanlun_v2.risk_notes)


def test_enforce_wait_confirmation_from_strategy_active() -> None:
    d = _deliverable_with_state("STRATEGY_ACTIVE")
    enforced, result = enforce_deliverable(d, _hints("WAIT_CONFIRMATION"))
    assert result["applied"] is True
    assert enforced.chanlun_v2 is not None
    assert enforced.chanlun_v2.state_machine.current_state == "WAIT_CONFIRMATION"
    assert enforced.chanlun_v2.state_machine.active_strategy.status == "WAIT"


def test_no_enforcement_when_already_compliant() -> None:
    d = _deliverable_with_state("WAIT_CONFIRMATION")
    enforced, result = enforce_deliverable(d, _hints("WAIT_CONFIRMATION"))
    assert result["applied"] is False
    assert enforced.chanlun_v2.state_machine.current_state == "WAIT_CONFIRMATION"
    assert len(enforced.chanlun_v2.risk_notes) == 1


def test_no_enforcement_without_floor() -> None:
    d = _deliverable_with_state("STRATEGY_ACTIVE")
    enforced, result = enforce_deliverable(d, {"recommended_floor": None})
    assert result["applied"] is False


def test_no_enforcement_without_chanlun_v2() -> None:
    d = _deliverable_with_state("STRATEGY_ACTIVE").model_copy(update={"chanlun_v2": None})
    enforced, result = enforce_deliverable(d, _hints("OBSERVE_ONLY"))
    assert result["applied"] is False
    assert enforced.chanlun_v2 is None


def test_enforce_chanlun_v2_preserves_other_fields() -> None:
    d = _deliverable_with_state("STRATEGY_ACTIVE")
    v2 = d.chanlun_v2
    assert v2 is not None
    updated, result = enforce_chanlun_v2(v2, _hints("OBSERVE_ONLY"))
    assert result["applied"] is True
    assert updated.meta.symbol == "BTC/USDT"
    assert updated.state_machine.active_strategy.direction == "up"
