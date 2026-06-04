"""structure 子命令：仅缠论结构（不调 LLM）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app.cli.common import clamp_lookback, display_symbol, normalize_symbol


def run_structure(args: argparse.Namespace, *, root: Path) -> int:
    symbol = normalize_symbol(args.symbol)
    interval = args.interval.lower().strip()
    lookback = clamp_lookback(args.limit)
    disp = display_symbol(symbol)

    if args.multi_tf:
        return _run_multi_structure(
            root=root,
            symbol=symbol,
            disp=disp,
            lookback=lookback,
            save=args.save,
            as_json=args.json,
        )
    return _run_single_structure(
        root=root,
        symbol=symbol,
        interval=interval,
        disp=disp,
        lookback=lookback,
        save=args.save,
        as_json=args.json,
    )


def _run_single_structure(
    *,
    root: Path,
    symbol: str,
    interval: str,
    disp: str,
    lookback: int,
    save: bool,
    as_json: bool,
) -> int:
    print(f"\n📊 FlowMarkets 结构 {disp} @ {interval}（{lookback} 根 K 线）")
    print("=" * 60)

    try:
        from app.services.chan.structure import build_chan_structure_snapshot
        from app.schemas.technical_analysis_display import format_structure_cli_summary

        snapshot = build_chan_structure_snapshot(symbol, interval, lookback=lookback)
    except Exception as exc:
        print(f"   ✗ 结构计算失败: {exc}", file=sys.stderr)
        return 1

    ds = snapshot.meta.data_size
    print(f"   ✓ K 线 {ds.kline} 根；笔 {ds.bi} / 段 {ds.segment}")
    print(format_structure_cli_summary(snapshot))

    if save or as_json:
        payload = snapshot.model_dump(mode="json")
        if as_json:
            print("\n=== structure JSON ===\n")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        if save:
            out_dir = root / "output"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = out_dir / f"{symbol}_{interval}_{ts}_structure.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"💾 结构 JSON: {path.resolve()}", file=sys.stderr)

    print("\n✓ 结构分析完成（未调用 AI）\n")
    return 0


def _run_multi_structure(
    *,
    root: Path,
    symbol: str,
    disp: str,
    lookback: int,
    save: bool,
    as_json: bool,
) -> int:
    print(f"\n🔗 FlowMarkets 多级别结构 {disp}（4h / 1h / 15m × {lookback}）")
    print("=" * 60)

    try:
        from app.services.chan.multi_timeframe import (
            build_multi_timeframe_snapshot,
            format_multi_timeframe_for_prompt,
        )

        snapshot = build_multi_timeframe_snapshot(symbol, lookback=lookback)
    except Exception as exc:
        print(f"   ✗ 多级别结构失败: {exc}", file=sys.stderr)
        return 1

    ok = sum(1 for lv in snapshot.levels.values() if lv.ok)
    print(f"   ✓ 成功 {ok}/3 个级别；partial={snapshot.partial}")
    for lv in snapshot.levels.values():
        status = "✓" if lv.ok else "✗"
        trend = lv.summary.get("trend", "?") if lv.ok else lv.error
        print(f"      {status} {lv.name} ({lv.timeframe}): {trend}")

    cj = snapshot.combined_judgment
    print("\n" + "=" * 60)
    print("多级别共振摘要")
    print("=" * 60)
    print(cj.prompt_text)
    if snapshot.partial:
        print("\n⚠ partial=true：部分周期计算失败，见 levels.*.error")

    mtf_json = format_multi_timeframe_for_prompt(snapshot)
    if as_json:
        print("\n=== multi_timeframe JSON ===\n")
        print(mtf_json)
    if save:
        out_dir = root / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"multi_timeframe_{symbol}_{ts}.json"
        path.write_text(mtf_json, encoding="utf-8")
        print(f"\n💾 多级别 JSON: {path.resolve()}", file=sys.stderr)

    print("\n✓ 多级别结构完成（未调用 AI）\n")
    return 0
