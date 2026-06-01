"""统计数据格式化为 Prompt / JSON（移植 chanlun stats_formatter）。"""

from __future__ import annotations

from typing import Any

_TREND_ZH = {
    "up_trend": "上升趋势",
    "down_trend": "下降趋势",
    "consolidation": "震荡整理",
    "unknown": "未知",
}
_POSITION_ZH = {
    "above_zs": "中枢上方",
    "inside_zs": "中枢内部",
    "below_zs": "中枢下方",
    "unknown": "未知",
}
_SIGNAL_ZH = {
    "1buy": "一买",
    "2buy": "二买",
    "3buy": "三买",
    "1sell": "一卖",
    "2sell": "二卖",
    "3sell": "三卖",
    "bc_buy": "底背驰买",
    "bc_sell": "顶背驰卖",
    "mixed": "混合信号",
    "none": "无信号",
    "unknown": "未知",
}


def _format_bucket_stats(
    rows: list,
    *,
    title: str,
    label_map: dict[str, str],
    min_samples: int = 3,
) -> str:
    if not rows:
        return ""
    lines = [f"{title}："]
    for key, total_n, hit_n, avg_score in rows:
        if total_n < min_samples:
            continue
        acc = (hit_n / total_n * 100) if total_n > 0 else 0
        label = label_map.get(key, key)
        lines.append(
            f"  {label}：{acc:.1f}% ({hit_n}/{total_n}) | 得分 {avg_score:.2f}"
        )
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""


def format_enhanced_report(stats: dict[str, Any] | None = None) -> str:
    """终端增强统计报表（供 4.3 CLI 调用）。"""
    from app.analysis_store.stats_service import StatsService

    if stats is None:
        stats = StatsService().full_report()

    if not stats or stats.get("total", 0) == 0:
        return "\n" + "=" * 70 + "\n  缠论分析统计报表\n" + "=" * 70 + "\n\n  （暂无已评估数据）\n"

    lines = [
        "",
        "=" * 70,
        "  FlowMarkets 分析统计报表",
        "=" * 70,
        "\n【1】整体性能",
        "-" * 70,
        f"  总样本数:     {stats['total']}",
        f"  命中次数:     {stats['hit_count']} ({stats.get('win_rate', 0) * 100:.1f}%)",
        f"  止损次数:     {stats.get('stop_count', 0)} ({stats.get('stop_rate', 0) * 100:.1f}%)",
        f"  平均得分:     {stats.get('avg_score', 0):.3f}",
        f"  增强得分:     {stats.get('avg_enhanced_score', 0):.3f}",
    ]
    if stats.get("avg_actual_rr"):
        lines.append(f"  平均盈亏比:   {stats['avg_actual_rr']:.2f}")
    if stats.get("avg_hit_bars"):
        lines.append(f"  平均命中K线:  {stats['avg_hit_bars']:.1f} 根")

    def _section(title: str, rows: list, label_map: dict[str, str]) -> None:
        if not rows:
            return
        lines.extend([f"\n{title}", "-" * 70])
        lines.append(f"  {'分类':<12} {'样本':<8} {'命中':<8} {'胜率':<10} {'均分':<8}")
        lines.append("  " + "-" * 50)
        for key, total_n, hit_n, avg_score in rows:
            acc = (hit_n / total_n * 100) if total_n > 0 else 0
            label = label_map.get(key, key)[:12]
            lines.append(
                f"  {label:<12} {total_n:<8} {hit_n:<8} {acc:>6.1f}%   {avg_score:<8.3f}"
            )

    _section("\n【2】按信号类型", stats.get("by_signal", []), _SIGNAL_ZH)
    _section("\n【3】按趋势类型", stats.get("by_trend", []), _TREND_ZH)
    _section("\n【4】按价格位置", stats.get("by_position", []), _POSITION_ZH)

    strength_zh = {
        "weakening": "力度衰竭",
        "strengthening": "力度增强",
        "similar": "力度相近",
        "unknown": "未知",
    }
    _section("\n【5】按力度对比", stats.get("by_strength", []), strength_zh)

    has_signal_zh = {"has_signal": "有信号", "no_signal": "无信号"}
    _section("\n【6】按有无信号", stats.get("by_has_signal", []), has_signal_zh)

    quality_rows = stats.get("by_signal_quality", [])
    if quality_rows and any(r[0] != "unknown" for r in quality_rows):
        grade_zh = {
            "A": "A-优质",
            "B": "B-良好",
            "C": "C-一般",
            "D": "D-低质",
            "unknown": "未评级",
        }
        _section("\n【7】按信号质量评级", quality_rows, grade_zh)

    combo = stats.get("combo_signal_direction", [])
    if combo:
        lines.extend(["\n【8】组合：信号 × 方向（样本≥3，前10）", "-" * 70])
        shown = 0
        for row in combo:
            if len(row) == 5:
                key, total_n, hit_n, win_rate, _avg = row
            else:
                key, total_n, hit_n, _avg = row[0], row[1], row[2], row[3]
                win_rate = hit_n / total_n if total_n else 0
            if total_n < 3:
                continue
            if "|" in str(key):
                sig, direction = str(key).split("|", 1)
            else:
                sig, direction = str(key), "?"
            sig_name = _SIGNAL_ZH.get(sig, sig)[:10]
            dir_name = {"up": "看涨", "down": "看跌"}.get(direction, direction)
            lines.append(
                f"  {sig_name:<10} {dir_name:<6} {total_n:<8} {hit_n:<6} {win_rate * 100:>6.1f}%"
            )
            shown += 1
            if shown >= 10:
                break

    lines.extend(
        [
            "\n" + "=" * 70,
            "  【提示】胜率 > 50% 且样本数 >= 10 的组合更具统计意义",
            "=" * 70 + "\n",
        ]
    )
    return "\n".join(lines)


