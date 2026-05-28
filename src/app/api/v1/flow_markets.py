"""FlowMarkets v1：交易研究 Crew 同步分析接口。"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_request_id, require_api_key
from app.crews.flows.flow_markets import run_flow_markets_analysis
from app.observability.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.flow_markets_api import FlowMarketsAnalyzeRequest, FlowMarketsAnalyzeResponse

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/analyze",
    response_model=ApiResponse[FlowMarketsAnalyzeResponse],
    summary="FlowMarkets 交易研究分析",
    description=(
        "同步执行技术分析师（get_chan_structure + chan-analysis Skill → TechnicalAnalysisDeliverable）。"
        "当前仅启用 technical_analyst，其余 Agent 已暂停。"
        "需配置 LLM API Key（如通义千问 qwen-max）。"
    ),
)
async def analyze(
    body: FlowMarketsAnalyzeRequest,
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[FlowMarketsAnalyzeResponse]:
    """执行技术分析师单链，返回 Markdown 报告。"""
    try:
        report, err = await asyncio.to_thread(
            run_flow_markets_analysis,
            user_query=body.user_query,
            symbol=body.symbol,
            notes=body.notes,
        )
    except Exception as e:
        logger.exception("flow_markets_api_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"FlowMarkets 执行异常: {e}") from e

    if err:
        return ApiResponse(
            code=1,
            message=err,
            data=FlowMarketsAnalyzeResponse(
                success=False,
                message=err,
                report_content=None,
            ),
            request_id=request_id,
        )

    return ApiResponse(
        code=0,
        message="ok",
        data=FlowMarketsAnalyzeResponse(
            success=True,
            message="分析完成",
            report_content=report,
        ),
        request_id=request_id,
    )
