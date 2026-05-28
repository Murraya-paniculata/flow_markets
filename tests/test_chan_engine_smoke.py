"""缠论结构引擎冒烟测试。"""
from __future__ import annotations

import pytest

from app.services.chan.backend import (
    ENGINE_ID,
    _bundled_engine_dir,
    ensure_chan_engine_importable,
    get_chan_engine_root,
)


def test_bundled_engine_exists():
    d = _bundled_engine_dir()
    assert d.is_dir() and (d / "Chan.py").is_file()


def test_chan_engine_import():
    assert get_chan_engine_root() == _bundled_engine_dir()
    ensure_chan_engine_importable()
    from Chan import CChan  # noqa: F401


@pytest.mark.skip(reason="需访问 Binance")
def test_build_kline_chart_payload():
    from app.services.chan import build_kline_chart_payload

    p = build_kline_chart_payload("BTCUSDT", "1d", limit=200)
    assert p["meta"]["engine"] == ENGINE_ID
    assert len(p["klines"]) >= 50
