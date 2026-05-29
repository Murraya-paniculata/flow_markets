"""相似案例检索（移植 chanlun history_context，Phase 2.5）。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.analysis_store.db_manager import get_db_conn, safe_json_loads
from app.analysis_store.stats_service import _is_scorable_outcome
from app.schemas.chan_structure import ChanStructureSnapshot

DEFAULT_SIMILARITY_THRESHOLD = 40.0
MIN_SIMILARITY_THRESHOLD = 20.0


def calculate_time_decay(
    case_timestamp: str,
    current_timestamp: str | None = None,
    half_life_days: int = 30,
) -> float:
    try:
        if current_timestamp is None:
            current_time = datetime.now(timezone.utc)
        else:
            current_time = datetime.fromisoformat(current_timestamp)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
        case_time = datetime.fromisoformat(case_timestamp)
        if case_time.tzinfo is None:
            case_time = case_time.replace(tzinfo=timezone.utc)
        days_diff = (current_time - case_time).days
        decay = 0.5 ** (days_diff / half_life_days)
        return max(0.1, min(1.0, decay))
    except Exception:
        return 1.0


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


def extract_context_from_structure(struct: dict[str, Any]) -> dict[str, str]:
    signal = struct.get("signal", {}) if struct else {}
    summary = struct.get("structure_summary", {}) if struct else {}
    buy_sell_points = signal.get("buy_sell_points", [])
    divergences = signal.get("divergences", [])
    return {
        "signal_type": _classify_signal(buy_sell_points, divergences),
        "trend": summary.get("trend", "unknown"),
        "position": summary.get("price_position", "unknown"),
        "strength": summary.get("strength_comparison", "unknown"),
    }


def context_match_to_similarity_ctx(context_match: dict[str, str]) -> dict[str, str]:
    return {
        "signal_type": context_match.get("signal_type", "unknown"),
        "trend": context_match.get("trend", "unknown"),
        "position": context_match.get("price_position", context_match.get("position", "unknown")),
        "strength": context_match.get("strength_comparison", context_match.get("strength", "unknown")),
    }


def calculate_similarity(
    current: dict[str, str],
    historical: dict[str, str],
    *,
    symbol_match: bool,
    interval_match: bool,
) -> float:
    score = 0.0
    if symbol_match:
        score += 20
    if interval_match:
        score += 15
    if current["signal_type"] == historical["signal_type"]:
        score += 25
    elif current["signal_type"] != "unknown" and historical["signal_type"] != "unknown":
        curr_is_buy = "buy" in current["signal_type"]
        hist_is_buy = "buy" in historical["signal_type"]
        if curr_is_buy == hist_is_buy:
            score += 15
    if current["trend"] == historical["trend"]:
        score += 20
    elif current["trend"] != "unknown" and historical["trend"] != "unknown":
        score += 5
    if current["position"] == historical["position"]:
        score += 15
    elif current["position"] != "unknown" and historical["position"] != "unknown":
        score += 5
    if current["strength"] == historical["strength"]:
        score += 5
    return score


@dataclass
class SimilarCase:
    snapshot_id: int
    symbol: str
    interval: str
    timestamp: str
    direction: str
    signal_type: str
    trend: str
    position: str
    hit_target: bool
    score: float
    target_pct: float
    stop_pct: float
    max_favorable: float
    max_adverse: float
    similarity_score: float


def search_similar_cases(
    symbol: str,
    interval: str,
    current_context: dict[str, str],
    *,
    direction: str | None = None,
    min_similarity: float | None = None,
    limit: int = 20,
    enable_time_decay: bool = True,
) -> tuple[list[SimilarCase], float]:
    if min_similarity is None:
        min_similarity = DEFAULT_SIMILARITY_THRESHOLD
    threshold_used = min_similarity

    with get_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol, interval, timestamp, ai_json, outcome_json, chanlun_json
            FROM analysis_snapshot
            WHERE evaluated = 1 AND outcome_json IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 500
            """
        ).fetchall()

    similar_cases: list[SimilarCase] = []
    current_time = datetime.now(timezone.utc).isoformat()

    for row in rows:
        snapshot_id, hist_symbol, hist_interval, timestamp, ai_str, outcome_str, chanlun_str = row
        outcome = safe_json_loads(outcome_str, {})
        if not _is_scorable_outcome(outcome):
            continue
        ai_json = safe_json_loads(ai_str, {})
        chanlun_json = safe_json_loads(chanlun_str, {}) if chanlun_str else {}
        hist_context = extract_context_from_structure(chanlun_json or ai_json)

        similarity = calculate_similarity(
            current_context,
            hist_context,
            symbol_match=(symbol == hist_symbol),
            interval_match=(interval == hist_interval),
        )
        hist_direction = outcome.get("direction", "unknown")
        if direction and direction == hist_direction:
            similarity += 10
        if enable_time_decay:
            similarity *= calculate_time_decay(timestamp, current_time)
        if similarity < min_similarity:
            continue

        primary = ai_json.get("primary_scenario", {}) if isinstance(ai_json, dict) else {}
        case = SimilarCase(
            snapshot_id=int(snapshot_id),
            symbol=hist_symbol,
            interval=hist_interval,
            timestamp=timestamp,
            direction=hist_direction,
            signal_type=hist_context["signal_type"],
            trend=hist_context["trend"],
            position=hist_context["position"],
            hit_target=bool(outcome.get("hit_target", False)),
            score=float(outcome.get("score", 0)),
            target_pct=float(primary.get("target_pct") or outcome.get("target_pct") or 0),
            stop_pct=float(primary.get("stop_pct") or outcome.get("stop_pct") or 0),
            max_favorable=float(outcome.get("max_favorable_move", 0)),
            max_adverse=float(outcome.get("max_adverse_move", 0)),
            similarity_score=round(similarity, 2),
        )
        similar_cases.append(case)

    similar_cases.sort(key=lambda c: c.similarity_score, reverse=True)

    if len(similar_cases) < 3 and min_similarity > MIN_SIMILARITY_THRESHOLD:
        lowered = max(min_similarity - 10, MIN_SIMILARITY_THRESHOLD)
        retry_cases, retry_threshold = search_similar_cases(
            symbol,
            interval,
            current_context,
            direction=direction,
            min_similarity=lowered,
            limit=limit,
            enable_time_decay=enable_time_decay,
        )
        return retry_cases, retry_threshold
    return similar_cases[:limit], threshold_used