def format_stats_for_prompt(stats: dict[str, Any], symbol: str, interval: str) -> str:
    if not stats or stats.get("total", 0) == 0:
        return (
            "【系统历史表现】\n"
            "暂无历史评估数据，这是系统首次运行。\n"
        )

    total = stats["total"]
    hit_count = stats["hit_count"]
    avg_score = stats.get("avg_score", 0)
    accuracy = (hit_count / total * 100) if total > 0 else 0

    output = f"""
【系统历史表现】
总评估次数：{total} 次
整体命中率：{accuracy:.1f}% (命中 {hit_count}/{total})
平均得分：{avg_score:.2f} / 1.0

"""
    direction_stats = _format_direction_stats(stats.get("by_direction", []))
    if direction_stats:
        output += direction_stats + "\n"
    symbol_stats = _format_symbol_stats(stats.get("by_symbol", []), symbol)
    if symbol_stats:
        output += symbol_stats + "\n"
    interval_stats = _format_interval_stats(stats.get("by_interval", []), interval)
    if interval_stats:
        output += interval_stats + "\n"
    outcome_stats = _format_outcome_stats(stats.get("by_outcome", []), total)
    if outcome_stats:
        output += outcome_stats + "\n"
    trend_stats = _format_bucket_stats(
        stats.get("by_trend", []),
        title="按趋势统计",
        label_map=_TREND_ZH,
    )
    if trend_stats:
        output += trend_stats + "\n"
    position_stats = _format_bucket_stats(
        stats.get("by_position", []),
        title="按价格位置统计",
        label_map=_POSITION_ZH,
    )
    if position_stats:
        output += position_stats + "\n"
    signal_stats = _format_bucket_stats(
        stats.get("by_signal", []),
        title="按信号类型统计",
        label_map=_SIGNAL_ZH,
    )
    if signal_stats:
        output += signal_stats + "\n"
    suggestions = _generate_suggestions(stats, symbol, interval)
    if suggestions:
        output += suggestions
    return output


def _format_direction_stats(by_direction: list) -> str:
    if not by_direction:
        return ""
    output = "按方向统计：\n"
    for direction, total_dir, hit_dir, avg_score_dir in by_direction:
        acc_dir = (hit_dir / total_dir * 100) if total_dir > 0 else 0
        direction_name = {"up": "看涨", "down": "看跌", "unknown": "未知"}.get(
            direction, direction
        )
        if acc_dir >= 50:
            rating = "表现良好"
        elif acc_dir >= 30:
            rating = "表现一般"
        else:
            rating = "表现不佳"
        output += (
            f"  {direction_name}：{acc_dir:.1f}% ({hit_dir}/{total_dir}) | "
            f"得分 {avg_score_dir:.2f} | {rating}\n"
        )
    return output


def _format_symbol_stats(by_symbol: list, current_symbol: str) -> str:
    if not by_symbol:
        return ""
    current_stats = None
    for sym, total_sym, hit_sym, avg_score_sym in by_symbol:
        if sym == current_symbol:
            current_stats = (sym, total_sym, hit_sym, avg_score_sym)
            break
    if not current_stats:
        return f"当前交易对 {current_symbol}：暂无历史数据\n"
    sym, total_sym, hit_sym, avg_score_sym = current_stats
    acc_sym = (hit_sym / total_sym * 100) if total_sym > 0 else 0
    rating = (
        "表现良好"
        if acc_sym >= 50
        else "表现一般"
        if acc_sym >= 30
        else "表现不佳"
    )
    return (
        f"当前交易对 {sym}：{acc_sym:.1f}% ({hit_sym}/{total_sym}) | "
        f"得分 {avg_score_sym:.2f} | {rating}\n"
    )


