"""FlowMarkets v1：交易研究 Crew 同步分析接口。"""

import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_request_id, require_api_key
from app.crews.flows.flow_markets import run_flow_markets_analysis
from app.observability.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.flow_markets_api import FlowMarketsAnalyzeRequest, FlowMarketsAnalyzeResponse
from app.services.analyze_streaming import (
    analyze_flow_markets_streaming,
    get_analysis_stream_result,
)

router = APIRouter()
logger = get_logger(__name__)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_task_id(body: FlowMarketsAnalyzeRequest) -> str:
    sym = (body.symbol or "NA").upper().replace("/", "").replace("-", "")
    tf = body.timeframe if not body.multi_tf else "multi"
    return f"{sym}_{tf}_{int(time.time() * 1000)}"


@router.post(
    "/analyze",
    response_model=ApiResponse[FlowMarketsAnalyzeResponse],
    summary="FlowMarkets 交易研究分析",
    description=(
        "同步执行技术分析师（get_chan_structure + chan-analysis Skill → TechnicalAnalysisDeliverable）。"
        "可选 timeframe / lookback 指定单周期；multi_tf=true 时联立 4h/1h/15m。"
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
    analysis_mode = "multi_timeframe" if body.multi_tf else "single"
    try:
        report, err = await asyncio.to_thread(
            run_flow_markets_analysis,
            user_query=body.user_query,
            symbol=body.symbol,
            notes=body.notes,
            timeframe=body.timeframe,
            lookback=body.lookback,
            save=body.save,
            analysis_mode=analysis_mode,
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


@router.post(
    "/analyze/stream",
    summary="FlowMarkets 交易研究分析（SSE 流式）",
    description=(
        "以 Server-Sent Events 推送分析进度：K线 → 结构 → AI → 治理。"
        "请求体与 POST /analyze 相同（timeframe / lookback / multi_tf / save）。"
        "事件：start → log（多条）→ result → complete；失败时 error。"
    ),
    response_class=StreamingResponse,
)
async def analyze_stream(
    body: FlowMarketsAnalyzeRequest,
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> StreamingResponse:
    """流式执行技术分析师单链，SSE 推送步骤日志与最终结果。"""
    analysis_mode = "multi_timeframe" if body.multi_tf else "single"
    task_id = _build_task_id(body)

    async def event_generator():
        yield _format_sse("start", {"task_id": task_id, "request_id": request_id})
        try:
            async for ev in analyze_flow_markets_streaming(
                user_query=body.user_query,
                symbol=body.symbol,
                notes=body.notes,
                timeframe=body.timeframe,
                lookback=body.lookback,
                save=body.save,
                analysis_mode=analysis_mode,
                task_id=task_id,
            ):
                if ev.get("type") == "result":
                    yield _format_sse("result", ev["data"])
                else:
                    yield _format_sse("log", ev)
            yield _format_sse("complete", {"task_id": task_id, "request_id": request_id})
        except Exception as e:
            logger.exception("flow_markets_stream_failed", task_id=task_id, error=str(e))
            yield _format_sse(
                "error",
                {"task_id": task_id, "message": f"FlowMarkets 流式执行异常: {e}"},
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get(
    "/analyze/stream/{task_id}/result",
    response_model=ApiResponse[dict],
    summary="获取流式分析最终结果",
    description="SSE 完成后按 task_id 读取内存中的分析结果（进程内有效，重启后丢失）。",
)
async def get_analyze_stream_result(
    task_id: str,
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[dict]:
    """返回流式分析存储的最终 result  payload。"""
    result = get_analysis_stream_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到 task_id={task_id} 的分析结果")
    return ApiResponse(
        code=0,
        message="ok",
        data=result,
        request_id=request_id,
    )
