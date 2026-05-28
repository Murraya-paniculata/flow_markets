#!/usr/bin/env python3
"""单独运行技术分析师（Tool + Skill → brief + chanlun_v2）。

项目根目录示例::

  FM_CHAN_PROGRESS=1 uv run python scripts/run_technical_analyst.py

  uv run python scripts/run_technical_analyst.py --symbol BTCUSDT --timeframe 1h --lookback 300 \\
    --user-query "看 1h 缠论结构，给情景与失效条件"

  uv run python scripts/run_technical_analyst.py -o ./data/technical_brief.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _bootstrap() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))
    os.chdir(root)
    return root


def _to_jsonable(result: object) -> dict:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")  # type: ignore[union-attr]
    if isinstance(result, dict):
        return result
    return {"raw": str(result)}


def main() -> int:
    _bootstrap()

    parser = argparse.ArgumentParser(description="单独运行 technical_analyst（缠论工具 + Skill）")
    parser.add_argument("--symbol", default="BTCUSDT", help="交易对，如 BTCUSDT")
    parser.add_argument("--timeframe", default="1h", help="传给 get_chan_structure 的周期")
    parser.add_argument("--lookback", type=int, default=300, help="K 线回溯根数")
    parser.add_argument(
        "--user-query",
        default="请基于缠论结构给出技术分析摘要、情景与失效条件。",
        help="用户诉求（写入 Task 占位符）",
    )
    parser.add_argument("--notes", default="", help="补充说明；默认「单独运行 technical_analyst」")
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="保存 TechnicalAnalysisDeliverable JSON（含 brief 与 chanlun_v2）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="额外在文案后打印完整 JSON（默认只打印交易者可读文案）",
    )
    args = parser.parse_args()

    from app.crews.flows.flow_markets import run_technical_analyst_only
    from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable
    from app.schemas.technical_analysis_display import format_trader_display

    print(
        f"运行 technical_analyst：symbol={args.symbol} timeframe={args.timeframe} "
        f"lookback={args.lookback}",
        file=sys.stderr,
    )
    result, err = run_technical_analyst_only(
        args.user_query,
        args.symbol,
        args.notes or None,
        timeframe=args.timeframe,
        lookback=args.lookback,
    )
    if err:
        print(err, file=sys.stderr)
        if result is not None:
            print(json.dumps(_to_jsonable(result), ensure_ascii=False, indent=2))
        return 1

    if isinstance(result, TechnicalAnalysisDeliverable):
        print(format_trader_display(result))
    else:
        print("(无法生成交易者文案：输出未解析为 TechnicalAnalysisDeliverable)", file=sys.stderr)

    payload = _to_jsonable(result)
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"JSON 已保存: {out.resolve()}", file=sys.stderr)

    if args.json:
        print("\n=== JSON（brief + chanlun_v2）===\n")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
