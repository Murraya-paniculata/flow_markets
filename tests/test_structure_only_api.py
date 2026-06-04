"""structure_only 服务与 no_ai 流式测试（Phase 5.4）。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services import analyze_streaming as streaming_mod
from app.services.structure_only import StructureOnlyResult, run_structure_only


def test_run_structure_only_single_mock() -> None:
    fake = MagicMock()
    fake.meta.symbol = "BTCUSDT"
    fake.meta.interval = "1h"
    fake.meta.data_size.kline = 100
    fake.meta.data_size.bi = 5
    fake.meta.data_size.segment = 2
    fake.meta.data_size.center = 1
    fake.market.latest_price = 50000.0
    fake.center = []
    fake.bi = []
    fake.signal.buy_sell_points = []
    fake.signal.divergences = []
    fake.structure_summary.trend_description = "升"
    fake.structure_summary.position_description = "上"
    fake.structure_summary.key_levels.zg = 0
    fake.structure_summary.key_levels.zd = 0
    fake.structure_summary.key_levels.gg = 0
    fake.structure_summary.key_levels.dd = 0
    fake.model_dump.return_value = {"symbol": "BTCUSDT"}

    with patch(
        "app.services.structure_only.build_chan_structure_snapshot",
        return_value=fake,
    ):
        result, err = run_structure_only(
            symbol="BTCUSDT",
            timeframe="1h",
            lookback=200,
            multi_tf=False,
        )

    assert err == ""
    assert result is not None
    assert result.multi_tf is False
    assert result.structure_payload["symbol"] == "BTCUSDT"
    assert "结构分析完成" in result.report_content


def test_run_structure_only_requires_symbol() -> None:
    result, err = run_structure_only(symbol="", timeframe="1h")
    assert result is None
    assert "symbol" in err


@pytest.mark.asyncio
async def test_streaming_no_ai_ends_after_structure() -> None:
    fake = MagicMock()
    fake.meta.data_size.kline = 100
    fake.meta.data_size.bi = 5
    fake.meta.data_size.segment = 2
    fake.meta.data_size.center = 1
    fake.model_dump.return_value = {"ok": True}

    struct = StructureOnlyResult(
        report_content="结构完成",
        structure_payload={"ok": True},
        multi_tf=False,
    )

    with (
        patch("app.services.analyze_streaming.get_settings") as mock_settings,
        patch("app.services.analyze_streaming.get_klines", return_value=[{}] * 200),
        patch(
            "app.services.analyze_streaming.build_chan_structure_snapshot",
            return_value=fake,
        ),
        patch("app.services.analyze_streaming._structure_info_lines", return_value=[]),
        patch(
            "app.services.analyze_streaming.structure_payload_from_snapshot",
            return_value=struct,
        ),
    ):
        mock_settings.return_value.llm_api_key = ""
        events: list[dict[str, Any]] = []
        async for ev in streaming_mod.analyze_flow_markets_streaming(
            user_query="结构",
            symbol="BTCUSDT",
            timeframe="1h",
            lookback=200,
            task_id="no_ai_test",
            no_ai=True,
        ):
            events.append(ev)

    phases = [e.get("phase") for e in events if e.get("type") != "result"]
    assert "ai" not in phases
    assert "governance" not in phases
    result = next(e for e in events if e.get("type") == "result")
    assert result["data"]["structure_only"] is True
    assert result["data"]["success"] is True
    assert result["data"]["structure_payload"] == {"ok": True}

    streaming_mod._stream_result_store.pop("no_ai_test", None)
