#!/usr/bin/env python3
"""初始化分析记忆库表结构（幂等）。

用法（在 flow_markets 项目根目录）:
  PYTHONPATH=src python scripts/init_analysis_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from app.analysis_store import get_db_conn, init_db


def main() -> None:
    path = init_db()
    with get_db_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM analysis_snapshot").fetchone()[0]
    print(f"✓ 分析库已就绪: {path.resolve()}")
    print(f"  analysis_snapshot 记录数: {n}")


if __name__ == "__main__":
    main()
