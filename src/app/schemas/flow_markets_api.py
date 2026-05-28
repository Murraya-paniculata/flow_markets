"""FlowMarkets HTTP API：请求/响应 Pydantic 模型（经 ApiResponse 统一出口）。

与 ``flow_markets_deliverables.py``（Crew 各 Task 结构化交付物）区分。
"""

from pydantic import BaseModel, Field


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
    save: bool = Field(
        False,
        description="为 true 时在分析成功后写入分析记忆库（analysis_snapshot）；亦受 APP_ANALYSIS_SAVE 影响。",
    )


class FlowMarketsAnalyzeResponse(BaseModel):
    """交易研究链分析响应（同步执行结果）。"""

    success: bool = Field(..., description="是否执行成功")
    message: str = Field("", description="提示或错误说明")
    report_content: str | None = Field(
        None,
        description="最终研究交付物（Markdown）：由各 Task 的 Pydantic 结构化输出按序组装",
    )
