#!/usr/bin/env python3
"""
本地命令行：不启动 HTTP，直接跑 FlowMarkets 编排。

零参数即可运行（使用内置默认或环境变量 FM_USER_QUERY / FM_SYMBOL / FM_OUTPUT）::

  python scripts/run_flow_markets.py

也可传参覆盖::

  python scripts/run_flow_markets.py "ETH 中线结构" ETH
  python scripts/run_flow_markets.py -o ./data/custom.md
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 无参数时的默认研究主题（可用环境变量覆盖）
_DEFAULT_QUERY = "BTC 波动与情绪"
_DEFAULT_SYMBOL = "BTC"
_DEFAULT_OUTPUT_DIR = "./data"


def _bootstrap() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))
    os.chdir(root)
    return root


def main() -> int:
    _bootstrap()

    parser = argparse.ArgumentParser(
        description="FlowMarkets：命令行跑研究编排（无参数时使用默认 BTC 研究主题）",
    )
    parser.add_argument("query", nargs="?", default="", help="研究问题（可选）")
    parser.add_argument("symbol_pos", nargs="?", default="", help="标的（可选）")
    parser.add_argument("--user-query", default="", help="研究问题")
    parser.add_argument("--symbol", default="", help="标的或交易对")
    parser.add_argument("--notes", default="", help="补充说明")
    parser.add_argument(
        "--pipeline",
        choices=("yaml", "trading_agents"),
        default=os.environ.get("FM_PIPELINE", "yaml"),
    )
    parser.add_argument("--analysis-date", default="")
    parser.add_argument("--stage", default="")
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="报告路径；未指定则写入 ./data/flow_markets_<时间戳>.md",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="将报告打印到终端，不写文件",
    )
    args = parser.parse_args()

    user_query = (
        args.user_query
        or args.query
        or os.environ.get("FM_USER_QUERY", _DEFAULT_QUERY)
    ).strip()
    symbol_raw = (
        args.symbol
        or args.symbol_pos
        or os.environ.get("FM_SYMBOL", _DEFAULT_SYMBOL)
    ).strip()
    symbol = symbol_raw or None

    output_path: Path | None = None
    if not args.stdout and args.output:
        output_path = Path(args.output)

    from app.crews.flows.flow_markets import analyze_flow_markets, flow_markets_report_path

    if output_path is None and not args.stdout:
        explicit = os.environ.get("FM_OUTPUT", "").strip()
        output_path = (
            Path(explicit)
            if explicit
            else flow_markets_report_path(_DEFAULT_OUTPUT_DIR)
        )

    print(
        f"FlowMarkets 开始：query={user_query!r} symbol={symbol!r} pipeline={args.pipeline}",
        file=sys.stderr,
    )
    if output_path:
        print(f"报告将写入：{output_path}", file=sys.stderr)

    report, err = analyze_flow_markets(
        user_query,
        symbol=symbol,
        notes=args.notes or None,
        pipeline=args.pipeline,  # type: ignore[arg-type]
        analysis_date=args.analysis_date or None,
        stage=args.stage or None,
        output_path=output_path,
    )

    if err:
        print(err, file=sys.stderr)
        return 1
    if output_path:
        print(f"完成，已写入：{output_path.resolve()}", file=sys.stderr)
    elif report:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
