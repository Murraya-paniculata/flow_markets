"""FlowMarkets 运行模式（Phase 6.1：technical_only | full）。"""

from __future__ import annotations

from typing import Literal

from app.core.config import get_settings

FlowMarketsMode = Literal["technical_only", "full"]

FLOW_MARKETS_MODE_TECHNICAL_ONLY: FlowMarketsMode = "technical_only"
FLOW_MARKETS_MODE_FULL: FlowMarketsMode = "full"

_VALID_MODES = frozenset({FLOW_MARKETS_MODE_TECHNICAL_ONLY, FLOW_MARKETS_MODE_FULL})


def get_flow_markets_mode() -> FlowMarketsMode:
    """当前模式；默认 ``technical_only``（与 Phase 5 行为一致）。"""
    mode = get_settings().flow_markets_mode
    if mode in _VALID_MODES:
        return mode
    return FLOW_MARKETS_MODE_TECHNICAL_ONLY


def is_flow_markets_full_mode() -> bool:
    return get_flow_markets_mode() == FLOW_MARKETS_MODE_FULL


def flow_markets_metrics_flow_name() -> str:
    return "flow_markets_full" if is_flow_markets_full_mode() else "flow_markets"
