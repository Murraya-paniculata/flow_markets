"""缠论结构快照：K 线 → 结构引擎 → 裁剪 JSON（与 chanlun ChanlunAIExporter 对齐）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

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
from app.services.chan.analyze import _apply_chan_engine_root, _run_chan_engine
from app.services.chan.backend import ENGINE_ID, ChanEngineICL
from app.services.chan.kline import cap_limit, get_klines_beijing, normalize_interval
from app.services.chan.types import SimpleBi, SimpleMMD, SimpleXD, SimpleZS

DEFAULT_LOOKBACK = 300
DEFAULT_MAX_BI = 15
DEFAULT_MAX_SEGMENT = 5
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


def _dt_iso(dt) -> str:
    if dt is None:
        return ""
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _collect_signals(icl: ChanEngineICL) -> ChanSignal:
    buy_sell: list[str] = []
    divergences: list[str] = []

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
        for bc in xd.bcs or []:
            if getattr(bc, "bc", False):
                t = getattr(bc, "type", "")
                if t:
                    divergences.append(str(t))

    return ChanSignal(
        buy_sell_points=sorted(set(buy_sell)),
        divergences=sorted(set(divergences)),
        last_signal_time=None,
    )


def _bi_item(bi: SimpleBi) -> ChanBiItem:
    mmds: List[SimpleMMD] = bi.mmds or []
    buy_sell = getattr(mmds[-1], "name", None) if mmds else None
    div = None
    for bc in bi.bcs or []:
        if getattr(bc, "bc", False):
            div = getattr(bc, "type", None)
            break

    kwargs = dict(
        index=int(bi.index),
        direction=str(bi.type),
        is_done=bool(bi.is_done()),
        start_time=_dt_iso(bi.start_time) or None,
        end_time=_dt_iso(bi.end_time) or None,
        start_price=float(bi.start_price),
        end_price=float(bi.end_price),
        buy_sell_point=buy_sell,
        divergence=str(div) if div else None,
    )
    if getattr(bi, "strength", 0):
        kwargs["strength"] = round(float(bi.strength), 2)
    if getattr(bi, "macd_strength", 0):
        kwargs["macd_strength"] = round(float(bi.macd_strength), 2)
    if getattr(bi, "price_strength", 0):
        kwargs["price_strength"] = round(float(bi.price_strength), 2)
    return ChanBiItem(**kwargs)


def _segment_item(xd: SimpleXD) -> ChanSegmentItem:
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
        buy_sell_point=None,
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
        high=float(getattr(zs, "high", zs.zg)),
        low=float(getattr(zs, "low", zs.zd)),
        level=int(getattr(zs, "level", 1)),
        relation=str(getattr(zs, "relation", "new")),
        bi_count=int(getattr(zs, "bi_count", 0)),
    )


def _count_centers(icl: ChanEngineICL) -> int:
    n = len(icl.get_bi_zss())
    n += len(icl.get_xd_zss())
    return n


def _build_trim_meta(
    *,
    total_bi: int,
    total_segment: int,
    max_bi: int,
    max_segment: int,
) -> dict[str, int] | None:
    """若 bi/segment 列表被条数上限裁剪，在 meta.trim 中记录上限（与 chanlun exporter 契约一致）。"""
    trim: dict[str, int] = {}
    if total_bi > max_bi:
        trim["bi"] = max_bi
    if total_segment > max_segment:
        trim["segment"] = max_segment
    return trim or None


def _build_structure_summary(
    icl: ChanEngineICL,
    latest_price: float,
) -> ChanStructureSummary:
    """与 chanlun/chanlun_ai_exporter._build_structure_summary 逻辑一致。"""
    bis = icl.get_bis()
    bi_zss = icl.get_bi_zss()
    summary = ChanStructureSummary()

    if len(bis) >= 5:
        recent_bis = bis[-5:]
        highs = [float(b.high) for b in recent_bis]
        lows = [float(b.low) for b in recent_bis]
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
        zg = float(latest_zs.zg)
        zd = float(latest_zs.zd)
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
        summary.latest_bi_strength = round(float(getattr(latest_bi, "strength", 0)), 2)

        prev_same = None
        for bi in reversed(bis[:-1]):
            if bi.type == latest_bi.type:
                prev_same = bi
                break
        if prev_same:
            summary.prev_bi_strength = round(float(getattr(prev_same, "strength", 0)), 2)
            if summary.latest_bi_strength > 0 and summary.prev_bi_strength > 0:
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
) -> ChanStructureSnapshot:
    """
    拉取 K 线、运行缠论结构引擎、导出缠论结构快照。

    Raises:
        ValueError: 参数或数据不足
        RuntimeError: 行情/引擎失败
    """
    _apply_chan_engine_root()
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
    icl = _run_chan_engine(display_symbol, interval, engine_klines)
    latest_price = float(raw[-1]["close"])

    all_bis = icl.get_bis()
    all_xds = icl.get_xds()
    centers: list[ChanCenterItem] = []
    for zs in icl.get_bi_zss():
        centers.append(_center_item(zs, "bi"))
    for zs in icl.get_xd_zss():
        centers.append(_center_item(zs, "segment"))

    export_bis = all_bis[-max_bi:] if max_bi > 0 else []
    export_segments = all_xds[-max_segment:] if max_segment > 0 else []

    meta = ChanMeta(
        symbol=display_symbol,
        interval=interval,
        timestamp=datetime.now(timezone.utc).isoformat(),
        data_size=ChanDataSize(
            kline=len(raw),
            bi=len(all_bis),
            segment=len(all_xds),
            center=_count_centers(icl),
        ),
        trim=_build_trim_meta(
            total_bi=len(all_bis),
            total_segment=len(all_xds),
            max_bi=max_bi,
            max_segment=max_segment,
        ),
    )

    return ChanStructureSnapshot(
        meta=meta,
        market=ChanMarket(latest_price=latest_price),
        bi=[_bi_item(b) for b in export_bis],
        segment=[_segment_item(x) for x in export_segments],
        center=centers,
        signal=_collect_signals(icl),
        structure_summary=_build_structure_summary(icl, latest_price),
        context=ChanContext(),
    )
