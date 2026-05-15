"""FlowMarkets v1：交易研究 Crew 同步分析接口。"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_request_id, require_api_key
from app.crews.flows.flow_markets import run_flow_markets_analysis
from app.observability.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.flow_markets import FlowMarketsAnalyzeRequest, FlowMarketsAnalyzeResponse

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/analyze",
    response_model=ApiResponse[FlowMarketsAnalyzeResponse],
    summary="FlowMarkets 交易研究分析",
    description=(
        "同步执行多 Agent 研究链。`pipeline=yaml`：YAML 顺序链；"
        "`pipeline=trading_agents`：TradingAgents 风格（新闻/多空结构化 JSON、guardrail）。"
        "需配置 LLM API Key。可选环境变量 TA_STAGE、TA_VERBOSE、TA_INTERMEDIATE_TOOL、TA_LLM_TRACE。"
        "长链路可能耗时数分钟，生产环境建议后续改为异步任务 + 轮询（见设计文档）。"
    ),
)
async def analyze(
    body: FlowMarketsAnalyzeRequest,
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[FlowMarketsAnalyzeResponse]:
    """执行 FlowMarkets CrewAI 编排，返回 Markdown 报告。"""
    try:
        report, err = await asyncio.to_thread(
            run_flow_markets_analysis,
            user_query=body.user_query,
            symbol=body.symbol,
            notes=body.notes,
            pipeline=body.pipeline,
            analysis_date=body.analysis_date,
            stage=body.stage,
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
