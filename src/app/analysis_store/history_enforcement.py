"""Phase 2.7：根据 history.state_machine_hints 强制降级 deliverable。"""

from __future__ import annotations

from typing import Any

from app.schemas.flow_markets_deliverables import (
    ChanlunStateMachineOutput,
    TechnicalAnalysisDeliverable,
)

STATE_RANK = {
    "STRATEGY_ACTIVE": 0,
    "WAIT_CONFIRMATION": 1,
    "OBSERVE_ONLY": 2,
}


def state_rank(state: str | None) -> int:
    return STATE_RANK.get(str(state or "").strip(), -1)


def is_state_below_floor(current: str | None, floor: str | None) -> bool:
    if not floor:
        return False
    cur = state_rank(current)
    fl = state_rank(floor)
    if cur < 0 or fl < 0:
        return False
    return cur < fl


def _status_for_state(state: str) -> str:
    if state == "OBSERVE_ONLY":
        return "INVALIDATED"
    if state == "WAIT_CONFIRMATION":
        return "WAIT"
    return "READY"


def _build_enforcement_note(
    *,
    original_state: str,
    new_state: str,
    hints: dict[str, Any],
) -> str:
    basis = hints.get("basis") or "overall"
    rate = hints.get("basis_hit_rate")
    rate_text = f"{float(rate) * 100:.1f}%" if rate is not None else "偏低"
    parts = [
        f"历史胜率 {rate_text}（{basis}）",
    ]
    if hints.get("system_floor"):
        parts.append(f"系统下限={hints['system_floor']}")
    if hints.get("similar_cases_floor"):
        parts.append(f"相似案例下限={hints['similar_cases_floor']}")
    detail = "，".join(parts)
    return (
        f"[历史约束] 原状态 {original_state} 已强制降级为 {new_state}（{detail}）。"
    )


def enforce_chanlun_v2(
    v2: ChanlunStateMachineOutput,
    hints: dict[str, Any],
) -> tuple[ChanlunStateMachineOutput, dict[str, Any]]:
    floor = hints.get("recommended_floor")
    if not floor or not is_state_below_floor(v2.state_machine.current_state, floor):
        return v2, {"applied": False}

    original = v2.state_machine.current_state
    new_state = str(floor)
    active = v2.state_machine.active_strategy.model_copy(
        update={"status": _status_for_state(new_state)}
    )
    sm = v2.state_machine.model_copy(
        update={
            "current_state": new_state,  # type: ignore[arg-type]
            "active_strategy": active,
        }
    )
    note = _build_enforcement_note(
        original_state=original,
        new_state=new_state,
        hints=hints,
    )
    risk_notes = list(v2.risk_notes)
    if note not in risk_notes:
        risk_notes.append(note)

    updated = v2.model_copy(update={"state_machine": sm, "risk_notes": risk_notes})
    return updated, {
        "applied": True,
        "recommended_floor": floor,
        "original_state": original,
        "new_state": new_state,
        "note": note,
    }


def enforce_deliverable(
    deliverable: TechnicalAnalysisDeliverable,
    hints: dict[str, Any] | None,
) -> tuple[TechnicalAnalysisDeliverable, dict[str, Any]]:
    """若 history 建议下限高于 LLM 输出状态，强制降级 chanlun_v2。"""
    if deliverable.chanlun_v2 is None or not hints:
        return deliverable, {"applied": False, "reason": "no_chanlun_v2_or_hints"}

    floor = hints.get("recommended_floor")
    if not floor:
        return deliverable, {"applied": False, "reason": "no_recommended_floor"}

    updated_v2, result = enforce_chanlun_v2(deliverable.chanlun_v2, hints)
    if not result.get("applied"):
        return deliverable, result

    return deliverable.model_copy(update={"chanlun_v2": updated_v2}), result
