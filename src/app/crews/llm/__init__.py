"""LLM 模型参数与 Provider 配置。支持阿里云通义千问、DeepSeek 等。"""

from __future__ import annotations

from crewai import BaseLLM

from app.core.config import get_settings
from app.crews.llm.aliyun_llm import AliyunLLM
from app.crews.llm.deepseek_llm import DeepSeekLLM

__all__ = ["AliyunLLM", "DeepSeekLLM", "get_llm"]


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    **kwargs: object,
) -> BaseLLM:
    """
    根据配置返回 LLM 实例。

    Args:
        provider: 不传则用 APP_LLM_PROVIDER（aliyun / deepseek）
        model: 不传则用 APP_LLM_MODEL
        **kwargs: 透传各 LLM 构造参数（api_key、temperature、timeout、region 等）

    Returns:
        CrewAI BaseLLM 实现类实例
    """
    settings = get_settings()
    provider = (provider or settings.llm_provider).lower()
    if provider == "aliyun":
        return AliyunLLM(
            model=model or settings.llm_model,
            api_key=kwargs.get("api_key"),  # type: ignore[arg-type]
            region=kwargs.get("region") or settings.llm_region,  # type: ignore[arg-type]
            temperature=kwargs.get("temperature"),  # type: ignore[arg-type]
            timeout=kwargs.get("timeout"),  # type: ignore[arg-type]
        )
    if provider == "deepseek":
        return DeepSeekLLM(
            model=model or settings.llm_model,
            api_key=kwargs.get("api_key"),  # type: ignore[arg-type]
            base_url=kwargs.get("base_url"),  # type: ignore[arg-type]
            temperature=kwargs.get("temperature"),  # type: ignore[arg-type]
            timeout=kwargs.get("timeout"),  # type: ignore[arg-type]
        )
    raise ValueError(f"不支持的 LLM provider: {provider}，当前支持: aliyun, deepseek")
