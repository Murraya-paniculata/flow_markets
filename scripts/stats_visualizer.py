#!/usr/bin/env python3
"""统计图表 PNG 导出（Phase 4.4，对标 chanlun stats_visualizer.py）。

用法（flow_markets 根目录，需 matplotlib）:
  uv sync --extra chart
  uv run python scripts/stats_visualizer.py
  uv run python scripts/stats_visualizer.py --output-dir output/stats
  uv run python scripts/stats_visualizer.py --symbol BTC/USDT --interval 1h
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from app.analysis_store import init_db
from app.analysis_store.stats_visualizer import (
    MatplotlibNotAvailableError,
    generate_all_stats_charts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成分析统计图表 PNG")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_ROOT / "output" / "stats",
        help="PNG 输出目录（默认 output/stats）",
    )
    parser.add_argument("--symbol", type=str, default=None, help="筛选交易对")
    parser.add_argument("--interval", type=str, default=None, help="筛选周期")
    args = parser.parse_args()

    init_db()
    symbol = (args.symbol or "").strip() or None
    interval = (args.interval or "").strip() or None

    print("=" * 60)
    print("  FlowMarkets 统计图表可视化")
    print("=" * 60)

    try:
        paths = generate_all_stats_charts(
            args.output_dir,
            symbol=symbol,
            interval=interval,
        )
    except MatplotlibNotAvailableError as exc:
        print(f"\n[错误] {exc}\n")
        return 1

    if not paths:
        return 0

    print(f"\n输出目录: {args.output_dir.resolve()}\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\n[中断] 用户取消\n")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n\n[错误] {exc}\n")
        traceback.print_exc()
        raise SystemExit(1)
