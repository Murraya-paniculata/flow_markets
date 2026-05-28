#!/usr/bin/env python3
"""项目根入口：用法同 scripts/flow_markets_ai.py（对齐 chanlun 的 chanlun_ai.py）。"""
from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "scripts" / "flow_markets_ai.py"
    runpy.run_path(str(script), run_name="__main__")
