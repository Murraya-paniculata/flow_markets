"""Phase 6.2：get_market_ticker_summary 服务与 FlowMarkets 上游 Agent 工具。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.crews.flows.flow_markets import FlowMarketsCrew
from app.crews.tools.get_market_ticker_summary import (
    GetMarketTickerSummaryInput,
    GetMarketTickerSummaryTool,
)
from app.services.market_ticker_summary import fetch_market_ticker_summary


def test_fetch_market_ticker_summary_spot_and_funding() -> None:
    spot_payload = {
        "symbol": "BTCUSDT",
        "lastPrice": "100000",
        "priceChangePercent": "2.5",
        "highPrice": "101000",
        "lowPrice": "99000",
        "volume": "1000",
        "quoteVolume": "100000000",
        "weightedAvgPrice": "100500",
    }
    funding_payload = {
        "markPrice": "100100",
        "indexPrice": "100000",
        "lastFundingRate": "0.0001",
        "nextFundingTime": 1234567890000,
    }

    with patch("app.services.market_ticker_summary.requests.get") as mock_get:
        mock_resp_spot = MagicMock()
        mock_resp_spot.raise_for_status = MagicMock()
        mock_resp_spot.json.return_value = spot_payload

        mock_resp_fund = MagicMock()
        mock_resp_fund.raise_for_status = MagicMock()
        mock_resp_fund.json.return_value = funding_payload

        mock_get.side_effect = [mock_resp_spot, mock_resp_fund]

        result = fetch_market_ticker_summary("BTC/USDT")

    assert result["ok"] is True
    assert result["symbol"] == "BTC/USDT"
    assert result["spot_24h"]["last_price"] == 100000.0
    assert result["perpetual_usdt"]["last_funding_rate"] == 0.0001


def test_get_market_ticker_summary_tool_invalid_symbol() -> None:
    tool = GetMarketTickerSummaryTool()
    with pytest.raises(ValueError):
        GetMarketTickerSummaryInput(symbol="  ")


@patch("app.crews.flows.flow_markets.Crew")
def test_flow_markets_upstream_agents_have_tools(mock_crew_cls: MagicMock) -> None:
    mock_crew_cls.return_value = MagicMock()
    flow = FlowMarketsCrew()
    market = flow.market_analyst()
    narrative = flow.narrative_analyst()
    sentiment = flow.sentiment_analyst()

    assert len(market.tools or []) == 2
    assert len(narrative.tools or []) == 1
    assert len(sentiment.tools or []) == 2
    tool_names = {getattr(t, "name", "") for t in (market.tools or [])}
    assert "get_market_ticker_summary" in tool_names
    assert "baidu_search" in tool_names
