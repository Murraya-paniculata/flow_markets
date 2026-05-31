"""缠论 K 线 + 结构 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_request_id, require_api_key
from app.observability.logging import get_logger
from app.schemas.chan_api import ChanKlineChartResponse
from app.schemas.common import ApiResponse
from app.services.chan.analyze import build_kline_chart_payload

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/kline/{symbol}/{interval}",
    response_model=ApiResponse[ChanKlineChartResponse],
    summary="K 线 + 缠论结构（chan.py）",
    description="Binance K 线 + 内置缠论结构计算。kline_mode=utc（默认）或 beijing。",
)
async def get_kline_chart(
    symbol: str,
    interval: str,
    limit: int = Query(350, ge=50, le=5000),
    kline_mode: str | None = Query(
        None,
        description="K 线对齐：utc（默认）或 beijing；省略时用 APP_KLINE_MODE",
    ),
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[ChanKlineChartResponse]:
    try:
        payload = build_kline_chart_payload(
            symbol.upper(),
            interval,
            limit=limit,
            kline_mode=kline_mode,
        )
        return ApiResponse(
            code=0,
            message="ok",
            data=ChanKlineChartResponse.model_validate(payload),
            request_id=request_id,
        )
    except ImportError as e:
        logger.warning("chan.py not available: %s", e)
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("chan kline chart failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
