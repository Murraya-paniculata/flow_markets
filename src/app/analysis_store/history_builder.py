"""组装 get_chan_structure 的 history 块（Phase 2.4 system_stats + 2.5 similar_cases）。"""

from __future__ import annotations

from typing import Any

from app.analysis_store.outcome import extract_structure_context
from app.analysis_store.similar_cases import (
    build_similar_cases_block,
    similar_cases_floor,
)
from app.analysis_store.stats_formatter import (
    bucket_hit_rate,
    format_stats_for_prompt,
    get_stats_summary,
)
from app.analysis_store.stats_service import calculate_accuracy, count_evaluated_samples
from app.observability.logging import get_logger
from app.schemas.chan_structure import ChanStructureSnapshot

logger = get_logger(__name__)

MIN_WIN_RATE_OBSERVE_ONLY = 0.25
MIN_WIN_RATE_WAIT_CONFIRMATION = 0.35
MIN_SAMPLES_FOR_HINTS = 5

_FLOOR_RANK = {"OBSERVE_ONLY": 2, "WAIT_CONFIRMATION": 1}


def _merge_recommended_floor(
    system_floor: str | None,
    similar_floor: str | None,
) -> str | None:
    if system_floor is None and similar_floor is None:
        return None
    if system_floor is None:
        return similar_floor
    if similar_floor is None:
        return system_floor
    if _FLOOR_RANK.get(system_floor, 0) >= _FLOOR_RANK.get(similar_floor, 0):
        return system_floor
    return similar_floor


def compute_state_machine_hints(
    stats: dict[str, Any],
    symbol: str,
    interval: str,
    *,
    similar_cases: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hit_rate, sample_size, basis = bucket_hit_rate(
        stats, symbol, interval, min_samples=MIN_SAMPLES_FOR_HINTS
    )
    hints: dict[str, Any] = {
        "min_win_rate_observe_only": MIN_WIN_RATE_OBSERVE_ONLY,
        "min_win_rate_wait_confirmation": MIN_WIN_RATE_WAIT_CONFIRMATION,
        "min_samples": MIN_SAMPLES_FOR_HINTS,
        "basis": basis,
        "basis_sample_size": sample_size,
        "basis_hit_rate": hit_rate,
        "recommended_floor": None,
        "system_floor": None,
        "similar_cases_floor": None,
    }

    system_floor: str | None = None
    if hit_rate is not None:
        if hit_rate < MIN_WIN_RATE_OBSERVE_ONLY:
            system_floor = "OBSERVE_ONLY"
        elif hit_rate < MIN_WIN_RATE_WAIT_CONFIRMATION:
            system_floor = "WAIT_CONFIRMATION"
    hints["system_floor"] = system_floor

    similar_floor: str | None = None
    if similar_cases and similar_cases.get("has_data"):
        similar_floor = similar_cases_floor(
            similar_cases.get("win_rate"),
            int(similar_cases.get("count") or 0),
        )
    hints["similar_cases_floor"] = similar_floor

    merged = _merge_recommended_floor(system_floor, similar_floor)
    hints["recommended_floor"] = merged

    if merged == "OBSERVE_ONLY":
        hints["message"] = "系统胜率或相似案例胜率偏低，建议 OBSERVE_ONLY"
    elif merged == "WAIT_CONFIRMATION":
        hints["message"] = "系统胜率或相似案例一般，至少 WAIT_CONFIRMATION"
    elif hit_rate is not None:
        hints["message"] = f"历史胜率 {hit_rate*100:.1f}%，可按结构选择 STRATEGY_ACTIVE"
    else:
        hints["message"] = "历史样本不足，不因胜率强制降级状态机"
    return hints


def _context_match_from_snapshot(snapshot: ChanStructureSnapshot) -> dict[str, str]:
    data = snapshot.model_dump(mode="json")
    ctx = extract_structure_context(data, {})
    return {
        "signal_type": ctx.get("signal_type", "none"),
        "trend": ctx.get("trend", "unknown"),
        "price_position": ctx.get("price_position", "unknown"),
        "strength_comparison": ctx.get("strength_comparison", "unknown"),
    }


def _build_system_stats(
    stats: dict[str, Any],
    symbol: str,
    interval: str,
) -> dict[str, Any]:
    summary = get_stats_summary(stats)
    if not summary.get("has_data"):
        return {
            "has_data": False,
            "total": 0,
            "hit_rate": 0.0,
            "avg_score": 0.0,
            "prompt_text": format_stats_for_prompt(stats, symbol, interval),
        }

    sym_row = next((s for s in stats.get("by_symbol", []) if s[0] == symbol), None)
    int_row = next((i for i in stats.get("by_interval", []) if i[0] == interval), None)

    def _row_to_bucket(row: tuple | None) -> dict[str, Any] | None:
        if not row:
            return None
        key, total, hit, avg = row
        return {
            "key": key,
            "total": total,
            "hit_count": hit,
            "hit_rate": round(hit / total, 4) if total > 0 else 0.0,
            "avg_score": avg,
        }

    return {
        "has_data": True,
        "total": summary["total"],
        "hit_rate": summary["hit_rate"],
        "avg_score": summary["avg_score"],
        "for_symbol": _row_to_bucket(sym_row),
        "for_interval": _row_to_bucket(int_row),
        "by_direction": [
            {
                "direction": d[0],
                "total": d[1],
                "hit_count": d[2],
                "hit_rate": round(d[2] / d[1], 4) if d[1] > 0 else 0.0,
                "avg_score": d[3],
            }
            for d in stats.get("by_direction", [])
        ],
        "prompt_text": format_stats_for_prompt(stats, symbol, interval),
    }


def build_history_block(snapshot: ChanStructureSnapshot) -> dict[str, Any]:
    """构建工具 JSON 的 history 段（system_stats + similar_cases + state_machine_hints）。"""
    symbol = snapshot.meta.symbol
    interval = snapshot.meta.interval
    db_evaluated = count_evaluated_samples()
    context_match = _context_match_from_snapshot(snapshot)

    try:
        stats = calculate_accuracy()
        system_stats = _build_system_stats(stats, symbol, interval)
        similar_cases = build_similar_cases_block(
            snapshot,
            context_match=context_match,
        )
        hints = compute_state_machine_hints(
            stats,
            symbol,
            interval,
            similar_cases=similar_cases,
        )
        available = system_stats.get("has_data", False) or similar_cases.get("has_data", False)
        return {
            "available": available,
            "reason": None if available else "NO_SCORABLE_EVALUATED_SAMPLES",
            "message": None
            if available
            else "尚无已评估且可计分的快照；完成 2.2 落库与 2.3 回填后再有胜率",
            "db_samples_evaluated": db_evaluated,
            "context_match": context_match,
            "system_stats": system_stats,
            "state_machine_hints": hints,
            "similar_cases": similar_cases,
            "learning_feedback": {"has_data": False, "message": "Phase 2.6"},
        }
    except Exception as exc:
        logger.warning("build_history_block_failed", error=str(exc))
        return {
            "available": False,
            "reason": "QUERY_ERROR",
            "message": str(exc),
            "db_samples_evaluated": db_evaluated,
            "context_match": context_match,
            "system_stats": {"has_data": False, "prompt_text": ""},
            "state_machine_hints": {},
            "similar_cases": {"has_data": False},
            "learning_feedback": {"has_data": False},
        }
