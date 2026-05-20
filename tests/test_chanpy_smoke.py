"""缠论模块冒烟测试。"""
from __future__ import annotations

import pytest

from app.services.chan.backend import _bundled_chanpy_dir, ensure_chanpy_importable, get_chanpy_root


def test_bundled_chanpy_exists():
    d = _bundled_chanpy_dir()
    assert d.is_dir() and (d / "Chan.py").is_file()


def test_chanpy_import():
    assert get_chanpy_root() == _bundled_chanpy_dir()
    ensure_chanpy_importable()
    from Chan import CChan  # noqa: F401


@pytest.mark.skip(reason="需访问 Binance")
def test_build_kline_chart_payload():
    from app.services.chan import build_kline_chart_payload

    p = build_kline_chart_payload("BTCUSDT", "1d", limit=200)
    assert p["meta"]["engine"] == "chanpy"
    assert len(p["klines"]) >= 50
