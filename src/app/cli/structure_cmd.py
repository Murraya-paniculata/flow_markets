"""structure 子命令：仅缠论结构（不调 LLM）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app.cli.common import clamp_lookback, display_symbol, normalize_symbol
from app.services.structure_only import run_structure_only


def run_structure(args: argparse.Namespace, *, root: Path) -> int:
    symbol = normalize_symbol(args.symbol)
    interval = (args.interval or "1h").lower().strip()
    lookback = clamp_lookback(args.limit)
    disp = display_symbol(symbol)

    print(f"\n📊 FlowMarkets 结构 {disp}" + (
        f"（多级别 4h/1h/15m × {lookback}）" if args.multi_tf else f" @ {interval}（{lookback} 根 K 线）"
    ))
    print("=" * 60)

    result, err = run_structure_only(
        symbol=symbol,
        timeframe=interval,
        lookback=lookback,
        multi_tf=args.multi_tf,
    )
    if err or result is None:
        print(f"   ✗ {err or '结构计算失败'}", file=sys.stderr)
        return 1

    print(result.report_content)

    if args.json:
        print("\n=== structure JSON ===\n")
        print(json.dumps(result.structure_payload, ensure_ascii=False, indent=2))

    if args.save:
        out_dir = root / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if args.multi_tf:
            path = out_dir / f"multi_timeframe_{symbol}_{ts}.json"
        else:
            path = out_dir / f"{symbol}_{interval}_{ts}_structure.json"
        path.write_text(
            json.dumps(result.structure_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"💾 结构 JSON: {path.resolve()}", file=sys.stderr)

    print("")
    return 0
