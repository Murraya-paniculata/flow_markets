"""get_chan_structure 工具与结构快照契约测试。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from app.crews.tools.get_chan_structure import GetChanStructureTool
from app.schemas.chan_structure import ChanStructureSnapshot
from app.services.chan.backend import ENGINE_ID, ChanEngineICL
from app.services.chan.structure import _bi_item, _segment_item, build_chan_structure_snapshot
from app.services.chan.types import SimpleBi, SimpleFX, SimpleXD


def _synthetic_klines(n: int = 120) -> list[dict]:
    base = datetime.now() - timedelta(hours=n)
    rows = []
    price = 65000.0
    for i in range(n):
        t = base + timedelta(hours=i)
        drift = (i % 7 - 3) * 80
        o = price + drift
        h = o + 120
        l = o - 120
        c = o + (40 if i % 2 == 0 else -40)
        price = c
        rows.append(
            {
                "open_time": t,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
            }
        )
    return rows


def test_bi_and_segment_is_done_follow_engine():
    """0.2.1：导出 JSON 的 is_done 须来自引擎笔/段确认状态，不得写死 True。"""
    t = datetime.now()
    fx = SimpleFX("ding", 0, None, 100.0, t, 0)
    done_bi = SimpleBi(0, "up", fx, fx, 0, 1, is_done=True)
    open_bi = SimpleBi(1, "down", fx, fx, 1, 2, is_done=False)
    assert _bi_item(done_bi).is_done is True
    assert _bi_item(open_bi).is_done is False

    seg_done = SimpleXD(0, "up", done_bi, done_bi, [done_bi], is_done=True)
    seg_open = SimpleXD(1, "down", open_bi, open_bi, [open_bi], is_done=False)
    assert _segment_item(seg_done).is_done is True
    assert _segment_item(seg_open).is_done is False


def test_snapshot_schema_from_synthetic_klines():
    raw = _synthetic_klines(120)
    engine = [
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
    df = pd.DataFrame(engine)
    icl = ChanEngineICL("BTC/USDT", "1h", {}).process_klines(df)

    with patch(
        "app.services.chan.structure.get_klines_beijing",
        return_value=raw,
    ):
        with patch(
            "app.services.chan.structure._run_chan_engine",
            return_value=icl,
        ):
            snap = build_chan_structure_snapshot("BTCUSDT", "1h", lookback=120)

    validated = ChanStructureSnapshot.model_validate(snap.model_dump())
    assert validated.meta.engine == ENGINE_ID
    assert validated.meta.data_size.kline == 120
    assert validated.market.latest_price == raw[-1]["close"]
    assert validated.structure_summary.trend_description
    # 最后一笔/段可能为未确认；导出须保留布尔值而非一律 True
    assert isinstance(validated.bi[-1].is_done, bool)
    if len(validated.segment) > 0:
        assert isinstance(validated.segment[-1].is_done, bool)


def test_tool_returns_ok_envelope():
    raw = _synthetic_klines(80)
    engine = [
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
    df = pd.DataFrame(engine)
    icl = ChanEngineICL("ETH/USDT", "4h", {}).process_klines(df)

    with patch(
        "app.services.chan.structure.get_klines_beijing",
        return_value=raw,
    ):
        with patch(
            "app.services.chan.structure._run_chan_engine",
            return_value=icl,
        ):
            out = GetChanStructureTool()._run(symbol="ETHUSDT", timeframe="4h", lookback=80)

    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["partial"] is False
    assert "data" in payload
    assert payload["data"]["meta"]["symbol"] == "ETH/USDT"


def test_tool_insufficient_data():
    with patch(
        "app.services.chan.structure.get_klines_beijing",
        return_value=[{"open_time": datetime.now(), "open": 1, "high": 2, "low": 0.5, "close": 1.5}],
    ):
        out = GetChanStructureTool()._run(symbol="BTCUSDT", timeframe="1h", lookback=50)

    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["error_code"] == "INSUFFICIENT_DATA"


@pytest.mark.skip(reason="需访问 Binance")
def test_live_binance_snapshot():
    snap = build_chan_structure_snapshot("BTCUSDT", "1h", lookback=200)
    assert len(snap.bi) <= 15
    assert snap.meta.data_size.kline >= 50
