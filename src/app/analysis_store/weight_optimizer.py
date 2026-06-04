"""信号质量六维权重优化（Phase 4.5，移植 chanlun/weight_optimizer.py）。"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.analysis_store.signal_classifier import classify_signal, extract_direction_from_ai
from app.analysis_store.signal_quality import (
    DEFAULT_WEIGHTS,
    _target_stop_pct_from_ai,
    _weights_path,
    reload_weights,
    score_history_winrate,
    score_price_position,
    score_signal_type,
    score_strength_divergence,
    score_trend_consistency,
    score_volatility,
)
from app.analysis_store.stats_service import EvaluatedRecord, StatsService

OptimizeMethod = Literal["correlation", "predictive", "mixed"]

DIM_NAMES: dict[str, str] = {
    "signal_type": "信号类型",
    "trend": "趋势一致性",
    "position": "价格位置",
    "strength": "力度背驰",
    "history": "历史胜率",
    "risk_reward": "盈亏比",
}

MIN_SAMPLES_HARD = 20
MIN_SAMPLES_RECOMMENDED = 50


@dataclass
class DimensionStats:
    name: str
    total_samples: int = 0
    high_score_samples: int = 0
    high_score_wins: int = 0
    low_score_samples: int = 0
    low_score_wins: int = 0
    correlation: float = 0.0
    predictive_power: float = 0.0
    scores: list[float] = field(default_factory=list)
    outcomes: list[int] = field(default_factory=list)


def dimension_ratios_for_record(
    chanlun_json: dict[str, Any],
    ai_json: dict[str, Any],
    *,
    history_ratio: float | None = None,
) -> dict[str, float]:
    """各维度 0–1 归一化得分（与 signal_quality 规则一致，max_score=1）。"""
    source = chanlun_json if chanlun_json else ai_json
    signal = source.get("signal", {}) if isinstance(source, dict) else {}
    summary = source.get("structure_summary", {}) if isinstance(source, dict) else {}

    buy_sell_points = signal.get("buy_sell_points", [])
    divergences = signal.get("divergences", [])
    trend = summary.get("trend", "unknown")
    position = summary.get("price_position", "unknown")
    strength = summary.get("strength_comparison", "unknown")

    direction = extract_direction_from_ai(ai_json)
    target_pct, stop_pct = _target_stop_pct_from_ai(ai_json)
    signal_type = classify_signal(buy_sell_points, divergences)
    has_divergence = bool(divergences)

    if history_ratio is None:
        hist_score, _ = score_history_winrate(signal_type, direction, max_score=1.0)
        history_ratio = hist_score

    return {
        "signal_type": score_signal_type(signal_type, direction, max_score=1.0)[0],
        "trend": score_trend_consistency(trend, direction, max_score=1.0)[0],
        "position": score_price_position(position, direction, max_score=1.0)[0],
        "strength": score_strength_divergence(strength, has_divergence, direction, max_score=1.0)[0],
        "history": history_ratio,
        "risk_reward": score_volatility(target_pct, stop_pct, max_score=1.0)[0],
    }


def _record_to_training_row(record: EvaluatedRecord) -> dict[str, Any] | None:
    try:
        direction = extract_direction_from_ai(record.ai) or record.outcome.get("direction", "unknown")
        if direction not in ("up", "down"):
            return None
        dim_scores = dimension_ratios_for_record(
            record.chanlun,
            record.ai,
            history_ratio=0.5,
        )
        return {
            "dim_scores": dim_scores,
            "hit_target": bool(record.outcome.get("hit_target")),
            "score": float(record.outcome.get("score", 0)),
            "direction": direction,
        }
    except Exception:
        return None


class WeightOptimizer:
    """基于可计分历史记录优化六维权重。"""

    def __init__(
        self,
        *,
        symbol: str | None = None,
        interval: str | None = None,
        limit: int = 2000,
    ) -> None:
        self.symbol = symbol
        self.interval = interval
        self.limit = limit
        self.records: list[dict[str, Any]] = []
        self.dimension_stats: dict[str, DimensionStats] = {}

    def load_historical_data(self) -> int:
        svc = StatsService()
        rows = svc.fetch_evaluated_records(symbol=self.symbol, interval=self.interval)
        if self.limit > 0:
            rows = rows[: self.limit]

        self.records = []
        for rec in rows:
            row = _record_to_training_row(rec)
            if row:
                self.records.append(row)

        return len(self.records)

    @staticmethod
    def _pearson(x: list[float], y: list[int]) -> float:
        n = len(x)
        if n < 10:
            return 0.0
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        sq_x = sum((xi - mean_x) ** 2 for xi in x)
        sq_y = sum((yi - mean_y) ** 2 for yi in y)
        denom = math.sqrt(sq_x * sq_y)
        if denom == 0:
            return 0.0
        return num / denom

    def analyze_dimensions(self) -> dict[str, DimensionStats]:
        if not self.records:
            return {}

        self.dimension_stats = {dim: DimensionStats(name=dim) for dim in DEFAULT_WEIGHTS}

        for rec in self.records:
            hit = 1 if rec["hit_target"] else 0
            for dim, score in rec["dim_scores"].items():
                stats = self.dimension_stats[dim]
                stats.total_samples += 1
                stats.scores.append(float(score))
                stats.outcomes.append(hit)
                if score >= 0.7:
                    stats.high_score_samples += 1
                    if hit:
                        stats.high_score_wins += 1
                elif score <= 0.5:
                    stats.low_score_samples += 1
                    if hit:
                        stats.low_score_wins += 1

        for stats in self.dimension_stats.values():
            high_wr = (
                stats.high_score_wins / stats.high_score_samples
                if stats.high_score_samples > 5
                else 0.5
            )
            low_wr = (
                stats.low_score_wins / stats.low_score_samples
                if stats.low_score_samples > 5
                else 0.5
            )
            stats.predictive_power = high_wr - low_wr
            stats.correlation = self._pearson(stats.scores, stats.outcomes)

        return self.dimension_stats

    def calculate_optimal_weights(self, method: OptimizeMethod = "correlation") -> dict[str, float]:
        if not self.dimension_stats:
            self.analyze_dimensions()
        if not self.dimension_stats:
            return DEFAULT_WEIGHTS.copy()

        raw_weights: dict[str, float] = {}
        for dim, stats in self.dimension_stats.items():
            if method == "correlation":
                raw_weights[dim] = max(0.01, abs(stats.correlation))
            elif method == "predictive":
                raw_weights[dim] = max(0.01, stats.predictive_power + 0.1)
            else:
                raw_weights[dim] = max(
                    0.01,
                    abs(stats.correlation) * 0.5 + stats.predictive_power * 0.5 + 0.05,
                )

        total = sum(raw_weights.values())
        if total == 0:
            return DEFAULT_WEIGHTS.copy()

        optimal = {dim: max(5.0, round((raw / total) * 100, 1)) for dim, raw in raw_weights.items()}
        diff = 100 - sum(optimal.values())
        if diff != 0:
            max_dim = max(optimal, key=optimal.get)
            optimal[max_dim] = round(optimal[max_dim] + diff, 1)
        return optimal

    def generate_report(self) -> str:
        if not self.dimension_stats:
            self.analyze_dimensions()

        lines = [
            "",
            "=" * 70,
            "  FlowMarkets · 信号质量权重优化分析报告",
            "=" * 70,
            f"\n  分析样本数: {len(self.records)} 条可计分记录",
        ]
        if self.records:
            wins = sum(1 for r in self.records if r["hit_target"])
            lines.append(f"  整体命中率: {wins / len(self.records) * 100:.1f}%")

        lines.extend(
            [
                "\n" + "-" * 70,
                "  【各维度预测力分析】",
                "-" * 70,
                f"  {'维度':<12} {'高分命中':<12} {'低分命中':<12} {'预测力':<10} {'相关系数':<10}",
                "  " + "-" * 58,
            ]
        )

        for dim, stats in sorted(
            self.dimension_stats.items(),
            key=lambda x: abs(x[1].correlation),
            reverse=True,
        ):
            high_wr = (
                stats.high_score_wins / stats.high_score_samples
                if stats.high_score_samples
                else 0.0
            )
            low_wr = (
                stats.low_score_wins / stats.low_score_samples if stats.low_score_samples else 0.0
            )
            lines.append(
                f"  {DIM_NAMES.get(dim, dim):<12} {high_wr * 100:>6.1f}%      {low_wr * 100:>6.1f}%      "
                f"{stats.predictive_power:>+6.1%}    {stats.correlation:>+6.3f}"
            )

        lines.extend(["\n" + "-" * 70, "  【权重优化建议】", "-" * 70])
        optimal_corr = self.calculate_optimal_weights("correlation")
        optimal_pred = self.calculate_optimal_weights("predictive")
        lines.append(f"  {'维度':<12} {'当前':<10} {'相关性法':<10} {'预测力法':<10}")
        lines.append("  " + "-" * 44)
        for dim in DEFAULT_WEIGHTS:
            lines.append(
                f"  {DIM_NAMES.get(dim, dim):<12} {DEFAULT_WEIGHTS[dim]:>6.0f}     "
                f"{optimal_corr.get(dim, 0):>6.1f}     {optimal_pred.get(dim, 0):>6.1f}"
            )

        sorted_dims = sorted(
            self.dimension_stats.items(),
            key=lambda x: abs(x[1].correlation),
            reverse=True,
        )
        if sorted_dims:
            best, worst = sorted_dims[0], sorted_dims[-1]
            lines.extend(
                [
                    "\n" + "-" * 70,
                    "  【优化建议】",
                    "-" * 70,
                    f"  最强预测维度: {DIM_NAMES.get(best[0], best[0])} (r={best[1].correlation:+.3f})",
                    f"  最弱预测维度: {DIM_NAMES.get(worst[0], worst[0])} (r={worst[1].correlation:+.3f})",
                    "\n" + "=" * 70,
                ]
            )
        return "\n".join(lines)

    def save_optimized_weights(
        self,
        method: OptimizeMethod = "correlation",
        *,
        path: Path | None = None,
    ) -> Path:
        optimal = self.calculate_optimal_weights(method)
        out_path = path or _weights_path()
        config = {
            "version": "1.0",
            "method": method,
            "sample_count": len(self.records),
            "weights": optimal,
            "default_weights": DEFAULT_WEIGHTS,
            "dimension_stats": {
                dim: {
                    "correlation": round(st.correlation, 4),
                    "predictive_power": round(st.predictive_power, 4),
                    "high_score_hit_rate": round(
                        st.high_score_wins / st.high_score_samples
                        if st.high_score_samples > 0
                        else 0,
                        4,
                    ),
                    "low_score_hit_rate": round(
                        st.low_score_wins / st.low_score_samples if st.low_score_samples > 0 else 0,
                        4,
                    ),
                }
                for dim, st in self.dimension_stats.items()
            },
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        reload_weights()
        return out_path.resolve()


def run_weight_optimization(
    *,
    save: bool = False,
    method: OptimizeMethod = "correlation",
    symbol: str | None = None,
    interval: str | None = None,
    min_samples: int = MIN_SAMPLES_HARD,
) -> tuple[int, str, Path | None]:
    """执行优化流程。返回 (样本数, 报告文本, 保存路径或 None)。"""
    optimizer = WeightOptimizer(symbol=symbol, interval=interval)
    count = optimizer.load_historical_data()

    if count < min_samples:
        msg = (
            f"样本太少（{count} 条可计分记录），至少需要 {min_samples} 条才能优化权重。"
        )
        return count, msg, None

    optimizer.analyze_dimensions()
    report = optimizer.generate_report()

    saved: Path | None = None
    if save:
        saved = optimizer.save_optimized_weights(method)

    return count, report, saved
