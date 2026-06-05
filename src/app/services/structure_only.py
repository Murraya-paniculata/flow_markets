"""仅缠论结构分析（Phase 5.4：对标 chanlun --no-ai / CLI structure）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.chan_structure import ChanStructureSnapshot, MultiTimeframeSnapshot
from app.schemas.technical_analysis_display import format_structure_cli_summary
from app.services.chan.multi_timeframe import build_multi_timeframe_snapshot
from app.services.chan.structure import build_chan_structure_snapshot


@dataclass
class StructureOnlyResult:
    """结构专用分析结果（不调 LLM）。"""

    report_content: str
    structure_payload: dict[str, Any]
    multi_tf: bool = False


def _normalize_symbol(symbol: str) -> str:
    from app.services.chan.symbols import normalize_binance_symbol

    return normalize_binance_symbol(symbol)[0]


def _multi_report(snapshot: MultiTimeframeSnapshot) -> str:
    lines = [
        "",
        "=" * 60,
        "【多级别缠论结构快览】",
        "=" * 60,
        "",
    ]
    ok = sum(1 for lv in snapshot.levels.values() if lv.ok)
    lines.append(f"有效级别：{ok}/3；partial={snapshot.partial}")
    lines.append("")
    for lv in snapshot.levels.values():
        status = "✓" if lv.ok else "✗"
        trend = lv.summary.get("trend", "?") if lv.ok else lv.error
        lines.append(f"{status} {lv.name} ({lv.timeframe}): {trend}")
    lines.append("")
    cj = snapshot.combined_judgment
    if cj and cj.prompt_text:
        lines.append(cj.prompt_text)
    if snapshot.partial:
        lines.append("\n⚠ partial=true：部分周期计算失败")
    lines.append("\n✓ 结构分析完成（未调用 AI）")
    return "\n".join(lines)


def run_structure_only(
    *,
    symbol: str,
    timeframe: str = "1h",
    lookback: int = 300,
    multi_tf: bool = False,
    engine_id: str | None = None,
    zs_algo: str | None = None,
) -> tuple[StructureOnlyResult | None, str]:
    """
    计算缠论结构并返回 Markdown 快览 + JSON payload。

    Returns:
        (result, error_message)；成功时 error_message 为空。
    """
    sym = _normalize_symbol(symbol)
    if not sym:
        return None, "no_ai 模式必须提供 symbol"

    try:
        if multi_tf:
            snapshot = build_multi_timeframe_snapshot(sym, lookback=lookback)
            ok = sum(1 for lv in snapshot.levels.values() if lv.ok)
            if ok == 0:
                return None, "多级别结构：所有周期均失败"
            return (
                StructureOnlyResult(
                    report_content=_multi_report(snapshot),
                    structure_payload=snapshot.model_dump(mode="json"),
                    multi_tf=True,
                ),
                "",
            )

        snap = build_chan_structure_snapshot(
            sym,
            timeframe,
            lookback=lookback,
            engine_id=engine_id,
            zs_algo=zs_algo,
        )
        return (
            StructureOnlyResult(
                report_content=format_structure_cli_summary(snap).strip()
                + "\n\n✓ 结构分析完成（未调用 AI）",
                structure_payload=snap.model_dump(mode="json"),
                multi_tf=False,
            ),
            "",
        )
    except Exception as exc:
        return None, f"结构计算失败: {exc}"


def structure_payload_from_snapshot(
    snapshot: ChanStructureSnapshot | MultiTimeframeSnapshot,
    *,
    multi_tf: bool,
) -> StructureOnlyResult:
    """从已算好的快照构建结果（供 streaming 复用）。"""
    if multi_tf:
        assert isinstance(snapshot, MultiTimeframeSnapshot)
        return StructureOnlyResult(
            report_content=_multi_report(snapshot),
            structure_payload=snapshot.model_dump(mode="json"),
            multi_tf=True,
        )
    assert isinstance(snapshot, ChanStructureSnapshot)
    return StructureOnlyResult(
        report_content=format_structure_cli_summary(snapshot).strip()
        + "\n\n✓ 结构分析完成（未调用 AI）",
        structure_payload=snapshot.model_dump(mode="json"),
        multi_tf=False,
    )
