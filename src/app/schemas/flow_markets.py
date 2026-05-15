"""FlowMarkets API：请求/响应 Pydantic 模型（经 ApiResponse 统一出口）。"""

from typing import Literal

from pydantic import BaseModel, Field


class FlowMarketsAnalyzeRequest(BaseModel):
    """交易研究链分析请求。"""

    pipeline: Literal["yaml", "trading_agents"] = Field(
        "yaml",
        description=(
            "编排管线：`yaml` 为现有 YAML+CrewBase 顺序链；`trading_agents` 为迁入的 "
            "TradingAgents 风格（Python 任务 + 结构化 JSON + guardrail）。"
        ),
    )
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
    analysis_date: str | None = Field(
        None,
        max_length=32,
        description="分析日期（YYYY-MM-DD）。`trading_agents` 管线使用；不传则服务端取当天。",
    )
    stage: str | None = Field(
        None,
        max_length=32,
        description=(
            "仅 `trading_agents`：执行阶段，覆盖环境变量 TA_STAGE。"
            "如 analysis、debate、rm、trader、pm、full 等，见 trading_agents.tasks.slice_by_stage。"
        ),
    )


class FlowMarketsAnalyzeResponse(BaseModel):
    """交易研究链分析响应（同步执行结果）。"""

    success: bool = Field(..., description="是否执行成功")
    message: str = Field("", description="提示或错误说明")
    report_content: str | None = Field(None, description="最终研究交付物（Markdown），通常以组合经理任务收束")
