"""多周期缠论结构服务（Phase 3.1：默认 4h / 1h / 15m）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.chan_structure import (
    ChanStructureSnapshot,
    MultiTimeframeCombinedJudgment,
    MultiTimeframeLevelResult,
    MultiTimeframeSnapshot,
)
from app.services.chan.structure import DEFAULT_LOOKBACK, build_chan_structure_snapshot

DEFAULT_MULTI_TF_LEVELS: dict[str, dict[str, Any]] = {
    "large": {"timeframe": "4h", "lookback": DEFAULT_LOOKBACK, "name": "大级别"},
    "medium": {"timeframe": "1h", "lookback": DEFAULT_LOOKBACK, "name": "中级别"},
    "small": {"timeframe": "15m", "lookback": DEFAULT_LOOKBACK, "name": "小级别"},
}

_TREND_LABELS = {
    "up_trend": "上升趋势",
    "down_trend": "下降趋势",
    "consolidation": "震荡盘整",
    "unknown": "未知",
}

_POSITION_LABELS = {
    "above_zs": "中枢上方",
    "below_zs": "中枢下方",
    "inside_zs": "中枢内部",
    "unknown": "无中枢",
}


def _extract_level_summary(snapshot: ChanStructureSnapshot) -> dict[str, Any]:
    summary = snapshot.structure_summary
    latest_bi = snapshot.bi[-1] if snapshot.bi else None
    latest_center = snapshot.center[-1] if snapshot.center else None
    return {
        "trend": summary.trend,
        "trend_description": summary.trend_description,
        "price_position": summary.price_position,
        "position_description": summary.position_description,
        "latest_bi_direction": summary.latest_bi_direction,
        "latest_bi_strength": summary.latest_bi_strength,
        "strength_comparison": summary.strength_comparison,
        "key_levels": summary.key_levels.model_dump(mode="json"),
        "latest_bi": latest_bi.model_dump(mode="json") if latest_bi else None,
        "latest_center": latest_center.model_dump(mode="json") if latest_center else None,
        "signals": list(snapshot.signal.buy_sell_points),
        "divergences": list(snapshot.signal.divergences),
        "data_size": snapshot.meta.data_size.model_dump(mode="json"),
    }


def _build_suggestion(
    *,
    main_trend: str,
    trend_strength: str,
    buy_signals: list[str],
    sell_signals: list[str],
    medium_summary: dict[str, Any],
) -> str:
    if trend_strength == "strong" and main_trend == "up":
        base = "三级别共振偏多，中级别找回调买点或小级别确认后介入"
    elif trend_strength == "strong" and main_trend == "down":
        base = "三级别共振偏空，中级别找反弹卖点或小级别确认后减仓"
    elif main_trend == "range":
        base = "级别分歧或震荡，优先区间操作，等待大级别方向确认"
    else:
        base = "部分级别同向，需小级别精确入场并严格止损"

    medium_pos = medium_summary.get("price_position", "unknown")
    if medium_pos == "inside_zs":
        base += "；中级别在中枢内，宜高抛低吸"
    elif medium_pos == "above_zs" and main_trend == "up":
        base += "；价格在中枢上方，回踩 ZG 附近关注"
    elif medium_pos == "below_zs" and main_trend == "down":
        base += "；价格在中枢下方，反弹 ZD 附近关注"

    if buy_signals and not sell_signals:
        base += f"；买点信号: {', '.join(buy_signals)}"
    elif sell_signals and not buy_signals:
        base += f"；卖点信号: {', '.join(sell_signals)}"
    return base


def combine_multi_timeframe_judgment(
    levels: dict[str, MultiTimeframeLevelResult],
) -> MultiTimeframeCombinedJudgment:
    """根据各级别 summary 生成共振判断（至少 2 个 ok 级别才有效）。"""
    summaries = {
        key: (levels[key].summary if levels.get(key) and levels[key].ok else {})
        for key in ("large", "medium", "small")
    }
    ok_count = sum(1 for lv in levels.values() if lv.ok)
    if ok_count < 2:
        return MultiTimeframeCombinedJudgment(
            main_trend="unknown",
            trend_strength="weak",
            resonance="unknown",
            suggestion="有效级别不足，无法做共振判断",
            prompt_text="多级别数据不足（需至少 2 个周期成功）",
        )

    trends = [summaries[k].get("trend", "unknown") for k in ("large", "medium", "small")]
    up_score = trends.count("up_trend")
    down_score = trends.count("down_trend")

    if up_score >= 2:
        main_trend = "up"
        trend_strength = "strong" if up_score == 3 else "moderate"
    elif down_score >= 2:
        main_trend = "down"
        trend_strength = "strong" if down_score == 3 else "moderate"
    else:
        main_trend = "range"
        trend_strength = "weak"

    all_signals: list[str] = []
    for key in ("large", "medium", "small"):
        all_signals.extend(summaries[key].get("signals") or [])

    buy_signals = sorted({s for s in all_signals if "buy" in s.lower()})
    sell_signals = sorted({s for s in all_signals if "sell" in s.lower()})

    positions = {
        key: summaries[key].get("price_position", "unknown")
        for key in ("large", "medium", "small")
    }

    resonance = (
        "aligned"
        if (up_score == 3 or down_score == 3)
        else ("partial" if up_score >= 2 or down_score >= 2 else "mixed")
    )

    suggestion = _build_suggestion(
        main_trend=main_trend,
        trend_strength=trend_strength,
        buy_signals=buy_signals,
        sell_signals=sell_signals,
        medium_summary=summaries.get("medium") or {},
    )

    def _level_label(key: str, default_tf: str) -> str:
        lv = levels.get(key)
        return lv.timeframe if lv and lv.ok else default_tf

    prompt_lines = [
        "## 多级别共振摘要",
        f"- 主趋势: {main_trend}（强度 {trend_strength}，共振 {resonance}）",
        (
            f"- 大级别({_level_label('large', '4h')}): "
            f"{_TREND_LABELS.get(summaries['large'].get('trend', 'unknown'), '未知')} / "
            f"{_POSITION_LABELS.get(summaries['large'].get('price_position', 'unknown'), '未知')}"
        ),
        (
            f"- 中级别({_level_label('medium', '1h')}): "
            f"{_TREND_LABELS.get(summaries['medium'].get('trend', 'unknown'), '未知')} / "
            f"{_POSITION_LABELS.get(summaries['medium'].get('price_position', 'unknown'), '未知')}"
        ),
        (
            f"- 小级别({_level_label('small', '15m')}): "
            f"{_TREND_LABELS.get(summaries['small'].get('trend', 'unknown'), '未知')} / "
            f"{_POSITION_LABELS.get(summaries['small'].get('price_position', 'unknown'), '未知')}"
        ),
    ]
    if buy_signals or sell_signals:
        prompt_lines.append(
            f"- 跨级别信号: 买 {', '.join(buy_signals) or '无'}；"
            f"卖 {', '.join(sell_signals) or '无'}"
        )
    prompt_lines.append(f"- 综合建议: {suggestion}")

    return MultiTimeframeCombinedJudgment(
        main_trend=main_trend,
        trend_strength=trend_strength,
        resonance=resonance,
        trend_alignment={
            "large": summaries["large"].get("trend", "unknown"),
            "medium": summaries["medium"].get("trend", "unknown"),
            "small": summaries["small"].get("trend", "unknown"),
        },
        position_alignment=positions,
        buy_signals=buy_signals,
        sell_signals=sell_signals,
        suggestion=suggestion,
        prompt_text="\n".join(prompt_lines),
    )


class MultiTimeframeService:
    """对同一标的拉取并组合多周期缠论结构（默认 4h / 1h / 15m）。"""

    def __init__(
        self,
        symbol: str,
        *,
        levels: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.symbol = symbol
        self.levels = levels or DEFAULT_MULTI_TF_LEVELS

    def build_snapshot(self) -> MultiTimeframeSnapshot:
        level_results: dict[str, MultiTimeframeLevelResult] = {}
        latest_price = 0.0
        display_symbol = ""

        for level_key, cfg in self.levels.items():
            timeframe = str(cfg["timeframe"])
            lookback = int(cfg.get("lookback", DEFAULT_LOOKBACK))
            name = str(cfg.get("name", level_key))
            try:
                snapshot = build_chan_structure_snapshot(
                    self.symbol,
                    timeframe,
                    lookback=lookback,
                )
                display_symbol = snapshot.meta.symbol
                if timeframe == str(self.levels.get("small", {}).get("timeframe", "15m")):
                    latest_price = snapshot.market.latest_price
                elif latest_price <= 0:
                    latest_price = snapshot.market.latest_price
                level_results[level_key] = MultiTimeframeLevelResult(
                    ok=True,
                    level_key=level_key,
                    name=name,
                    timeframe=timeframe,
                    lookback=lookback,
                    snapshot=snapshot,
                    summary=_extract_level_summary(snapshot),
                    error=None,
                )
            except Exception as exc:
                level_results[level_key] = MultiTimeframeLevelResult(
                    ok=False,
                    level_key=level_key,
                    name=name,
                    timeframe=timeframe,
                    lookback=lookback,
                    snapshot=None,
                    summary={},
                    error=str(exc),
                )

        ok_levels = [r for r in level_results.values() if r.ok]
        if ok_levels and latest_price <= 0:
            latest_price = ok_levels[-1].snapshot.market.latest_price if ok_levels[-1].snapshot else 0.0

        combined = combine_multi_timeframe_judgment(level_results)

        return MultiTimeframeSnapshot(
            meta={
                "symbol": display_symbol or self.symbol,
                "analysis_type": "multi_timeframe",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latest_price": latest_price,
                "level_keys": list(self.levels.keys()),
            },
            levels=level_results,
            combined_judgment=combined,
            partial=len(ok_levels) < len(self.levels),
        )


def build_multi_timeframe_snapshot(
    symbol: str,
    *,
    levels: dict[str, dict[str, Any]] | None = None,
    lookback: int | None = None,
) -> MultiTimeframeSnapshot:
    """便捷入口：构建多周期结构快照。"""
    cfg = levels
    if cfg is None and lookback is not None:
        cfg = {
            key: {**val, "lookback": lookback}
            for key, val in DEFAULT_MULTI_TF_LEVELS.items()
        }
    return MultiTimeframeService(symbol, levels=cfg).build_snapshot()


def format_multi_timeframe_for_prompt(snapshot: MultiTimeframeSnapshot) -> str:
    """将多级别快照格式化为注入 Task 的 JSON 文本（对齐 chanlun build_multi_level_prompt 粒度）。

    - 三级均含 summary；中级别额外含完整 snapshot（作操作主周期）
    - 含 combined_judgment（含 prompt_text）
    """
    import json

    levels_out: dict[str, Any] = {}
    for key, lv in snapshot.levels.items():
        entry: dict[str, Any] = {
            "ok": lv.ok,
            "level_key": lv.level_key,
            "name": lv.name,
            "timeframe": lv.timeframe,
            "lookback": lv.lookback,
            "summary": lv.summary,
            "error": lv.error,
        }
        if lv.ok and lv.snapshot is not None:
            if key == "medium":
                entry["snapshot"] = lv.snapshot.model_dump(mode="json")
        levels_out[key] = entry

    payload = {
        "meta": snapshot.meta,
        "partial": snapshot.partial,
        "combined_judgment": snapshot.combined_judgment.model_dump(mode="json"),
        "levels": levels_out,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


_SINGLE_MODE_CONTEXT = (
    "（单周期模式：无预注入多级别 JSON；结构事实以 get_chan_structure 返回的 data 为准。）"
)
