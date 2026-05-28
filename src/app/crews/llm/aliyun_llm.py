"""阿里云通义千问 LLM，基于 OpenAI 兼容 Chat Completions，适配本项目配置与日志规范。"""

from __future__ import annotations

from typing import ClassVar

from app.core.config import get_settings
from app.crews.llm.chat_completions_llm import OpenAICompatChatLLM


class AliyunLLM(OpenAICompatChatLLM):
    """阿里云通义千问 LLM，兼容 CrewAI BaseLLM 接口。"""

    ENDPOINTS: ClassVar[dict[str, str]] = {
        "cn": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "intl": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
        "finance": "https://dashscope-finance.aliyuncs.com/compatible-mode/v1/chat/completions",
    }

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        region: str | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
    ) -> None:
        """
        初始化阿里云 LLM。未传参数时从 APP_* 配置读取。

        Args:
            model: 模型名称，如 qwen-plus、qwen-turbo
            api_key: API Key，不传则用 APP_LLM_API_KEY
            region: 地域 cn / intl / finance，不传则用 APP_LLM_REGION
            temperature: 采样温度
            timeout: 请求超时秒数
        """
        settings = get_settings()
        model = model or settings.llm_model
        api_key = (api_key or settings.llm_api_key or "").strip()
        region = region or settings.llm_region
        if region not in self.ENDPOINTS:
            raise ValueError(
                f"不支持的地域: {region}，支持: {list(self.ENDPOINTS.keys())}"
            )
        endpoint = self.ENDPOINTS[region]
        timeout_val = timeout if timeout is not None else settings.llm_timeout
        super().__init__(
            model=model,
            api_key=api_key,
            endpoint=endpoint,
            temperature=temperature,
            timeout=timeout_val,
            missing_key_message=(
                "阿里云 API Key 未配置。请设置环境变量 APP_LLM_API_KEY 或在构造时传入 api_key"
            ),
        )
        self.region = region
