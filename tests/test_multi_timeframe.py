"""Phase 3.1：MultiTimeframeService。"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.schemas.chan_structure import (
    ChanDataSize,
    ChanMarket,
    ChanMeta,
    ChanSignal,
    ChanStructureSnapshot,
    ChanStructureSummary,
    MultiTimeframeLevelResult,
)
from app.services.chan.multi_timeframe import (
    DEFAULT_MULTI_TF_LEVELS,
    MultiTimeframeService,
    build_multi_timeframe_snapshot,
    combine_multi_timeframe_judgment,
    format_multi_timeframe_for_prompt,
)


def _fake_snapshot(trend: str, pos: str, interval: str, price: float = 65000.0) -> ChanStructureSnapshot:
    return ChanStructureSnapshot(
        meta=ChanMeta(
            symbol="BTC/USDT",
            interval=interval,
            timestamp=datetime.now().isoformat(),
            data_size=ChanDataSize(kline=100, bi=10, segment=3, center=2),
        ),
        market=ChanMarket(latest_price=price),
        bi=[],
        segment=[],
        center=[],
        signal=ChanSignal(buy_sell_points=["1buy"] if trend == "up_trend" else []),
        structure_summary=ChanStructureSummary(trend=trend, price_position=pos),
    )


def test_default_levels_config() -> None:
    assert set(DEFAULT_MULTI_TF_LEVELS) == {"large", "medium", "small"}
    assert DEFAULT_MULTI_TF_LEVELS["large"]["timeframe"] == "4h"
    assert DEFAULT_MULTI_TF_LEVELS["medium"]["timeframe"] == "1h"
    assert DEFAULT_MULTI_TF_LEVELS["small"]["timeframe"] == "15m"


def test_combine_judgment_aligned_up() -> None:
    levels = {
        "large": MultiTimeframeLevelResult(
            ok=True,
            level_key="large",
            name="大级别",
            timeframe="4h",
            lookback=300,
            snapshot=_fake_snapshot("up_trend", "above_zs", "4h"),
            summary={"trend": "up_trend", "price_position": "above_zs", "signals": []},
        ),
        "medium": MultiTimeframeLevelResult(
            ok=True,
            level_key="medium",
            name="中级别",
            timeframe="1h",
            lookback=300,
            snapshot=_fake_snapshot("up_trend", "inside_zs", "1h"),
            summary={"trend": "up_trend", "price_position": "inside_zs", "signals": ["1buy"]},
        ),
        "small": MultiTimeframeLevelResult(
            ok=True,
            level_key="small",
            name="小级别",
            timeframe="15m",
            lookback=300,
            snapshot=_fake_snapshot("up_trend", "above_zs", "15m"),
            summary={"trend": "up_trend", "price_position": "above_zs", "signals": []},
        ),
    }
    j = combine_multi_timeframe_judgment(levels)
    assert j.main_trend == "up"
    assert j.trend_strength == "strong"
    assert j.resonance == "aligned"
    assert "多级别共振摘要" in j.prompt_text
    assert j.buy_signals == ["1buy"]


def test_combine_judgment_insufficient_levels() -> None:
    levels = {
        "large": MultiTimeframeLevelResult(
            ok=True,
            level_key="large",
            name="大",
            timeframe="4h",
            lookback=300,
            summary={"trend": "up_trend", "price_position": "above_zs"},
        ),
        "medium": MultiTimeframeLevelResult(
            ok=False,
            level_key="medium",
            name="中",
            timeframe="1h",
            lookback=300,
            error="network",
        ),
        "small": MultiTimeframeLevelResult(
            ok=False,
            level_key="small",
            name="小",
            timeframe="15m",
            lookback=300,
            error="network",
        ),
    }
    j = combine_multi_timeframe_judgment(levels)
    assert j.main_trend == "unknown"
    assert "不足" in j.prompt_text


def test_combine_judgment_mixed_range() -> None:
    levels = {
        "large": MultiTimeframeLevelResult(
            ok=True,
            level_key="large",
            name="大",
            timeframe="4h",
            lookback=300,
            summary={"trend": "up_trend", "price_position": "above_zs", "signals": []},
        ),
        "medium": MultiTimeframeLevelResult(
            ok=True,
            level_key="medium",
            name="中",
            timeframe="1h",
            lookback=300,
            summary={"trend": "consolidation", "price_position": "inside_zs", "signals": []},
        ),
        "small": MultiTimeframeLevelResult(
            ok=True,
            level_key="small",
            name="小",
            timeframe="15m",
            lookback=300,
            summary={"trend": "down_trend", "price_position": "below_zs", "signals": []},
        ),
    }
    j = combine_multi_timeframe_judgment(levels)
    assert j.main_trend == "range"
    assert j.resonance == "mixed"


def test_multi_timeframe_service_with_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_build(symbol: str, timeframe: str, lookback: int = 300, **kwargs):
        trend_map = {"4h": "up_trend", "1h": "consolidation", "15m": "up_trend"}
        pos_map = {"4h": "above_zs", "1h": "inside_zs", "15m": "above_zs"}
        price_map = {"4h": 65000.0, "1h": 64950.0, "15m": 64980.0}
        return _fake_snapshot(
            trend_map.get(timeframe, "unknown"),
            pos_map.get(timeframe, "unknown"),
            timeframe,
            price_map.get(timeframe, 65000.0),
        )

    monkeypatch.setattr(
        "app.services.chan.multi_timeframe.build_chan_structure_snapshot",
        fake_build,
    )
    snap = MultiTimeframeService("BTCUSDT").build_snapshot()
    assert snap.meta["symbol"] == "BTC/USDT"
    assert snap.meta["latest_price"] == 64980.0
    assert len(snap.levels) == 3
    assert all(lv.ok for lv in snap.levels.values())
    assert snap.partial is False
    assert snap.combined_judgment.main_trend in ("up", "down", "range")


def test_multi_timeframe_service_partial_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_build(symbol: str, timeframe: str, lookback: int = 300, **kwargs):
        if timeframe == "15m":
            raise ValueError("K 线不足")
        return _fake_snapshot("up_trend", "above_zs", timeframe)

    monkeypatch.setattr(
        "app.services.chan.multi_timeframe.build_chan_structure_snapshot",
        fake_build,
    )
    snap = build_multi_timeframe_snapshot("BTCUSDT")
    assert snap.partial is True
    assert snap.levels["small"].ok is False
    assert snap.levels["small"].error is not None
    assert snap.levels["large"].ok is True
    assert snap.combined_judgment.main_trend == "up"


def test_format_multi_timeframe_for_prompt_medium_has_snapshot() -> None:
    snap = MultiTimeframeService("BTCUSDT", levels=DEFAULT_MULTI_TF_LEVELS)
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "app.services.chan.multi_timeframe.build_chan_structure_snapshot",
        side_effect=lambda sym, tf, lookback=300, **kw: _fake_snapshot(
            "up_trend", "above_zs", tf
        ),
    ):
        built = snap.build_snapshot()
    text = format_multi_timeframe_for_prompt(built)
    import json

    payload = json.loads(text)
    assert payload["combined_judgment"]["main_trend"] == "up"
    assert "snapshot" in payload["levels"]["medium"]
    assert "snapshot" not in payload["levels"]["large"]
    assert "snapshot" not in payload["levels"]["small"]


def test_build_technical_crew_inputs_single_and_multi() -> None:
    from app.crews.flows.flow_markets import _build_technical_crew_inputs

    single = _build_technical_crew_inputs(
        user_query="q",
        symbol="BTCUSDT",
        notes="n",
        timeframe="4h",
        lookback=200,
        analysis_mode="single",
    )
    assert single["analysis_mode"] == "single"
    assert single["primary_timeframe"] == "4h"
    assert single["lookback"] == "200"
    assert "单周期" in single["multi_timeframe_context"]

    multi = _build_technical_crew_inputs(
        user_query="q",
        symbol="BTCUSDT",
        notes="n",
        timeframe="4h",
        lookback=300,
        analysis_mode="multi_timeframe",
        multi_timeframe_context='{"levels":{}}',
    )
    assert multi["analysis_mode"] == "multi_timeframe"
    assert multi["primary_timeframe"] == "1h"
    assert multi["multi_timeframe_context"].startswith("{")
