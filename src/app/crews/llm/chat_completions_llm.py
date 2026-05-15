"""OpenAI 兼容 Chat Completions LLM（阿里云、DeepSeek 等共用）。"""

from __future__ import annotations

import json
from typing import Any

import requests
from crewai import BaseLLM

from app.observability.logging import get_logger

logger = get_logger(__name__)


class OpenAICompatChatLLM(BaseLLM):
    """调用 OpenAI 兼容 `/v1/chat/completions` 接口，兼容 CrewAI BaseLLM。"""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        endpoint: str,
        temperature: float | None = None,
        timeout: int = 600,
        missing_key_message: str = "LLM API Key 未配置。请设置 APP_LLM_API_KEY 或在构造时传入 api_key",
        request_log_extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(model=model, temperature=temperature)
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise ValueError(missing_key_message)
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self._request_log_extra = request_log_extra or {}

    def call(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        max_iterations: int = 10,
        _retry_on_empty: bool = True,
        **kwargs: Any,
    ) -> str | Any:
        if max_iterations <= 0:
            raise RuntimeError("Function calling 达到最大迭代次数，可能存在无限循环")

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        self._validate_messages(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.stop and self.supports_stop_words():
            stop_value = self._prepare_stop_words(self.stop)
            if stop_value:
                payload["stop"] = stop_value
        if tools and self.supports_function_calling():
            payload["tools"] = tools

        if callbacks:
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    try:
                        cb.on_llm_start(messages)
                    except Exception:
                        pass

        log_fields: dict[str, Any] = {
            "endpoint": self.endpoint,
            "model": self.model,
            "num_messages": len(messages),
            "raw_messages": messages,
        }
        log_fields.update(self._request_log_extra)
        logger.info("llm_request", **log_fields)

        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            logger.info("llm_response", result=result)
        except requests.Timeout:
            logger.warning("llm_timeout", timeout=self.timeout)
            raise TimeoutError(f"LLM 请求超时（{self.timeout} 秒）")
        except requests.RequestException as e:
            logger.exception("llm_request_failed", error=str(e))
            raise RuntimeError(f"LLM 请求失败: {e}") from e

        if callbacks:
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    try:
                        cb.on_llm_end(result)
                    except Exception:
                        pass

        if "choices" not in result or not result["choices"]:
            raise ValueError("响应中未找到 choices 字段")

        message = result["choices"][0].get("message", {})
        if "tool_calls" in message:
            if available_functions:
                return self._handle_function_calls(
                    message["tool_calls"],
                    messages,
                    tools,
                    available_functions,
                    max_iterations - 1,
                )
            raise ValueError(
                "响应包含 tool_calls 但未提供 available_functions，无法执行工具调用"
            )

        content = message.get("content")
        if content is None:
            raise ValueError("响应中未找到 content 字段")

        if isinstance(content, str) and not content.strip():
            if _retry_on_empty:
                logger.warning("llm_empty_content_retry", model=self.model)
                return self.call(
                    messages,
                    tools=tools,
                    callbacks=callbacks,
                    available_functions=available_functions,
                    max_iterations=max_iterations,
                    _retry_on_empty=False,
                    **kwargs,
                )
            raise ValueError(
                "LLM 返回空内容，可能是模型限流或偶发异常，请稍后重试或检查 API 配额"
            )
        return content

    def _handle_function_calls(
        self,
        tool_calls: list[dict],
        messages: list[dict[str, Any]],
        tools: list[dict] | None,
        available_functions: dict[str, Any],
        max_iterations: int,
    ) -> str | Any:
        if max_iterations <= 0:
            raise RuntimeError("Function calling 达到最大迭代次数，可能存在无限循环")

        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        })

        for tool_call in tool_calls:
            fn_info = tool_call.get("function", {})
            fn_name = fn_info.get("name")
            tool_call_id = tool_call.get("id")
            if not tool_call_id:
                raise ValueError(f"tool_call 缺少 id: {tool_call}")

            if fn_name in available_functions:
                try:
                    raw = fn_info.get("arguments", "{}")
                    args = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
                except json.JSONDecodeError as e:
                    raise ValueError(f"无法解析函数参数: {e}") from e
                try:
                    function_result = available_functions[fn_name](**args)
                except Exception as e:
                    function_result = f"函数执行错误: {str(e)}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": str(function_result),
                })
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": f"函数 {fn_name} 不可用",
                })

        return self.call(messages, tools, None, available_functions, max_iterations - 1)

    def supports_function_calling(self) -> bool:
        # 与 Aliyun 一致：走 ReAct 文本解析，避免部分模型不返回规范 tool_calls
        return False

    def supports_stop_words(self) -> bool:
        return True

    def _validate_messages(self, messages: list[dict[str, Any]]) -> None:
        valid_roles = {"system", "user", "assistant", "tool"}
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"消息 {i} 必须是字典: {msg}")
            if "role" not in msg or msg["role"] not in valid_roles:
                raise ValueError(f"消息 {i} 缺少或无效的 role: {msg}")
            if msg["role"] == "tool":
                if "tool_call_id" not in msg or "content" not in msg:
                    raise ValueError(f"tool 消息 {i} 缺少 tool_call_id/content: {msg}")
            elif "content" not in msg and msg.get("tool_calls") is None:
                raise ValueError(f"消息 {i} 缺少 content 且无 tool_calls: {msg}")
            else:
                content = msg.get("content")
                if content is not None and not isinstance(content, (str, list)):
                    raise ValueError(f"消息 {i} 的 content 须为 str 或 list: {type(content)}")
                if isinstance(content, list):
                    for j, item in enumerate(content):
                        if not isinstance(item, dict) or "type" not in item:
                            raise ValueError(f"消息 {i} content[{j}] 须为含 type 的 dict: {item}")

    def _prepare_stop_words(
        self, stop: str | list[str | int]
    ) -> str | list[str | int] | None:
        if not stop:
            return None
        if isinstance(stop, str):
            return stop
        if isinstance(stop, list) and stop:
            return stop
        return None

    def get_context_window_size(self) -> int:
        m = self.model.lower()
        if "deepseek" in m:
            if "reasoner" in m or "r1" in m:
                return 64_000
            return 128_000
        if "long" in m:
            return 200_000
        if "max" in m or "plus" in m or "turbo" in m or "flash" in m:
            return 8192
        return 8192
