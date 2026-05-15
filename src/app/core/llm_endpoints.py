"""LLM 兼容网关 URL 工具（无 CrewAI 依赖）。"""

from __future__ import annotations

DEFAULT_DEEPSEEK_CHAT_URL = "https://api.deepseek.com/v1/chat/completions"


def resolve_deepseek_chat_endpoint(base_url: str | None) -> str:
    """
    由 APP_LLM_BASE_URL 得到 DeepSeek（或兼容网关）完整 chat/completions URL。

    - 未配置：默认官方地址
    - 已含 chat/completions：原样使用（去掉末尾多余 /）
    - 以 /v1 结尾：在其后追加 /chat/completions
    - 其他：视为 API 根（如 https://api.deepseek.com），追加 /v1/chat/completions
    """
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return DEFAULT_DEEPSEEK_CHAT_URL
    if "chat/completions" in raw:
        return raw
    if raw.endswith("/v1"):
        return f"{raw}/chat/completions"
    return f"{raw}/v1/chat/completions"
