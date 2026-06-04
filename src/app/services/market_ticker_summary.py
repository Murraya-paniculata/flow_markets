"""Binance 现货 24h 行情 + U 本位永续资金费率摘要（Phase 6.2 市场/情绪 Agent 工具）。"""

from __future__ import annotations

import json
from typing import Any

import requests

from app.observability.logging import get_logger

logger = get_logger(__name__)

_SPOT_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
_FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
_TIMEOUT = 15


def _normalize_binance_symbol(symbol: str) -> tuple[str, str]:
    raw = (symbol or "").strip().upper().replace("/", "").replace("-", "")
    if not raw:
        raise ValueError("symbol 不能为空")
    if len(raw) >= 6 and raw.endswith("USDT"):
        base = raw[:-4]
        display = f"{base}/USDT"
    else:
        display = raw
    return raw, display


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_market_ticker_summary(symbol: str) -> dict[str, Any]:
    """
    拉取标的公开行情摘要（现货 24h ticker；USDT 永续尝试资金费率）。

    不调用 LLM；失败时 ``ok=false`` 并附 ``error``。
    """
    sym, display = _normalize_binance_symbol(symbol)
    out: dict[str, Any] = {
        "ok": True,
        "symbol": display,
        "binance_symbol": sym,
        "source": "binance_public_api",
    }

    try:
        resp = requests.get(
            _SPOT_TICKER_URL,
            params={"symbol": sym},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        row = resp.json()
    except requests.RequestException as exc:
        logger.warning("spot_ticker_failed", symbol=sym, error=str(exc))
        return {
            "ok": False,
            "symbol": display,
            "binance_symbol": sym,
            "error": f"现货 24h 行情获取失败: {exc}",
        }

    if not isinstance(row, dict):
        return {
            "ok": False,
            "symbol": display,
            "binance_symbol": sym,
            "error": "现货行情响应格式异常",
        }

    last = _safe_float(row.get("lastPrice"))
    change_pct = _safe_float(row.get("priceChangePercent"))
    high = _safe_float(row.get("highPrice"))
    low = _safe_float(row.get("lowPrice"))
    volume = _safe_float(row.get("volume"))
    quote_volume = _safe_float(row.get("quoteVolume"))
    weighted_avg = _safe_float(row.get("weightedAvgPrice"))

    out["spot_24h"] = {
        "last_price": last,
        "price_change_percent_24h": change_pct,
        "high_24h": high,
        "low_24h": low,
        "volume_base": volume,
        "volume_quote_usdt": quote_volume,
        "weighted_avg_price": weighted_avg,
    }

    if sym.endswith("USDT"):
        try:
            fresp = requests.get(
                _FUNDING_URL,
                params={"symbol": sym},
                timeout=_TIMEOUT,
            )
            fresp.raise_for_status()
            funding = fresp.json()
            if isinstance(funding, dict):
                out["perpetual_usdt"] = {
                    "mark_price": _safe_float(funding.get("markPrice")),
                    "index_price": _safe_float(funding.get("indexPrice")),
                    "last_funding_rate": _safe_float(funding.get("lastFundingRate")),
                    "next_funding_time_ms": funding.get("nextFundingTime"),
                }
        except requests.RequestException as exc:
            logger.info("funding_fetch_skipped", symbol=sym, error=str(exc))
            out["perpetual_usdt"] = {
                "note": "U 本位永续资金费率暂不可用",
                "error": str(exc),
            }

    return out


def format_market_ticker_summary(payload: dict[str, Any]) -> str:
    """格式化为 Agent 可读文本。"""
    return json.dumps(payload, ensure_ascii=False, indent=2)
