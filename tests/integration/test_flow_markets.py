"""FlowMarkets 集成测试：仅需 LLM Key（无需百度搜索）。"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

SKIP_REASON = "未设置 APP_LLM_API_KEY、QWEN_API_KEY 或 DEEPSEEK_API_KEY，跳过 FlowMarkets 集成测试"


def _has_llm_key() -> bool:
    return bool(
        os.environ.get("APP_LLM_API_KEY")
        or os.environ.get("QWEN_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_llm_key(), reason=SKIP_REASON)
async def test_flow_markets_analyze() -> None:
    """调用 /api/v1/flow-markets/analyze，断言 200 且报告非空。"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=600.0,
    ) as client:
        r = await client.post(
            "/api/v1/flow-markets/analyze",
            json={
                "user_query": "简要分析 BTC 与 ETH 近期波动率差异的研究框架，不做投资建议",
                "symbol": "BTCUSDT",
                "notes": "测试用请求",
            },
            headers={"X-API-Key": "dev-no-key"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("code") == 0, data
    assert "request_id" in data
    payload = data.get("data") or {}
    assert payload.get("success") is True, payload
    assert payload.get("report_content"), "报告内容不应为空"
