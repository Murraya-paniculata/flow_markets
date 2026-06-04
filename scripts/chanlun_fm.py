#!/usr/bin/env python3
"""FlowMarkets 统一 CLI（Phase 5.3，对标 chanlun chanlun_ai.py）。

子命令:
  analyze    结构 + AI 技术分析师（单周期或多级别联立）
  structure  仅缠论结构（不调 LLM）
  stats      分析记忆库查询与胜率统计

示例（flow_markets 根目录）::

  FM_CHAN_PROGRESS=1 uv run python scripts/chanlun_fm.py analyze BTCUSDT 1h --limit 200 --save
  uv run python scripts/chanlun_fm.py analyze BTCUSDT 1h --multi-tf --save
  uv run python scripts/chanlun_fm.py structure BTCUSDT 1h --limit 200
  uv run python scripts/chanlun_fm.py structure BTCUSDT --multi-tf
  uv run python scripts/chanlun_fm.py stats --accuracy
  uv run python scripts/chanlun_fm.py stats --export-csv output/stats_export.csv
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chanlun_fm",
        description="FlowMarkets 缠论 CLI（analyze / structure / stats）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  chanlun_fm.py analyze BTCUSDT 1h --limit 200 --save
  chanlun_fm.py analyze BTCUSDT 1h --multi-tf
  chanlun_fm.py structure ETHUSDT 4h --json
  chanlun_fm.py stats --accuracy --symbol BTC/USDT
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="结构 + AI 分析")
    p_analyze.add_argument("symbol", help="交易对，如 BTCUSDT")
    p_analyze.add_argument("interval", help="周期（单周期模式），如 1h 4h；--multi-tf 时作展示用")
    p_analyze.add_argument("--limit", type=int, default=300, help="K 线回溯根数（lookback）")
    p_analyze.add_argument(
        "--multi-tf",
        action="store_true",
        help="多级别联立 4h/1h/15m（忽略 interval 作计算周期）",
    )
    p_analyze.add_argument("--save", action="store_true", help="写 output/ 并强制落库")
    p_analyze.add_argument("--user-query", default="", help="自定义研究问题")
    p_analyze.add_argument("--json", action="store_true", help="额外打印 Deliverable JSON")
    p_analyze.add_argument(
        "--table",
        action="store_true",
        help="交易者可读输出（默认已开启，与 chanlun --table 同类）",
    )
    _add_engine_flags(p_analyze)

    p_structure = sub.add_parser("structure", help="仅缠论结构（不调 LLM）")
    p_structure.add_argument("symbol", help="交易对")
    p_structure.add_argument(
        "interval",
        nargs="?",
        default="1h",
        help="单周期模式下的周期（默认 1h；--multi-tf 时可省略）",
    )
    p_structure.add_argument("--limit", type=int, default=300, help="K 线回溯根数")
    p_structure.add_argument("--multi-tf", action="store_true", help="多级别 4h/1h/15m")
    p_structure.add_argument("--save", action="store_true", help="保存结构 JSON 到 output/")
    p_structure.add_argument("--json", action="store_true", help="终端打印结构 JSON")
    _add_engine_flags(p_structure)

    p_stats = sub.add_parser("stats", help="分析库统计")
    p_stats.add_argument("--snapshots", action="store_true", help="最近分析快照")
    p_stats.add_argument("--outcomes", action="store_true", help="最近 outcome 回填")
    p_stats.add_argument("--accuracy", action="store_true", help="准确率与分维度胜率")
    p_stats.add_argument("--export-csv", type=Path, metavar="FILE", help="导出 CSV")
    p_stats.add_argument("--limit", type=int, default=10, help="列表条数")
    p_stats.add_argument("--symbol", default=None, help="筛选交易对")
    p_stats.add_argument("--interval", default=None, help="筛选周期")
    p_stats.add_argument("--charts", action="store_true", help="生成 PNG 到 output/stats")
    p_stats.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/stats"),
        help="--charts 输出目录",
    )

    return parser


def _add_engine_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--engine",
        choices=("structure-engine", "chanlun_icl"),
        default=None,
        help="结构引擎（默认 APP_CHAN_STRUCTURE_ENGINE=structure-engine；chanlun_icl 仅对比）",
    )
    parser.add_argument(
        "--zs-algo",
        choices=("normal", "over_seg", "auto"),
        default=None,
        dest="zs_algo",
        help="chanpy 中枢算法（仅 structure-engine；默认 APP_CHAN_ZS_ALGO=normal）",
    )


def main(argv: list[str] | None = None) -> int:
    from app.cli.analyze_cmd import run_analyze
    from app.cli.common import bootstrap
    from app.cli.stats_cmd import run_stats
    from app.cli.structure_cmd import run_structure

    parser = _build_parser()
    args = parser.parse_args(argv)
    root = bootstrap()
    os.environ.setdefault("FM_CHAN_PROGRESS", "1")

    if args.command == "analyze":
        return run_analyze(args, root=root)
    if args.command == "structure":
        return run_structure(args, root=root)
    if args.command == "stats":
        return run_stats(args, root=root)
    parser.error(f"未知子命令: {args.command}")
    return 2


if __name__ == "__main__":
    # scripts/ 入口：确保可 import app
    _root = Path(__file__).resolve().parents[1]
    _src = _root / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\n[中断] 用户取消\n")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n\n[错误] {exc}\n")
        traceback.print_exc()
        raise SystemExit(1)
