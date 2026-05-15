"""示例 v1 接口：带鉴权、深度调研 Demo。"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_request_id, require_api_key
from app.crews.flows.deep_research import run_deep_research
from app.observability.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.deep_research import DeepResearchRequest, DeepResearchResponse

router = APIRouter()
logger = get_logger(__name__)


@router.get("/ping", response_model=ApiResponse[dict])
async def ping(
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[dict]:
    """示例：需要 X-API-Key，返回 request_id。"""
    return ApiResponse(
        code=0,
        message="pong",
        data={"request_id": request_id},
        request_id=request_id,
    )


@router.post(
    "/deep-research",
    response_model=ApiResponse[DeepResearchResponse],
    summary="深度调研（Demo）",
    description="提交调研主题，同步执行多 Agent 编排（研究专家→撰写研究员+搜索专家+审核编辑），返回最终报告。需配置 LLM（阿里云或 DeepSeek 等）与百度搜索 API Key。",
)
async def deep_research(
    body: DeepResearchRequest,
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[DeepResearchResponse]:
    """深度调研：Pydantic 入参，YAML Agent/Task，CrewAI + 百度搜索，返回报告内容与路径。"""
    try:
        report_content, report_path, error = await asyncio.to_thread(
            run_deep_research,
            topic=body.topic,
            extra_instructions=body.extra_instructions,
            output_dir=None,
        )
    except Exception as e:
        logger.exception(
            "deep_research_failed",
            topic=body.topic,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"深度调研执行异常: {e}") from e

    if error:
        return ApiResponse(
            code=1,
            message=error,
            data=DeepResearchResponse(
                success=False,
                topic=body.topic,
                message=error,
                report_content=None,
                report_path=None,
                task_id=None,
            ),
            request_id=request_id,
        )

    return ApiResponse(
        code=0,
        message="ok",
        data=DeepResearchResponse(
            success=True,
            topic=body.topic,
            message="报告已生成",
            report_content=report_content,
            report_path=report_path,
            task_id=None,
        ),
        request_id=request_id,
    )
