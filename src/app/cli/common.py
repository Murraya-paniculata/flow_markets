"""CLI 公共工具（bootstrap、symbol 规范化）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MIN_LOOKBACK = 50


def bootstrap() -> Path:
    """将 ``src`` 加入 PYTHONPATH 并 chdir 到项目根（flow_markets/）。"""
    here = Path(__file__).resolve()
    root = here.parents[3]  # .../flow_markets/src/app/cli/common.py
    src = here.parents[2]
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    os.chdir(root)
    return root


def normalize_symbol(symbol: str) -> str:
    return (symbol or "").upper().replace("/", "").replace("-", "").strip()


def display_symbol(symbol: str) -> str:
    sym = normalize_symbol(symbol)
    if len(sym) > 6 and sym.endswith("USDT"):
        return f"{sym[:-4]}/USDT"
    if len(sym) > 6:
        return f"{sym[:3]}/{sym[3:]}"
    return sym


def clamp_lookback(limit: int) -> int:
    return max(MIN_LOOKBACK, int(limit))
