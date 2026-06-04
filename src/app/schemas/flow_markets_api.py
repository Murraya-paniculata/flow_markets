"""FlowMarkets HTTP API：请求/响应 Pydantic 模型（经 ApiResponse 统一出口）。

与 ``flow_markets_deliverables.py``（Crew 各 Task 结构化交付物）区分。
"""

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.chan.kline import SUPPORTED_INTERVALS, normalize_interval
from app.services.chan.structure import DEFAULT_LOOKBACK

_MIN_LOOKBACK = 50
_MAX_LOOKBACK = 800
_SUPPORTED_TIMEFRAMES = ", ".join(SUPPORTED_INTERVALS)


class FlowMarketsAnalyzeRequest(BaseModel):
    """交易研究链分析请求。"""

    user_query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="用户投资意图或研究问题，如「BTC 中线是否偏多」「对比 ETH 与 SOL 的波动」等。",
    )
    symbol: str | None = Field(
        None,
        max_length=32,
        description="可选，交易对或标的提示，如 BTCUSDT、ETH；不传则由模型从 user_query 推断并在报告中说明不确定性。",
    )
    notes: str | None = Field(
        None,
        max_length=1000,
        description="可选补充约束：时间尺度、风险偏好、是否含合约等。",
    )
    timeframe: str = Field(
        "1h",
        description=f"单周期模式下的 K 线周期（与 CLI interval 同义）。支持: {_SUPPORTED_TIMEFRAMES}。",
    )
    lookback: int = Field(
        DEFAULT_LOOKBACK,
        ge=_MIN_LOOKBACK,
        le=_MAX_LOOKBACK,
        description="回溯 K 线根数（与 CLI --limit 同义）；服务端会按周期封顶。",
    )
    multi_tf: bool = Field(
        False,
        description="为 true 时启用多级别联立（4h/1h/15m JSON 预注入 AI）；须同时提供 symbol。",
    )
    save: bool | None = Field(
        None,
        description="为 true 时强制写入分析记忆库；为 false 时强制不写；省略时遵循 APP_ANALYSIS_SAVE。",
    )

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        return normalize_interval(v)

    @model_validator(mode="after")
    def require_symbol_for_multi_tf(self) -> "FlowMarketsAnalyzeRequest":
        sym = (self.symbol or "").strip()
        if self.multi_tf and not sym:
            raise ValueError("multi_tf=true 时必须提供 symbol")
        return self


class FlowMarketsAnalyzeResponse(BaseModel):
    """交易研究链分析响应（同步执行结果）。"""

    success: bool = Field(..., description="是否执行成功")
    message: str = Field("", description="提示或错误说明")
    report_content: str | None = Field(
        None,
        description="最终研究交付物（Markdown）：由各 Task 的 Pydantic 结构化输出按序组装",
    )
