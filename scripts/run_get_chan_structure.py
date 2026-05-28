#!/usr/bin/env python3
"""单独调试 get_chan_structure 工具；可选让技术分析师 LLM 解读结果。

项目根目录示例::

  # 仅工具 JSON（需能访问 Binance）
  FM_CHAN_PROGRESS=1 uv run python scripts/run_get_chan_structure.py

  uv run python scripts/run_get_chan_structure.py --symbol BTCUSDT --timeframe 1h --lookback 300

  # 工具 + 技术分析师（需 APP_LLM_API_KEY 等）
  uv run python scripts/run_get_chan_structure.py --symbol BTCUSDT --ai \\
    --user-query "看 1h 缠论结构，给情景与失效条件"

  # 保存工具 JSON
  uv run python scripts/run_get_chan_structure.py -o ./data/my_chan.json
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


def _print_tool_summary(payload: dict) -> None:
    if not payload.get("ok"):
        print(
            f"\n[失败] error_code={payload.get('error_code')} "
            f"message={payload.get('message', '')[:200]}",
            file=sys.stderr,
        )
        if payload.get("hint"):
            print(f"hint: {payload['hint']}", file=sys.stderr)
        return
    data = payload["data"]
    ss = data.get("structure_summary", {})
    mkt = data.get("market", {})
    print("\n--- 结构摘要 ---", file=sys.stderr)
    print(f"symbol={data.get('meta', {}).get('symbol')} interval={data.get('meta', {}).get('interval')}", file=sys.stderr)
    print(f"latest_price={mkt.get('latest_price')}", file=sys.stderr)
    print(f"trend: {ss.get('trend_description', ss.get('trend'))}", file=sys.stderr)
    print(f"position: {ss.get('position_description', ss.get('price_position'))}", file=sys.stderr)
    print(f"strength_comparison: {ss.get('strength_comparison')}", file=sys.stderr)
    kl = ss.get("key_levels") or {}
    if kl:
        print(f"ZG={kl.get('zg')} ZD={kl.get('zd')} GG={kl.get('gg')} DD={kl.get('dd')}", file=sys.stderr)
    sig = data.get("signal", {})
    if sig.get("buy_sell_points") or sig.get("divergences"):
        print(f"signals: bsp={sig.get('buy_sell_points')} div={sig.get('divergences')}", file=sys.stderr)
    print(
        f"counts: bi={len(data.get('bi', []))} segment={len(data.get('segment', []))} "
        f"center={len(data.get('center', []))}",
        file=sys.stderr,
    )


def _run_tool(symbol: str, timeframe: str, lookback: int) -> str:
    from app.crews.tools import GetChanStructureTool

    return GetChanStructureTool()._run(
        symbol=symbol,
        timeframe=timeframe,
        lookback=lookback,
    )


def _run_technical_ai(
    user_query: str,
    symbol: str,
    timeframe: str,
    lookback: int,
) -> tuple[str | None, str]:
    from app.crews.flows.flow_markets import run_technical_analyst_only

    result, err = run_technical_analyst_only(
        user_query,
        symbol,
        notes="由 run_get_chan_structure.py --ai 触发",
        timeframe=timeframe,
        lookback=lookback,
    )
    if err:
        return None, err
    if hasattr(result, "model_dump"):
        text = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
    elif isinstance(result, dict):
        text = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        text = str(result)
    return text, ""


def main() -> int:
    _bootstrap()

    parser = argparse.ArgumentParser(description="单独调试 get_chan_structure（可选 AI 解读）")
    parser.add_argument("--symbol", default="BTCUSDT", help="交易对，如 BTCUSDT")
    parser.add_argument("--timeframe", default="1h", help="K 线周期")
    parser.add_argument("--lookback", type=int, default=300, help="回溯根数")
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="保存工具 JSON 到文件；--ai 时另存 TechnicalBrief 需加 --ai-output",
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="在工具成功后调用技术分析师 LLM，输出 brief+chanlun_v2 JSON",
    )
    parser.add_argument(
        "--user-query",
        default="请基于缠论结构给出技术分析摘要、情景与失效条件。",
        help="--ai 时的用户诉求",
    )
    parser.add_argument(
        "--ai-output",
        default="",
        help="--ai 时保存 TechnicalBrief JSON 的路径",
    )
    parser.add_argument(
        "--tool-only",
        action="store_true",
        help="只打印工具 JSON 到 stdout，即使有 --ai 也不跑 LLM（用于先确认行情）",
    )
    args = parser.parse_args()

    print("调用 get_chan_structure …", file=sys.stderr)
    text = _run_tool(args.symbol, args.timeframe, args.lookback)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        print(text)
        return 1

    _print_tool_summary(payload)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"工具 JSON 已保存: {out.resolve()}", file=sys.stderr)

    if args.tool_only or not args.ai:
        print(text)
        if not payload.get("ok"):
            return 1
        return 0

    if not payload.get("ok"):
        print(text)
        print("工具失败，跳过 AI 解读。", file=sys.stderr)
        return 1

    print("\n调用技术分析师 LLM …", file=sys.stderr)
    ai_text, err = _run_technical_ai(
        args.user_query,
        args.symbol,
        args.timeframe,
        args.lookback,
    )
    if err:
        print(err, file=sys.stderr)
        return 1

    if args.ai_output and ai_text:
        ai_out = Path(args.ai_output)
        ai_out.parent.mkdir(parents=True, exist_ok=True)
        ai_out.write_text(ai_text, encoding="utf-8")
        print(f"TechnicalBrief 已保存: {ai_out.resolve()}", file=sys.stderr)

    try:
        from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable
        from app.schemas.technical_analysis_display import format_trader_display

        parsed = TechnicalAnalysisDeliverable.model_validate(json.loads(ai_text))
        print(format_trader_display(parsed))
    except Exception:
        print("\n=== TechnicalAnalysisDeliverable（brief + chanlun_v2）===\n")
        print(ai_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
