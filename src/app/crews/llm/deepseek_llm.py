"""DeepSeek LLM：OpenAI 兼容接口，默认 https://api.deepseek.com/v1/chat/completions。"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.llm_endpoints import resolve_deepseek_chat_endpoint
from app.crews.llm.chat_completions_llm import OpenAICompatChatLLM


class DeepSeekLLM(OpenAICompatChatLLM):
    """DeepSeek Chat API，与 CrewAI BaseLLM 兼容。"""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
    ) -> None:
        settings = get_settings()
        model = model or settings.llm_model
        api_key = (api_key or settings.llm_api_key or "").strip()
        endpoint = resolve_deepseek_chat_endpoint(
            base_url if base_url is not None else settings.llm_base_url
        )
        timeout_val = timeout if timeout is not None else settings.llm_timeout
        super().__init__(
            model=model,
            api_key=api_key,
            endpoint=endpoint,
            temperature=temperature,
            timeout=timeout_val,
            missing_key_message=(
                "DeepSeek API Key 未配置。请设置 APP_LLM_API_KEY（或 DEEPSEEK_API_KEY）"
                " 或在构造时传入 api_key"
            ),
        )
