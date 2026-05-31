#!/usr/bin/env python3
"""多级别联立分析 CLI（对齐 chanlun multi_level_analyzer.py）。

单周期 AI 分析请用 ``scripts/flow_markets_ai.py``；本脚本固定 4h/1h/15m 联立并将 JSON 注入 AI。

示例::

  # 多级别结构 + 终端共振摘要（不调 LLM）
  uv run python scripts/multi_timeframe_analyze.py BTCUSDT --no-ai --limit 300

  # 多级别结构 + AI 联立分析（预注入 JSON → 技术分析师）
  FM_CHAN_PROGRESS=1 uv run python scripts/multi_timeframe_analyze.py BTCUSDT --save --limit 300

  # 保存 multi_timeframe_*.json + analysis JSON
  uv run python scripts/multi_timeframe_analyze.py BTCUSDT --save
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def _bootstrap() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))
    os.chdir(root)
    return root


def _normalize_symbol(symbol: str) -> str:
    s = symbol.upper().replace("/", "").replace("-", "")
    return s


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FlowMarkets 多级别联立分析（4h/1h/15m → AI）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  uv run python scripts/multi_timeframe_analyze.py BTCUSDT --no-ai
  uv run python scripts/multi_timeframe_analyze.py BTCUSDT --save --limit 300
        """,
    )
    parser.add_argument("symbol", help="交易对，如 BTCUSDT")
    parser.add_argument(
        "--limit",
        type=int,
        default=300,
        help="每个级别的 K 线回溯根数（默认 300）",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="仅计算多级别结构与共振摘要，不调用 LLM",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="保存 output/multi_timeframe_*.json；若调 AI 则另存 analysis JSON",
    )
    parser.add_argument(
        "--user-query",
        default="",
        help="自定义研究问题",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="终端打印完整 multi_timeframe JSON",
    )
    return parser.parse_args()


def _default_user_query(display_symbol: str) -> str:
    return (
        f"请对 {display_symbol} 进行缠论多级别联立分析（4h 定方向、1h 找买卖点、15m 精入场）："
        "三级别趋势是否一致、主操作方向、入场/止损/目标与状态机建议。"
    )


def _print_combined(snapshot) -> None:
    j = snapshot.combined_judgment
    print("\n" + "=" * 60)
    print("多级别共振摘要")
    print("=" * 60)
    print(j.prompt_text)
    if snapshot.partial:
        print("\n⚠ partial=true：部分周期计算失败，见 levels.*.error")


def main() -> int:
    root = _bootstrap()
    args = _parse_args()
    os.environ.setdefault("FM_CHAN_PROGRESS", "1")

    symbol = _normalize_symbol(args.symbol)
    lookback = max(50, int(args.limit))
    display_symbol = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) > 6 else symbol

    print(f"\n🔗 FlowMarkets 多级别联立 {display_symbol}（4h / 1h / 15m × {lookback} 根）")
    print("=" * 60)

    print("\n📊 步骤 1: 计算三级别结构...")
    try:
        from app.services.chan.multi_timeframe import (
            build_multi_timeframe_snapshot,
            format_multi_timeframe_for_prompt,
        )

        snapshot = build_multi_timeframe_snapshot(symbol, lookback=lookback)
    except Exception as e:
        print(f"   ✗ 多级别结构失败: {e}", file=sys.stderr)
        return 1

    ok = sum(1 for lv in snapshot.levels.values() if lv.ok)
    print(f"   ✓ 成功 {ok}/3 个级别；partial={snapshot.partial}")
    for key, lv in snapshot.levels.items():
        status = "✓" if lv.ok else "✗"
        trend = lv.summary.get("trend", "?") if lv.ok else lv.error
        print(f"      {status} {lv.name} ({lv.timeframe}): {trend}")

    _print_combined(snapshot)

    out_dir = root / "output"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_stem = f"multi_timeframe_{symbol}_{ts}"
    mtf_json = format_multi_timeframe_for_prompt(snapshot)

    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)
        mtf_path = out_dir / f"{file_stem}.json"
        mtf_path.write_text(mtf_json, encoding="utf-8")
        print(f"\n💾 多级别 JSON: {mtf_path.resolve()}", file=sys.stderr)

    if args.json:
        print("\n=== multi_timeframe JSON ===\n")
        print(mtf_json)

    if args.no_ai:
        print("\n✓ 多级别结构分析完成（已跳过 AI）\n")
        return 0

    if ok == 0:
        print("✗ 无有效级别，无法调用 AI", file=sys.stderr)
        return 1

    print("\n🤖 步骤 2: 调用技术分析师（预注入多级别 JSON + get_chan_structure@1h history）...")
    from app.core.config import get_settings
    from app.crews.flows.flow_markets import run_technical_analyst_only
    from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable
    from app.schemas.technical_analysis_display import format_trader_display

    settings = get_settings()
    if not (settings.llm_api_key or "").strip():
        print("✗ 未配置 APP_LLM_API_KEY", file=sys.stderr)
        return 1

    user_query = (args.user_query or "").strip() or _default_user_query(display_symbol)
    result, err = run_technical_analyst_only(
        user_query,
        symbol,
        notes=f"multi_timeframe_analyze.py --limit {lookback}",
        lookback=lookback,
        save=True if args.save else None,
        analysis_mode="multi_timeframe",
        multi_timeframe_context=mtf_json,
    )
    if err:
        print(f"   ✗ {err}", file=sys.stderr)
        return 1

    if not isinstance(result, TechnicalAnalysisDeliverable):
        print("   ⚠ 未解析为 TechnicalAnalysisDeliverable", file=sys.stderr)
        return 1

    print("   ✓ AI 多级别联立分析完成")
    print("\n📋 交易者可读报告:")
    print(format_trader_display(result))

    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = out_dir / f"{file_stem}_analysis.json"
        analysis_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        txt_path = out_dir / f"{file_stem}_report.txt"
        txt_path.write_text(format_trader_display(result), encoding="utf-8")
        print(f"💾 分析 JSON: {analysis_path.resolve()}", file=sys.stderr)
        print(f"💾 终端文案: {txt_path.resolve()}", file=sys.stderr)

    print("\n✓ 多级别联立分析完成\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