def _format_interval_stats(by_interval: list, current_interval: str) -> str:
    if not by_interval:
        return ""
    current_stats = None
    for intv, total_int, hit_int, avg_score_int in by_interval:
        if intv == current_interval:
            current_stats = (intv, total_int, hit_int, avg_score_int)
            break
    if not current_stats:
        return f"当前周期 {current_interval}：暂无历史数据\n"
    intv, total_int, hit_int, avg_score_int = current_stats
    acc_int = (hit_int / total_int * 100) if total_int > 0 else 0
    rating = (
        "表现良好"
        if acc_int >= 50
        else "表现一般"
        if acc_int >= 30
        else "表现不佳"
    )
    return (
        f"当前周期 {intv}：{acc_int:.1f}% ({hit_int}/{total_int}) | "
        f"得分 {avg_score_int:.2f} | {rating}\n"
    )


def _format_outcome_stats(by_outcome: list, total: int) -> str:
    if not by_outcome:
        return ""
    output = "结果类型分布：\n"
    names = {
        "success": "成功（命中目标）",
        "partial": "部分正确（方向对）",
        "stopped": "止损出局",
        "failed": "失败（方向错误）",
        "unknown": "未知",
        "no_direction": "无方向",
    }
    for outcome_type, count in sorted(by_outcome, key=lambda x: x[1], reverse=True):
        pct = (count / total * 100) if total > 0 else 0
        output += f"  {names.get(outcome_type, outcome_type)}: {count} 次 ({pct:.1f}%)\n"
    return output


def _generate_suggestions(stats: dict[str, Any], symbol: str, interval: str) -> str:
    suggestions = ["【AI 调整建议】"]
    by_direction = {d[0]: (d[2], d[1], d[3]) for d in stats.get("by_direction", [])}
    if "up" in by_direction:
        up_hit, up_total, _ = by_direction["up"]
        if up_total > 0 and (up_hit / up_total * 100) < 20:
            suggestions.append("1. 看涨预测历史表现不佳，建议降低看涨概率并提高确认门槛。")
    if "down" in by_direction:
        down_hit, down_total, _ = by_direction["down"]
        if down_total > 0 and (down_hit / down_total * 100) > 50:
            suggestions.append("2. 看跌预测历史表现相对较好，但仍需结构确认。")
    by_symbol_dict = {s[0]: (s[2], s[1], s[3]) for s in stats.get("by_symbol", [])}
    if symbol in by_symbol_dict:
        sym_hit, sym_total, _ = by_symbol_dict[symbol]
        if sym_total > 0 and (sym_hit / sym_total * 100) < 20:
            suggestions.append(f"3. {symbol} 历史准确率较低，建议采用更保守的状态机。")
    if stats.get("avg_score", 0) < 0.3:
        suggestions.append("4. 整体得分偏低，优先小幅机会并严格止损。")
    if len(suggestions) == 1:
        return ""
    return "\n".join(suggestions) + "\n"


def get_stats_summary(stats: dict[str, Any]) -> dict[str, Any]:
    if not stats or stats.get("total", 0) == 0:
        return {
            "has_data": False,
            "total": 0,
            "accuracy": 0.0,
            "hit_rate": 0.0,
            "avg_score": 0.0,
        }
    total = stats["total"]
    hit_count = stats["hit_count"]
    avg_score = stats.get("avg_score", 0)
    accuracy = (hit_count / total * 100) if total > 0 else 0
    by_direction = {
        d[0]: {"acc": (d[2] / d[1] * 100) if d[1] > 0 else 0, "score": d[3], "total": d[1]}
        for d in stats.get("by_direction", [])
    }
    by_symbol = {
        s[0]: {"acc": (s[2] / s[1] * 100) if s[1] > 0 else 0, "score": s[3], "total": s[1]}
        for s in stats.get("by_symbol", [])
    }
    by_interval = {
        i[0]: {"acc": (i[2] / i[1] * 100) if i[1] > 0 else 0, "score": i[3], "total": i[1]}
        for i in stats.get("by_interval", [])
    }
    return {
        "has_data": True,
        "total": total,
        "accuracy": accuracy,
        "hit_rate": round(hit_count / total, 4) if total > 0 else 0.0,
        "avg_score": avg_score,
        "by_direction": by_direction,
        "by_symbol": by_symbol,
        "by_interval": by_interval,
    }


def bucket_hit_rate(
    stats: dict[str, Any], symbol: str, interval: str, *, min_samples: int = 5
) -> tuple[float | None, int, str]:
    """返回 (hit_rate 0-1, sample_size, basis_key) 供状态机降级。"""
    summary = get_stats_summary(stats)
    if not summary.get("has_data"):
        return None, 0, "none"

    sym = summary.get("by_symbol", {}).get(symbol)
    if sym and sym.get("total", 0) >= min_samples:
        return sym["acc"] / 100.0, int(sym["total"]), "for_symbol"

    intv = summary.get("by_interval", {}).get(interval)
    if intv and intv.get("total", 0) >= min_samples:
        return intv["acc"] / 100.0, int(intv["total"]), "for_interval"

    total = summary["total"]
    if total >= min_samples:
        return summary["hit_rate"], int(total), "overall"

    return None, int(total), "insufficient_samples"