def analyze_similar_cases(cases: list[SimilarCase]) -> dict[str, Any]:
    if not cases:
        return {
            "total": 0,
            "has_data": False,
            "message": "无相似历史案例",
        }

    total = len(cases)
    wins = sum(1 for c in cases if c.hit_target)
    win_rate = wins / total if total > 0 else 0.0
    avg_score = sum(c.score for c in cases) / total if total > 0 else 0.0

    by_direction: dict[str, dict[str, float]] = defaultdict(
        lambda: {"total": 0, "wins": 0, "score": 0.0}
    )
    for c in cases:
        by_direction[c.direction]["total"] += 1
        by_direction[c.direction]["score"] += c.score
        if c.hit_target:
            by_direction[c.direction]["wins"] += 1

    direction_stats = {
        d: {
            "total": int(s["total"]),
            "wins": int(s["wins"]),
            "win_rate": round(s["wins"] / s["total"], 3) if s["total"] > 0 else 0.0,
            "avg_score": round(s["score"] / s["total"], 3) if s["total"] > 0 else 0.0,
        }
        for d, s in by_direction.items()
    }

    avg_favorable = sum(c.max_favorable for c in cases) / total
    avg_adverse = sum(c.max_adverse for c in cases) / total

    if win_rate >= 0.5:
        suggestion = "历史相似案例表现良好，当前信号可信度较高"
        confidence = "high"
    elif win_rate >= 0.3:
        suggestion = "历史相似案例表现一般，建议谨慎操作"
        confidence = "medium"
    elif win_rate >= 0.15:
        suggestion = "历史相似案例胜率偏低，建议降低仓位或观望"
        confidence = "low"
    else:
        suggestion = "历史相似案例表现很差，强烈建议观望"
        confidence = "very_low"

    return {
        "total": total,
        "has_data": True,
        "wins": wins,
        "win_rate": round(win_rate, 3),
        "avg_score": round(avg_score, 3),
        "by_direction": direction_stats,
        "avg_favorable_move_pct": round(avg_favorable, 2),
        "avg_adverse_move_pct": round(avg_adverse, 2),
        "suggestion": suggestion,
        "confidence": confidence,
    }


