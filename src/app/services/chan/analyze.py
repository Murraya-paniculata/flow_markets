"""拉取 K 线并计算缠论结构，组装 API 图表载荷。"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import pandas as pd

from app.core.config import get_settings

from .backend import ChanpyICL
from .chart import (
    bi_to_chart_json,
    fx_to_chart_json,
    merged_klines_to_json,
    to_frontend_bars,
    xd_to_chart_json,
    zs_to_chart_json,
)
from .kline import cap_limit, get_klines_beijing, normalize_interval


def _chart_dt(dt: Any) -> str:
    if dt is None:
        return ""
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    s = str(dt)
    if " " in s and "T" not in s[:20]:
        return s.replace(" ", "T", 1)
    return s


def _apply_chanpy_root() -> None:
    root = (get_settings().chanpy_root or "").strip()
    if root and not os.environ.get("CHANPY_ROOT"):
        os.environ["CHANPY_ROOT"] = root


def _run_chanpy(code: str, frequency: str, klines: List[Dict[str, Any]]) -> ChanpyICL:
    if len(klines) < 50:
        raise ValueError(f"K 线数量不足，至少需要 50 根，当前 {len(klines)} 根")
    df = pd.DataFrame(klines)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        raise ValueError("K 线 date 字段无效")
    return ChanpyICL(code, frequency, {}).process_klines(df)


def build_kline_chart_payload(
    symbol: str,
    interval: str,
    limit: int = 350,
) -> Dict[str, Any]:
    _apply_chanpy_root()

    interval_norm = normalize_interval(interval)
    effective_limit = cap_limit(interval_norm, limit)
    raw = get_klines_beijing(symbol, interval_norm, effective_limit)
    if not raw or len(raw) < 3:
        raise ValueError("Insufficient kline data")

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
    icl = _run_chanpy(symbol, interval_norm, engine_klines)

    bi_zs = icl.get_bi_zss()
    xd_zs = icl.get_xd_zss() if hasattr(icl, "get_xd_zss") else []
    zs_list = list(bi_zs) + list(xd_zs)

    frontend_bars = to_frontend_bars(raw)
    merged_json = merged_klines_to_json(
        icl.get_merged_klines() if hasattr(icl, "get_merged_klines") else [],
        frontend_bars,
        dt_format=_chart_dt,
    )
    merged_len = len(merged_json)

    return {
        "meta": {
            "symbol": symbol,
            "interval": interval_norm,
            "timezone": "Asia/Shanghai",
            "base_interval": "5m",
            "chart_axis": "merged" if merged_len >= 3 else "time",
            "merged_count": merged_len,
            "count": len(frontend_bars),
            "limit": effective_limit,
            "engine": "chanpy",
        },
        "klines": frontend_bars,
        "merged_klines": merged_json,
        "bi": [bi_to_chart_json(b, _chart_dt) for b in icl.get_bis()],
        "xd": [xd_to_chart_json(x, _chart_dt) for x in icl.get_xds()],
        "zs": [zs_to_chart_json(z, _chart_dt, merged_len) for z in zs_list],
        "fx": [fx_to_chart_json(f, _chart_dt) for f in icl.get_fx_list()],
        "bsp": icl.get_bsp_list() if hasattr(icl, "get_bsp_list") else [],
    }
