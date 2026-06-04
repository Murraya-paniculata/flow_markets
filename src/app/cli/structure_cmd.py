"""structure 子命令：仅缠论结构（不调 LLM）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.cli.common import clamp_lookback, display_symbol, normalize_symbol
from app.services.analysis_output import write_structure_only_artifacts
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
        try:
            paths = write_structure_only_artifacts(
                symbol=symbol,
                structure_payload=result.structure_payload,
                multi_tf=args.multi_tf,
                interval=interval,
                project_root=root,
            )
            for rel in paths:
                print(f"💾 {rel}", file=sys.stderr)
        except Exception as exc:
            print(f"   ✗ 保存失败: {exc}", file=sys.stderr)

    print("")
    return 0
