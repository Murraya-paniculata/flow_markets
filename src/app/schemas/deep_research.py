"""深度调研 Demo：请求/响应 Pydantic 结构。"""

from pydantic import BaseModel, Field


class DeepResearchRequest(BaseModel):
    """深度调研 API 请求体。"""

    topic: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="调研主题，如「极客时间平台」「某产品市场」等。",
    )
    extra_instructions: str | None = Field(
        None,
        max_length=2000,
        description="可选：额外调研要求或范围说明。",
    )


class DeepResearchResponse(BaseModel):
    """深度调研 API 响应体（同步执行结果）。"""

    success: bool = Field(..., description="是否执行成功")
    topic: str = Field(..., description="调研主题")
    message: str = Field("", description="提示信息")
    report_content: str | None = Field(None, description="最终报告正文（Markdown）")
    report_path: str | None = Field(None, description="报告落盘路径（若写入文件）")
    task_id: str | None = Field(None, description="任务 ID（异步模式时使用）")
