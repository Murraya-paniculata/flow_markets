"""0.2.5：结构快照与 chanlun ChanlunAIExporter 导出契约对齐（不测数值、不测 LLM）。

chanlun 使用自研 ICL，本仓库使用结构引擎；本模块只锁定 JSON 形状与导出规则，防止 structure.py 漂移。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from app.schemas.chan_structure import ChanStructureSnapshot
from app.services.chan.backend import ENGINE_ID, ChanEngineICL
from app.services.chan.structure import (
    DEFAULT_MAX_BI,
    DEFAULT_MAX_SEGMENT,
    build_chan_structure_snapshot,
)
from app.services.chan.types import SimpleZS

# chanlun_ai_exporter.export() 顶层块（meta.engine 名称按本项目约定为 structure-engine）
EXPORTER_TOP_LEVEL_KEYS = frozenset(
    {
        "meta",
        "market",
        "bi",
        "segment",
        "center",
        "signal",
        "context",
        "structure_summary",
    }
)

META_KEYS = frozenset(
    {"symbol", "interval", "timestamp", "engine", "engine_version", "data_size", "trim"}
)
DATA_SIZE_KEYS = frozenset({"kline", "bi", "segment", "center"})
MARKET_KEYS = frozenset({"latest_price", "trend_hint", "volatility_hint"})
BI_ITEM_KEYS = frozenset(
    {
        "index",
        "direction",
        "is_done",
        "start_time",
        "end_time",
        "start_price",
        "end_price",
        "buy_sell_point",
        "divergence",
        "strength",
        "macd_strength",
        "price_strength",
    }
)
SEGMENT_ITEM_KEYS = frozenset(
    {
        "index",
        "direction",
        "is_done",
        "start_time",
        "end_time",
        "start_price",
        "end_price",
        "buy_sell_point",
        "divergence",
    }
)
CENTER_ITEM_KEYS = frozenset(
    {
        "index",
        "type",
        "zs_type",
        "start_time",
        "end_time",
        "zg",
        "zd",
        "gg",
        "dd",
        "high",
        "low",
        "relation",
        "bi_count",
        "level",
    }
)
SIGNAL_KEYS = frozenset({"buy_sell_points", "divergences", "last_signal_time"})
SUMMARY_KEYS = frozenset(
    {
        "trend",
        "price_position",
        "latest_bi_direction",
        "latest_bi_strength",
        "prev_bi_strength",
        "strength_comparison",
        "key_levels",
        "trend_description",
        "position_description",
    }
)
KEY_LEVELS_KEYS = frozenset({"zg", "zd", "gg", "dd"})
CONTEXT_KEYS = frozenset({"analysis_goal", "market_type", "allowed_strategy"})

TREND_VALUES = frozenset({"up_trend", "down_trend", "consolidation", "unknown"})
POSITION_VALUES = frozenset({"above_zs", "below_zs", "inside_zs", "unknown"})


def _synthetic_klines(n: int = 120) -> list[dict]:
    base = datetime.now() - timedelta(hours=n)
    rows = []
    price = 65000.0
    for i in range(n):
        t = base + timedelta(hours=i)
        drift = (i % 7 - 3) * 80
        o = price + drift
        c = o + (40 if i % 2 == 0 else -40)
        price = c
        rows.append(
            {
                "open_time": t,
                "open": o,
                "high": o + 120,
                "low": o - 120,
                "close": c,
            }
        )
    return rows


def _snapshot_dict(
    *,
    lookback: int = 120,
    max_bi: int = DEFAULT_MAX_BI,
    max_segment: int = DEFAULT_MAX_SEGMENT,
) -> dict[str, Any]:
    raw = _synthetic_klines(lookback)
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
    with patch("app.services.chan.structure.get_klines_beijing", return_value=raw):
        with patch("app.services.chan.structure._run_chan_engine", return_value=icl):
            snap = build_chan_structure_snapshot(
                "BTCUSDT",
                "1h",
                lookback=lookback,
                max_bi=max_bi,
                max_segment=max_segment,
            )
    return snap.model_dump(mode="json")


def _assert_keys(actual: dict[str, Any], expected: frozenset[str], label: str) -> None:
    missing = expected - set(actual.keys())
    extra = set(actual.keys()) - expected
    assert not missing, f"{label} 缺少字段: {sorted(missing)}"
    assert not extra, f"{label} 多出字段: {sorted(extra)}"


def assert_exporter_contract(data: dict[str, Any]) -> None:
    """与 ChanlunAIExporter.export() 对齐的结构性断言（可复用于其它测试）。"""
    _assert_keys(data, EXPORTER_TOP_LEVEL_KEYS, "顶层")

    meta = data["meta"]
    _assert_keys(meta, META_KEYS, "meta")
    _assert_keys(meta["data_size"], DATA_SIZE_KEYS, "meta.data_size")
    assert meta["engine"] == ENGINE_ID
    assert meta["engine_version"] == "flow-markets-v1"

    _assert_keys(data["market"], MARKET_KEYS, "market")
    _assert_keys(data["signal"], SIGNAL_KEYS, "signal")
    _assert_keys(data["context"], CONTEXT_KEYS, "context")
    assert data["context"]["analysis_goal"] == "predict_next_move"
    assert data["context"]["market_type"] == "crypto"
    assert data["context"]["allowed_strategy"] == ["trend_follow", "range_trade"]

    summary = data["structure_summary"]
    _assert_keys(summary, SUMMARY_KEYS, "structure_summary")
    _assert_keys(summary["key_levels"], KEY_LEVELS_KEYS, "structure_summary.key_levels")
    assert summary["trend"] in TREND_VALUES
    assert summary["price_position"] in POSITION_VALUES
    assert summary["trend_description"]
    assert summary["position_description"]

    ds = meta["data_size"]
    assert ds["kline"] >= 50
    assert ds["bi"] >= len(data["bi"])
    assert ds["segment"] >= len(data["segment"])

    trim = meta.get("trim")
    if trim is None:
        assert len(data["bi"]) == ds["bi"] or ds["bi"] <= DEFAULT_MAX_BI
        assert len(data["segment"]) == ds["segment"] or ds["segment"] <= DEFAULT_MAX_SEGMENT
    else:
        if "bi" in trim:
            assert len(data["bi"]) == trim["bi"]
            assert ds["bi"] > trim["bi"]
        if "segment" in trim:
            assert len(data["segment"]) == trim["segment"]
            assert ds["segment"] > trim["segment"]

    for item in data["bi"]:
        _assert_keys(item, BI_ITEM_KEYS, "bi[]")
        assert isinstance(item["is_done"], bool)
    for item in data["segment"]:
        _assert_keys(item, SEGMENT_ITEM_KEYS, "segment[]")
        assert isinstance(item["is_done"], bool)
    for item in data["center"]:
        _assert_keys(item, CENTER_ITEM_KEYS, "center[]")
        assert item["type"] in ("bi", "segment")
        if item.get("zg") is not None and item.get("zd") is not None:
            assert item["zg"] >= item["zd"]

    if len(data["bi"]) >= 2:
        indices = [b["index"] for b in data["bi"]]
        assert indices == sorted(indices), "导出 bi 应按 index 升序（最近 N 条为尾部切片）"


def test_exporter_top_level_matches_chanlun_shape():
    data = _snapshot_dict()
    assert_exporter_contract(data)
    ChanStructureSnapshot.model_validate(data)


def test_exporter_contract_with_trim():
    data = _snapshot_dict(max_bi=5, max_segment=1)
    assert_exporter_contract(data)
    assert data["meta"]["trim"] is not None


def test_center_item_mapping_matches_exporter_fields():
    """中枢项须含 zg/zd/gg/dd 与 level（与 exporter _build_center 一致）。"""
    zs = SimpleZS(
        index=0,
        zs_type="standard",
        direction="zd",
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        zg=100.0,
        zd=90.0,
        gg=105.0,
        dd=88.0,
        relation="new",
        bi_count=3,
    )
    zs.high = zs.zg
    zs.low = zs.zd
    from app.services.chan.structure import _center_item

    item = _center_item(zs, "bi").model_dump()
    _assert_keys(item, CENTER_ITEM_KEYS, "center")
    assert item["zg"] == 100.0
    assert item["level"] == 1
