"""FlowMarkets 流式分析（Phase 5.2：SSE 步骤 K线→结构→AI→治理）。"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, AsyncGenerator

from app.core.config import get_settings
from app.crews.flows.deep_research import _get_report_from_crew_result
from app.crews.flows.flow_markets import (
    FlowMarketsCrew,
    _ANALYSIS_MODE_MULTI,
    _ANALYSIS_MODE_SINGLE,
    _PRIMARY_TF_MULTI,
    _build_technical_crew_inputs,
    _execute_flow_markets_crew,
    _extract_technical_deliverable,
    _govern_technical_deliverable,
    _maybe_persist_technical_deliverable,
    _resolve_multi_timeframe_context,
    create_flow_markets_crew_for_run,
)
from app.crews.flows.flow_markets_mode import is_flow_markets_full_mode
from app.observability.logging import get_logger
from app.observability.metrics import crew_execution_seconds
from app.schemas.flow_markets_deliverables import (
    TechnicalAnalysisDeliverable,
    assemble_flow_markets_report,
)
from app.schemas.technical_analysis_display import format_structure_cli_summary
from app.services.analysis_output import (
    should_write_output_artifacts,
    write_analyze_save_artifacts,
    write_structure_only_artifacts,
)
from app.services.chan.kline import cap_limit, get_klines
from app.services.chan.multi_timeframe import (
    build_multi_timeframe_snapshot,
    format_multi_timeframe_for_prompt,
)
from app.services.structure_only import structure_payload_from_snapshot
from app.services.chan.structure import MIN_KLINES, build_chan_structure_snapshot

logger = get_logger(__name__)

TOTAL_STEPS = 4
_stream_result_store: dict[str, dict[str, Any]] = {}


def get_analysis_stream_result(task_id: str) -> dict[str, Any] | None:
    """按 task_id 读取流式分析最终结果（内存，进程内有效）。"""
    return _stream_result_store.get(task_id)


def _display_symbol(symbol: str | None) -> str:
    sym = (symbol or "").strip().upper().replace("/", "").replace("-", "")
    if len(sym) > 6 and sym.endswith("USDT"):
        return f"{sym[: -4]}/USDT"
    return sym or "（未指定）"


def _emit_log(
    level: str,
    message: str,
    *,
    step: int | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    return {
        "level": level,
        "message": message,
        "step": step,
        "total_steps": TOTAL_STEPS,
        "phase": phase,
        "timestamp": time.time(),
    }


def _structure_info_lines(snapshot) -> list[str]:
    """从结构快照拆成多条 info 日志（对标 chanlun 结构快览）。"""
    lines: list[str] = []
    summary_text = format_structure_cli_summary(snapshot)
    for block in summary_text.splitlines():
        stripped = block.strip()
        if not stripped or set(stripped) <= {"=", "-"}:
            continue
        if stripped.startswith("【") and stripped.endswith("】"):
            continue
        lines.append(stripped)
    return lines


def _deliverable_payload(
    deliverable: TechnicalAnalysisDeliverable | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if deliverable is None:
        return None
    if isinstance(deliverable, TechnicalAnalysisDeliverable):
        return deliverable.model_dump(mode="json")
    if isinstance(deliverable, dict):
        return deliverable
    return {"raw": str(deliverable)}


def _build_final_result(
    *,
    success: bool,
    message: str,
    report_content: str | None,
    deliverable: TechnicalAnalysisDeliverable | dict[str, Any] | None,
    structure_only: bool = False,
    structure_payload: dict[str, Any] | None = None,
    output_files: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "success": success,
        "message": message,
        "report_content": report_content,
        "deliverable": _deliverable_payload(deliverable),
        "structure_only": structure_only,
        "structure_payload": structure_payload,
        "output_files": output_files or [],
    }


async def analyze_flow_markets_streaming(
    *,
    user_query: str,
    symbol: str | None = None,
    notes: str | None = None,
    timeframe: str = "1h",
    lookback: int = 300,
    save: bool | None = None,
    analysis_mode: str = _ANALYSIS_MODE_SINGLE,
    task_id: str,
    no_ai: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    流式分析主函数：yield 日志 dict；结束时 yield ``{"type": "result", "data": ...}``。

    步骤：no_ai 时 K线 → 结构；否则 K线 → 结构 → AI → 治理
    """
    settings = get_settings()
    mode = analysis_mode if analysis_mode in (_ANALYSIS_MODE_SINGLE, _ANALYSIS_MODE_MULTI) else _ANALYSIS_MODE_SINGLE
    persist_tf = _PRIMARY_TF_MULTI if mode == _ANALYSIS_MODE_MULTI else timeframe
    disp = _display_symbol(symbol)
    capped = cap_limit(persist_tf if mode == _ANALYSIS_MODE_SINGLE else "1h", lookback)
    total_steps = 2 if no_ai else TOTAL_STEPS

    yield _emit_log(
        "step",
        f"🚀 开始{'结构' if no_ai else '分析'} {disp} · {persist_tf}（lookback={capped}，模式={mode}）",
        step=0,
        phase="start",
    )
    await asyncio.sleep(0)

    if not no_ai and not (settings.llm_api_key or "").strip():
        result = _build_final_result(
            success=False,
            message="未配置 APP_LLM_API_KEY（或 QWEN_API_KEY / DEEPSEEK_API_KEY），无法调用大模型",
            report_content=None,
            deliverable=None,
        )
        _stream_result_store[task_id] = result
        yield _emit_log("error", result["message"], step=3, phase="ai")
        yield {"type": "result", "data": result}
        return

    sym = (symbol or "").strip()
    mtf_ctx: str | None = None
    snapshot = None
    mtf_snapshot = None

    # --- 步骤 1：K 线 ---
    if mode == _ANALYSIS_MODE_MULTI:
        yield _emit_log(
            "step",
            f"📊 步骤 1/{total_steps}: 拉取多级别 K 线（4h / 1h / 15m × {capped}）...",
            step=1,
            phase="kline",
        )
        await asyncio.sleep(0)
        if not sym:
            msg = "多级别模式需要有效 symbol"
            result = _build_final_result(False, msg, None, None)
            _stream_result_store[task_id] = result
            yield _emit_log("error", f"✗ {msg}", step=1, phase="kline")
            yield {"type": "result", "data": result}
            return
    else:
        yield _emit_log(
            "step",
            f"📊 步骤 1/{total_steps}: 获取 Binance K 线（{timeframe} × {capped}）...",
            step=1,
            phase="kline",
        )
        await asyncio.sleep(0)
        if not sym:
            if no_ai:
                msg = "no_ai 模式需要有效 symbol"
                result = _build_final_result(False, msg, None, None)
                _stream_result_store[task_id] = result
                yield _emit_log("error", f"✗ {msg}", step=1, phase="kline")
                yield {"type": "result", "data": result}
                return
            yield _emit_log(
                "info",
                "   ℹ 未指定 symbol，跳过预拉 K 线（AI 阶段仍可从 user_query 推断）",
                step=1,
                phase="kline",
            )
            await asyncio.sleep(0)
        else:
            try:
                klines = await asyncio.to_thread(get_klines, sym, timeframe, capped)
                if not klines or len(klines) < MIN_KLINES:
                    msg = f"K 线数据不足（需要至少 {MIN_KLINES} 根，实际 {len(klines or [])}）"
                    result = _build_final_result(False, msg, None, None)
                    _stream_result_store[task_id] = result
                    yield _emit_log("error", f"✗ {msg}", step=1, phase="kline")
                    yield {"type": "result", "data": result}
                    return
                yield _emit_log(
                    "success",
                    f"   ✓ 获取到 {len(klines)} 根 K 线",
                    step=1,
                    phase="kline",
                )
                await asyncio.sleep(0)
            except Exception as exc:
                msg = f"获取 K 线失败: {exc}"
                result = _build_final_result(False, msg, None, None)
                _stream_result_store[task_id] = result
                yield _emit_log("error", f"✗ {msg}", step=1, phase="kline")
                yield {"type": "result", "data": result}
                return

    if mode == _ANALYSIS_MODE_MULTI:
        try:
            mtf_snapshot = await asyncio.to_thread(
                build_multi_timeframe_snapshot,
                sym,
                lookback=lookback,
            )
        except Exception as exc:
            msg = f"多级别 K 线/结构失败: {exc}"
            result = _build_final_result(False, msg, None, None)
            _stream_result_store[task_id] = result
            yield _emit_log("error", f"✗ {msg}", step=1, phase="kline")
            yield {"type": "result", "data": result}
            return

        ok_count = sum(1 for lv in mtf_snapshot.levels.values() if lv.ok)
        kline_bits = []
        for lv in mtf_snapshot.levels.values():
            if lv.ok and lv.summary.get("data_size"):
                ds = lv.summary["data_size"]
                kline_bits.append(f"{lv.timeframe}:{ds.get('kline', '?')}")
        yield _emit_log(
            "success",
            f"   ✓ 多级别 K 线就绪（{', '.join(kline_bits) or f'{ok_count}/3 有效'}）",
            step=1,
            phase="kline",
        )
        await asyncio.sleep(0)

    # --- 步骤 2：结构 ---
    yield _emit_log(
        "step",
        f"🧮 步骤 2/{total_steps}: 缠论结构计算...",
        step=2,
        phase="structure",
    )
    await asyncio.sleep(0)

    if mode == _ANALYSIS_MODE_MULTI:
        assert mtf_snapshot is not None
        if ok_count == 0:
            msg = "多级别结构：所有周期均失败"
            result = _build_final_result(False, msg, None, None)
            _stream_result_store[task_id] = result
            yield _emit_log("error", f"✗ {msg}", step=2, phase="structure")
            yield {"type": "result", "data": result}
            return

        mtf_ctx = format_multi_timeframe_for_prompt(mtf_snapshot)
        yield _emit_log(
            "success",
            f"   ✓ 多级别结构完成（{ok_count}/3 有效；partial={mtf_snapshot.partial}）",
            step=2,
            phase="structure",
        )
        await asyncio.sleep(0)
        for key, lv in mtf_snapshot.levels.items():
            status = "✓" if lv.ok else "✗"
            trend = lv.summary.get("trend", "?") if lv.ok else lv.error
            yield _emit_log(
                "info",
                f"   {status} {lv.name} ({lv.timeframe}): {trend}",
                step=2,
                phase="structure",
            )
            await asyncio.sleep(0)
        cj = mtf_snapshot.combined_judgment
        if cj and cj.prompt_text:
            for line in cj.prompt_text.splitlines()[:8]:
                if line.strip():
                    yield _emit_log("info", f"   {line.strip()}", step=2, phase="structure")
                    await asyncio.sleep(0)
    elif sym:
        try:
            snapshot = await asyncio.to_thread(
                build_chan_structure_snapshot,
                sym,
                timeframe,
                lookback=lookback,
            )
        except Exception as exc:
            msg = f"缠论结构计算失败: {exc}"
            result = _build_final_result(False, msg, None, None)
            _stream_result_store[task_id] = result
            yield _emit_log("error", f"✗ {msg}", step=2, phase="structure")
            yield {"type": "result", "data": result}
            return

        ds = snapshot.meta.data_size
        yield _emit_log(
            "success",
            f"   ✓ 结构完成：K线 {ds.kline} / 笔 {ds.bi} / 段 {ds.segment} / 中枢 {ds.center}",
            step=2,
            phase="structure",
        )
        await asyncio.sleep(0)
        for line in _structure_info_lines(snapshot):
            yield _emit_log("info", line, step=2, phase="structure")
            await asyncio.sleep(0)
    else:
        yield _emit_log(
            "info",
            "   ℹ 无 symbol，结构快览跳过（由 AI 工具 get_chan_structure 拉取）",
            step=2,
            phase="structure",
        )
        await asyncio.sleep(0)

    if no_ai:
        try:
            if mode == _ANALYSIS_MODE_MULTI:
                assert mtf_snapshot is not None
                struct = structure_payload_from_snapshot(mtf_snapshot, multi_tf=True)
            else:
                assert snapshot is not None
                struct = structure_payload_from_snapshot(snapshot, multi_tf=False)
        except Exception as exc:
            msg = f"结构结果组装失败: {exc}"
            result = _build_final_result(False, msg, None, None)
            _stream_result_store[task_id] = result
            yield _emit_log("error", f"✗ {msg}", step=2, phase="structure")
            yield {"type": "result", "data": result}
            return

        yield _emit_log("info", "   ℹ 已跳过 AI 与治理（no_ai=true）", step=2, phase="structure")
        await asyncio.sleep(0)
        output_files: list[str] = []
        if should_write_output_artifacts(save=save) and sym:
            try:
                output_files = await asyncio.to_thread(
                    write_structure_only_artifacts,
                    symbol=sym,
                    structure_payload=struct.structure_payload,
                    multi_tf=mode == _ANALYSIS_MODE_MULTI,
                    interval=timeframe,
                )
            except Exception as exc:
                logger.warning("stream_structure_save_artifacts_failed", error=str(exc))
        result = _build_final_result(
            success=True,
            message="结构分析完成",
            report_content=struct.report_content,
            deliverable=None,
            structure_only=True,
            structure_payload=struct.structure_payload,
            output_files=output_files,
        )
        _stream_result_store[task_id] = result
        yield _emit_log("success", f"✅ 结构分析完成（task_id={task_id}）", step=2, phase="structure")
        await asyncio.sleep(0)
        yield {"type": "result", "data": result}
        return

    # --- 步骤 3：AI ---
    if mode == _ANALYSIS_MODE_MULTI and mtf_ctx is None:
        mtf_ctx, mtf_err = _resolve_multi_timeframe_context(symbol, lookback=lookback)
        if mtf_err:
            result = _build_final_result(False, mtf_err, None, None)
            _stream_result_store[task_id] = result
            yield _emit_log("error", f"✗ {mtf_err}", step=3, phase="ai")
            yield {"type": "result", "data": result}
            return

    os.environ["CREWAI_TESTING"] = "true"
    inputs = _build_technical_crew_inputs(
        user_query=user_query,
        symbol=symbol,
        notes=notes,
        timeframe=timeframe,
        lookback=lookback,
        analysis_mode=mode,
        multi_timeframe_context=mtf_ctx,
    )

    yield _emit_log(
        "step",
        (
            f"🤖 步骤 3/{TOTAL_STEPS}: 调用 FlowMarkets"
            f"（{'完整研究链' if is_flow_markets_full_mode() else '技术分析师'}）..."
        ),
        step=3,
        phase="ai",
    )
    await asyncio.sleep(0)
    yield _emit_log(
        "info",
        f"   ⚙️  LLM: {settings.llm_provider}/{settings.llm_model}",
        step=3,
        phase="ai",
    )
    await asyncio.sleep(0)
    yield _emit_log(
        "info",
        "   ⏳ 等待 AI 响应（可能需要 20–120 秒）...",
        step=3,
        phase="ai",
    )
    await asyncio.sleep(0)

    flow = FlowMarketsCrew()
    stream_metrics_name = "flow_markets"
    deliverable: TechnicalAnalysisDeliverable | dict[str, Any] | None = None
    t0 = time.perf_counter()
    try:
        if is_flow_markets_full_mode():
            yield _emit_log(
                "info",
                "   ℹ full：上游四域 → 治理 technical → 注入 stats → 综合/交易/组合",
                step=3,
                phase="ai",
            )
            await asyncio.sleep(0)
            crew_result, deliverable, stream_metrics_name = await asyncio.to_thread(
                _execute_flow_markets_crew,
                flow,
                inputs,
                persist_tf=persist_tf,
                lookback=lookback,
                symbol_hint=symbol,
            )
        else:
            crew_obj, stream_metrics_name = create_flow_markets_crew_for_run(flow)
            crew_result = await asyncio.to_thread(crew_obj.kickoff, inputs=inputs)
            deliverable = _extract_technical_deliverable(crew_result)
    except Exception as exc:
        logger.exception("analyze_streaming_ai_failed", error=str(exc))
        msg = f"FlowMarkets 执行失败: {exc}"
        result = _build_final_result(False, msg, None, None)
        _stream_result_store[task_id] = result
        yield _emit_log("error", f"✗ {msg}", step=3, phase="ai")
        yield {"type": "result", "data": result}
        return
    finally:
        elapsed = time.perf_counter() - t0
        try:
            crew_execution_seconds.labels(flow_name=stream_metrics_name).observe(elapsed)
        except Exception:
            logger.warning("analyze_stream_metrics_observe_failed", exc_info=True)

    yield _emit_log(
        "success",
        f"   ✓ {'完整研究链' if is_flow_markets_full_mode() else 'AI 分析'}完成",
        step=3,
        phase="ai",
    )
    await asyncio.sleep(0)

    # --- 步骤 4：治理（technical_only 在此执行；full 已在 synthesis 前完成）---
    yield _emit_log(
        "step",
        f"📋 步骤 4/{TOTAL_STEPS}: 治理（历史约束 + 信号质量 + 落库）...",
        step=4,
        phase="governance",
    )
    await asyncio.sleep(0)

    if not is_flow_markets_full_mode():
        deliverable = _govern_technical_deliverable(
            deliverable,
            timeframe=persist_tf,
            lookback=lookback,
            symbol_hint=symbol,
        )
        yield _emit_log("success", "   ✓ 历史约束（history enforcement）已应用", step=4, phase="governance")
        await asyncio.sleep(0)
        yield _emit_log("success", "   ✓ 信号质量评分已写入 brief/snapshot", step=4, phase="governance")
        await asyncio.sleep(0)
    else:
        yield _emit_log(
            "success",
            "   ✓ 技术域已在研究经理综合前完成治理（enforcement + signal_quality）",
            step=4,
            phase="governance",
        )
        await asyncio.sleep(0)

    record_id = _maybe_persist_technical_deliverable(
        deliverable,
        timeframe=persist_tf,
        lookback=lookback,
        symbol_hint=symbol,
        save=save,
    )
    if record_id is not None:
        yield _emit_log(
            "success",
            f"   ✓ 已写入分析记忆库（id={record_id}）",
            step=4,
            phase="governance",
        )
    else:
        yield _emit_log("info", "   ℹ 未写入分析记忆库（save=false 或未启用 APP_ANALYSIS_SAVE）", step=4, phase="governance")
    await asyncio.sleep(0)

    report = assemble_flow_markets_report(
        crew_result,
        user_query=inputs["user_query"],
        symbol=inputs["symbol"],
    )
    if not report:
        report = _get_report_from_crew_result(crew_result)
    if not report:
        report = "(未从 Crew 输出解析到报告正文，请检查各任务输出或日志)"

    output_files: list[str] = []
    if (
        should_write_output_artifacts(save=save)
        and isinstance(deliverable, TechnicalAnalysisDeliverable)
        and sym
    ):
        try:
            output_files = await asyncio.to_thread(
                write_analyze_save_artifacts,
                symbol=sym,
                timeframe=persist_tf if mode == _ANALYSIS_MODE_SINGLE else "1h",
                lookback=lookback,
                deliverable=deliverable,
                multi_tf=mode == _ANALYSIS_MODE_MULTI,
            )
        except Exception as exc:
            logger.warning("stream_analyze_save_artifacts_failed", error=str(exc))

    result = _build_final_result(
        success=True,
        message="分析完成",
        report_content=report,
        deliverable=deliverable,
        output_files=output_files,
    )
    _stream_result_store[task_id] = result
    yield _emit_log("success", f"✅ 分析完成（task_id={task_id}）", step=4, phase="governance")
    await asyncio.sleep(0)
    yield {"type": "result", "data": result}
