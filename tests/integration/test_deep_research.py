"""深度调研 Demo 集成测试：需配置 QWEN_API_KEY / BAIDU_API_KEY（或 APP_LLM_API_KEY / APP_BAIDU_API_KEY）。"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# 未配置任一 Key 时跳过（避免 CI 必填）
SKIP_REASON = "未设置 APP_LLM_API_KEY、QWEN_API_KEY 或 DEEPSEEK_API_KEY，跳过深度调研集成测试"


def _has_llm_key() -> bool:
    return bool(
        os.environ.get("APP_LLM_API_KEY")
        or os.environ.get("QWEN_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
    )


def _has_baidu_key() -> bool:
    return bool(
        os.environ.get("APP_BAIDU_API_KEY") or os.environ.get("BAIDU_API_KEY")
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _has_llm_key() or not _has_baidu_key(),
    reason=SKIP_REASON,
)
async def test_deep_research_crewai() -> None:
    """调用深度调研接口，主题「调研 crewai」，断言 200 且 success 为 True、报告非空。"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=300.0,
    ) as client:
        r = await client.post(
            "/api/v1/demo/deep-research",
            json={"topic": "调研 crewai", "extra_instructions": None},
            headers={"X-API-Key": "dev-no-key"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("code") == 0, data
    assert "request_id" in data
    payload = data.get("data") or {}
    assert payload.get("success") is True, payload
    assert payload.get("topic") == "调研 crewai"
    assert payload.get("report_content"), "报告内容不应为空"
