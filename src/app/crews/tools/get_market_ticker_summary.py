"""get_market_ticker_summary：现货 24h 行情 + 永续资金费率（Phase 6.2）。"""

from __future__ import annotations

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from app.observability.logging import get_logger
from app.services.market_ticker_summary import (
    fetch_market_ticker_summary,
    format_market_ticker_summary,
)

logger = get_logger(__name__)


class GetMarketTickerSummaryInput(BaseModel):
    """行情摘要工具输入。"""

    symbol: str = Field(
        ...,
        description="交易对，如 BTCUSDT 或 BTC/USDT。将映射为 Binance 现货符号。",
    )

    @field_validator("symbol")
    @classmethod
    def strip_symbol(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("symbol 不能为空")
        return s


class GetMarketTickerSummaryTool(BaseTool):
    """
    获取 Binance 公开行情摘要 JSON。

    含现货 24h 涨跌、高低、成交量；USDT 永续对另含 mark/index 价与最近资金费率。
    禁止在未调用本工具前编造具体价格、成交量或资金费率数字。
    """

    name: str = "get_market_ticker_summary"
    description: str = (
        "获取指定交易对的 Binance 现货 24 小时行情摘要（最新价、涨跌幅、高低、成交量）。"
        "对 *USDT 交易对另尝试附带 U 本位永续资金费率与标记价格。"
        "返回 JSON 字符串；失败时 ok=false 并说明原因。"
    )
    args_schema: type[BaseModel] = GetMarketTickerSummaryInput

    def _run(self, symbol: str) -> str:
        logger.info("get_market_ticker_summary_start", symbol=symbol[:32])
        try:
            payload = fetch_market_ticker_summary(symbol)
        except ValueError as exc:
            return format_market_ticker_summary(
                {"ok": False, "error": str(exc), "symbol": symbol},
            )
        except Exception as exc:
            logger.exception("get_market_ticker_summary_failed", error=str(exc))
            return format_market_ticker_summary(
                {"ok": False, "error": f"行情摘要异常: {exc}", "symbol": symbol},
            )
        return format_market_ticker_summary(payload)
