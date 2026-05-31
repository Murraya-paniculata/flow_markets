"""AI 学习反馈（移植 chanlun learning_feedback，Phase 2.6）。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.analysis_store.db_manager import get_db_conn, safe_json_loads
from app.analysis_store.outcome import extract_scenario_for_eval, extract_structure_context
from app.analysis_store.stats_service import _is_scorable_outcome
from app.schemas.chan_structure import ChanStructureSnapshot

DEFAULT_LOOKBACK_DAYS = 30
MIN_BUCKET_SAMPLES = 5


def get_min_sample_size(total_samples: int) -> int:
    if total_samples < 50:
        return 5
    if total_samples < 200:
        return 10
    if total_samples < 500:
        return 15
    return 20


@dataclass
class PerformanceStats:
    total: int = 0
    wins: int = 0
    losses: int = 0
    avg_score: float = 0.0
    avg_target_pct: float = 0.0
    avg_actual_move: float = 0.0
    target_deviation: float = 0.0
    total_predictions: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total if self.total > 0 else 0.0

    def has_enough_samples(self) -> bool:
        return self.total >= get_min_sample_size(self.total_predictions)


@dataclass
class ErrorPattern:
    pattern_type: str
    description: str
    frequency: int
    severity: str
    suggestion: str


@dataclass
class LearningReport:
    total_predictions: int = 0
    overall_win_rate: float = 0.0
    overall_avg_score: float = 0.0
    by_direction: dict[str, PerformanceStats] = field(default_factory=dict)
    by_signal_type: dict[str, PerformanceStats] = field(default_factory=dict)
    by_interval: dict[str, PerformanceStats] = field(default_factory=dict)
    error_patterns: list[ErrorPattern] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    confidence_adjustments: dict[str, float] = field(default_factory=dict)


def _bucket_stats(
    data: dict[str, dict[str, Any]],
    total_predictions: int,
) -> dict[str, PerformanceStats]:
    out: dict[str, PerformanceStats] = {}
    for key, d in data.items():
        stats = PerformanceStats(
            total=d["total"],
            wins=d["wins"],
            losses=d["total"] - d["wins"],
            avg_score=d["score"] / d["total"] if d["total"] > 0 else 0.0,
            avg_target_pct=sum(d["targets"]) / len(d["targets"]) if d["targets"] else 0.0,
            avg_actual_move=sum(d["actuals"]) / len(d["actuals"]) if d["actuals"] else 0.0,
            total_predictions=total_predictions,
        )
        stats.target_deviation = stats.avg_target_pct - stats.avg_actual_move
        out[key] = stats
    return out


def _identify_error_patterns(
    report: LearningReport,
    target_deviations: list[float],
) -> list[ErrorPattern]:
    patterns: list[ErrorPattern] = []
    if target_deviations:
        avg_deviation = sum(target_deviations) / len(target_deviations)
        if avg_deviation > 1.0:
            patterns.append(
                ErrorPattern(
                    pattern_type="target_too_high",
                    description=f"目标幅度平均偏高 {avg_deviation:.1f}%",
                    frequency=len([d for d in target_deviations if d > 1.0]),
                    severity="high",
                    suggestion="降低目标幅度，建议不超过历史实际变动的 1.5 倍",
                )
            )

    up_stats = report.by_direction.get("up")
    if up_stats and up_stats.total >= 10 and up_stats.win_rate < 0.15:
        patterns.append(
            ErrorPattern(
                pattern_type="up_prediction_weak",
                description=f"看涨预测胜率仅 {up_stats.win_rate * 100:.1f}%",
                frequency=up_stats.total,
                severity="high",
                suggestion="对看涨预测应更谨慎，降低概率或建议观望",
            )
        )

    none_stats = report.by_signal_type.get("none")
    if none_stats and none_stats.total >= 10 and none_stats.win_rate < 0.15:
        patterns.append(
            ErrorPattern(
                pattern_type="no_signal_guessing",
                description=f"无明确信号时预测胜率仅 {none_stats.win_rate * 100:.1f}%",
                frequency=none_stats.total,
                severity="high",
                suggestion="无明确买卖点信号时应建议观望，勿强行预测",
            )
        )

    for intv, stats in report.by_interval.items():
        if stats.total >= 10 and stats.win_rate < 0.1:
            patterns.append(
                ErrorPattern(
                    pattern_type=f"weak_interval_{intv}",
                    description=f"{intv} 周期预测胜率仅 {stats.win_rate * 100:.1f}%",
                    frequency=stats.total,
                    severity="medium",
                    suggestion=f"在 {intv} 周期应采用更保守策略",
                )
            )
    return patterns


def _generate_recommendations(report: LearningReport) -> None:
    dir_names = {"up": "看涨", "down": "看跌", "range": "震荡"}
    for direction, stats in report.by_direction.items():
        if stats.has_enough_samples() and stats.win_rate >= 0.3:
            report.strengths.append(
                f"{dir_names.get(direction, direction)}预测胜率 {stats.win_rate * 100:.0f}%，表现较好"
            )
    for signal, stats in report.by_signal_type.items():
        if stats.has_enough_samples() and stats.win_rate >= 0.35:
            report.strengths.append(f"{signal} 信号预测胜率 {stats.win_rate * 100:.0f}%")

    for direction, stats in report.by_direction.items():
        if stats.has_enough_samples() and stats.win_rate < 0.15:
            report.weaknesses.append(
                f"{dir_names.get(direction, direction)}预测胜率仅 {stats.win_rate * 100:.0f}%"
            )
    for signal, stats in report.by_signal_type.items():
        if stats.has_enough_samples() and stats.win_rate < 0.1:
            report.weaknesses.append(f"{signal} 信号预测胜率仅 {stats.win_rate * 100:.0f}%")

    if report.total_predictions >= MIN_BUCKET_SAMPLES and report.overall_win_rate < 0.2:
        report.recommendations.append("整体胜率偏低，建议采用更保守的预测策略")

    for pattern in report.error_patterns:
        if pattern.severity == "high":
            report.recommendations.append(pattern.suggestion)


def _calculate_confidence_adjustments(report: LearningReport) -> dict[str, float]:
    adjustments: dict[str, float] = {}
    for direction, stats in report.by_direction.items():
        if not stats.has_enough_samples():
            continue
        if stats.win_rate < 0.15:
            adjustments[f"direction_{direction}"] = 0.5
        elif stats.win_rate < 0.25:
            adjustments[f"direction_{direction}"] = 0.7
        elif stats.win_rate >= 0.4:
            adjustments[f"direction_{direction}"] = 1.1
    for signal, stats in report.by_signal_type.items():
        if not stats.has_enough_samples():
            continue
        if stats.win_rate < 0.1:
            adjustments[f"signal_{signal}"] = 0.5
        elif stats.win_rate >= 0.35:
            adjustments[f"signal_{signal}"] = 1.15
    return adjustments


def analyze_learning_feedback(
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    symbol: str | None = None,
    interval: str | None = None,
) -> LearningReport:
    query = """
        SELECT ai_json, outcome_json, chanlun_json, symbol, interval, timestamp, price
        FROM analysis_snapshot
        WHERE evaluated = 1 AND outcome_json IS NOT NULL
    """
    params: list[Any] = []
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query += " AND timestamp >= ?"
        params.append(cutoff.isoformat())
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if interval:
        query += " AND interval = ?"
        params.append(interval)
    query += " ORDER BY timestamp DESC LIMIT 1000"

    with get_db_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    report = LearningReport()
    direction_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "wins": 0, "score": 0.0, "targets": [], "actuals": []}
    )
    signal_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "wins": 0, "score": 0.0, "targets": [], "actuals": []}
    )
    interval_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "wins": 0, "score": 0.0, "targets": [], "actuals": []}
    )
    all_scores: list[float] = []
    all_wins = 0
    target_deviations: list[float] = []

    for ai_str, outcome_str, chanlun_str, sym, intv, _ts, price in rows:
        outcome = safe_json_loads(outcome_str, {})
        if not _is_scorable_outcome(outcome):
            continue
        ai = safe_json_loads(ai_str, {})
        chanlun = safe_json_loads(chanlun_str, {}) if chanlun_str else {}

        scenario = extract_scenario_for_eval(ai, float(price or outcome.get("entry_price") or 0))
        direction = (
            outcome.get("direction")
            or (scenario.direction if scenario else "unknown")
            or "unknown"
        )
        target_pct = float(
            outcome.get("target_pct")
            or (scenario.target_pct if scenario else 0)
            or 0
        )
        hit_target = bool(outcome.get("hit_target", False))
        score = float(outcome.get("score", 0))
        max_favorable = float(outcome.get("max_favorable_move", 0))

        ctx = extract_structure_context(chanlun, ai)
        signal_type = ctx.get("signal_type", "none")

        report.total_predictions += 1
        all_scores.append(score)
        if hit_target:
            all_wins += 1

        for bucket, key in (
            (direction_data, str(direction)),
            (signal_data, signal_type),
            (interval_data, intv),
        ):
            bucket[key]["total"] += 1
            bucket[key]["score"] += score
            if hit_target:
                bucket[key]["wins"] += 1
        direction_data[str(direction)]["targets"].append(target_pct)
        direction_data[str(direction)]["actuals"].append(max_favorable)

        if target_pct > 0:
            target_deviations.append(target_pct - max_favorable)

    if report.total_predictions > 0:
        report.overall_win_rate = all_wins / report.total_predictions
        report.overall_avg_score = sum(all_scores) / len(all_scores)

    report.by_direction = _bucket_stats(direction_data, report.total_predictions)
    report.by_signal_type = _bucket_stats(signal_data, report.total_predictions)
    report.by_interval = _bucket_stats(interval_data, report.total_predictions)
    report.error_patterns = _identify_error_patterns(report, target_deviations)
    _generate_recommendations(report)
    report.confidence_adjustments = _calculate_confidence_adjustments(report)
    return report


def format_learning_prompt(
    report: LearningReport,
    *,
    current_direction: str | None = None,
    current_signal: str | None = None,
) -> str:
    if report.total_predictions < MIN_BUCKET_SAMPLES:
        return "【AI自我认知】\n历史可计分样本不足，暂不注入学习反馈。\n"

    lines = [
        "\n【AI自我认知 - 基于历史表现】",
        "-" * 50,
        "你最近的整体表现：",
        f"  - 总预测: {report.total_predictions} 次",
        f"  - 整体胜率: {report.overall_win_rate * 100:.1f}%",
        f"  - 平均得分: {report.overall_avg_score:.2f}/1.0",
        "\n你的方向预测表现：",
    ]
    dir_names = {"up": "看涨", "down": "看跌", "range": "震荡"}
    for direction, stats in report.by_direction.items():
        if stats.total >= MIN_BUCKET_SAMPLES:
            name = dir_names.get(direction, direction)
            mark = "✓" if stats.win_rate >= 0.25 else "✗"
            lines.append(f"  {mark} {name}: 胜率 {stats.win_rate * 100:.0f}% ({stats.total} 次)")
            if stats.target_deviation > 1.0:
                lines.append(f"      ⚠️ {name} 目标平均偏高 {stats.target_deviation:.1f}%")

    if report.error_patterns:
        lines.append("\n⚠️ 你的常见错误模式：")
        for pattern in report.error_patterns[:3]:
            lines.append(f"  - {pattern.description}")

    if current_direction:
        dir_stats = report.by_direction.get(current_direction)
        if dir_stats and dir_stats.has_enough_samples() and dir_stats.win_rate < 0.15:
            name = dir_names.get(current_direction, current_direction)
            lines.append(
                f"\n🚨 重要警告：你当前想预测 {name}，但历史胜率仅 {dir_stats.win_rate * 100:.0f}%！"
            )
            lines.append("   建议：降低概率或改为观望")

    if current_signal:
        sig_stats = report.by_signal_type.get(current_signal)
        if sig_stats and sig_stats.has_enough_samples() and sig_stats.win_rate < 0.15:
            lines.append(
                f"\n🚨 警告：当前信号类型 ({current_signal}) 历史胜率仅 {sig_stats.win_rate * 100:.0f}%"
            )

    lines.append("\n【基于以上历史表现，本次分析要求】")
    if report.overall_win_rate < 0.2:
        lines.append("1. 整体胜率很低，必须采用保守策略")
        lines.append("2. 概率不要超过 40%，目标幅度不要超过 1.5%")
    else:
        lines.append("1. 参考历史表现调整预测置信度")

    avg_actual = max((s.avg_actual_move for s in report.by_direction.values()), default=0.0)
    if avg_actual > 0:
        lines.append(f"3. 历史实际平均变动约 {avg_actual:.1f}%，目标不应超过 {avg_actual * 1.5:.1f}%")
    for rec in report.recommendations[:2]:
        lines.append(f"4. {rec}")
    lines.append("-" * 50)
    return "\n".join(lines)


def _stats_to_dict(stats: PerformanceStats) -> dict[str, Any]:
    return {
        "total": stats.total,
        "wins": stats.wins,
        "win_rate": round(stats.win_rate, 3),
        "avg_score": round(stats.avg_score, 3),
        "avg_target_pct": round(stats.avg_target_pct, 3),
        "avg_actual_move": round(stats.avg_actual_move, 3),
        "target_deviation": round(stats.target_deviation, 3),
    }


def build_learning_feedback_block(
    snapshot: ChanStructureSnapshot,
    *,
    context_match: dict[str, str] | None = None,
    days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    symbol = snapshot.meta.symbol
    interval = snapshot.meta.interval
    ctx = context_match or {}
    current_signal = ctx.get("signal_type")
    current_direction: str | None = None
    struct = snapshot.model_dump(mode="json")
    sig = struct.get("signal") or {}
    bsp = sig.get("buy_sell_points") or []
    if bsp:
        sl = str(bsp[0]).lower()
        if "buy" in sl:
            current_direction = "up"
        elif "sell" in sl:
            current_direction = "down"

    report = analyze_learning_feedback(days=days, symbol=symbol, interval=interval)
    has_data = report.total_predictions >= MIN_BUCKET_SAMPLES

    block: dict[str, Any] = {
        "has_data": has_data,
        "lookback_days": days,
        "total_predictions": report.total_predictions,
        "overall_win_rate": round(report.overall_win_rate, 3),
        "overall_avg_score": round(report.overall_avg_score, 3),
        "by_direction": {k: _stats_to_dict(v) for k, v in report.by_direction.items()},
        "by_signal_type": {k: _stats_to_dict(v) for k, v in report.by_signal_type.items()},
        "error_patterns": [asdict(p) for p in report.error_patterns],
        "strengths": report.strengths,
        "weaknesses": report.weaknesses,
        "recommendations": report.recommendations,
        "confidence_adjustments": report.confidence_adjustments,
        "prompt_text": format_learning_prompt(
            report,
            current_direction=current_direction,
            current_signal=current_signal,
        ),
    }
    if not has_data:
        block["message"] = f"可计分样本不足（需要至少 {MIN_BUCKET_SAMPLES} 条）"
    return block
