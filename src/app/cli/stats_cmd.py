"""stats 子命令：分析记忆库查询与胜率统计（Phase 4.3）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.analysis_store import init_db
from app.analysis_store.query_stats_cli import (
    export_stats_csv,
    print_accuracy_report,
    print_db_overview,
    print_outcomes,
    print_snapshots,
)


def run_stats(args: argparse.Namespace, *, root: Path) -> int:
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

        output_dir = args.output_dir
        if not output_dir.is_absolute():
            output_dir = root / output_dir
        try:
            generate_all_stats_charts(output_dir, symbol=symbol, interval=interval)
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
