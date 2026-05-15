"""DeepSeek Chat Completions URL 解析。"""

from app.core.llm_endpoints import (
    DEFAULT_DEEPSEEK_CHAT_URL,
    resolve_deepseek_chat_endpoint,
)


def test_resolve_empty() -> None:
    assert resolve_deepseek_chat_endpoint(None) == DEFAULT_DEEPSEEK_CHAT_URL
    assert resolve_deepseek_chat_endpoint("") == DEFAULT_DEEPSEEK_CHAT_URL
    assert resolve_deepseek_chat_endpoint("   ") == DEFAULT_DEEPSEEK_CHAT_URL


def test_resolve_full_url() -> None:
    u = "https://api.deepseek.com/v1/chat/completions"
    assert resolve_deepseek_chat_endpoint(u) == u
    assert resolve_deepseek_chat_endpoint(u + "/") == u


def test_resolve_base_host() -> None:
    assert (
        resolve_deepseek_chat_endpoint("https://api.deepseek.com")
        == DEFAULT_DEEPSEEK_CHAT_URL
    )
    assert (
        resolve_deepseek_chat_endpoint("https://api.deepseek.com/")
        == DEFAULT_DEEPSEEK_CHAT_URL
    )


def test_resolve_v1_suffix() -> None:
    assert (
        resolve_deepseek_chat_endpoint("https://api.deepseek.com/v1")
        == DEFAULT_DEEPSEEK_CHAT_URL
    )
