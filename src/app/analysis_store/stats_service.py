"""分析库统计（移植 chanlun query_stats.calculate_accuracy）。"""

from __future__ import annotations

from typing import Any

from app.analysis_store.db_manager import get_db_conn, safe_json_loads
from app.analysis_store.outcome import extract_structure_context


def _classify_signal(buy_sell_points: list, divergences: list) -> str:
    if not buy_sell_points and not divergences:
        return "none"
    for signal in buy_sell_points:
        sl = signal.lower()
        if "1buy" in sl:
            return "1buy"
        if "2buy" in sl:
            return "2buy"
        if "3buy" in sl:
            return "3buy"
        if "1sell" in sl:
            return "1sell"
        if "2sell" in sl:
            return "2sell"
        if "3sell" in sl:
            return "3sell"
    for bc in divergences:
        bl = bc.lower()
        if "bottom" in bl or "底" in bc:
            return "bc_buy"
        if "top" in bl or "顶" in bc:
            return "bc_sell"
    return "mixed"


def extract_structure_context_from_record(
    chanlun_json: dict[str, Any],
    ai_json: dict[str, Any],
    outcome_json: dict[str, Any],
) -> dict[str, Any]:
    """与 chanlun query_stats.extract_structure_context 对齐。"""
    ctx = outcome_json.get("structure_context", {}) if outcome_json else {}
    if ctx and ctx.get("trend") != "unknown":
        return ctx

    source = chanlun_json if chanlun_json else ai_json
    if not source:
        return extract_structure_context(ai_json, chanlun_json)

    signal = source.get("signal", {})
    summary = source.get("structure_summary", {})
    buy_sell_points = signal.get("buy_sell_points", [])
    divergences = signal.get("divergences", [])
    return {
        "trend": summary.get("trend", "unknown"),
        "price_position": summary.get("price_position", "unknown"),
        "strength_comparison": summary.get("strength_comparison", "unknown"),
        "signal_type": _classify_signal(buy_sell_points, divergences),
        "has_signal": bool(buy_sell_points or divergences),
    }


def _is_scorable_outcome(outcome: dict[str, Any]) -> bool:
    """排除纯错误回填，避免稀释胜率（insufficient_data 等）。"""
    if not outcome:
        return False
    err = outcome.get("error")
    if err in (
        "insufficient_data",
        "insufficient_klines",
        "abnormal_price_movement",
        "invalid_entry_price",
        "no_evaluable_scenario",
        "json_parse_error",
    ):
        return False
    if outcome.get("outcome") == "skipped":
        return False
    return True


def calculate_accuracy() -> dict[str, Any]:
    """聚合 evaluated=1 记录的命中率与分维度统计。"""
    with get_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT outcome_json, symbol, interval, chanlun_json, ai_json
            FROM analysis_snapshot
            WHERE evaluated = 1 AND outcome_json IS NOT NULL
            """
        ).fetchall()

    total = 0
    hit_count = 0
    stop_count = 0
    by_direction_map: dict[str, dict[str, float]] = {}
    by_symbol_map: dict[str, dict[str, float]] = {}
    by_interval_map: dict[str, dict[str, float]] = {}
    by_outcome_map: dict[str, int] = {}
    by_trend_map: dict[str, dict[str, float]] = {}
    by_position_map: dict[str, dict[str, float]] = {}
    by_signal_map: dict[str, dict[str, float]] = {}
    total_score = 0.0
    total_enhanced_score = 0.0

    for outcome_json_str, symbol, interval, chanlun_json_str, ai_json_str in rows:
        outcome = safe_json_loads(outcome_json_str, {})
        if not _is_scorable_outcome(outcome):
            continue
        chanlun_data = safe_json_loads(chanlun_json_str, {})
        ai_data = safe_json_loads(ai_json_str, {})

        total += 1
        direction = outcome.get("direction", "unknown")
        hit_target = bool(outcome.get("hit_target", False))
        hit_stop = bool(outcome.get("hit_stop", False))
        outcome_type = outcome.get("outcome", "unknown")
        score = float(outcome.get("score", 0))
        enhanced_score = float(outcome.get("enhanced_score", score))

        total_score += score
        total_enhanced_score += enhanced_score
        if hit_target:
            hit_count += 1
        if hit_stop:
            stop_count += 1

        ctx = extract_structure_context_from_record(chanlun_data, ai_data, outcome)
        trend = ctx.get("trend", "unknown")
        position = ctx.get("price_position", "unknown")
        signal_type = ctx.get("signal_type", "none")

        def _acc(map_data: dict, key: str) -> None:
            stats = map_data.setdefault(key, {"total": 0, "hit": 0, "score": 0.0})
            stats["total"] += 1
            stats["score"] += score
            if hit_target:
                stats["hit"] += 1

        _acc(by_direction_map, direction)
        _acc(by_symbol_map, symbol)
        _acc(by_interval_map, interval)
        _acc(by_trend_map, trend)
        _acc(by_position_map, position)
        _acc(by_signal_map, signal_type)
        by_outcome_map[outcome_type] = by_outcome_map.get(outcome_type, 0) + 1

    def build_list(map_data: dict[str, dict[str, float]]) -> list[tuple]:
        result = []
        for key, stats in map_data.items():
            t = int(stats["total"])
            avg = stats["score"] / t if t > 0 else 0.0
            result.append((key, t, int(stats["hit"]), round(avg, 4)))
        return result

    avg_score = total_score / total if total > 0 else 0.0
    avg_enhanced = total_enhanced_score / total if total > 0 else 0.0

    return {
        "total": total,
        "hit_count": hit_count,
        "stop_count": stop_count,
        "avg_score": round(avg_score, 4),
        "avg_enhanced_score": round(avg_enhanced, 4),
        "by_direction": build_list(by_direction_map),
        "by_symbol": build_list(by_symbol_map),
        "by_interval": build_list(by_interval_map),
        "by_outcome": list(by_outcome_map.items()),
        "by_trend": build_list(by_trend_map),
        "by_position": build_list(by_position_map),
        "by_signal": build_list(by_signal_map),
    }


def count_evaluated_samples() -> int:
    """库内 evaluated=1 行数（含不可评分 outcome）。"""
    with get_db_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM analysis_snapshot WHERE evaluated = 1"
        ).fetchone()
    return int(row[0]) if row else 0
