"""0.2.4：笔级 MACD 力度与导出。"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
from app.services.chan.backend import ChanEngineICL
from app.services.chan.macd_strength import compute_macd_hist
from app.services.chan.structure import build_chan_structure_snapshot


def _synthetic_df(n: int = 120) -> pd.DataFrame:
    base = datetime.now() - timedelta(hours=n)
    rows = []
    price = 65000.0
    for i in range(n):
        t = base + timedelta(hours=i)
        drift = (i % 7 - 3) * 80
        o = price + drift
        c = o + (40 if i % 2 == 0 else -40)
        price = c
        rows.append({"date": t, "open": o, "high": o + 120, "low": o - 120, "close": c})
    return pd.DataFrame(rows)


def test_compute_macd_hist_length_matches_close():
    df = _synthetic_df(50)
    hist = compute_macd_hist(df["close"])
    assert len(hist) == len(df)


def test_engine_sets_macd_strength_on_bis():
    df = _synthetic_df(120)
    icl = ChanEngineICL("BTC/USDT", "1h", {}).process_klines(df)
    bis = icl.get_bis()
    assert bis
    with_macd = [b for b in bis if b.macd_strength > 0]
    assert with_macd, "至少一笔应有 macd_strength"
    for b in with_macd:
        assert b.strength > 0
        assert b.price_strength > 0


def test_snapshot_exports_macd_strength():
    df = _synthetic_df(120)
    raw = [
        {
            "open_time": r["date"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
        }
        for r in df.to_dict("records")
    ]
    icl = ChanEngineICL("BTC/USDT", "1h", {}).process_klines(df)
    with patch("app.services.chan.structure.get_klines_beijing", return_value=raw):
        with patch("app.services.chan.structure._run_chan_engine", return_value=icl):
            snap = build_chan_structure_snapshot("BTCUSDT", "1h", lookback=120)
    exported = [b for b in snap.bi if b.macd_strength is not None and b.macd_strength > 0]
    assert exported
