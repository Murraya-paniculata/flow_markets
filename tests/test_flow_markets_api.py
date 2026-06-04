"""FlowMarkets HTTP API 单元测试（Phase 5.1）。"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.main import app
from app.schemas.flow_markets_api import FlowMarketsAnalyzeRequest


def test_analyze_request_defaults() -> None:
    req = FlowMarketsAnalyzeRequest(user_query="分析 BTC")
    assert req.timeframe == "1h"
    assert req.lookback == 300
    assert req.multi_tf is False


def test_analyze_request_normalizes_timeframe_alias() -> None:
    req = FlowMarketsAnalyzeRequest(user_query="x", timeframe="60m")
    assert req.timeframe == "1h"


def test_analyze_request_rejects_invalid_timeframe() -> None:
    with pytest.raises(ValidationError):
        FlowMarketsAnalyzeRequest(user_query="x", timeframe="2h")


def test_analyze_request_rejects_lookback_out_of_range() -> None:
    with pytest.raises(ValidationError):
        FlowMarketsAnalyzeRequest(user_query="x", lookback=10)
    with pytest.raises(ValidationError):
        FlowMarketsAnalyzeRequest(user_query="x", lookback=900)


def test_analyze_request_multi_tf_requires_symbol() -> None:
    with pytest.raises(ValidationError, match="symbol"):
        FlowMarketsAnalyzeRequest(user_query="x", multi_tf=True)


@pytest.mark.asyncio
async def test_analyze_endpoint_passes_timeframe_lookback_multi_tf() -> None:
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return "# report", ""

    with patch(
        "app.api.v1.flow_markets.run_flow_markets_analysis",
        side_effect=fake_run,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/flow-markets/analyze",
                json={
                    "user_query": "BTC 多级别联立",
                    "symbol": "BTCUSDT",
                    "timeframe": "4h",
                    "lookback": 200,
                    "multi_tf": True,
                    "save": True,
                },
                headers={"X-API-Key": "dev-no-key"},
            )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("code") == 0
    assert captured["timeframe"] == "4h"
    assert captured["lookback"] == 200
    assert captured["analysis_mode"] == "multi_timeframe"
    assert captured["save"] is True
    assert captured["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_analyze_endpoint_single_mode_by_default() -> None:
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return "# ok", ""

    with patch(
        "app.api.v1.flow_markets.run_flow_markets_analysis",
        side_effect=fake_run,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/flow-markets/analyze",
                json={"user_query": "简要结构分析", "symbol": "ETHUSDT"},
                headers={"X-API-Key": "dev-no-key"},
            )

    assert r.status_code == 200, r.text
    assert captured["timeframe"] == "1h"
    assert captured["lookback"] == 300
    assert captured["analysis_mode"] == "single"


@pytest.mark.asyncio
async def test_analyze_endpoint_422_multi_tf_without_symbol() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/api/v1/flow-markets/analyze",
            json={"user_query": "多级别", "multi_tf": True},
            headers={"X-API-Key": "dev-no-key"},
        )
    assert r.status_code == 422
