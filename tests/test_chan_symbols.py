"""Binance symbol 规范化。"""
from __future__ import annotations

import pytest

from app.services.chan.symbols import (
    is_placeholder_symbol,
    normalize_binance_symbol,
)


def test_btc_to_btcusdt():
    b, d = normalize_binance_symbol("BTC")
    assert b == "BTCUSDT"
    assert d == "BTC/USDT"


def test_slash_form():
    b, d = normalize_binance_symbol("eth/usdt")
    assert b == "ETHUSDT"
    assert d == "ETH/USDT"


def test_already_full():
    b, d = normalize_binance_symbol("BTCUSDT")
    assert b == "BTCUSDT"
    assert d == "BTC/USDT"


def test_placeholder_rejected():
    assert is_placeholder_symbol("未指定")
    assert is_placeholder_symbol("（未指定）")
    with pytest.raises(ValueError, match="未指定"):
        normalize_binance_symbol("未指定")


def test_invalid_symbol_rejected():
    with pytest.raises(ValueError):
        normalize_binance_symbol("!!!")
