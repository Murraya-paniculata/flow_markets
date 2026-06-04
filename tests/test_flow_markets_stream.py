"""FlowMarkets SSE 流式分析测试（Phase 5.2）。"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import analyze_streaming as streaming_mod


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for chunk in body.strip().split("\n\n"):
        if not chunk.strip():
            continue
        event_type: str | None = None
        data: dict[str, Any] | None = None
        for line in chunk.splitlines():
            if line.startswith("event: "):
                event_type = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_type is not None and data is not None:
            events.append((event_type, data))
    return events


async def _fake_stream_success(**_kwargs) -> AsyncGenerator[dict[str, Any], None]:
    yield {
        "level": "step",
        "message": "步骤 1",
        "step": 1,
        "total_steps": 4,
        "phase": "kline",
    }
    yield {
        "level": "success",
        "message": "步骤 4 完成",
        "step": 4,
        "total_steps": 4,
        "phase": "governance",
    }
    yield {
        "type": "result",
        "data": {
            "success": True,
            "message": "分析完成",
            "report_content": "# 测试报告",
            "deliverable": None,
        },
    }


@pytest.mark.asyncio
async def test_analyze_stream_sse_event_sequence() -> None:
    with patch(
        "app.api.v1.flow_markets.analyze_flow_markets_streaming",
        side_effect=_fake_stream_success,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/flow-markets/analyze/stream",
                json={
                    "user_query": "BTC 结构",
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "lookback": 200,
                },
                headers={"X-API-Key": "dev-no-key"},
            )

    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    events = _parse_sse(r.text)
    kinds = [e[0] for e in events]
    assert kinds[0] == "start"
    assert "log" in kinds
    assert "result" in kinds
    assert kinds[-1] == "complete"

    result_ev = next(data for kind, data in events if kind == "result")
    assert result_ev["success"] is True
    assert result_ev["report_content"] == "# 测试报告"

    start_ev = events[0][1]
    assert "task_id" in start_ev
    assert streaming_mod.get_analysis_stream_result(start_ev["task_id"]) is None


@pytest.mark.asyncio
async def test_get_analyze_stream_result() -> None:
    task_id = "TEST_BTCUSDT_1h_123"
    payload = {
        "success": True,
        "message": "ok",
        "report_content": "# cached",
        "deliverable": None,
    }
    streaming_mod._stream_result_store[task_id] = payload

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get(
            f"/api/v1/flow-markets/analyze/stream/{task_id}/result",
            headers={"X-API-Key": "dev-no-key"},
        )

    streaming_mod._stream_result_store.pop(task_id, None)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["report_content"] == "# cached"


@pytest.mark.asyncio
async def test_get_analyze_stream_result_not_found() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get(
            "/api/v1/flow-markets/analyze/stream/no-such-task/result",
            headers={"X-API-Key": "dev-no-key"},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_streaming_pipeline_phases_with_mocks() -> None:
    """单元：mock K线/结构/Crew，断言四阶段 log 与 result。"""
    fake_snapshot = MagicMock()
    fake_snapshot.meta.data_size.kline = 200
    fake_snapshot.meta.data_size.bi = 10
    fake_snapshot.meta.data_size.segment = 3
    fake_snapshot.meta.data_size.center = 2
    fake_snapshot.meta.symbol = "BTCUSDT"
    fake_snapshot.meta.interval = "1h"
    fake_snapshot.market.latest_price = 50000.0
    fake_snapshot.center = []
    fake_snapshot.bi = []
    fake_snapshot.signal.buy_sell_points = []
    fake_snapshot.signal.divergences = []
    fake_snapshot.structure_summary.trend = "up_trend"
    fake_snapshot.structure_summary.trend_description = "上升"
    fake_snapshot.structure_summary.price_position = "above_zs"
    fake_snapshot.structure_summary.position_description = "上方"

    deliverable = MagicMock()
    crew_result = MagicMock()
    crew_result.pydantic = deliverable

    settings = MagicMock()
    settings.llm_api_key = "sk-test"
    settings.llm_provider = "aliyun"
    settings.llm_model = "qwen-plus"

    task_id = "unit_stream_test"

    with (
        patch("app.services.analyze_streaming.get_settings", return_value=settings),
        patch("app.services.analyze_streaming.get_klines", return_value=[{"close": 1}] * 200),
        patch(
            "app.services.analyze_streaming.build_chan_structure_snapshot",
            return_value=fake_snapshot,
        ),
        patch("app.services.analyze_streaming._structure_info_lines", return_value=["💰 当前价格：50000"]),
        patch("app.services.analyze_streaming.FlowMarketsCrew") as mock_crew_cls,
        patch(
            "app.services.analyze_streaming.create_flow_markets_crew_for_run",
        ) as mock_create_crew,
        patch(
            "app.services.analyze_streaming._execute_flow_markets_crew",
        ) as mock_execute,
        patch("app.services.analyze_streaming._maybe_persist_technical_deliverable", return_value=None),
        patch(
            "app.services.analyze_streaming.assemble_flow_markets_report",
            return_value="# mock report",
        ),
    ):
        mock_crew = mock_crew_cls.return_value
        mock_crew.technical_analyst.return_value = MagicMock()
        mock_crew_obj = MagicMock()
        mock_crew_obj.kickoff.return_value = crew_result
        mock_create_crew.return_value = (mock_crew_obj, "flow_markets")
        mock_execute.return_value = (crew_result, deliverable, "flow_markets")
        events: list[dict[str, Any]] = []
        async for ev in streaming_mod.analyze_flow_markets_streaming(
            user_query="测试",
            symbol="BTCUSDT",
            timeframe="1h",
            lookback=200,
            task_id=task_id,
        ):
            events.append(ev)

    phases = [e.get("phase") for e in events if e.get("type") != "result"]
    assert "kline" in phases
    assert "structure" in phases
    assert "ai" in phases
    assert "governance" in phases

    result_ev = next(e for e in events if e.get("type") == "result")
    assert result_ev["data"]["success"] is True
    assert result_ev["data"]["report_content"] == "# mock report"
    assert streaming_mod.get_analysis_stream_result(task_id) == result_ev["data"]

    streaming_mod._stream_result_store.pop(task_id, None)