def format_similar_cases_prompt(
    current_context: dict[str, str],
    cases: list[SimilarCase],
    stats: dict[str, Any],
) -> str:
    if not stats.get("has_data"):
        return "【历史参考 - 相似案例分析】\n无足够相似的历史案例可供参考。\n"

    dir_lines = []
    for d, s in stats.get("by_direction", {}).items():
        dir_name = {"up": "看涨", "down": "看跌"}.get(d, d)
        dir_lines.append(
            f"  - {dir_name}: {s['total']}条, 胜率{s['win_rate']*100:.1f}%, 平均得分{s['avg_score']:.2f}"
        )
    dir_text = "\n".join(dir_lines) if dir_lines else "  - 无"

    case_lines = []
    for c in cases[:5]:
        result = "命中" if c.hit_target else "未中"
        dir_name = {"up": "看涨", "down": "看跌"}.get(c.direction, c.direction)
        case_lines.append(
            f"  - [{c.symbol} {c.interval}] {dir_name}, {result}, "
            f"得分{c.score:.2f}, 相似度{c.similarity_score:.0f}"
        )
    cases_text = "\n".join(case_lines) if case_lines else "  - 无"

    return f"""【历史参考 - 相似案例分析】
当前结构特征: 信号={current_context['signal_type']}, 趋势={current_context['trend']}, 位置={current_context['position']}

相似案例统计（共{stats['total']}条）:
- 整体胜率: {stats['win_rate']*100:.1f}%
- 平均得分: {stats['avg_score']:.2f}/1.0
- 平均有利变动: {stats['avg_favorable_move_pct']:.2f}%
- 平均不利变动: {stats['avg_adverse_move_pct']:.2f}%

按方向统计:
{dir_text}

最相似案例:
{cases_text}

历史建议: {stats['suggestion']}
置信度: {stats['confidence']}

【重要提示】
1. 参考历史胜率调整预测概率；胜率<20% 应更保守
2. 胜率>40% 可适当提高置信度（仍须结构确认）
3. 参考历史平均变动设置目标与止损
"""


def build_similar_cases_block(
    snapshot: ChanStructureSnapshot,
    *,
    context_match: dict[str, str] | None = None,
    direction: str | None = None,
    threshold_used: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    symbol = snapshot.meta.symbol
    interval = snapshot.meta.interval
    struct = snapshot.model_dump(mode="json")
    current_context = context_match_to_similarity_ctx(
        context_match or extract_context_from_structure(struct)
    )
    # normalize context_match keys for output
    if context_match is None:
        context_match = {
            "signal_type": current_context["signal_type"],
            "trend": current_context["trend"],
            "price_position": current_context["position"],
            "strength_comparison": current_context["strength"],
        }

    cases, used_threshold = search_similar_cases(
        symbol,
        interval,
        current_context,
        direction=direction,
        min_similarity=threshold_used,
    )
    stats = analyze_similar_cases(cases)

    top_cases = [
        {
            "snapshot_id": c.snapshot_id,
            "symbol": c.symbol,
            "interval": c.interval,
            "timestamp": c.timestamp,
            "direction": c.direction,
            "hit_target": c.hit_target,
            "score": c.score,
            "similarity_score": c.similarity_score,
        }
        for c in cases[:5]
    ]

    block: dict[str, Any] = {
        "has_data": stats.get("has_data", False),
        "threshold_used": used_threshold,
        "count": stats.get("total", 0),
        "win_rate": stats.get("win_rate", 0.0),
        "avg_score": stats.get("avg_score", 0.0),
        "avg_favorable_move_pct": stats.get("avg_favorable_move_pct", 0.0),
        "avg_adverse_move_pct": stats.get("avg_adverse_move_pct", 0.0),
        "confidence": stats.get("confidence"),
        "suggestion": stats.get("suggestion"),
        "by_direction": stats.get("by_direction", {}),
        "top_cases": top_cases,
        "prompt_text": format_similar_cases_prompt(current_context, cases, stats),
    }
    if not block["has_data"]:
        block["message"] = stats.get("message", "无相似历史案例")
    return block


def similar_cases_floor(win_rate: float | None, count: int, *, min_samples: int = 3) -> str | None:
    """由相似案例胜率推导状态机下限（与 chanlun state_machine_converter 对齐）。"""
    if count < min_samples or win_rate is None:
        return None
    if win_rate <= 0:
        return "OBSERVE_ONLY"
    if win_rate < 0.25:
        return "OBSERVE_ONLY"
    if win_rate < 0.35:
        return "WAIT_CONFIRMATION"
    return None
