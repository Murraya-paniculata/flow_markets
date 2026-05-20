"""Binance K 线拉取 + 北京时间 5m 基准多周期聚合。"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

_BASE_URL = "https://api.binance.com"
_KLINES_PATH = "/api/v3/klines"
BEIJING = ZoneInfo("Asia/Shanghai")

SUPPORTED_INTERVALS = ("5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M")
INTERVAL_ALIASES: Dict[str, str] = {"60m": "1h", "240m": "4h", "1mon": "1M", "1month": "1M"}

_FIVE_MIN_PER_BAR: Dict[str, int] = {
    "5m": 1, "15m": 3, "30m": 6, "1h": 12, "4h": 48, "1d": 288, "1w": 288 * 7, "1M": 288 * 31,
}
MAX_LIMIT_BY_INTERVAL: Dict[str, int] = {
    "5m": 800, "15m": 500, "30m": 400, "1h": 350, "4h": 300, "1d": 500, "1w": 104, "1M": 60,
}
_CACHE_TTL_SEC = 60
_cache: Dict[Tuple[str, str, int], Tuple[float, List[Dict[str, Any]]]] = {}


def normalize_interval(interval: str) -> str:
    iv = INTERVAL_ALIASES.get((interval or "1h").strip(), (interval or "1h").strip())
    if iv not in SUPPORTED_INTERVALS:
        raise ValueError(f"不支持的周期: {interval}，可选: {', '.join(SUPPORTED_INTERVALS)}")
    return iv


def cap_limit(interval: str, limit: int) -> int:
    cap = MAX_LIMIT_BY_INTERVAL.get(normalize_interval(interval), 350)
    return max(1, min(int(limit), cap))


def fetch_klines_raw(
    symbol: str,
    interval: str,
    limit: int,
    start_time: int | None = None,
    end_time: int | None = None,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """Binance /api/v3/klines → UTC datetime 字典列表。"""
    params: Dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time is not None:
        params["startTime"] = int(start_time)
    if end_time is not None:
        params["endTime"] = int(end_time)

    data = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(_BASE_URL + _KLINES_PATH, params=params, timeout=10)
            if not resp.ok:
                raise RuntimeError(f"Binance HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            if not isinstance(data, list):
                raise RuntimeError(f"Binance 返回格式异常: {data}")
            break
        except requests.RequestException as exc:
            if attempt >= max_retries - 1:
                raise RuntimeError(f"Binance 请求失败: {exc}") from exc
            time.sleep(2**attempt)

    results: List[Dict[str, Any]] = []
    for item in data or []:
        if not (isinstance(item, (list, tuple)) and len(item) >= 7):
            raise RuntimeError(f"K 线格式异常: {item}")
        open_dt = datetime.fromtimestamp(int(item[0]) / 1000.0, tz=timezone.utc)
        close_dt = datetime.fromtimestamp(int(item[6]) / 1000.0, tz=timezone.utc)
        results.append({
            "open_time": open_dt,
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "close_time": close_dt,
        })
    results.sort(key=lambda x: x["open_time"])
    return results


def to_beijing(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING)


def beijing_to_utc(dt_bj: datetime) -> datetime:
    if dt_bj.tzinfo is None:
        dt_bj = dt_bj.replace(tzinfo=BEIJING)
    return dt_bj.astimezone(timezone.utc)


def _floor_beijing_5m(dt: datetime) -> datetime:
    bj = to_beijing(dt)
    total_min = bj.hour * 60 + bj.minute
    floored = (total_min // 5) * 5
    return bj.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def _bucket_15m(dt: datetime) -> datetime:
    bj = to_beijing(dt)
    total_min = bj.hour * 60 + bj.minute
    floored = (total_min // 15) * 15
    return bj.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def _bucket_30m(dt: datetime) -> datetime:
    bj = to_beijing(dt)
    total_min = bj.hour * 60 + bj.minute
    floored = (total_min // 30) * 30
    return bj.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def _bucket_1h(dt: datetime) -> datetime:
    bj = to_beijing(dt)
    return bj.replace(minute=0, second=0, microsecond=0)


def _bucket_4h(dt: datetime) -> datetime:
    bj = to_beijing(dt)
    return bj.replace(hour=(bj.hour // 4) * 4, minute=0, second=0, microsecond=0)


def _bucket_1d(dt: datetime) -> datetime:
    bj = to_beijing(dt)
    return bj.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket_1w(dt: datetime) -> datetime:
    bj = to_beijing(dt)
    monday = bj - timedelta(days=bj.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket_1M(dt: datetime) -> datetime:
    bj = to_beijing(dt)
    return bj.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _bucket_fn(interval: str) -> Callable[[datetime], datetime]:
    return {
        "5m": _floor_beijing_5m, "15m": _bucket_15m, "30m": _bucket_30m,
        "1h": _bucket_1h, "4h": _bucket_4h, "1d": _bucket_1d, "1w": _bucket_1w, "1M": _bucket_1M,
    }[interval]


def _merge_bar(target: Optional[Dict[str, Any]], src: Dict[str, Any]) -> Dict[str, Any]:
    if target is None:
        return dict(src)
    target["high"] = max(target["high"], src["high"])
    target["low"] = min(target["low"], src["low"])
    target["close"] = src["close"]
    target["close_time"] = src["close_time"]
    return target


def _aggregate_bars(bars: List[Dict[str, Any]], bucket: Callable[[datetime], datetime]) -> List[Dict[str, Any]]:
    groups: Dict[datetime, Dict[str, Any]] = {}
    order: List[datetime] = []
    for bar in sorted(bars, key=lambda x: x["open_time"]):
        bj_key = bucket(bar["open_time"])
        if bj_key not in groups:
            groups[bj_key] = {
                "open_time": beijing_to_utc(bj_key),
                "open": bar["open"], "high": bar["high"], "low": bar["low"],
                "close": bar["close"], "close_time": bar["close_time"],
            }
            order.append(bj_key)
        else:
            groups[bj_key] = _merge_bar(groups[bj_key], bar)
    return [groups[k] for k in order]


def fetch_klines_paginated(symbol: str, interval: str, total_bars: int) -> List[Dict[str, Any]]:
    if total_bars <= 0:
        return []
    collected: List[Dict[str, Any]] = []
    end_ms: Optional[int] = None
    while len(collected) < total_bars:
        batch_limit = min(1000, total_bars - len(collected))
        chunk = fetch_klines_raw(symbol, interval, batch_limit, end_time=end_ms)
        if not chunk:
            break
        if end_ms is not None and collected:
            earliest = collected[0]["open_time"]
            chunk = [c for c in chunk if c["open_time"] < earliest]
            if not chunk:
                break
        collected = chunk + collected
        end_ms = int(collected[0]["open_time"].timestamp() * 1000) - 1
        if len(chunk) < batch_limit:
            break
    return collected[-total_bars:] if len(collected) > total_bars else collected


def get_klines_beijing(symbol: str, interval: str, limit: int = 500) -> List[Dict[str, Any]]:
    """北京时间对齐 K 线（5m 分页拉取后合成目标周期）。"""
    iv = normalize_interval(interval)
    limit = cap_limit(iv, limit)
    cache_key = (symbol.upper(), iv, limit)
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    need_5m = limit * _FIVE_MIN_PER_BAR[iv] + 5
    bars_5m = _aggregate_bars(fetch_klines_paginated(symbol, "5m", need_5m), _floor_beijing_5m)
    if not bars_5m:
        return []
    result = bars_5m if iv == "5m" else _aggregate_bars(bars_5m, _bucket_fn(iv))
    if len(result) > limit:
        result = result[-limit:]
    _cache[cache_key] = (now + _CACHE_TTL_SEC, result)
    return result
