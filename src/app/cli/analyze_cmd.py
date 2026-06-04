"""analyze 子命令：结构 + AI 技术分析师（单周期或多级别联立）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app.cli.common import clamp_lookback, display_symbol, normalize_symbol


def _default_user_query_single(disp: str, interval: str) -> str:
    return (
        f"请基于 {disp} {interval} 缠论结构给出技术分析："
        "趋势与中枢位置、最新笔与背驰/买卖点、三向策略概率与入场/目标/止损。"
    )


def _default_user_query_multi(disp: str) -> str:
    return (
        f"请对 {disp} 进行缠论多级别联立分析（4h 定方向、1h 找买卖点、15m 精入场）："
        "三级别趋势是否一致、主操作方向、入场/止损/目标与状态机建议。"
    )


def _print_deliverable(
    result,
    *,
    use_trader_display: bool,
) -> None:
    from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable

    if not isinstance(result, TechnicalAnalysisDeliverable):
        print("   ⚠ 未解析为 TechnicalAnalysisDeliverable", file=sys.stderr)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    if use_trader_display:
        from app.schemas.technical_analysis_display import format_trader_display

        print(format_trader_display(result))
        if result.signal_quality is not None:
            from app.analysis_store.signal_quality import format_quality_report

            print(format_quality_report(result.signal_quality))
    else:
        from app.schemas.flow_markets_deliverables import render_task_deliverable

        print(render_task_deliverable(result))


def _save_deliverable(
    *,
    root: Path,
    file_stem: str,
    result,
    use_trader_display: bool,
) -> None:
    from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable

    if not isinstance(result, TechnicalAnalysisDeliverable):
        return
    out_dir = root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    deliverable_path = out_dir / f"{file_stem}_analysis.json"
    deliverable_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"💾 分析 JSON: {deliverable_path.resolve()}", file=sys.stderr)
    if use_trader_display:
        from app.schemas.technical_analysis_display import format_trader_display

        txt_path = out_dir / f"{file_stem}_report.txt"
        txt_path.write_text(format_trader_display(result), encoding="utf-8")
        print(f"💾 终端文案: {txt_path.resolve()}", file=sys.stderr)


def run_analyze(args: argparse.Namespace, *, root: Path) -> int:
    symbol = normalize_symbol(args.symbol)
    interval = args.interval.lower().strip()
    lookback = clamp_lookback(args.limit)
    disp = display_symbol(symbol)
    use_trader_display = True  # analyze 默认交易者可读输出（对标 chanlun --table）

    if args.multi_tf:
        return _run_multi_analyze(
            root=root,
            symbol=symbol,
            disp=disp,
            lookback=lookback,
            save=args.save,
            user_query=(args.user_query or "").strip(),
            as_json=args.json,
        )

    return _run_single_analyze(
        root=root,
        symbol=symbol,
        interval=interval,
        disp=disp,
        lookback=lookback,
        save=args.save,
        user_query=(args.user_query or "").strip(),
        as_json=args.json,
        use_trader_display=use_trader_display,
    )


def _run_single_analyze(
    *,
    root: Path,
    symbol: str,
    interval: str,
    disp: str,
    lookback: int,
    save: bool,
    user_query: str,
    as_json: bool,
    use_trader_display: bool,
) -> int:
    print(f"\n🚀 FlowMarkets 分析 {disp} @ {interval}（{lookback} 根 K 线）")
    print("=" * 60)

    print("\n📊 步骤 1/3: 获取行情并计算缠论结构...")
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

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_stem = f"{symbol}_{interval}_{ts}"

    if save:
        out_dir = root / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        struct_path = out_dir / f"{file_stem}_structure.json"
        struct_path.write_text(
            json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"💾 结构 JSON: {struct_path.resolve()}", file=sys.stderr)

    print("\n🤖 步骤 2/3: 调用技术分析师（get_chan_structure + Skill）...")
    from app.core.config import get_settings
    from app.crews.flows.flow_markets import run_technical_analyst_only
    from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable

    settings = get_settings()
    if not (settings.llm_api_key or "").strip():
        print("✗ 未配置 APP_LLM_API_KEY，无法调用 AI", file=sys.stderr)
        print("  可使用: chanlun_fm.py structure ... 仅看结构", file=sys.stderr)
        return 1

    query = user_query or _default_user_query_single(disp, interval)
    result, err = run_technical_analyst_only(
        query,
        symbol,
        notes=f"chanlun_fm analyze --limit {lookback}",
        timeframe=interval,
        lookback=lookback,
        save=True if save else None,
    )
    if err:
        print(f"   ✗ {err}", file=sys.stderr)
        if result is not None:
            print(
                json.dumps(
                    result.model_dump(mode="json") if hasattr(result, "model_dump") else result,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        return 1

    if not isinstance(result, TechnicalAnalysisDeliverable):
        print("   ⚠ 输出未解析为 TechnicalAnalysisDeliverable", file=sys.stderr)
        return 1

    print("   ✓ AI 分析完成")
    print("\n📋 步骤 3/3: 生成交易者可读报告...")
    _print_deliverable(result, use_trader_display=use_trader_display)

    if save:
        _save_deliverable(
            root=root,
            file_stem=file_stem,
            result=result,
            use_trader_display=use_trader_display,
        )

    if as_json:
        print("\n=== TechnicalAnalysisDeliverable JSON ===\n")
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    print("\n✓ 全部分析完成\n")
    return 0


def _run_multi_analyze(
    *,
    root: Path,
    symbol: str,
    disp: str,
    lookback: int,
    save: bool,
    user_query: str,
    as_json: bool,
) -> int:
    print(f"\n🔗 FlowMarkets 多级别联立 {disp}（4h / 1h / 15m × {lookback}）")
    print("=" * 60)

    print("\n📊 步骤 1: 计算三级别结构...")
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

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_stem = f"multi_timeframe_{symbol}_{ts}"
    mtf_json = format_multi_timeframe_for_prompt(snapshot)

    if save:
        out_dir = root / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        mtf_path = out_dir / f"{file_stem}.json"
        mtf_path.write_text(mtf_json, encoding="utf-8")
        print(f"\n💾 多级别 JSON: {mtf_path.resolve()}", file=sys.stderr)

    if ok == 0:
        print("✗ 无有效级别，无法调用 AI", file=sys.stderr)
        return 1

    print("\n🤖 步骤 2: 调用技术分析师（预注入多级别 JSON + get_chan_structure@1h history）...")
    from app.core.config import get_settings
    from app.crews.flows.flow_markets import run_technical_analyst_only
    from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable

    settings = get_settings()
    if not (settings.llm_api_key or "").strip():
        print("✗ 未配置 APP_LLM_API_KEY", file=sys.stderr)
        return 1

    query = user_query or _default_user_query_multi(disp)
    result, err = run_technical_analyst_only(
        query,
        symbol,
        notes=f"chanlun_fm analyze --multi-tf --limit {lookback}",
        lookback=lookback,
        save=True if save else None,
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
    _print_deliverable(result, use_trader_display=True)

    if save:
        _save_deliverable(
            root=root,
            file_stem=file_stem,
            result=result,
            use_trader_display=True,
        )

    if as_json:
        print("\n=== TechnicalAnalysisDeliverable JSON ===\n")
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    print("\n✓ 多级别联立分析完成\n")
    return 0
