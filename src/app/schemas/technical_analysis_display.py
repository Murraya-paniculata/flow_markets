"""技术分析师双交付 → 终端/CLI 交易者可读文案（对齐 chanlun 展示风格）。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.chan_structure import ChanStructureSnapshot
    from app.schemas.flow_markets_deliverables import (
        ChanlunStateMachineOutput,
        TechnicalAnalysisDeliverable,
    )

_WIDTH = 60
_SEP = "=" * _WIDTH
_SUB = "-" * _WIDTH

_CONDITION_ZH: dict[str, str] = {
    "price_below_zd": "价格低于 ZD",
    "price_above_zg": "价格高于 ZG",
    "price_hold_zd": "价格守住 ZD",
    "price_hold_dd": "价格守住 DD",
    "price_break_zd": "价格突破 ZD",
    "price_reclaim_zg": "价格站回 ZG",
    "bi_down": "向下笔延续",
    "bi_up": "向上笔延续",
    "no_new_down_bi": "无新向下笔",
    "no_new_up_bi": "无新向上笔",
}


def _zh_condition(code: str) -> str:
    key = (code or "").strip().lower()
    return _CONDITION_ZH.get(key, code)


def _indent_paragraphs(text: str, prefix: str = "  ") -> str:
    lines: list[str] = []
    for block in re.split(r"\n+", text.strip()):
        block = block.strip()
        if not block:
            continue
        # 已有列表项则保留
        if re.match(r"^[\d①②③④⑤⑥⑦⑧⑨⑩][\.、．)]", block):
            lines.append(f"{prefix}{block}")
        else:
            lines.append(f"{prefix}{block}")
    return "\n".join(lines)


def _trend_label(trend: str) -> str:
    m = {
        "consolidation": "震荡盘整",
        "up_trend": "上升趋势",
        "down_trend": "下降趋势",
    }
    return m.get(trend, trend)


def _position_label(pos: str) -> str:
    m = {
        "below_zs": "中枢下方（偏空）",
        "above_zs": "中枢上方（偏多）",
        "inside_zs": "中枢内部（震荡）",
    }
    return m.get(pos, pos)


def _state_label(state: str) -> str:
    m = {
        "STRATEGY_ACTIVE": "策略激活",
        "WAIT_CONFIRMATION": "等待确认",
        "OBSERVE_ONLY": "观望为主",
    }
    return m.get(state, state)


def _infer_strategy_probs(
    chanlun: ChanlunStateMachineOutput,
) -> tuple[float, float, float]:
    """从状态机 + 结构判断推断 做多/做空/震荡 展示用概率（归一化）。"""
    sj = chanlun.structure_judgement
    sm = chanlun.state_machine
    up, down, rng = 0.28, 0.32, 0.40

    trend = (sj.trend or "").lower()
    pos = (sj.price_position or "").lower()
    if "consolidation" in trend or trend == "range":
        rng += 0.12
        up -= 0.06
        down -= 0.06
    elif "up" in trend:
        up += 0.15
        down -= 0.08
        rng -= 0.07
    elif "down" in trend:
        down += 0.15
        up -= 0.08
        rng -= 0.07

    if pos == "below_zs":
        down += 0.10
        up -= 0.05
    elif pos == "above_zs":
        up += 0.10
        down -= 0.05
    elif pos == "inside_zs":
        rng += 0.08

    direction = sm.active_strategy.direction
    if direction == "down":
        down = max(down, 0.38)
    else:
        up = max(up, 0.38)

    if sm.current_state == "OBSERVE_ONLY":
        rng = max(rng, 0.45)
        up *= 0.85
        down *= 0.85
    elif sm.current_state == "WAIT_CONFIRMATION":
        rng += 0.05

    total = up + down + rng
    if total <= 0:
        return 0.33, 0.33, 0.34
    return up / total, down / total, rng / total


def _format_active_strategy_block(
    chanlun: ChanlunStateMachineOutput,
    up_p: float,
    down_p: float,
    range_p: float,
) -> list[str]:
    sm = chanlun.state_machine
    active = sm.active_strategy
    exe = active.execution
    zone = active.entry_gate.price_zone
    z0, z1 = (zone[0], zone[1]) if len(zone) >= 2 else (0.0, 0.0)
    entry_lo, entry_hi = min(z0, z1), max(z0, z1)
    lines: list[str] = []

    state = sm.current_state
    if state == "OBSERVE_ONLY":
        lines.append(
            f"  状态机建议【{_state_label(state)}】：暂不激进开仓，"
            f"优先等待结构触发条件满足。"
        )
        lines.append("")

    direction = active.direction
    status = active.status
    pct = down_p if direction == "down" else up_p
    label = "做空" if direction == "down" else "做多"
    emoji = "📉" if direction == "down" else "📈"

    conds = "、".join(_zh_condition(c) for c in active.entry_gate.structure_required[:4])
    lines.append(
        f"  【{label}策略（概率 {pct * 100:.0f}%）】"
        f"状态 {status}；入场 {entry_lo:,.0f}–{entry_hi:,.0f}；"
        f"目标 {exe.target:,.0f}；止损 {exe.stop_loss:,.0f}（{exe.entry_type}，RR≈{exe.rr:.1f}）。"
    )
    if conds:
        lines.append(f"    结构门槛：{conds}。")

    inv = sm.invalidation.invalidate_active_if
    if inv:
        inv_zh = "、".join(_zh_condition(c) for c in inv[:3])
        lines.append(f"    失效/否决：{inv_zh} → {sm.invalidation.next_state}。")

    if range_p >= 0.15:
        zs = chanlun.structure_judgement.zs
        lines.append(
            f"  【震荡策略（概率 {range_p * 100:.0f}%）】"
            f"区间参考 ZD {zs.zd:,.0f} – ZG {zs.zg:,.0f}（GG {zs.gg:,.0f} / DD {zs.dd:,.0f}），高抛低吸。"
        )

    standby = sm.standby_strategies
    if standby:
        for sb in standby[:2]:
            acts = "、".join(_zh_condition(a) for a in sb.activate_if[:3])
            d = {"up": "做多", "down": "做空", "range": "震荡"}.get(sb.direction, sb.direction)
            lines.append(f"  【待命·{d}】激活条件：{acts}。")

    return lines


def format_structure_cli_summary(snapshot: ChanStructureSnapshot) -> str:
    """缠论结构快览（对齐 chanlun output_formatter.format_summary，供 --no-ai 或步骤展示）。"""
    symbol = snapshot.meta.symbol
    interval = snapshot.meta.interval
    ss = snapshot.structure_summary
    mkt = snapshot.market
    sig = snapshot.signal
    ds = snapshot.meta.data_size

    lines: list[str] = []
    lines.append("")
    lines.append(_SEP)
    lines.append(f"【{symbol} · {interval} 缠论结构快览】")
    lines.append(_SEP)
    lines.append("")
    lines.append(f"💰 当前价格：{mkt.latest_price:,.2f}")
    lines.append("")

    if snapshot.center:
        for i, c in enumerate(snapshot.center):
            zg = c.zg or c.high or 0
            zd = c.zd or c.low or 0
            rel = {"new": "新建", "extend": "延伸"}.get(c.relation or "", c.relation or "")
            lines.append(f"🧱 中枢 #{i + 1}（{c.type}）：{zd:,.2f} ~ {zg:,.2f}")
            lines.append(f"   关系：{rel}")
    else:
        lines.append("🧱 中枢：暂无")
    lines.append("")

    if snapshot.bi:
        lb = snapshot.bi[-1]
        direction = "↑ 向上" if lb.direction == "up" else "↓ 向下"
        status = "（已完成）" if lb.is_done else "（进行中）"
        end_p = lb.end_price if lb.end_price is not None else 0
        extra = ""
        if lb.buy_sell_point:
            extra += f" 买卖点={lb.buy_sell_point}"
        if lb.divergence:
            extra += f" 背驰={lb.divergence}"
        lines.append(f"📊 最新一笔：{direction} {status} 结束价 {end_p:,.2f}{extra}")
    else:
        lines.append("📊 最新一笔：数据不足")
    lines.append("")

    if sig.buy_sell_points or sig.divergences:
        lines.append("🚨 近期信号：")
        if sig.buy_sell_points:
            lines.append(f"   买卖点：{', '.join(sig.buy_sell_points)}")
        if sig.divergences:
            lines.append(f"   背驰：{', '.join(sig.divergences)}")
    else:
        lines.append("🚨 近期信号：无")
    lines.append("")

    lines.append(
        f"📈 结构统计：{ds.bi} 笔 / {ds.segment} 线段 / {ds.center} 中枢"
        f"（K 线 {ds.kline} 根）"
    )
    lines.append(f"📐 趋势：{ss.trend_description}；位置：{ss.position_description}")
    kl = ss.key_levels
    if kl.zg or kl.zd:
        lines.append(
            f"📍 关键位 ZG={kl.zg:,.0f} ZD={kl.zd:,.0f} GG={kl.gg:,.0f} DD={kl.dd:,.0f}"
        )
    lines.append("")
    lines.append(_SEP)
    lines.append("")
    return "\n".join(lines)


def _format_analysis_markdown_block(markdown: str) -> list[str]:
    """对齐 chanlun output_formatter.format_analysis：原样输出 Markdown。"""
    body = markdown.strip()
    if not body:
        return []
    lines = ["", _SEP, "【AI 缠论分析】", _SEP, "", body, "", _SEP, ""]
    return lines


def format_trader_display(
    deliverable: TechnicalAnalysisDeliverable,
) -> str:
    """
    将 TechnicalAnalysisDeliverable 格式化为给交易者看的终端文案。

    有 brief.analysis_markdown 时对齐 chanlun --table（六节 Markdown 长文）；
    否则回退为摘要 + 状态机卡片。
    """
    brief = deliverable.brief
    chanlun = deliverable.chanlun_v2
    symbol = brief.symbol
    interval = brief.interval or "1h"
    analysis_md = (brief.analysis_markdown or "").strip()

    out: list[str] = []

    if brief.data_status == "待K线数据":
        out.append("")
        out.append(_SEP)
        out.append("📝 AI 市场分析（给交易者看的解读）")
        out.append(_SEP)
        out.append(f"  {symbol} · {interval}：缠论结构暂不可用。")
        out.append(f"  {brief.summary.strip()}")
        if brief.missing_data_checklist:
            out.append("  待办：")
            for item in brief.missing_data_checklist:
                out.append(f"    - {item}")
        out.append(_SEP)
        out.append("")
        return "\n".join(out)

    if analysis_md:
        meta_price = chanlun.meta.price if chanlun else None
        out.append("")
        out.append(_SEP)
        out.append(f"【{symbol} · {interval} 缠论 AI 分析】")
        out.append(_SEP)
        if meta_price is not None:
            out.append(f"💰 当前价格：{meta_price:,.2f}")
            out.append("")
        if (brief.summary or "").strip():
            out.append("【执行摘要】")
            out.append(brief.summary.strip())
            out.append("")
        out.extend(_format_analysis_markdown_block(analysis_md))
        if (brief.disclaimer or "").strip():
            out.append(brief.disclaimer.strip())
        out.append("")
        return "\n".join(out)

    out.append("")
    out.append(_SEP)
    out.append("📝 AI 市场分析（给交易者看的解读）")
    out.append(_SEP)

    meta_price = chanlun.meta.price if chanlun else None
    open_line = f"  当前 {symbol} 处于 {interval} 周期缠论结构中。"
    if meta_price is not None:
        open_line += f" 最新价约 {meta_price:,.2f}。"
    out.append(open_line)

    if chanlun:
        sj = chanlun.structure_judgement
        out.append(
            f"  结构：{_trend_label(sj.trend)}，{_position_label(sj.price_position)}；"
            f"状态机 {_state_label(chanlun.state_machine.current_state)}。"
        )

    if (brief.structure_quickview or "").strip():
        out.append(f"  快览：{brief.structure_quickview.strip()}")
    out.append("")
    out.append(_indent_paragraphs(brief.summary))
    out.append("")
    out.append(_SEP)

    if chanlun:
        up_p, down_p, range_p = _infer_strategy_probs(chanlun)
        out.append("")
        out.append("📊 策略概率分布：")
        out.append(_SUB)
        out.append(f"  📈 做多策略概率: {up_p * 100:.1f}%")
        out.append(f"  📉 做空策略概率: {down_p * 100:.1f}%")
        out.append(f"  ↔️  震荡策略概率: {range_p * 100:.1f}%")
        out.append(_SUB)
        out.append("")
        out.append("🎯 策略与执行要点")
        out.append(_SUB)
        out.extend(_format_active_strategy_block(chanlun, up_p, down_p, range_p))
        if chanlun.risk_notes:
            out.append("")
            out.append("  ⚠️ 风险提示")
            for note in chanlun.risk_notes:
                out.append(f"    - {note}")

    out.append("")
    out.append(_SEP)
    if (brief.disclaimer or "").strip():
        out.append(f"  {brief.disclaimer.strip()}")
    out.append(_SEP)
    out.append("")
    return "\n".join(out)
