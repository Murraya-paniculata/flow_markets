#!/usr/bin/env python3
"""导出 get_chan_structure 工具结果为 JSON 夹具（写入 data/fixtures/）。

用法（项目根目录）:
  uv run python scripts/export_chan_structure_fixture.py
  uv run python scripts/export_chan_structure_fixture.py --symbol ETHUSDT --timeframe 1h --lookback 200
  uv run python scripts/export_chan_structure_fixture.py -o data/fixtures/my_snapshot.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from app.crews.tools import GetChanStructureTool  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="导出缠论结构快照 JSON")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="4h")
    parser.add_argument("--lookback", type=int, default=300)
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="输出路径；默认 data/fixtures/chan_structure_{symbol}_{timeframe}_{lookback}.json",
    )
    args = parser.parse_args()

    sym = args.symbol.upper().replace("/", "")
    if args.output:
        out = Path(args.output)
    else:
        out = _ROOT / "data" / "fixtures" / f"chan_structure_{sym.lower()}_{args.timeframe}_{args.lookback}.json"

    out.parent.mkdir(parents=True, exist_ok=True)
    text = GetChanStructureTool()._run(
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback=args.lookback,
    )
    out.write_text(text, encoding="utf-8")

    payload = json.loads(text)
    print(f"saved: {out.resolve()}")
    print(f"chars: {len(text)}")
    if payload.get("ok"):
        data = payload["data"]
        print(
            f"ok=true bi={len(data.get('bi', []))} "
            f"segment={len(data.get('segment', []))} "
            f"center={len(data.get('center', []))}"
        )
    else:
        print(f"ok=false error_code={payload.get('error_code')}")


if __name__ == "__main__":
    main()
