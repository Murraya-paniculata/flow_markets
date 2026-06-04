"""分析库查询与统计 CLI 逻辑（Phase 4.3，对标 chanlun query_stats.py）。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.analysis_store.db_manager import get_db_conn, get_db_path, safe_json_loads
from app.analysis_store.signal_classifier import extract_direction_from_ai
from app.analysis_store.stats_formatter import (
    _POSITION_ZH,
    _SIGNAL_ZH,
    _TREND_ZH,
    format_enhanced_report,
)
from app.analysis_store.stats_service import (
    StatsService,
    extract_structure_context_from_record,
    is_scorable_outcome,
)

_STRENGTH_ZH = {
    "weakening": "力度衰竭",
    "strengthening": "力度增强",
    "similar": "力度相近",
    "unknown": "未知",
}
_DIRECTION_ZH = {"up": "看涨", "down": "看跌", "unknown": "未知"}
_OUTCOME_ZH = {
    "success": "成功命中",
    "partial": "部分正确",
    "stopped": "止损出局",
    "failed": "方向错误",
    "unknown": "未知",
    "no_direction": "无方向",
}
_QUALITY_ZH = {
    "A": "A-优质",
    "B": "B-良好",
    "C": "C-一般",
    "D": "D-低质",
    "unknown": "未评级",
}
_ACTION_ZH = {
    "trade": "建议交易",
    "wait": "建议观望",
    "skip": "建议跳过",
    "": "无建议",
}

STATS_CSV_COLUMNS = [
    "ID",
    "交易对",
    "周期",
    "分析时间",
    "入场价格",
    "方向",
    "状态机",
    "目标(%)",
    "止损(%)",
    "命中目标",
    "触发止损",
    "结果类型",
    "得分",
    "增强得分",
    "最终价格",
    "最终变动(%)",
    "最大有利变动(%)",
    "最大不利变动(%)",
    "实际盈亏比",
    "命中K线位置",
    "评估K线数",
    "最高价",
    "最低价",
    "趋势类型",
    "价格位置",
    "力度对比",
    "信号类型",
    "有无信号",
    "brief摘要",
    "信号质量评级",
    "信号质量得分",
    "建议动作",
]


def print_db_overview() -> None:
    db = get_db_path().resolve()
    print("=" * 72)
    print("FlowMarkets 分析统计（query_analysis_stats）")
    print("=" * 72)
    print(f"数据库: {db}")
    with get_db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM analysis_snapshot").fetchone()[0]
        evaluated = conn.execute(
            "SELECT COUNT(*) FROM analysis_snapshot WHERE evaluated = 1"
        ).fetchone()[0]
        scorable = 0
        for (raw,) in conn.execute(
            "SELECT outcome_json FROM analysis_snapshot WHERE evaluated = 1"
        ).fetchall():
            if is_scorable_outcome(safe_json_loads(raw)):
                scorable += 1
    print(f"快照总数: {total}  |  已评估: {evaluated}  |  可计分: {scorable}")
    if scorable == 0:
        print(
            "\n提示: 尚无可用统计样本。流程: analyze --save → evaluate_outcomes → 再运行本工具"
        )
    print()


def _where_symbol_interval(
    symbol: str | None, interval: str | None
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    if interval:
        clauses.append("interval = ?")
        params.append(interval)
    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params


def print_snapshots(
    limit: int = 10,
    *,
    symbol: str | None = None,
    interval: str | None = None,
) -> None:
    where, params = _where_symbol_interval(symbol, interval)
    sql = f"""
        SELECT id, symbol, interval, timestamp, price,
               CASE WHEN ai_json IS NOT NULL THEN '是' ELSE '否' END
        FROM analysis_snapshot
        WHERE 1=1{where}
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(limit)
    with get_db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    print("\n【最近分析快照】")
    print("=" * 90)
    print(f"{'ID':<6} {'交易对':<14} {'周期':<8} {'时间':<28} {'价格':<12} {'AI'}")
    print("-" * 90)
    if not rows:
        print("（暂无数据）")
    else:
        for sid, sym, intv, ts, price, has_ai in rows:
            print(
                f"{sid:<6} {sym:<14} {intv:<8} {str(ts)[:28]:<28} "
                f"{float(price):<12.2f} {has_ai}"
            )
    print()


