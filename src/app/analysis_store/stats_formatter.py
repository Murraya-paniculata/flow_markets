"""统计数据格式化为 Prompt / JSON（移植 chanlun stats_formatter）。"""

from __future__ import annotations

from typing import Any


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
