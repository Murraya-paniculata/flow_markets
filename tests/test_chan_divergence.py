"""0.2.3：背驰 bcs → signal.divergences / bi.divergence。"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from app.services.chan.backend import ChanEngineICL
from app.services.chan.divergence import (
    _check_bi_divergence,
    attach_bcs_from_engine_bsp,
)
from app.services.chan.structure import _collect_signals, build_chan_structure_snapshot
from app.services.chan.types import SimpleBi, SimpleFX


def _synthetic_klines(n: int = 200) -> list[dict]:
    base = datetime.now() - timedelta(hours=n)
    rows = []
    price = 65000.0
    for i in range(n):
        t = base + timedelta(hours=i)
        drift = (i % 11 - 5) * 100
        o = price + drift
        h = o + 200
        l = o - 200
        c = o + (60 if i % 2 == 0 else -60)
        price = c
        rows.append(
            {
                "date": t,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
            }
        )
    return rows


def test_strength_divergence_detects_weaker_same_direction_bi():
    t = datetime.now()
    fx = SimpleFX("ding", 0, None, 100.0, t, 0)
    prev = SimpleBi(0, "up", fx, fx, 0, 1, is_done=True)
    prev.end_price = 110.0
    prev.strength = 10.0
    curr = SimpleBi(1, "up", fx, fx, 1, 2, is_done=True)
    curr.end_price = 115.0
    curr.strength = 5.0
    assert _check_bi_divergence(prev, curr) is True


def test_engine_attaches_bcs_and_exports_to_signal():
    rows = _synthetic_klines(200)
    raw = [
        {
            "open_time": r["date"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
        }
        for r in rows
    ]
    df = pd.DataFrame(rows)
    icl = ChanEngineICL("BTC/USDT", "1h", {}).process_klines(df)
    total_bcs = sum(len(b.bcs or []) for b in icl.get_bis()) + sum(
        len(x.bcs or []) for x in icl.get_xds()
    )
    assert total_bcs >= 1
    sig = _collect_signals(icl)
    assert sig.divergences
    for t in sig.divergences:
        assert t in ("bi", "xd", "pz", "qs", "zsd")
    with patch("app.services.chan.structure.get_klines_beijing", return_value=raw):
        with patch("app.services.chan.structure._run_chan_engine", return_value=icl):
            snap = build_chan_structure_snapshot("BTCUSDT", "1h", lookback=200)
    assert snap.signal.divergences
    assert any(b.divergence for b in snap.bi)


def test_bsp1_maps_1p_to_pz_bc():
    """盘整一类 BSP 应映射为 pz 背驰类型。"""
    from unittest.mock import MagicMock

    class _T1P:
        value = "1p"

    t = datetime.now()
    fx = SimpleFX("ding", 0, None, 100.0, t, 0)
    bi = SimpleBi(2, "down", fx, fx, 0, 2, is_done=True)
    bis = [bi, bi, bi]
    bsp = MagicMock()
    bsp.bi = MagicMock(idx=2)
    bsp.type = [_T1P()]
    kl_data = MagicMock()
    kl_data.bs_point_lst.bsp1_list = [bsp]
    kl_data.seg_bs_point_lst.bsp1_list = []
    attach_bcs_from_engine_bsp(kl_data, bis, [], [], [], {})
    assert len(bi.bcs) == 1
    assert bi.bcs[0].type == "pz"
    assert bi.bcs[0].bc is True
