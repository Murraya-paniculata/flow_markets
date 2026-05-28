"""预测结果回填：用未来 K 线评估 2.2 写入的快照（对齐 chanlun evaluate_outcome）。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.analysis_store.db_manager import get_db_conn, safe_json_dumps, safe_json_loads
from app.observability.logging import get_logger
from app.services.chan.kline import fetch_klines_raw, normalize_interval

logger = get_logger(__name__)

SLIPPAGE_PCT = 0.1

FUTURE_BARS_CONFIG: dict[str, int] = {
    "15m": 96,
    "1h": 48,
    "4h": 24,
    "1d": 10,
}

MIN_EVAL_KLINES = 5

_INTERVAL_MS: dict[str, int] = {
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
}


@dataclass
class ScenarioForEval:
    direction: str
    target_pct: float
    stop_pct: float
    source: str
    skip_reason: str | None = None


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
    if buy_sell_points or divergences:
        return "mixed"
    return "none"


def extract_structure_context(ai_json: dict, chanlun_json: dict | None = None) -> dict[str, Any]:
    """从结构 JSON / AI JSON 提取统计用上下文。"""
    context: dict[str, Any] = {
        "buy_sell_points": [],
        "divergences": [],
        "trend": "unknown",
        "price_position": "unknown",
        "strength_comparison": "unknown",
        "zg": 0,
        "zd": 0,
        "has_signal": False,
    }
    source = chanlun_json if chanlun_json else ai_json
    signal = source.get("signal", {}) if isinstance(source, dict) else {}
    context["buy_sell_points"] = signal.get("buy_sell_points", [])
    context["divergences"] = signal.get("divergences", [])
    context["has_signal"] = bool(context["buy_sell_points"] or context["divergences"])

    summary = source.get("structure_summary", {}) if isinstance(source, dict) else {}
    if summary:
        context["trend"] = summary.get("trend", "unknown")
        context["price_position"] = summary.get("price_position", "unknown")
        context["strength_comparison"] = summary.get("strength_comparison", "unknown")
        key_levels = summary.get("key_levels", {})
        if isinstance(key_levels, dict):
            context["zg"] = key_levels.get("zg", 0)
            context["zd"] = key_levels.get("zd", 0)

    v2 = ai_json.get("chanlun_v2") if isinstance(ai_json, dict) else None
    if not summary and v2:
        sj = v2.get("structure_judgement", {})
        zs = sj.get("zs", {}) if isinstance(sj, dict) else {}
        if isinstance(zs, dict):
            context["trend"] = sj.get("trend", context["trend"])
            context["price_position"] = sj.get("price_position", context["price_position"])
            context["zg"] = zs.get("zg", 0) or context["zg"]
            context["zd"] = zs.get("zd", 0) or context["zd"]

    context["signal_type"] = _classify_signal(
        context["buy_sell_points"], context["divergences"]
    )
    return context


def _pct_move(from_price: float, to_price: float) -> float:
    if from_price <= 0:
        return 0.0
    return abs(to_price - from_price) / from_price * 100.0


def extract_scenario_for_eval(
    ai_json: dict[str, Any],
    entry_price: float,
) -> ScenarioForEval | None:
    """从 deliverable / chanlun 旧 JSON 提取可评估的方向与目标/止损百分比。"""
    root = ai_json
    if "chanlun_v2" in ai_json or "brief" in ai_json:
        root = ai_json

    primary = root.get("primary_scenario")
    if not primary:
        scenarios = root.get("scenarios") or []
        primary = next((s for s in scenarios if s.get("rank") == 1), None)
    if primary:
        direction = str(primary.get("direction", "unknown")).lower()
        return ScenarioForEval(
            direction=direction,
            target_pct=float(primary.get("target_pct") or 0),
            stop_pct=float(primary.get("stop_pct") or 0),
            source="primary_scenario",
        )

    v2 = root.get("chanlun_v2")
    if not v2 or not isinstance(v2, dict):
        return None

    sm = v2.get("state_machine") or {}
    state = str(sm.get("current_state", "")).upper()
    if state == "OBSERVE_ONLY":
        return ScenarioForEval(
            direction="unknown",
            target_pct=0,
            stop_pct=0,
            source="chanlun_v2",
            skip_reason="observe_only",
        )

    active = sm.get("active_strategy") or {}
    direction = str(active.get("direction", "unknown")).lower()
    if direction not in ("up", "down"):
        return ScenarioForEval(
            direction=direction,
            target_pct=0,
            stop_pct=0,
            source="chanlun_v2",
            skip_reason=f"invalid_direction:{direction}",
        )

    exe = active.get("execution") or {}
    target_price = float(exe.get("target") or 0)
    stop_price = float(exe.get("stop_loss") or 0)
    if entry_price <= 0 or target_price <= 0 or stop_price <= 0:
        return ScenarioForEval(
            direction=direction,
            target_pct=0,
            stop_pct=0,
            source="chanlun_v2",
            skip_reason="missing_execution_prices",
        )

    target_pct = _pct_move(entry_price, target_price)
    stop_pct = _pct_move(entry_price, stop_price)
    return ScenarioForEval(
        direction=direction,
        target_pct=round(target_pct, 4),
        stop_pct=round(stop_pct, 4),
        source="chanlun_v2",
    )


def _calculate_enhanced_score(
    *,
    hit_target: bool,
    hit_stop: bool,
    direction: str,
    final_move: float,
    max_favorable_move: float,
    target_pct: float,
    hit_target_bar: int | None,
    total_bars: int,
    expected_rr: float = 0,
    actual_rr: float = 0,
) -> float:
    score = 0.0
    if hit_target and not hit_stop:
        score += 0.35
    elif hit_target and hit_stop:
        score += 0.2
    if direction == "up" and final_move > 0:
        score += 0.2
    elif direction == "down" and final_move < 0:
        score += 0.2
    if target_pct > 0:
        score += 0.2 * min(max_favorable_move / target_pct, 1.0)
    if hit_target_bar is not None and total_bars > 0:
        score += 0.15 * (1.0 - hit_target_bar / total_bars)
    if expected_rr > 0 and actual_rr > 0:
        if actual_rr > expected_rr * 1.2:
            score += 0.1
        elif actual_rr > expected_rr:
            score += 0.05
        elif actual_rr < expected_rr * 0.8:
            score -= 0.05
    return round(min(score, 1.0), 3)


def evaluate_outcome(
    ai_json: dict[str, Any],
    future_klines: list[dict[str, Any]],
    entry_price: float,
    chanlun_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """用未来 K 线评估预测结果（与 chanlun 核心规则一致）。"""
    if not future_klines or len(future_klines) < MIN_EVAL_KLINES:
        return {
            "error": "insufficient_klines",
            "evaluated_bars": len(future_klines) if future_klines else 0,
            "message": f"K线数据不足（至少需要{MIN_EVAL_KLINES}根）",
        }

    closes = [float(k["close"]) for k in future_klines]
    if max(closes) > 0 and min(closes) > 0 and max(closes) / min(closes) > 10:
        return {
            "error": "abnormal_price_movement",
            "evaluated_bars": len(future_klines),
            "message": "价格波动异常",
        }

    if entry_price <= 0:
        return {"error": "invalid_entry_price", "entry_price": entry_price}

    scenario = extract_scenario_for_eval(ai_json, entry_price)
    if scenario is None:
        return {
            "error": "no_evaluable_scenario",
            "evaluated_bars": len(future_klines),
        }
    if scenario.skip_reason:
        return {
            "error": scenario.skip_reason,
            "direction": scenario.direction,
            "evaluated_bars": len(future_klines),
            "outcome": "skipped",
            "score": 0.0,
        }

    direction = scenario.direction
    target_pct = scenario.target_pct
    stop_pct = scenario.stop_pct

    future_highs = [float(k["high"]) for k in future_klines]
    future_lows = [float(k["low"]) for k in future_klines]
    max_high = max(future_highs)
    min_low = min(future_lows)

    max_up_move = (max_high - entry_price) / entry_price * 100
    max_down_move = (min_low - entry_price) / entry_price * 100

    if direction == "up":
        effective_target = max(target_pct * (1 - SLIPPAGE_PCT / 100), 0)
        effective_stop = stop_pct * (1 + SLIPPAGE_PCT / 100)
        hit_target = max_up_move >= effective_target
        hit_stop = max_down_move <= -effective_stop
        max_favorable_move = round(max_up_move, 2)
        max_adverse_move = round(max_down_move, 2)
    elif direction == "down":
        effective_target = max(target_pct * (1 - SLIPPAGE_PCT / 100), 0)
        effective_stop = stop_pct * (1 + SLIPPAGE_PCT / 100)
        hit_target = max_down_move <= -effective_target
        hit_stop = max_up_move >= effective_stop
        max_favorable_move = round(-max_down_move, 2)
        max_adverse_move = round(max_up_move, 2)
    else:
        hit_target = False
        hit_stop = False
        max_favorable_move = round(max(abs(max_up_move), abs(max_down_move)), 2)
        max_adverse_move = round(min(abs(max_up_move), abs(max_down_move)), 2)

    final_close = closes[-1]
    final_move = (final_close - entry_price) / entry_price * 100

    if direction in ("up", "down"):
        if hit_target and not hit_stop:
            score = 1.0
            outcome = "success"
        elif hit_stop:
            score = 0.0
            outcome = "stopped"
        elif (direction == "up" and final_move > 0) or (direction == "down" and final_move < 0):
            score = 0.5
            outcome = "partial"
        else:
            score = 0.0
            outcome = "failed"
    else:
        score = 0.0
        outcome = "no_direction"

    structure_context = extract_structure_context(ai_json, chanlun_json)
    hit_target_bar: int | None = None
    hit_stop_bar: int | None = None

    for i, k in enumerate(future_klines):
        high = float(k["high"])
        low = float(k["low"])
        if direction == "up":
            k_up = (high - entry_price) / entry_price * 100
            k_down = (low - entry_price) / entry_price * 100
            if hit_target_bar is None and k_up >= target_pct:
                hit_target_bar = i + 1
            if hit_stop_bar is None and k_down <= -stop_pct:
                hit_stop_bar = i + 1
        elif direction == "down":
            k_up = (high - entry_price) / entry_price * 100
            k_down = (low - entry_price) / entry_price * 100
            if hit_target_bar is None and k_down <= -target_pct:
                hit_target_bar = i + 1
            if hit_stop_bar is None and k_up >= stop_pct:
                hit_stop_bar = i + 1

    actual_rr = round(abs(max_favorable_move / max_adverse_move), 2) if max_adverse_move else 0
    expected_rr = round(target_pct / stop_pct, 2) if stop_pct > 0 else 0
    enhanced_score = _calculate_enhanced_score(
        hit_target=hit_target,
        hit_stop=hit_stop,
        direction=direction,
        final_move=final_move,
        max_favorable_move=max_favorable_move,
        target_pct=target_pct,
        hit_target_bar=hit_target_bar,
        total_bars=len(future_klines),
        expected_rr=expected_rr,
        actual_rr=actual_rr,
    )

    return {
        "direction": direction,
        "target_pct": target_pct,
        "stop_pct": stop_pct,
        "hit_target": hit_target,
        "hit_stop": hit_stop,
        "max_favorable_move": max_favorable_move,
        "max_adverse_move": max_adverse_move,
        "final_move": round(final_move, 2),
        "evaluated_bars": len(future_klines),
        "entry_price": entry_price,
        "final_price": round(final_close, 4),
        "max_high": max_high,
        "min_low": min_low,
        "score": score,
        "enhanced_score": enhanced_score,
        "outcome": outcome,
        "hit_target_bar": hit_target_bar,
        "hit_stop_bar": hit_stop_bar,
        "actual_rr": actual_rr,
        "expected_rr": expected_rr,
        "structure_context": structure_context,
        "scenario_source": scenario.source,
        "scoring_mode": "target_based",
        "best_score": enhanced_score,
        "signal_type": structure_context.get("signal_type", "none"),
    }


def fetch_pending_records(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        """
        SELECT id, symbol, interval, timestamp, price, ai_json, chanlun_json
        FROM analysis_snapshot
        WHERE evaluated = 0 AND ai_json IS NOT NULL
        ORDER BY id ASC
        """
    ).fetchall()


def mark_as_evaluated(conn: sqlite3.Connection, record_id: int, outcome_json: dict) -> None:
    conn.execute(
        """
        UPDATE analysis_snapshot
        SET outcome_json = ?, evaluated = 1
        WHERE id = ?
        """,
        (safe_json_dumps(outcome_json), record_id),
    )


@dataclass
class EvaluateRunResult:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    details: list[str] | None = None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch_klines_after_analysis(
    symbol: str,
    interval: str,
    analysis_time: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    """从分析时刻起拉未来 K 线；startTime 无数据时回退为最近 K 线再按 open_time 过滤。"""
    interval_norm = normalize_interval(interval)
    analysis_time = _ensure_utc(analysis_time)
    start_ms = int(analysis_time.timestamp() * 1000)
    klines = fetch_klines_raw(
        symbol, interval_norm, limit=limit, start_time=start_ms
    )
    if len(klines) >= MIN_EVAL_KLINES:
        return klines

    step = _INTERVAL_MS.get(interval_norm, 60 * 60_000)
    klines = fetch_klines_raw(
        symbol, interval_norm, limit=limit, start_time=max(0, start_ms - step)
    )
    klines = [k for k in klines if _ensure_utc(k["open_time"]) >= analysis_time]
    if len(klines) >= MIN_EVAL_KLINES:
        return klines

    recent = fetch_klines_raw(symbol, interval_norm, limit=min(limit, 500))
    return [k for k in recent if _ensure_utc(k["open_time"]) >= analysis_time]


def evaluate_pending_snapshots(
    *,
    snapshot_id: int | None = None,
    future_bars_override: dict[str, int] | None = None,
    min_required_bars: int | None = None,
    dry_run: bool = False,
) -> EvaluateRunResult:
    """回填所有（或指定）待评估快照。"""
    bars_cfg = {**FUTURE_BARS_CONFIG, **(future_bars_override or {})}
    result = EvaluateRunResult(details=[])

    with get_db_conn() as conn:
        rows = fetch_pending_records(conn)
        if snapshot_id is not None:
            rows = [r for r in rows if r[0] == snapshot_id]

        for row in rows:
            record_id, symbol, interval, timestamp_str, entry_price, ai_json_str, chanlun_str = row
            line_prefix = f"#{record_id} {symbol}@{interval}"

            if dry_run:
                result.details.append(f"[dry-run] would evaluate {line_prefix}")
                continue

            try:
                ai_json = safe_json_loads(ai_json_str, {})
                chanlun_json = safe_json_loads(chanlun_str, {}) if chanlun_str else {}
            except Exception as exc:
                result.failed += 1
                result.details.append(f"{line_prefix} json error: {exc}")
                continue

            try:
                analysis_time = _ensure_utc(datetime.fromisoformat(timestamp_str))
            except ValueError as exc:
                result.failed += 1
                result.details.append(f"{line_prefix} bad timestamp: {exc}")
                continue

            interval_norm = normalize_interval(interval)
            future_bars = bars_cfg.get(interval_norm, 50)
            required = min_required_bars if min_required_bars is not None else future_bars

            binance_symbol = symbol.replace("/", "").replace("-", "")

            try:
                klines = fetch_klines_after_analysis(
                    binance_symbol,
                    interval_norm,
                    analysis_time,
                    future_bars,
                )
            except Exception as exc:
                result.failed += 1
                result.details.append(f"{line_prefix} klines error: {exc}")
                continue

            if len(klines) < required:
                outcome = {
                    "error": "insufficient_data",
                    "error_message": f"K线数量不足（{len(klines)}/{required}）",
                    "evaluated_bars": len(klines),
                    "required_bars": required,
                    "score": 0.0,
                    "outcome": "failed",
                }
                mark_as_evaluated(conn, record_id, outcome)
                result.failed += 1
                result.details.append(f"{line_prefix} insufficient klines {len(klines)}/{required}")
                continue

            outcome = evaluate_outcome(ai_json, klines, float(entry_price), chanlun_json)
            mark_as_evaluated(conn, record_id, outcome)

            if outcome.get("outcome") == "skipped" or outcome.get("error") in (
                "observe_only",
                "no_evaluable_scenario",
            ):
                result.skipped += 1
                result.details.append(f"{line_prefix} skipped: {outcome.get('error')}")
            elif "error" in outcome:
                result.failed += 1
                result.details.append(f"{line_prefix} error: {outcome.get('error')}")
            else:
                result.success += 1
                result.details.append(
                    f"{line_prefix} {outcome.get('outcome')} "
                    f"hit={outcome.get('hit_target')} score={outcome.get('score')}"
                )

    return result
