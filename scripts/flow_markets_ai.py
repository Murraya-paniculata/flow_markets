#!/usr/bin/env python3
"""缠论 AI 分析 CLI（用法对齐 chanlun 的 chanlun_ai.py）。

项目根目录示例::

  # 单周期 AI 分析（默认，对齐 chanlun 单 interval）
  FM_CHAN_PROGRESS=1 uv run python scripts/flow_markets_ai.py BTCUSDT 1h --table --limit 200

  # 多级别联立（4h/1h/15m JSON 注入 AI）→ scripts/multi_timeframe_analyze.py
  uv run python scripts/multi_timeframe_analyze.py BTCUSDT --save --limit 300

  # 仅结构快览（不调 LLM）
  uv run python scripts/flow_markets_ai.py BTCUSDT 1h --no-ai --limit 200

  # 保存结构 JSON + 分析 JSON + 终端文案 .txt，并强制写入分析记忆库
  uv run python scripts/flow_markets_ai.py BTCUSDT 1h --table --limit 200 --save

  # 仅落库（不写 output/）：在 .env 设置 APP_ANALYSIS_SAVE=true
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
    if s.endswith("USDT") and len(s) > 4:
        return s
    return s


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FlowMarkets 缠论 AI 分析（结构引擎 + 技术分析师）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  uv run python scripts/flow_markets_ai.py BTCUSDT 1h --table --limit 200
  uv run python scripts/flow_markets_ai.py ETHUSDT 4h --no-ai --limit 300
  uv run python scripts/flow_markets_ai.py BTCUSDT 1h --table --save
        """,
    )
    parser.add_argument("symbol", help="交易对，如 BTCUSDT")
    parser.add_argument("interval", help="周期，如 1m 5m 15m 1h 4h 1d")
    parser.add_argument(
        "--limit",
        type=int,
        default=300,
        help="K 线回溯根数（对应 lookback，默认 300）",
    )
    parser.add_argument(
        "--table",
        action="store_true",
        help="交易者可读输出（默认开启；与 chanlun --table 同类用途）",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="仅显示缠论结构，不调用 LLM",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="保存到 output/（结构+分析 JSON）并强制写入分析记忆库；仅落库可设 APP_ANALYSIS_SAVE=true",
    )
    parser.add_argument(
        "--user-query",
        default="",
        help="自定义研究问题（默认按标的与周期生成）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="在终端文案之后额外打印 TechnicalAnalysisDeliverable JSON",
    )
    return parser.parse_args()


def _default_user_query(symbol: str, interval: str) -> str:
    return (
        f"请基于 {symbol} {interval} 缠论结构给出技术分析："
        "趋势与中枢位置、最新笔与背驰/买卖点、三向策略概率与入场/目标/止损。"
    )


def main() -> int:
    root = _bootstrap()
    args = _parse_args()
    os.environ.setdefault("FM_CHAN_PROGRESS", "1")

    symbol = _normalize_symbol(args.symbol)
    interval = args.interval.lower().strip()
    lookback = max(50, int(args.limit))
    # --table 为 chanlun 习惯参数；未传 --table 且未 --no-ai 时同样走交易者文案
    use_trader_display = args.table or not args.no_ai

    display_symbol = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) > 6 else symbol
    print(f"\n🚀 FlowMarkets 分析 {display_symbol} @ {interval}（{lookback} 根 K 线）")
    print("=" * 60)

    print("\n📊 步骤 1/3: 获取行情并计算缠论结构...")
    try:
        from app.services.chan.structure import build_chan_structure_snapshot
        from app.schemas.technical_analysis_display import format_structure_cli_summary

        snapshot = build_chan_structure_snapshot(symbol, interval, lookback=lookback)
    except Exception as e:
        print(f"   ✗ 结构计算失败: {e}", file=sys.stderr)
        return 1

    print(f"   ✓ K 线 {snapshot.meta.data_size.kline} 根；"
          f"笔 {snapshot.meta.data_size.bi} / 段 {snapshot.meta.data_size.segment}")
    print(format_structure_cli_summary(snapshot))

    out_dir = root / "output"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_stem = f"{symbol}_{interval}_{ts}"

    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)
        struct_path = out_dir / f"{file_stem}_structure.json"
        struct_path.write_text(
            json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"💾 结构 JSON: {struct_path.resolve()}", file=sys.stderr)

    if args.no_ai:
        print("✓ 结构分析完成（已跳过 AI）\n")
        return 0

    print("\n🤖 步骤 2/3: 调用技术分析师（get_chan_structure + Skill）...")
    from app.core.config import get_settings
    from app.crews.flows.flow_markets import run_technical_analyst_only
    from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable
    from app.schemas.technical_analysis_display import format_trader_display

    settings = get_settings()
    if not (settings.llm_api_key or "").strip():
        print("✗ 未配置 APP_LLM_API_KEY，无法调用 AI", file=sys.stderr)
        print("  可在 .env 中设置，或使用 --no-ai 仅看结构", file=sys.stderr)
        return 1

    user_query = (args.user_query or "").strip() or _default_user_query(display_symbol, interval)
    result, err = run_technical_analyst_only(
        user_query,
        symbol,
        notes=f"flow_markets_ai.py --table --limit {lookback}",
        timeframe=interval,
        lookback=lookback,
        save=True if args.save else None,
    )
    if err:
        print(f"   ✗ {err}", file=sys.stderr)
        if result is not None:
            print(json.dumps(
                result.model_dump(mode="json")
                if hasattr(result, "model_dump")
                else result,
                ensure_ascii=False,
                indent=2,
            ))
        return 1

    if not isinstance(result, TechnicalAnalysisDeliverable):
        print("   ⚠ 输出未解析为 TechnicalAnalysisDeliverable，见 stderr JSON", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, indent=2) if result else "{}")
        return 1

    print("   ✓ AI 分析完成")
    print("\n📋 步骤 3/3: 生成交易者可读报告...")
    if use_trader_display:
        print(format_trader_display(result))
    else:
        from app.schemas.flow_markets_deliverables import render_task_deliverable

        print(render_task_deliverable(result))

    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)
        deliverable_path = out_dir / f"{file_stem}_analysis.json"
        deliverable_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if use_trader_display:
            txt_path = out_dir / f"{file_stem}_report.txt"
            txt_path.write_text(format_trader_display(result), encoding="utf-8")
            print(f"💾 分析 JSON: {deliverable_path.resolve()}", file=sys.stderr)
            print(f"💾 终端文案: {txt_path.resolve()}", file=sys.stderr)
        else:
            print(f"💾 分析 JSON: {deliverable_path.resolve()}", file=sys.stderr)

    if args.json:
        print("\n=== TechnicalAnalysisDeliverable JSON ===\n")
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    print("✓ 全部分析完成\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
