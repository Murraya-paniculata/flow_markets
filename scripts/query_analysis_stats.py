#!/usr/bin/env python3
"""兼容入口 → 请改用 ``scripts/chanlun_fm.py stats``。

示例:
  uv run python scripts/query_analysis_stats.py --accuracy
  → uv run python scripts/chanlun_fm.py stats --accuracy
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
    return _load_chanlun_fm().main(["stats", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
