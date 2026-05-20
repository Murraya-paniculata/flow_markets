"""缠论结构快照：K 线 → chanpy → 裁剪 JSON（供 Agent 工具与 API 共用）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from app.schemas.chan_structure import (
    ChanBiItem,
    ChanCenterItem,
    ChanContext,
    ChanDataSize,
    ChanMarket,
    ChanMeta,
    ChanSegmentItem,
    ChanSignal,
    ChanStructureSnapshot,
    ChanStructureSummary,
    ChanKeyLevels,
)
from app.services.chan.analyze import _apply_chanpy_root, _run_chanpy
from app.services.chan.backend import ChanpyICL
from app.services.chan.kline import cap_limit, get_klines_beijing, normalize_interval
from app.services.chan.types import SimpleBi, SimpleMMD, SimpleXD, SimpleZS

DEFAULT_LOOKBACK = 300
DEFAULT_MAX_BI = 15
DEFAULT_MAX_SEGMENT = 5
DEFAULT_MAX_CENTER = 8
MIN_KLINES = 50


def _normalize_symbol(symbol: str) -> tuple[str, str]:
    """返回 (binance_symbol, display_symbol)。"""
    raw = (symbol or "").strip().upper().replace("/", "").replace("-", "")
    if not raw:
        raise ValueError("symbol 不能为空")
    if len(raw) >= 6 and raw.endswith("USDT"):
        base = raw[:-4]
        display = f"{base}/USDT"
    else:
        display = raw
    return raw, display


def _dt_iso(dt: Any) -> str:
    if dt is None:
        return ""
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _bi_price_strength(bi: SimpleBi) -> float:
    return round(abs(float(bi.end_price) - float(bi.start_price)), 2)


def _collect_signals(icl: ChanpyICL) -> ChanSignal:
    buy_sell: list[str] = []
    divergences: list[str] = []
    last_time: Optional[str] = None

    for bi in icl.get_bis():
        for mmd in bi.mmds or []:
            name = getattr(mmd, "name", None)
            if name:
                buy_sell.append(str(name))
        for bc in bi.bcs or []:
            if getattr(bc, "bc", False):
                t = getattr(bc, "type", "")
                if t:
                    divergences.append(str(t))

    for xd in icl.get_xds():
        for mmd in xd.mmds or []:
            name = getattr(mmd, "name", None)
            if name:
                buy_sell.append(str(name))

    if icl.get_bis():
        last_time = _dt_iso(icl.get_bis()[-1].end_time)

    return ChanSignal(
        buy_sell_points=sorted(set(buy_sell)),
        divergences=sorted(set(divergences)),
        last_signal_time=last_time or None,
    )


def _bi_item(bi: SimpleBi) -> ChanBiItem:
    mmds: List[SimpleMMD] = bi.mmds or []
    buy_sell = getattr(mmds[-1], "name", None) if mmds else None
    div = None
    for bc in bi.bcs or []:
        if getattr(bc, "bc", False):
            div = getattr(bc, "type", None)
            break
    return ChanBiItem(
        index=int(bi.index),
        direction=str(bi.type),
        is_done=bool(bi.is_done()),
        start_time=_dt_iso(bi.start_time) or None,
        end_time=_dt_iso(bi.end_time) or None,
        start_price=float(bi.start_price),
        end_price=float(bi.end_price),
        buy_sell_point=buy_sell,
        divergence=str(div) if div else None,
        price_strength=_bi_price_strength(bi),
    )


def _segment_item(xd: SimpleXD) -> ChanSegmentItem:
    mmds = xd.mmds or []
    buy_sell = getattr(mmds[-1], "name", None) if mmds else None
    div = None
    for bc in xd.bcs or []:
        if getattr(bc, "bc", False):
            div = getattr(bc, "type", None)
            break
    return ChanSegmentItem(
        index=int(xd.index),
        direction=str(xd.type),
        is_done=bool(xd.is_done()),
        start_time=_dt_iso(xd.start_time) or None,
        end_time=_dt_iso(xd.end_time) or None,
        start_price=float(xd.start_price),
        end_price=float(xd.end_price),
        buy_sell_point=buy_sell,
        divergence=str(div) if div else None,
    )


def _center_item(zs: SimpleZS, zs_kind: str) -> ChanCenterItem:
    return ChanCenterItem(
        index=int(zs.index),
        type="bi" if zs_kind == "bi" else "segment",
        zs_type=str(getattr(zs, "zs_type", "standard")),
        start_time=_dt_iso(zs.start_time) or None,
        end_time=_dt_iso(zs.end_time) or None,
        zg=float(zs.zg),
        zd=float(zs.zd),
        gg=float(zs.gg),
        dd=float(zs.dd),
        high=float(zs.zg),
        low=float(zs.zd),
        relation=str(getattr(zs, "relation", "new")),
        bi_count=int(getattr(zs, "bi_count", 0)),
    )


def _build_structure_summary(
    icl: ChanpyICL,
    latest_price: float,
) -> ChanStructureSummary:
    bis = icl.get_bis()
    bi_zss = icl.get_bi_zss()

    summary = ChanStructureSummary()

    if len(bis) >= 3:
        highs = [max(b.start_price, b.end_price) for b in bis[-5:]]
        lows = [min(b.start_price, b.end_price) for b in bis[-5:]]
        highs_rising = all(highs[i] <= highs[i + 1] for i in range(len(highs) - 1))
        lows_rising = all(lows[i] <= lows[i + 1] for i in range(len(lows) - 1))
        highs_falling = all(highs[i] >= highs[i + 1] for i in range(len(highs) - 1))
        lows_falling = all(lows[i] >= lows[i + 1] for i in range(len(lows) - 1))
        if highs_rising and lows_rising:
            summary.trend = "up_trend"
        elif highs_falling and lows_falling:
            summary.trend = "down_trend"
        else:
            summary.trend = "consolidation"

    if bi_zss:
        latest_zs = bi_zss[-1]
        zg, zd = float(latest_zs.zg), float(latest_zs.zd)
        if latest_price > zg:
            summary.price_position = "above_zs"
        elif latest_price < zd:
            summary.price_position = "below_zs"
        else:
            summary.price_position = "inside_zs"
        summary.key_levels = ChanKeyLevels(
            zg=zg,
            zd=zd,
            gg=float(latest_zs.gg),
            dd=float(latest_zs.dd),
        )

    if bis:
        latest_bi = bis[-1]
        summary.latest_bi_direction = str(latest_bi.type)
        summary.latest_bi_strength = _bi_price_strength(latest_bi)

        prev_same = None
        for bi in reversed(bis[:-1]):
            if bi.type == latest_bi.type:
                prev_same = bi
                break
        if prev_same:
            summary.prev_bi_strength = _bi_price_strength(prev_same)
            if summary.prev_bi_strength > 0:
                ratio = summary.latest_bi_strength / summary.prev_bi_strength
                if ratio < 0.8:
                    summary.strength_comparison = "weakening"
                elif ratio > 1.2:
                    summary.strength_comparison = "strengthening"
                else:
                    summary.strength_comparison = "similar"

    trend_desc = {
        "up_trend": "上升趋势（高点和低点依次抬高）",
        "down_trend": "下降趋势（高点和低点依次降低）",
        "consolidation": "震荡盘整（无明显趋势）",
        "unknown": "未知",
    }
    position_desc = {
        "above_zs": "价格在中枢上方（多头占优）",
        "below_zs": "价格在中枢下方（空头占优）",
        "inside_zs": "价格在中枢内部（多空博弈）",
        "unknown": "无中枢参考",
    }
    summary.trend_description = trend_desc.get(summary.trend, "未知")
    summary.position_description = position_desc.get(summary.price_position, "未知")
    return summary


def build_chan_structure_snapshot(
    symbol: str,
    timeframe: str,
    lookback: int = DEFAULT_LOOKBACK,
    *,
    max_bi: int = DEFAULT_MAX_BI,
    max_segment: int = DEFAULT_MAX_SEGMENT,
    max_center: int = DEFAULT_MAX_CENTER,
) -> ChanStructureSnapshot:
    """
    拉取 K 线、运行 chanpy、导出缠论结构快照。

    Raises:
        ValueError: 参数或数据不足
        RuntimeError: 行情/引擎失败
    """
    _apply_chanpy_root()
    binance_symbol, display_symbol = _normalize_symbol(symbol)
    interval = normalize_interval(timeframe)
    limit = cap_limit(interval, lookback)

    raw = get_klines_beijing(binance_symbol, interval, limit)
    if not raw or len(raw) < MIN_KLINES:
        raise ValueError(
            f"K 线不足：需要至少 {MIN_KLINES} 根，当前 {len(raw)} 根。"
            f"请增大 lookback 或更换周期。"
        )

    engine_klines = [
        {
            "date": k["open_time"],
            "open": k["open"],
            "high": k["high"],
            "low": k["low"],
            "close": k["close"],
            "volume": 0.0,
        }
        for k in raw
    ]
    icl = _run_chanpy(display_symbol, interval, engine_klines)
    latest_price = float(raw[-1]["close"])

    all_bis = icl.get_bis()
    all_xds = icl.get_xds()
    centers: list[ChanCenterItem] = []
    for zs in icl.get_bi_zss()[-max_center:]:
        centers.append(_center_item(zs, "bi"))
    for zs in icl.get_xd_zss()[-2:]:
        centers.append(_center_item(zs, "segment"))

    trimmed = len(all_bis) > max_bi or len(all_xds) > max_segment
    meta = ChanMeta(
        symbol=display_symbol,
        interval=interval,
        timestamp=datetime.now(timezone.utc).isoformat(),
        data_size=ChanDataSize(
            kline=len(raw),
            bi=len(all_bis),
            segment=len(all_xds),
            center=len(centers),
        ),
        trim={"max_bi": max_bi, "max_segment": max_segment} if trimmed else None,
    )

    return ChanStructureSnapshot(
        meta=meta,
        market=ChanMarket(latest_price=latest_price),
        bi=[_bi_item(b) for b in all_bis[-max_bi:]],
        segment=[_segment_item(x) for x in all_xds[-max_segment:]],
        center=centers,
        signal=_collect_signals(icl),
        structure_summary=_build_structure_summary(icl, latest_price),
        context=ChanContext(),
    )
