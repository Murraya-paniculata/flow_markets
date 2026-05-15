"""百度搜索工具：基于百度千帆搜索 API 的 CrewAI 工具，适配本项目配置与日志规范。"""

from __future__ import annotations

import json
from typing import Any, Literal

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)

BAIDU_SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"
MAX_TOP_K = {"web": 50, "video": 10, "image": 30, "aladdin": 5}
ERROR_HINTS = {
    "400": "请求参数错误，请检查输入的参数是否正确",
    "500": "服务器内部错误，请稍后重试",
    "501": "服务调用超时，请稍后重试",
    "502": "服务响应超时，请稍后重试",
    "216003": "API Key认证失败，请检查API Key是否正确或是否已过期",
}


class BaiduSearchInput(BaseModel):
    """百度搜索工具的输入参数。"""

    query: str = Field(
        ...,
        description="搜索查询内容，即用户要搜索的问题或关键词。不能为空，不能只包含空白字符。",
    )
    api_key: str | None = Field(
        None,
        description="百度千帆 AppBuilder API Key。不提供则使用 APP_BAIDU_API_KEY。",
    )
    resource_type: Literal["web", "video", "image", "aladdin"] = Field(
        "web",
        description="主要搜索的资源类型: web(网页,最大top_k=50), video(视频,最大10), image(图片,最大30), aladdin(阿拉丁,最大5)。",
    )
    top_k: int = Field(
        20,
        description="返回的搜索结果数量。web最大50, video最大10, image最大30, aladdin最大5。",
    )
    enable_video: bool = Field(False, description="是否同时搜索视频，最多10条。")
    enable_image: bool = Field(False, description="是否同时搜索图片，最多30条。")
    enable_aladdin: bool = Field(False, description="是否同时搜索阿拉丁，最多5条。")
    edition: Literal["standard", "lite"] = Field(
        "standard",
        description="搜索版本: standard(完整), lite(精简时延更短)。",
    )
    search_recency_filter: Literal["week", "month", "semiyear", "year"] | None = Field(
        None,
        description="网页发布时间筛选: week/month/semiyear/year。仅对网页有效。",
    )
    sites: list[str] | None = Field(
        None,
        description="指定搜索的站点列表，最多20个。阿拉丁不支持。",
    )
    block_websites: list[str] | None = Field(
        None,
        description="需要屏蔽的站点列表。",
    )
    page_time_gte: str | None = Field(
        None,
        description="网页发布时间范围起始，如 now-1w/d。须与 page_time_lte 同时使用。",
    )
    page_time_lte: str | None = Field(
        None,
        description="网页发布时间范围结束，如 now/d。须与 page_time_gte 同时使用。",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("查询内容不能为空，请提供有效的搜索关键词或问题。")
        return v.strip()

    @field_validator("sites")
    @classmethod
    def validate_sites(cls, v: list[str] | None) -> list[str] | None:
        if v and len(v) > 20:
            raise ValueError(f"站点列表最多支持20个，当前 {len(v)} 个。")
        return v

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v: int) -> int:
        if v < 0:
            raise ValueError("top_k 必须大于等于 0。")
        return v


