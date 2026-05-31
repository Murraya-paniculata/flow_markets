"""Phase 3.4：APP_KLINE_MODE / get_klines 调度。"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from app.core.config import Settings, get_settings
from app.services.chan.analyze import build_kline_chart_payload
from app.services.chan.backend import ChanEngineICL
from app.services.chan.kline import get_klines, resolve_kline_mode


def _synthetic_klines(n: int = 120) -> list[dict]:
    base = datetime.now() - timedelta(hours=n)
    rows = []
    price = 65000.0
    for i in range(n):
        t = base + timedelta(hours=i)
        t_end = t + timedelta(hours=1) - timedelta(milliseconds=1)
        o = price + i * 10
        rows.append(
            {
                "open_time": t,
                "close_time": t_end,
                "open": o,
                "high": o + 50,
                "low": o - 50,
                "close": o + 5,
            }
        )
    return rows


def test_settings_kline_mode_default() -> None:
    s = Settings(_env_file=None)
    assert s.kline_mode == "utc"


def test_resolve_kline_mode_explicit() -> None:
    assert resolve_kline_mode("beijing") == "beijing"
    assert resolve_kline_mode("utc") == "utc"


def test_resolve_kline_mode_default_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_KLINE_MODE", raising=False)
    get_settings.cache_clear()
    assert resolve_kline_mode() == "utc"
    get_settings.cache_clear()


def test_resolve_kline_mode_invalid() -> None:
    with pytest.raises(ValueError, match="不支持的 kline_mode"):
        resolve_kline_mode("invalid")


def test_get_klines_dispatches_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def fake_paginated(symbol: str, interval: str, total: int) -> list:
        called.append("utc")
        return _synthetic_klines(min(total, 60))

    monkeypatch.setattr("app.services.chan.kline.fetch_klines_paginated", fake_paginated)
    out = get_klines("BTCUSDT", "1h", 100, mode="utc")
    assert called == ["utc"]
    assert len(out) == 60


def test_get_klines_dispatches_beijing(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def fake_bj(symbol: str, interval: str, limit: int) -> list:
        called.append("beijing")
        return _synthetic_klines(limit)

    monkeypatch.setattr("app.services.chan.kline.get_klines_beijing", fake_bj)
    get_klines("BTCUSDT", "1h", 100, mode="beijing")
    assert called == ["beijing"]


def test_build_kline_chart_payload_meta_kline_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _synthetic_klines(120)

    def fake_engine(code: str, freq: str, klines: list) -> ChanEngineICL:
        df = pd.DataFrame(klines)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return ChanEngineICL(code, freq, {}).process_klines(df)

    monkeypatch.setattr("app.services.chan.analyze.get_klines", lambda *a, **k: raw)
    monkeypatch.setattr("app.services.chan.analyze._run_chan_engine", fake_engine)

    payload_utc = build_kline_chart_payload("BTCUSDT", "1h", limit=120, kline_mode="utc")
    assert payload_utc["meta"]["kline_mode"] == "utc"
    assert payload_utc["meta"]["timezone"] == "UTC"
    assert payload_utc["meta"]["base_interval"] == "native"

    payload_bj = build_kline_chart_payload("BTCUSDT", "1h", limit=120, kline_mode="beijing")
    assert payload_bj["meta"]["kline_mode"] == "beijing"
    assert payload_bj["meta"]["timezone"] == "Asia/Shanghai"
    assert payload_bj["meta"]["base_interval"] == "5m"
