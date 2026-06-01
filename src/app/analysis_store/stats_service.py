"""分析库统计（Phase 4.2：StatsService，移植 chanlun query_stats + stats_enhanced）。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.analysis_store.db_manager import get_db_conn, safe_json_loads
from app.analysis_store.outcome import extract_structure_context
from app.analysis_store.signal_classifier import classify_signal, extract_direction_from_ai

# 兼容旧代码：4 元组 (key, total, hits, avg_score)
LegacyBucketTuple = tuple[str, int, int, float]
# 增强：5 元组含显式胜率
BucketTuple = tuple[str, int, int, float, float]


@dataclass
class EvaluatedRecord:
    id: int
    symbol: str
    interval: str
    price: float
    ai: dict[str, Any]
    outcome: dict[str, Any]
    chanlun: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class BucketStat:
    key: str
    total: int
    hits: int
    win_rate: float
    avg_score: float
    avg_enhanced_score: float = 0.0

    def as_legacy_tuple(self) -> LegacyBucketTuple:
        return (self.key, self.total, self.hits, round(self.avg_score, 4))

    def as_tuple(self) -> BucketTuple:
        return (
            self.key,
            self.total,
            self.hits,
            round(self.win_rate, 4),
            round(self.avg_score, 4),
        )


def is_scorable_outcome(outcome: dict[str, Any]) -> bool:
    """排除纯错误回填，避免稀释胜率。"""
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


def extract_structure_context_from_record(
    chanlun_json: dict[str, Any],
    ai_json: dict[str, Any],
    outcome_json: dict[str, Any],
) -> dict[str, Any]:
    """与 chanlun query_stats.extract_structure_context 对齐。"""
    ctx = outcome_json.get("structure_context", {}) if outcome_json else {}
    if ctx and ctx.get("trend") != "unknown":
        source = chanlun_json if chanlun_json else ai_json
        signal = source.get("signal", {}) if source else {}
        bsp = signal.get("buy_sell_points", [])
        div = signal.get("divergences", [])
        if bsp or div or ctx.get("signal_type") in (None, "none", "unknown"):
            ctx = {
                **ctx,
                "signal_type": classify_signal(bsp, div),
                "has_signal": bool(bsp or div),
            }
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
        "signal_type": classify_signal(buy_sell_points, divergences),
        "has_signal": bool(buy_sell_points or divergences),
    }


def _accumulate(
    buckets: dict[str, dict[str, float]],
    key: str,
    *,
    hit: bool,
    score: float,
    enhanced_score: float,
) -> None:
    s = buckets.setdefault(
        key,
        {"total": 0, "hit": 0, "score": 0.0, "enhanced_score": 0.0},
    )
    s["total"] += 1
    s["score"] += score
    s["enhanced_score"] += enhanced_score
    if hit:
        s["hit"] += 1


def _finalize_buckets(
    buckets: dict[str, dict[str, float]],
    *,
    sort_order: dict[str, int] | None = None,
) -> list[BucketStat]:
    result: list[BucketStat] = []
    for key, s in buckets.items():
        total = int(s["total"])
        hits = int(s["hit"])
        win_rate = round(hits / total, 4) if total > 0 else 0.0
        result.append(
            BucketStat(
                key=key,
                total=total,
                hits=hits,
                win_rate=win_rate,
                avg_score=round(s["score"] / total, 4) if total > 0 else 0.0,
                avg_enhanced_score=round(s["enhanced_score"] / total, 4) if total > 0 else 0.0,
            )
        )
    if sort_order:
        result.sort(key=lambda b: sort_order.get(b.key, 99))
    else:
        result.sort(key=lambda b: b.total, reverse=True)
    return result


def _legacy_list(stats: list[BucketStat]) -> list[LegacyBucketTuple]:
    return [b.as_legacy_tuple() for b in stats]


class StatsService:
    """分析记忆库统计服务。"""

    def fetch_evaluated_records(
        self,
        *,
        symbol: str | None = None,
        interval: str | None = None,
    ) -> list[EvaluatedRecord]:
        query = """
            SELECT id, symbol, interval, price, ai_json, outcome_json, chanlun_json
            FROM analysis_snapshot
            WHERE evaluated = 1
              AND ai_json IS NOT NULL
              AND outcome_json IS NOT NULL
        """
        params: list[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if interval:
            query += " AND interval = ?"
            params.append(interval)

        with get_db_conn() as conn:
            rows = conn.execute(query, params).fetchall()

        records: list[EvaluatedRecord] = []
        for rid, sym, intv, price, ai_str, outcome_str, chanlun_str in rows:
            try:
                ai = safe_json_loads(ai_str, {})
                outcome = safe_json_loads(outcome_str, {})
                chanlun = safe_json_loads(chanlun_str, {})
            except Exception:
                continue
            if not is_scorable_outcome(outcome):
                continue
            ctx = extract_structure_context_from_record(chanlun, ai, outcome)
            records.append(
                EvaluatedRecord(
                    id=int(rid),
                    symbol=str(sym),
                    interval=str(intv),
                    price=float(price),
                    ai=ai,
                    outcome=outcome,
                    chanlun=chanlun,
                    context=ctx,
                )
            )
        return records

    def performance_metrics(self, records: list[EvaluatedRecord]) -> dict[str, Any]:
        if not records:
            return {}

        total = len(records)
        wins = sum(1 for r in records if r.outcome.get("hit_target"))
        stops = sum(1 for r in records if r.outcome.get("hit_stop"))
        total_score = sum(float(r.outcome.get("score", 0)) for r in records)
        total_enhanced = sum(
            float(r.outcome.get("enhanced_score", r.outcome.get("score", 0)))
            for r in records
        )
        rr_list = [
            float(r.outcome["actual_rr"])
            for r in records
            if float(r.outcome.get("actual_rr") or 0) > 0
        ]
        hit_bars = [
            int(r.outcome["hit_target_bar"])
            for r in records
            if r.outcome.get("hit_target_bar")
        ]

        return {
            "total": total,
            "wins": wins,
            "stops": stops,
            "win_rate": round(wins / total, 4) if total > 0 else 0.0,
            "stop_rate": round(stops / total, 4) if total > 0 else 0.0,
            "avg_score": round(total_score / total, 4) if total > 0 else 0.0,
            "avg_enhanced_score": round(total_enhanced / total, 4) if total > 0 else 0.0,
            "avg_actual_rr": round(sum(rr_list) / len(rr_list), 2) if rr_list else 0.0,
            "avg_hit_bars": round(sum(hit_bars) / len(hit_bars), 1) if hit_bars else 0.0,
        }

    def by_trend(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            key = rec.context.get("trend", "unknown")
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, key, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(
            buckets,
            sort_order={"up_trend": 0, "down_trend": 1, "consolidation": 2, "unknown": 3},
        )

    def by_position(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            key = rec.context.get("price_position", "unknown")
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, key, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(
            buckets,
            sort_order={"above_zs": 0, "inside_zs": 1, "below_zs": 2, "unknown": 3},
        )

    def by_signal_type(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            key = rec.context.get("signal_type", "none")
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, key, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(buckets)

    def by_strength(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            key = rec.context.get("strength_comparison", "unknown")
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, key, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(
            buckets,
            sort_order={
                "weakening": 0,
                "strengthening": 1,
                "similar": 2,
                "unknown": 3,
            },
        )

    def by_has_signal(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            key = "has_signal" if rec.context.get("has_signal") else "no_signal"
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, key, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(buckets)

    def by_signal_quality(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            quality = rec.ai.get("signal_quality") or {}
            grade = quality.get("grade", "unknown")
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, grade, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(
            buckets,
            sort_order={"A": 0, "B": 1, "C": 2, "D": 3, "unknown": 4},
        )

    def combo_signal_direction(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            sig = rec.context.get("signal_type", "unknown")
            direction = extract_direction_from_ai(rec.ai, rec.outcome)
            key = f"{sig}|{direction}"
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, key, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(buckets)

    def by_direction(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            key = str(rec.outcome.get("direction", "unknown"))
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, key, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(buckets)

    def by_symbol(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, rec.symbol, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(buckets)

    def by_interval(self, records: list[EvaluatedRecord]) -> list[BucketStat]:
        buckets: dict[str, dict[str, float]] = {}
        for rec in records:
            hit = bool(rec.outcome.get("hit_target"))
            score = float(rec.outcome.get("score", 0))
            enhanced = float(rec.outcome.get("enhanced_score", score))
            _accumulate(buckets, rec.interval, hit=hit, score=score, enhanced_score=enhanced)
        return _finalize_buckets(buckets)

    def by_outcome_type(self, records: list[EvaluatedRecord]) -> list[tuple[str, int]]:
        counts: dict[str, int] = defaultdict(int)
        for rec in records:
            counts[str(rec.outcome.get("outcome", "unknown"))] += 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)

    def history_buckets_for_scoring(self) -> dict[str, dict[str, dict[str, int]]]:
        """供 signal_quality 历史胜率维使用的缓存结构。"""
        records = self.fetch_evaluated_records()
        signal_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "wins": 0})
        trend_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "wins": 0})
        position_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "wins": 0})
        direction_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "wins": 0})
        combo_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "wins": 0})

        for rec in records:
            hit = bool(rec.outcome.get("hit_target"))
            ctx = rec.context
            signal_type = ctx.get("signal_type", "none")
            trend = ctx.get("trend", "unknown")
            position = ctx.get("price_position", "unknown")
            direction = extract_direction_from_ai(rec.ai, rec.outcome)
            combo_key = f"{signal_type}_{direction}"

            for bucket, key in (
                (signal_stats, signal_type),
                (trend_stats, trend),
                (position_stats, position),
                (direction_stats, direction),
                (combo_stats, combo_key),
            ):
                bucket[key]["total"] += 1
                if hit:
                    bucket[key]["wins"] += 1

        return {
            "signal": dict(signal_stats),
            "trend": dict(trend_stats),
            "position": dict(position_stats),
            "direction": dict(direction_stats),
            "combo": dict(combo_stats),
        }

    def full_report(
        self,
        *,
        symbol: str | None = None,
        interval: str | None = None,
    ) -> dict[str, Any]:
        """一次聚合全部统计（兼容 ``calculate_accuracy`` 返回形状并扩展）。"""
        records = self.fetch_evaluated_records(symbol=symbol, interval=interval)
        metrics = self.performance_metrics(records)

        by_direction = self.by_direction(records)
        by_symbol = self.by_symbol(records)
        by_interval = self.by_interval(records)
        by_trend = self.by_trend(records)
        by_position = self.by_position(records)
        by_signal = self.by_signal_type(records)
        by_strength = self.by_strength(records)
        by_has_signal = self.by_has_signal(records)
        by_quality = self.by_signal_quality(records)
        combo = self.combo_signal_direction(records)

        total = metrics.get("total", 0)
        return {
            "total": total,
            "hit_count": metrics.get("wins", 0),
            "stop_count": metrics.get("stops", 0),
            "win_rate": metrics.get("win_rate", 0.0),
            "stop_rate": metrics.get("stop_rate", 0.0),
            "avg_score": metrics.get("avg_score", 0.0),
            "avg_enhanced_score": metrics.get("avg_enhanced_score", 0.0),
            "avg_actual_rr": metrics.get("avg_actual_rr", 0.0),
            "avg_hit_bars": metrics.get("avg_hit_bars", 0.0),
            "by_direction": _legacy_list(by_direction),
            "by_symbol": _legacy_list(by_symbol),
            "by_interval": _legacy_list(by_interval),
            "by_outcome": self.by_outcome_type(records),
            "by_trend": _legacy_list(by_trend),
            "by_position": _legacy_list(by_position),
            "by_signal": _legacy_list(by_signal),
            "by_strength": _legacy_list(by_strength),
            "by_has_signal": _legacy_list(by_has_signal),
            "by_signal_quality": _legacy_list(by_quality),
            "combo_signal_direction": [b.as_tuple() for b in combo],
            "buckets": {
                "by_trend": [b.__dict__ for b in by_trend],
                "by_position": [b.__dict__ for b in by_position],
                "by_signal_type": [b.__dict__ for b in by_signal],
                "by_strength": [b.__dict__ for b in by_strength],
                "by_has_signal": [b.__dict__ for b in by_has_signal],
                "by_signal_quality": [b.__dict__ for b in by_quality],
                "combo_signal_direction": [
                    {
                        "signal_type": b.key.split("|", 1)[0],
                        "direction": b.key.split("|", 1)[-1],
                        **{k: v for k, v in b.__dict__.items() if k != "key"},
                    }
                    for b in combo
                ],
            },
        }


_default_service = StatsService()


def calculate_accuracy() -> dict[str, Any]:
    """聚合 evaluated=1 记录（兼容旧 API，委托 StatsService）。"""
    return _default_service.full_report()


def count_evaluated_samples() -> int:
    with get_db_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM analysis_snapshot WHERE evaluated = 1"
        ).fetchone()
    return int(row[0]) if row else 0


# 向后兼容别名
_is_scorable_outcome = is_scorable_outcome
