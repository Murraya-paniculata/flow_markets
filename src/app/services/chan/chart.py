"""缠论结构 → 前端图表 JSON。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


# --- 原始 K 线 → ECharts 蜡烛 ---


@dataclass
class _Bar:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    close_time: datetime


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e10:
            ts /= 1000.0
        return datetime.fromtimestamp(ts)
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    raise ValueError(f"无法解析时间: {value!r}")


def to_frontend_bars(klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Binance 标准 K 线 dict → {date,o,h,l,c,a}。"""
    if not klines:
        return []
    bars = [
        _Bar(
            _parse_dt(k["open_time"]),
            float(k["open"]),
            float(k["high"]),
            float(k["low"]),
            float(k["close"]),
            _parse_dt(k["close_time"]),
        )
        for k in klines
        if isinstance(k, dict)
    ]
    bars.sort(key=lambda b: b.open_time)
    return [
        {
            "date": b.open_time.isoformat(),
            "o": b.open,
            "h": b.high,
            "l": b.low,
            "c": b.close,
            "a": 0.0,
        }
        for b in bars
    ]


def merged_klines_to_json(
    merged_list: List[Any],
    frontend_bars: List[Dict[str, Any]],
    *,
    dt_format: Callable[[Any], str] | None = None,
) -> List[Dict[str, Any]]:
    """合并 K 线 → 含 chart_idx / start_date / end_date 的 JSON。"""
    if not merged_list or not frontend_bars:
        return []

    def _fmt(dt: Any) -> str:
        if dt_format:
            return dt_format(dt)
        try:
            return dt.strftime("%Y-%m-%d %H:%M:%S")  # type: ignore[union-attr]
        except Exception:
            return str(dt)

    n = len(frontend_bars)
    out: List[Dict[str, Any]] = []
    for mk in merged_list:
        indices = list(getattr(mk, "raw_indices", None) or [])
        if not indices:
            indices = [int(getattr(mk, "index", 0))]
        start_i = max(0, min(indices))
        end_i = min(n - 1, max(indices))
        o = float(getattr(mk, "open", getattr(mk, "open_price", 0)))
        h, l, c = float(mk.high), float(mk.low), float(mk.close)
        chart_idx = len(out)
        out.append({
            "index": int(getattr(mk, "index", chart_idx)),
            "chart_idx": chart_idx,
            "start_date": _fmt(frontend_bars[start_i].get("date")),
            "end_date": _fmt(frontend_bars[end_i].get("date")),
            "o": o,
            "h": h,
            "l": l,
            "c": c,
            "raw_count": len(indices),
            "direction": "up" if c >= o else "down",
        })
    return out


# --- 笔 / 段 / 中枢 / 分型 ---


def _bi_merged_indices(bi: Any) -> Tuple[Optional[int], Optional[int]]:
    s = getattr(bi, "start_index", None)
    e = getattr(bi, "end_index", None)
    if s is None and getattr(bi, "start_fx", None) is not None:
        s = getattr(bi.start_fx, "index", None)
    if e is None and getattr(bi, "end_fx", None) is not None:
        e = getattr(bi.end_fx, "index", None)
    if s is None or e is None:
        return None, None
    return int(s), int(e)


def _xd_merged_indices(xd: Any) -> Tuple[Optional[int], Optional[int]]:
    start_bi = getattr(xd, "start_bi", None)
    end_bi = getattr(xd, "end_bi", None)
    if start_bi is not None and end_bi is not None:
        return _bi_merged_indices(start_bi)[0], _bi_merged_indices(end_bi)[1]
    bi_list = getattr(xd, "bi_list", None) or []
    if bi_list:
        return _bi_merged_indices(bi_list[0])[0], _bi_merged_indices(bi_list[-1])[1]
    return None, None


def _fx_merged_index(fx: Any) -> Optional[int]:
    idx = getattr(fx, "index", None)
    return int(idx) if idx is not None else None


def _zs_merged_range(zs: Any, merged_len: int) -> Tuple[Optional[int], Optional[int]]:
    s = getattr(zs, "start_merged_idx", None)
    e = getattr(zs, "end_merged_idx", None)
    if s is not None and e is not None:
        return int(s), int(e)
    begin = getattr(zs, "begin_bi", None)
    end = getattr(zs, "end_bi", None)
    if begin is not None and end is not None:
        s2, _ = _bi_merged_indices(begin)
        _, e2 = _bi_merged_indices(end)
        if s2 is not None and e2 is not None:
            return s2, e2
    return 0, max(0, merged_len - 1)


def bi_to_chart_json(bi: Any, chart_dt: Callable[[Any], str]) -> Dict[str, Any]:
    s_mi, e_mi = _bi_merged_indices(bi)
    return {
        "index": bi.index,
        "type": bi.type,
        "start_price": bi.start_price,
        "end_price": bi.end_price,
        "start_date": chart_dt(bi.start_time),
        "end_date": chart_dt(bi.end_time),
        "start_merged_idx": s_mi,
        "end_merged_idx": e_mi,
        "buy_sell_point": bi.mmds[0].name if bi.mmds else None,
        "buy_sell_points": [m.name for m in (bi.mmds or [])],
        "divergences": [bc.type for bc in (bi.bcs or []) if getattr(bc, "bc", False)],
        "is_done": bi.is_done() if hasattr(bi, "is_done") else True,
    }


def xd_to_chart_json(xd: Any, chart_dt: Callable[[Any], str]) -> Dict[str, Any]:
    s_mi, e_mi = _xd_merged_indices(xd)
    return {
        "index": xd.index,
        "type": xd.type,
        "start_price": xd.start_price,
        "end_price": xd.end_price,
        "start_date": chart_dt(xd.start_time),
        "end_date": chart_dt(xd.end_time),
        "start_merged_idx": s_mi,
        "end_merged_idx": e_mi,
        "buy_sell_points": [m.name for m in (xd.mmds or [])],
        "divergences": [bc.type for bc in (xd.bcs or []) if getattr(bc, "bc", False)],
        "is_done": xd.is_done() if hasattr(xd, "is_done") else True,
    }


def zs_to_chart_json(zs: Any, chart_dt: Callable[[Any], str], merged_len: int) -> Dict[str, Any]:
    s_mi, e_mi = _zs_merged_range(zs, merged_len)
    return {
        "index": zs.index,
        "zg": zs.zg,
        "zd": zs.zd,
        "gg": zs.gg,
        "dd": zs.dd,
        "relation": getattr(zs, "relation", "new"),
        "direction": getattr(zs, "direction", "zd"),
        "zs_type": getattr(zs, "zs_type", "bi"),
        "is_sure": bool(getattr(zs, "is_sure", True)),
        "start_date": chart_dt(zs.start_time),
        "end_date": chart_dt(zs.end_time),
        "start_merged_idx": s_mi,
        "end_merged_idx": e_mi,
    }


def fx_to_chart_json(fx: Any, chart_dt: Callable[[Any], str]) -> Dict[str, Any]:
    return {
        "index": fx.index,
        "type": fx.type,
        "price": fx.val,
        "date": chart_dt(fx.time),
        "merged_idx": _fx_merged_index(fx),
    }