class BaiduSearchTool(BaseTool):
    """
    百度搜索工具。使用百度千帆搜索 API，支持网页、视频、图片、阿拉丁等类型，
    可按时间、站点等条件筛选。需配置 APP_BAIDU_API_KEY 或传入 api_key。
    """

    name: str = "baidu_search"
    description: str = (
        "使用百度搜索引擎查找相关信息。"
        "支持搜索网页、视频、图片、阿拉丁等多种类型。"
        "可按时间范围、指定站点等条件筛选。"
        "返回结果包含标题、链接、内容摘要、相关性评分、权威性评分等。"
        "需提供百度千帆 AppBuilder API Key（api_key 参数或 APP_BAIDU_API_KEY 环境变量）。"
    )
    args_schema: type[BaseModel] = BaiduSearchInput

    def _run(
        self,
        query: str,
        api_key: str | None = None,
        resource_type: str = "web",
        top_k: int = 20,
        enable_video: bool = False,
        enable_image: bool = False,
        enable_aladdin: bool = False,
        edition: str = "standard",
        search_recency_filter: str | None = None,
        sites: list[str] | None = None,
        block_websites: list[str] | None = None,
        page_time_gte: str | None = None,
        page_time_lte: str | None = None,
    ) -> str:
        """执行百度搜索，返回格式化结果字符串。"""
        settings = get_settings()
        key = api_key or settings.baidu_api_key
        timeout = settings.baidu_search_timeout

        logger.info(
            "baidu_search_start",
            query=query[:100],
            resource_type=resource_type,
            top_k=top_k,
        )

        if not key:
            msg = (
                "搜索失败：缺少 API Key。"
                "请设置环境变量 APP_BAIDU_API_KEY 或通过 api_key 参数传入。"
                "API Key 可从百度智能云千帆控制台获取。"
            )
            logger.warning("baidu_search_skip_no_api_key")
            return msg

        max_k = MAX_TOP_K.get(resource_type, 50)
        if top_k > max_k:
            logger.debug("baidu_search_top_k_capped", original=top_k, capped=max_k)
            top_k = max_k

        resource_type_filter = [{"type": resource_type, "top_k": top_k}]
        if enable_video:
            resource_type_filter.append({"type": "video", "top_k": 10})
        if enable_image:
            resource_type_filter.append({"type": "image", "top_k": 30})
        if enable_aladdin:
            resource_type_filter.append({"type": "aladdin", "top_k": 5})

        payload: dict[str, Any] = {
            "messages": [{"content": query, "role": "user"}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": resource_type_filter,
            "edition": edition,
        }
        if search_recency_filter:
            payload["search_recency_filter"] = search_recency_filter

        search_filter: dict[str, Any] = {}
        if sites:
            search_filter["match"] = {"site": sites}
        if page_time_gte and page_time_lte:
            search_filter.setdefault("range", {})["page_time"] = {
                "gte": page_time_gte,
                "lte": page_time_lte,
            }
        elif page_time_gte or page_time_lte:
            msg = (
                "搜索失败：page_time_gte 与 page_time_lte 必须同时提供才能使用时间范围查询。"
            )
            logger.warning("baidu_search_invalid_time_range")
            return msg
        if search_filter:
            payload["search_filter"] = search_filter
        if block_websites:
            payload["block_websites"] = block_websites

        headers = {
            "X-Appbuilder-Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                BAIDU_SEARCH_URL,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.Timeout:
            logger.warning("baidu_search_timeout", timeout=timeout)
            return (
                "搜索失败：请求超时。请检查网络或稍后重试。"
                f"当前超时设置：{timeout} 秒。"
            )
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else "未知"
            logger.warning("baidu_search_http_error", status_code=code, error=str(e))
            return (
                f"搜索失败：HTTP 错误，状态码 {code}。"
                "请检查 API Key 与网络，若为 401/403 检查权限，429 请稍后重试。"
            )
        except requests.exceptions.RequestException as e:
            logger.exception("baidu_search_request_error", error=str(e))
            return f"搜索失败：网络请求异常。{type(e).__name__}: {e}"
        except json.JSONDecodeError as e:
            logger.warning("baidu_search_json_error", error=str(e))
            return "搜索失败：响应非有效 JSON，请稍后重试。"

        request_id = result.get("request_id") or result.get("requestId", "")
        error_code = result.get("code")
        if error_code is not None and error_code != 0 and error_code != "":
            err_msg = result.get("message", "未知错误")
            hint = ERROR_HINTS.get(str(error_code), "")
            logger.warning(
                "baidu_search_api_error",
                code=error_code,
                message=err_msg,
                request_id=request_id,
            )
            return (
                f"搜索失败：API 返回错误。\n"
                f"错误信息：{err_msg}\n错误码：{error_code}\n请求ID：{request_id}"
                + (f"\n提示：{hint}" if hint else "")
            )

        references = result.get("references", [])
        if not references:
            logger.info("baidu_search_no_results", query=query[:80])
            return (
                f"搜索完成，未找到相关结果。关键词：{query}\n"
                "建议：更换关键词、放宽过滤条件或尝试启用视频/图片等类型。"
            )

        type_counts: dict[str, int] = {}
        for ref in references:
            t = ref.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        logger.info(
            "baidu_search_success",
            total=len(references),
            type_counts=type_counts,
        )

        lines = [
            f"找到 {len(references)} 条搜索结果",
            ", ".join(f"{k}:{v}条" for k, v in type_counts.items()) if len(type_counts) > 1 else "",
            "",
        ]
        for ref in references:
            title = ref.get("title", "无标题")
            url = ref.get("url", "")
            content = ref.get("content", "")
            date = ref.get("date", "")
            ref_type = ref.get("type", "unknown")
            website = ref.get("website", "")
            web_anchor = ref.get("web_anchor", "")
            rerank_score = ref.get("rerank_score")
            authority_score = ref.get("authority_score")

            line = f"[{ref.get('id', '?')}] {title}"
            if url:
                line += f"\n  链接: {url}"
            if website:
                line += f"\n  站点: {website}"
            if web_anchor:
                line += f"\n  锚文本: {web_anchor}"
            if date:
                line += f"\n  日期: {date}"
            line += f"\n  类型: {ref_type}"
            if rerank_score is not None:
                line += f"\n  相关性评分: {rerank_score:.3f}"
            if authority_score is not None:
                line += f"\n  权威性评分: {authority_score:.3f}"
            if ref.get("image"):
                img = ref["image"]
                line += f"\n  图片: {img.get('url', '')} ({img.get('width', '')}x{img.get('height', '')})"
            if ref.get("video"):
                vid = ref["video"]
                line += f"\n  视频: {vid.get('url', '')} (时长: {vid.get('duration', '')}秒)"
            if content:
                preview = content[:800] + "..." if len(content) > 800 else content
                line += f"\n  内容摘要: {preview}"
            lines.append(line)
            lines.append("")

        return "\n".join(lines).strip()
