#!/usr/bin/env python3
"""兼容入口 → 请改用 ``scripts/chanlun_fm.py analyze``。

示例:
  uv run python scripts/flow_markets_ai.py BTCUSDT 1h --table --limit 200
  → uv run python scripts/chanlun_fm.py analyze BTCUSDT 1h --limit 200
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_chanlun_fm():
    path = Path(__file__).resolve().with_name("chanlun_fm.py")
    spec = importlib.util.spec_from_file_location("_chanlun_fm", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 chanlun_fm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    argv = list(sys.argv[1:])
    if "--no-ai" in argv:
        argv = [a for a in argv if a != "--no-ai"]
        return _load_chanlun_fm().main(["structure", *argv])
    return _load_chanlun_fm().main(["analyze", *argv])


if __name__ == "__main__":
    raise SystemExit(main())