def print_outcomes(
    limit: int = 10,
    *,
    symbol: str | None = None,
    interval: str | None = None,
) -> None:
    where, params = _where_symbol_interval(symbol, interval)
    sql = f"""
        SELECT id, symbol, interval, price, outcome_json
        FROM analysis_snapshot
        WHERE evaluated = 1 AND outcome_json IS NOT NULL{where}
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(limit)
    with get_db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    print("\n【最近评估结果】")
    print("=" * 110)
    print(
        f"{'ID':<6} {'交易对':<14} {'周期':<8} {'K线数':<8} {'起始价':<10} "
        f"{'最高价':<10} {'最低价':<10} {'方向':<8} {'命中':<8}"
    )
    print("-" * 110)
    if not rows:
        print("（暂无数据）")
    else:
        for sid, sym, intv, price, outcome_str in rows:
            outcome = safe_json_loads(outcome_str, {})
            direction = outcome.get("direction", "unknown")
            direction_cn = _DIRECTION_ZH.get(direction, direction)
            evaluated_bars = outcome.get("evaluated_bars", 0)
            entry_price = outcome.get("entry_price", price)
            max_high = outcome.get("max_high", entry_price)
            min_low = outcome.get("min_low", entry_price)
            hit_str = "是" if outcome.get("hit_target") else "否"
            print(
                f"{sid:<6} {sym:<14} {intv:<8} {evaluated_bars:<8} "
                f"{float(entry_price):<10.2f} {float(max_high):<10.2f} "
                f"{float(min_low):<10.2f} {direction_cn:<8} {hit_str:<8}"
            )
    print()


def _print_bucket_section(
    title: str,
    rows: list[tuple],
    label_map: dict[str, str],
    *,
    sort_order: dict[str, int] | None = None,
) -> None:
    if not rows:
        return
    if sort_order:
        rows = sorted(rows, key=lambda x: sort_order.get(x[0], 99))
    print(f"\n{title}")
    print(f"  {'分类':<12} {'样本':<10} {'命中':<8} {'胜率':<10} {'均分'}")
    print("  " + "-" * 52)
    for key, total_n, hit_n, avg_score in rows:
        acc = (hit_n / total_n * 100) if total_n > 0 else 0
        label = label_map.get(key, key)[:12]
        print(f"  {label:<12} {total_n:<10} {hit_n:<8} {acc:>6.1f}%   {avg_score:.3f}")


def print_accuracy_report(
    *,
    symbol: str | None = None,
    interval: str | None = None,
) -> None:
    """增强准确率报表 = format_enhanced_report + 方向/标的/周期/结果类型。"""
    svc = StatsService()
    stats = svc.full_report(symbol=symbol, interval=interval)

    if symbol or interval:
        filt = []
        if symbol:
            filt.append(f"标的={symbol}")
        if interval:
            filt.append(f"周期={interval}")
        print(f"\n（筛选: {', '.join(filt)}）")

    print(format_enhanced_report(stats))

    total = stats.get("total", 0)
    if total == 0:
        return

    hit_count = stats.get("hit_count", 0)
    stop_count = stats.get("stop_count", 0)
    accuracy = hit_count / total * 100 if total > 0 else 0
    stop_rate = stop_count / total * 100 if total > 0 else 0

    print("\n【补充】按预测方向 / 交易对 / 周期")
    print("-" * 70)
    print(f"  总样本: {total}  命中: {hit_count} ({accuracy:.1f}%)  止损: {stop_count} ({stop_rate:.1f}%)")
    print(f"  平均得分: {stats.get('avg_score', 0):.3f}  增强得分: {stats.get('avg_enhanced_score', 0):.3f}")

    if stats.get("by_outcome"):
        print("\n【按结果类型】")
        for outcome_type, count in sorted(
            stats["by_outcome"], key=lambda x: x[1], reverse=True
        ):
            pct = count / total * 100 if total > 0 else 0
            name = _OUTCOME_ZH.get(outcome_type, outcome_type)
            print(f"  {name:<20} {count:>4} ({pct:>5.1f}%)")

    _print_bucket_section(
        "\n【按预测方向】",
        stats.get("by_direction", []),
        _DIRECTION_ZH,
    )
    _print_bucket_section(
        "\n【按交易对】",
        stats.get("by_symbol", []),
        {},
    )
    _print_bucket_section(
        "\n【按时间周期】",
        stats.get("by_interval", []),
        {},
    )


def _row_for_stats_csv(
    snapshot_id: int,
    symbol: str,
    interval: str,
    timestamp: str,
    price: float,
    ai: dict[str, Any],
    outcome: dict[str, Any],
    chanlun: dict[str, Any],
) -> dict[str, Any] | None:
    if not is_scorable_outcome(outcome):
        return None

    ctx = extract_structure_context_from_record(chanlun, ai, outcome)
    v2 = ai.get("chanlun_v2") or {}
    sm = v2.get("state_machine") or {}
    active = sm.get("active_strategy") or {}
    exec_ = active.get("execution") or {}
    meta = v2.get("meta") or {}
    entry = float(outcome.get("entry_price") or price or meta.get("price") or 0)
    target_pct = float(outcome.get("target_pct") or 0)
    stop_pct = float(outcome.get("stop_pct") or 0)
    if entry > 0 and exec_.get("target") and exec_.get("stop_loss"):
        try:
            target_pct = abs(float(exec_["target"]) - entry) / entry * 100
            stop_pct = abs(float(exec_["stop_loss"]) - entry) / entry * 100
        except (TypeError, ValueError):
            pass

    quality = ai.get("signal_quality") or {}
    direction = extract_direction_from_ai(ai, outcome)
    brief = (ai.get("brief") or {}).get("summary", "") or ""

    return {
        "ID": snapshot_id,
        "交易对": symbol,
        "周期": interval,
        "分析时间": timestamp,
        "入场价格": entry,
        "方向": _DIRECTION_ZH.get(direction, direction),
        "状态机": sm.get("current_state", ""),
        "目标(%)": round(target_pct, 4),
        "止损(%)": round(stop_pct, 4),
        "命中目标": "是" if outcome.get("hit_target") else "否",
        "触发止损": "是" if outcome.get("hit_stop") else "否",
        "结果类型": _OUTCOME_ZH.get(outcome.get("outcome", "unknown"), outcome.get("outcome")),
        "得分": outcome.get("score", 0),
        "增强得分": outcome.get("enhanced_score", outcome.get("score", 0)),
        "最终价格": outcome.get("final_price", 0),
        "最终变动(%)": outcome.get("final_move", 0),
        "最大有利变动(%)": outcome.get("max_favorable_move", 0),
        "最大不利变动(%)": outcome.get("max_adverse_move", 0),
        "实际盈亏比": outcome.get("actual_rr", 0),
        "命中K线位置": outcome.get("hit_target_bar", ""),
        "评估K线数": outcome.get("evaluated_bars", 0),
        "最高价": outcome.get("max_high", 0),
        "最低价": outcome.get("min_low", 0),
        "趋势类型": _TREND_ZH.get(ctx.get("trend", "unknown"), ctx.get("trend")),
        "价格位置": _POSITION_ZH.get(ctx.get("price_position", "unknown"), ctx.get("price_position")),
        "力度对比": _STRENGTH_ZH.get(
            ctx.get("strength_comparison", "unknown"), ctx.get("strength_comparison")
        ),
        "信号类型": _SIGNAL_ZH.get(ctx.get("signal_type", "none"), ctx.get("signal_type")),
        "有无信号": "是" if ctx.get("has_signal") else "否",
        "brief摘要": brief[:120],
        "信号质量评级": _QUALITY_ZH.get(quality.get("grade", "unknown"), quality.get("grade")),
        "信号质量得分": quality.get("total_score", ""),
        "建议动作": _ACTION_ZH.get(quality.get("action", ""), quality.get("action", "")),
    }


def export_stats_csv(
    path: Path,
    *,
    symbol: str | None = None,
    interval: str | None = None,
) -> int:
    where, params = _where_symbol_interval(symbol, interval)
    sql = f"""
        SELECT id, symbol, interval, timestamp, price, ai_json, outcome_json, chanlun_json
        FROM analysis_snapshot
        WHERE evaluated = 1 AND outcome_json IS NOT NULL{where}
        ORDER BY timestamp ASC
    """
    with get_db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    csv_rows: list[dict[str, Any]] = []
    for row in rows:
        sid, sym, intv, ts, price, ai_str, outcome_str, chanlun_str = row
        ai = safe_json_loads(ai_str, {})
        outcome = safe_json_loads(outcome_str, {})
        chanlun = safe_json_loads(chanlun_str, {})
        built = _row_for_stats_csv(
            int(sid), str(sym), str(intv), str(ts), float(price), ai, outcome, chanlun
        )
        if built:
            csv_rows.append(built)

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STATS_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"[OK] 已导出 {len(csv_rows)} 条可计分记录 → {path}")
    return len(csv_rows)
