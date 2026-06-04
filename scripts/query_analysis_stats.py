#!/usr/bin/env python3
"""分析记忆库查询与胜率统计（Phase 4.3，对标 chanlun query_stats.py）。

用法（flow_markets 根目录）:
  uv run python scripts/query_analysis_stats.py
  uv run python scripts/query_analysis_stats.py --accuracy
  uv run python scripts/query_analysis_stats.py --snapshots --limit 20
  uv run python scripts/query_analysis_stats.py --outcomes --limit 20
  uv run python scripts/query_analysis_stats.py --accuracy --symbol BTC/USDT --interval 1h
  uv run python scripts/query_analysis_stats.py --export-csv output/stats_export.csv
  uv run python scripts/query_analysis_stats.py --charts
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
from app.analysis_store.query_stats_cli import (
    export_stats_csv,
    print_accuracy_report,
    print_db_overview,
    print_outcomes,
    print_snapshots,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="分析库查询与统计（胜率按趋势/位置/信号类型等）",
    )
    parser.add_argument("--snapshots", action="store_true", help="显示最近分析快照列表")
    parser.add_argument("--outcomes", action="store_true", help="显示最近评估回填结果")
    parser.add_argument("--accuracy", action="store_true", help="显示准确率与分维度胜率报表")
    parser.add_argument(
        "--export-csv",
        type=Path,
        metavar="FILE",
        help="导出可计分记录到 CSV（含结构上下文与信号质量列）",
    )
    parser.add_argument("--limit", type=int, default=10, help="快照/结果列表条数（默认 10）")
    parser.add_argument("--symbol", type=str, default=None, help="筛选交易对，如 BTC/USDT")
    parser.add_argument("--interval", type=str, default=None, help="筛选周期，如 1h")
    parser.add_argument(
        "--charts",
        action="store_true",
        help="生成统计 PNG 到 output/stats（需 uv sync --extra chart）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_ROOT / "output" / "stats",
        help="配合 --charts 的 PNG 输出目录",
    )
    args = parser.parse_args()

    init_db()
    symbol = (args.symbol or "").strip() or None
    interval = (args.interval or "").strip() or None

    if args.export_csv:
        export_stats_csv(args.export_csv, symbol=symbol, interval=interval)
        return 0

    if args.charts:
        from app.analysis_store.stats_visualizer import (
            MatplotlibNotAvailableError,
            generate_all_stats_charts,
        )

        try:
            generate_all_stats_charts(
                args.output_dir,
                symbol=symbol,
                interval=interval,
            )
        except MatplotlibNotAvailableError as exc:
            print(f"\n[错误] {exc}\n", file=sys.stderr)
            return 1
        if not (args.snapshots or args.outcomes or args.accuracy):
            return 0

    show_all = not (args.snapshots or args.outcomes or args.accuracy)

    if show_all:
        print_db_overview()

    if show_all or args.snapshots:
        print_snapshots(args.limit, symbol=symbol, interval=interval)

    if show_all or args.outcomes:
        print_outcomes(args.limit, symbol=symbol, interval=interval)

    if show_all or args.accuracy:
        print_accuracy_report(symbol=symbol, interval=interval)

    if show_all:
        print("[完成] 逐行查看快照 → scripts/show_analysis_db.py")
        print("[完成] 回填 outcome → scripts/evaluate_outcomes.py\n")
    else:
        print("[完成]\n")

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
