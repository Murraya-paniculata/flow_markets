"""信号质量评分（移植 chanlun/signal_quality.py，适配 FlowMarkets 结构 JSON + 状态机 v2）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.analysis_store.db_manager import get_db_path
from app.analysis_store.signal_classifier import (
    classify_signal,
    extract_direction_from_ai,
)
from app.schemas.flow_markets_deliverables import SignalQualitySummary, TechnicalAnalysisDeliverable

DEFAULT_WEIGHTS: dict[str, float] = {
    "signal_type": 20,
    "trend": 20,
    "position": 15,
    "strength": 15,
    "history": 20,
    "risk_reward": 10,
}

_HISTORY_STATS_CACHE: dict[str, dict] = {}


def get_min_sample_size(total_samples: int) -> int:
    if total_samples < 50:
        return 5
    if total_samples < 200:
        return 10
    if total_samples < 500:
        return 15
    return 20


def _weights_path() -> Path:
    return get_db_path().parent / "optimized_weights.json"


def _load_weights() -> dict[str, float]:
    path = _weights_path()
    if path.exists():
        try:
            with path.open(encoding="utf-8") as f:
                config = json.load(f)
            weights = config.get("weights", {})
            if weights:
                return {k: float(v) for k, v in weights.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return DEFAULT_WEIGHTS.copy()


WEIGHTS = _load_weights()


def reset_history_stats_cache() -> None:
    """测试或刷新历史统计缓存。"""
    global _HISTORY_STATS_CACHE
    _HISTORY_STATS_CACHE = {}


def reload_weights() -> dict[str, float]:
    """重新加载权重配置（含 optimized_weights.json）。"""
    global WEIGHTS
    WEIGHTS = _load_weights()
    return WEIGHTS


def _load_history_stats() -> dict[str, dict]:
    global _HISTORY_STATS_CACHE
    if _HISTORY_STATS_CACHE:
        return _HISTORY_STATS_CACHE

    try:
        from app.analysis_store.stats_service import StatsService

        _HISTORY_STATS_CACHE = StatsService().history_buckets_for_scoring()
    except Exception:
        _HISTORY_STATS_CACHE = {}

    return _HISTORY_STATS_CACHE


def _target_stop_pct_from_ai(ai: dict[str, Any]) -> tuple[float, float]:
    primary = ai.get("primary_scenario") or {}
    if primary.get("target_pct") is not None and primary.get("stop_pct") is not None:
        return float(primary["target_pct"]), float(primary["stop_pct"])

    v2 = ai.get("chanlun_v2") or {}
    meta = v2.get("meta") or {}
    active = (v2.get("state_machine") or {}).get("active_strategy") or {}
    execution = active.get("execution") or {}

    price = float(meta.get("price") or 0)
    target = float(execution.get("target") or 0)
    stop = float(execution.get("stop_loss") or 0)
    rr = float(execution.get("rr") or 0)

    if price > 0 and target > 0 and stop > 0:
        return (
            abs(target - price) / price * 100,
            abs(stop - price) / price * 100,
        )
    if rr > 0:
        stop_pct = 1.5
        return stop_pct * rr, stop_pct
    return 2.0, 1.5


def _get_win_rate(stats_dict: dict, key: str, total_samples: int = 0) -> float:
    if not stats_dict or key not in stats_dict:
        return 0.5

    s = stats_dict[key]
    total = s.get("total", 0)
    wins = s.get("wins", 0)
    min_size = get_min_sample_size(total_samples)
    if total < min_size:
        return 0.5
    return wins / total if total else 0.5


def score_signal_type(signal_type: str, direction: str, max_score: float | None = None) -> tuple[float, str]:
    if max_score is None:
        max_score = WEIGHTS.get("signal_type", 20)

    if direction == "up":
        if signal_type in ("1buy", "bc_buy"):
            ratio, reason = 1.0, "一买/底背驰 + 看涨，强买入信号"
        elif signal_type == "2buy":
            ratio, reason = 0.9, "二买 + 看涨，较强买入信号"
        elif signal_type == "3buy":
            ratio, reason = 0.75, "三买 + 看涨，回调买入信号"
        elif signal_type in ("1sell", "2sell", "3sell", "bc_sell"):
            ratio, reason = 0.25, "卖出信号 + 看涨，方向冲突"
        elif signal_type == "mixed":
            ratio, reason = 0.5, "混合信号 + 看涨"
        else:
            ratio, reason = 0.4, "无明确信号 + 看涨"
    elif direction == "down":
        if signal_type in ("1sell", "bc_sell"):
            ratio, reason = 1.0, "一卖/顶背驰 + 看跌，强卖出信号"
        elif signal_type == "2sell":
            ratio, reason = 0.9, "二卖 + 看跌，较强卖出信号"
        elif signal_type == "3sell":
            ratio, reason = 0.75, "三卖 + 看跌，反弹卖出信号"
        elif signal_type in ("1buy", "2buy", "3buy", "bc_buy"):
            ratio, reason = 0.25, "买入信号 + 看跌，方向冲突"
        elif signal_type == "mixed":
            ratio, reason = 0.5, "混合信号 + 看跌"
        else:
            ratio, reason = 0.4, "无明确信号 + 看跌"
    else:
        ratio, reason = 0.5, "震荡方向，信号参考价值有限"

    return round(ratio * max_score, 1), reason


def score_trend_consistency(trend: str, direction: str, max_score: float | None = None) -> tuple[float, str]:
    if max_score is None:
        max_score = WEIGHTS.get("trend", 20)

    if direction == "up":
        if trend == "up_trend":
            ratio, reason = 1.0, "上升趋势 + 看涨，顺势做多"
        elif trend == "consolidation":
            ratio, reason = 0.6, "震荡 + 看涨，需等待突破确认"
        elif trend == "down_trend":
            ratio, reason = 0.25, "下降趋势 + 看涨，逆势操作风险高"
        else:
            ratio, reason = 0.5, "趋势未知"
    elif direction == "down":
        if trend == "down_trend":
            ratio, reason = 1.0, "下降趋势 + 看跌，顺势做空"
        elif trend == "consolidation":
            ratio, reason = 0.6, "震荡 + 看跌，需等待破位确认"
        elif trend == "up_trend":
            ratio, reason = 0.25, "上升趋势 + 看跌，逆势操作风险高"
        else:
            ratio, reason = 0.5, "趋势未知"
    else:
        if trend == "consolidation":
            ratio, reason = 0.75, "震荡行情，高抛低吸策略"
        else:
            ratio, reason = 0.5, "方向不明确"

    return round(ratio * max_score, 1), reason


def score_price_position(position: str, direction: str, max_score: float | None = None) -> tuple[float, str]:
    if max_score is None:
        max_score = WEIGHTS.get("position", 15)

    if direction == "up":
        if position == "below_zs":
            ratio, reason = 1.0, "价格在中枢下方，做多空间充足"
        elif position == "inside_zs":
            ratio, reason = 0.8, "价格在中枢内部，等待方向选择"
        elif position == "above_zs":
            ratio, reason = 0.53, "价格在中枢上方，追涨风险"
        else:
            ratio, reason = 0.67, "位置未知"
    elif direction == "down":
        if position == "above_zs":
            ratio, reason = 1.0, "价格在中枢上方，做空空间充足"
        elif position == "inside_zs":
            ratio, reason = 0.8, "价格在中枢内部，等待方向选择"
        elif position == "below_zs":
            ratio, reason = 0.53, "价格在中枢下方，追跌风险"
        else:
            ratio, reason = 0.67, "位置未知"
    else:
        if position == "inside_zs":
            ratio, reason = 1.0, "价格在中枢内部，震荡策略有效"
        else:
            ratio, reason = 0.67, "价格远离中枢"

    return round(ratio * max_score, 1), reason


def score_strength_divergence(
    strength: str,
    has_divergence: bool,
    direction: str,
    max_score: float | None = None,
) -> tuple[float, str]:
    if max_score is None:
        max_score = WEIGHTS.get("strength", 15)

    base_ratio = 0.47
    reason_parts: list[str] = []

    if strength == "weakening":
        if direction in ("up", "down"):
            base_ratio = 0.8
            reason_parts.append("力度衰竭")
    elif strength == "strengthening":
        if direction in ("up", "down"):
            base_ratio = 0.67
            reason_parts.append("力度增强")
    elif strength == "similar":
        reason_parts.append("力度相近")
    else:
        reason_parts.append("力度未知")

    if has_divergence:
        base_ratio = min(1.0, base_ratio + 0.2)
        reason_parts.append("存在背驰信号")

    return round(base_ratio * max_score, 1), "，".join(reason_parts) if reason_parts else "力度正常"


def score_history_winrate(
    signal_type: str,
    direction: str,
    max_score: float | None = None,
    total_samples: int = 0,
) -> tuple[float, str]:
    if max_score is None:
        max_score = WEIGHTS.get("history", 20)

    stats = _load_history_stats()
    if not stats:
        return round(0.5 * max_score, 1), "历史数据不足"

    combo_key = f"{signal_type}_{direction}"
    combo_stats = stats.get("combo", {})
    signal_stats = stats.get("signal", {})
    combo_wr = _get_win_rate(combo_stats, combo_key, total_samples)
    signal_wr = _get_win_rate(signal_stats, signal_type, total_samples)
    avg_wr = combo_wr * 0.6 + signal_wr * 0.4
    score = avg_wr * max_score
    combo_total = combo_stats.get(combo_key, {}).get("total", 0)
    min_size = get_min_sample_size(total_samples)

    if combo_total < min_size:
        reason = f"样本不足({combo_total}条)，历史胜率参考有限"
    elif avg_wr >= 0.5:
        reason = f"历史胜率{avg_wr * 100:.1f}%（{combo_total}条样本），表现良好"
    elif avg_wr >= 0.3:
        reason = f"历史胜率{avg_wr * 100:.1f}%（{combo_total}条样本），表现一般"
    else:
        reason = f"历史胜率{avg_wr * 100:.1f}%（{combo_total}条样本），表现较差"

    return round(score, 1), reason


def score_volatility(target_pct: float, stop_pct: float, max_score: float | None = None) -> tuple[float, str]:
    if max_score is None:
        max_score = WEIGHTS.get("risk_reward", 10)

    if stop_pct <= 0:
        return round(0.5 * max_score, 1), "止损参数异常"

    rr_ratio = target_pct / stop_pct
    if rr_ratio >= 3:
        ratio, reason = 1.0, f"盈亏比 {rr_ratio:.1f}:1，风险收益极佳"
    elif rr_ratio >= 2:
        ratio, reason = 0.8, f"盈亏比 {rr_ratio:.1f}:1，风险收益良好"
    elif rr_ratio >= 1.5:
        ratio, reason = 0.6, f"盈亏比 {rr_ratio:.1f}:1，风险收益一般"
    elif rr_ratio >= 1:
        ratio, reason = 0.4, f"盈亏比 {rr_ratio:.1f}:1，风险收益较差"
    else:
        ratio, reason = 0.2, f"盈亏比 {rr_ratio:.1f}:1，风险大于收益"

    return round(ratio * max_score, 1), reason


def calculate_signal_quality(
    chanlun_json: dict[str, Any],
    ai_json: dict[str, Any],
) -> dict[str, Any]:
    """六维综合评分。``ai_json`` 支持 chanlun primary_scenario 或 FlowMarkets deliverable。"""
    source = chanlun_json if chanlun_json else ai_json
    signal = source.get("signal", {})
    summary = source.get("structure_summary", {})

    buy_sell_points = signal.get("buy_sell_points", [])
    divergences = signal.get("divergences", [])
    trend = summary.get("trend", "unknown")
    position = summary.get("price_position", "unknown")
    strength = summary.get("strength_comparison", "unknown")

    direction = extract_direction_from_ai(ai_json)
    target_pct, stop_pct = _target_stop_pct_from_ai(ai_json)
    signal_type = classify_signal(buy_sell_points, divergences)
    has_divergence = bool(divergences)
    weights = WEIGHTS

    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    max_scores: dict[str, float] = {}

    max_scores["signal_type"] = weights.get("signal_type", 20)
    s1, r1 = score_signal_type(signal_type, direction, max_scores["signal_type"])
    scores["signal_type"] = s1
    reasons["signal_type"] = r1

    max_scores["trend"] = weights.get("trend", 20)
    s2, r2 = score_trend_consistency(trend, direction, max_scores["trend"])
    scores["trend"] = s2
    reasons["trend"] = r2

    max_scores["position"] = weights.get("position", 15)
    s3, r3 = score_price_position(position, direction, max_scores["position"])
    scores["position"] = s3
    reasons["position"] = r3

    max_scores["strength"] = weights.get("strength", 15)
    s4, r4 = score_strength_divergence(strength, has_divergence, direction, max_scores["strength"])
    scores["strength"] = s4
    reasons["strength"] = r4

    max_scores["history"] = weights.get("history", 20)
    s5, r5 = score_history_winrate(signal_type, direction, max_scores["history"])
    scores["history"] = s5
    reasons["history"] = r5

    max_scores["risk_reward"] = weights.get("risk_reward", 10)
    s6, r6 = score_volatility(target_pct, stop_pct, max_scores["risk_reward"])
    scores["risk_reward"] = s6
    reasons["risk_reward"] = r6

    total_score = sum(scores.values())

    if total_score >= 80:
        grade, grade_name, action, action_name = "A", "优质信号", "trade", "建议交易"
    elif total_score >= 60:
        grade, grade_name, action, action_name = "B", "良好信号", "trade", "可以交易"
    elif total_score >= 40:
        grade, grade_name, action, action_name = "C", "一般信号", "wait", "谨慎观望"
    else:
        grade, grade_name, action, action_name = "D", "低质信号", "skip", "建议放弃"

    dim_names = {
        "signal_type": "信号类型",
        "trend": "趋势一致性",
        "position": "价格位置",
        "strength": "力度背驰",
        "history": "历史胜率",
        "risk_reward": "盈亏比",
    }
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_dim, worst_dim = sorted_scores[0], sorted_scores[-1]
    advice_parts = [f"优势: {dim_names[best_dim[0]]}({best_dim[1]}分)"]
    if worst_dim[1] < 10:
        advice_parts.append(f"风险: {dim_names[worst_dim[0]]}({worst_dim[1]}分)")

    return {
        "total_score": round(total_score, 1),
        "grade": grade,
        "grade_name": grade_name,
        "action": action,
        "action_name": action_name,
        "scores": scores,
        "max_scores": max_scores,
        "reasons": reasons,
        "advice": "；".join(advice_parts),
        "signal_type": signal_type,
        "direction": direction,
        "weights_optimized": _weights_path().exists(),
    }


def apply_signal_quality_to_deliverable(
    deliverable: TechnicalAnalysisDeliverable,
    chanlun_json: dict[str, Any],
) -> TechnicalAnalysisDeliverable:
    """治理后交付物附加六维评分（写入 ``signal_quality`` 字段）。"""
    if deliverable.chanlun_v2 is None:
        return deliverable
    ai_dict = deliverable.model_dump(mode="json")
    quality = calculate_signal_quality(chanlun_json, ai_dict)
    return deliverable.model_copy(
        update={"signal_quality": SignalQualitySummary.model_validate(quality)}
    )


def format_quality_report(quality: dict[str, Any] | SignalQualitySummary) -> str:
    """终端六维详细报告（对齐 chanlun format_quality_report）。"""
    if isinstance(quality, SignalQualitySummary):
        quality = quality.model_dump(mode="json")

    lines = [
        "",
        "=" * 60,
        "  信号质量评分",
        "=" * 60,
        f"\n  总分: {quality['total_score']}/100  评级: {quality['grade']} ({quality['grade_name']})",
        f"  建议: {quality['action_name']}",
        "\n  【各维度得分】",
        "-" * 60,
    ]

    dim_names = {
        "signal_type": "信号类型",
        "trend": "趋势一致性",
        "position": "价格位置",
        "strength": "力度背驰",
        "history": "历史胜率",
        "risk_reward": "盈亏比",
    }
    scores = quality.get("scores", {})
    reasons = quality.get("reasons", {})
    max_scores = quality.get("max_scores", WEIGHTS)

    for key, name in dim_names.items():
        max_score = max_scores.get(key, WEIGHTS.get(key, 10))
        score = scores.get(key, 0)
        reason = reasons.get(key, "")
        bar_len = int(score / max_score * 10) if max_score > 0 else 0
        bar = "#" * bar_len + "-" * (10 - bar_len)
        lines.append(f"  {name:<10} [{bar}] {score:>5.1f}/{max_score:.0f}")
        if reason:
            lines.append(f"              {reason}")

    lines.extend(
        [
            "\n  【综合分析】",
            "-" * 60,
            f"  {quality.get('advice', '')}",
            "\n" + "=" * 60,
        ]
    )
    return "\n".join(lines)
