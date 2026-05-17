"""多空研究员结构化输出契约（BullResearchCase / BearResearchCase）。"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

Confidence3 = Literal["低", "中", "高"]


class DebateClaim(BaseModel):
    claim: str = Field(..., description="核心论点（一句话讲清楚）。")
    evidence_to_check: List[str] = Field(
        ...,
        description="可验证线索/证据清单（至少 2 条，明确应该去看什么数据/事实）。",
    )
    invalidation_conditions: List[str] = Field(
        ...,
        description="反证/失效条件（至少 2 条：出现什么现象/数据就推翻该论点）。",
    )


class BullResearchCase(BaseModel):
    stance: Literal["看多"] = Field("看多", description="立场固定为“看多”。")
    headline: str = Field(..., description="一句话看多结论（不含买卖指令）。")
    confidence: Confidence3 = Field(..., description="主观把握度：低/中/高（三选一）。")
    claims: List[DebateClaim] = Field(..., description="看多论点列表（建议 3-6 条）。")
    key_unknowns: List[str] = Field(..., description="关键不确定性/需要验证的问题（至少 3 条）。")
    disclaimer: str = Field(..., description="风险声明：必须明确不构成投资建议。")
    not_investment_advice: Literal[False] = Field(False, description="必须为 False。")


class BearResearchCase(BaseModel):
    stance: Literal["看空"] = Field("看空", description="立场固定为“看空”。")
    headline: str = Field(..., description="一句话看空/风险结论（不含买卖指令）。")
    confidence: Confidence3 = Field(..., description="主观把握度：低/中/高（三选一）。")
    claims: List[DebateClaim] = Field(..., description="看空/风险论点列表（建议 3-6 条）。")
    mitigation_conditions: List[str] = Field(
        ...,
        description="缓解条件（至少 3 条：出现什么现象/数据可降低风险或缓解看空观点）。",
    )
    disclaimer: str = Field(..., description="风险声明：必须明确不构成投资建议。")
    not_investment_advice: Literal[False] = Field(False, description="必须为 False。")
