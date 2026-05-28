"""analysis_store.outcome：场景提取与 evaluate_outcome。"""

from __future__ import annotations

from app.analysis_store.outcome import (
    evaluate_outcome,
    extract_scenario_for_eval,
)


def _future_klines_up(entry: float, steps: int = 20) -> list[dict]:
    out = []
    for i in range(steps):
        p = entry * (1 + 0.002 * (i + 1))
        out.append({"open": p, "high": p * 1.001, "low": p * 0.999, "close": p})
    return out


def test_extract_scenario_from_chanlun_v2() -> None:
    ai = {
        "chanlun_v2": {
            "state_machine": {
                "current_state": "STRATEGY_ACTIVE",
                "active_strategy": {
                    "direction": "up",
                    "execution": {"target": 1030.0, "stop_loss": 970.0},
                },
            }
        }
    }
    s = extract_scenario_for_eval(ai, 1000.0)
    assert s is not None
    assert s.skip_reason is None
    assert s.direction == "up"
    assert s.target_pct == 3.0
    assert s.stop_pct == 3.0


def test_extract_scenario_skips_observe_only() -> None:
    ai = {
        "chanlun_v2": {
            "state_machine": {
                "current_state": "OBSERVE_ONLY",
                "active_strategy": {"direction": "up", "execution": {"target": 110, "stop_loss": 90}},
            }
        }
    }
    s = extract_scenario_for_eval(ai, 100.0)
    assert s is not None
    assert s.skip_reason == "observe_only"


def test_evaluate_outcome_up_hit_target() -> None:
    entry = 100.0
    ai = {
        "primary_scenario": {
            "direction": "up",
            "target_pct": 1.5,
            "stop_pct": 2.0,
        }
    }
    klines = _future_klines_up(entry, 30)
    out = evaluate_outcome(ai, klines, entry)
    assert "error" not in out
    assert out["direction"] == "up"
    assert out["hit_target"] is True
    assert out["score"] == 1.0


def test_evaluate_outcome_from_deliverable_shape() -> None:
    entry = 70000.0
    ai = {
        "brief": {"symbol": "BTC/USDT"},
        "chanlun_v2": {
            "state_machine": {
                "current_state": "WAIT_CONFIRMATION",
                "active_strategy": {
                    "direction": "up",
                    "execution": {"stop_loss": 68000.0, "target": 73000.0},
                },
            }
        },
    }
    klines = _future_klines_up(entry, 40)
    out = evaluate_outcome(ai, klines, entry)
    assert out.get("scenario_source") == "chanlun_v2"
    assert out["direction"] == "up"
    assert out["target_pct"] > 0
