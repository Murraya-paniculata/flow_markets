"""买卖点 / 方向分类（stats_service 与 signal_quality 共用）。"""

from __future__ import annotations

from typing import Any


def classify_signal(buy_sell_points: list[Any], divergences: list[Any]) -> str:
    if not buy_sell_points and not divergences:
        return "none"

    for signal in buy_sell_points:
        signal_lower = str(signal).lower()
        if "1buy" in signal_lower:
            return "1buy"
        if "2buy" in signal_lower:
            return "2buy"
        if "3buy" in signal_lower:
            return "3buy"
        if "1sell" in signal_lower:
            return "1sell"
        if "2sell" in signal_lower:
            return "2sell"
        if "3sell" in signal_lower:
            return "3sell"

    for bc in divergences:
        bc_lower = str(bc).lower()
        if "bottom" in bc_lower or "底" in bc_lower:
            return "bc_buy"
        if "top" in bc_lower or "顶" in bc_lower:
            return "bc_sell"

    return "mixed"


def extract_direction_from_ai(
    ai: dict[str, Any],
    outcome: dict[str, Any] | None = None,
) -> str:
    primary = ai.get("primary_scenario") or {}
    direction = primary.get("direction")
    if direction:
        return str(direction)

    v2 = ai.get("chanlun_v2") or {}
    active = (v2.get("state_machine") or {}).get("active_strategy") or {}
    direction = active.get("direction")
    if direction:
        return str(direction)

    if outcome:
        return str(outcome.get("direction", "unknown"))
    return "unknown"
