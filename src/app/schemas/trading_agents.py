"""TradingAgents 风格结构化输出契约（多空辩论 → 研究计划 → 交易提案 → 组合决策）。"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

Rating5 = Literal["买入", "增持", "观望", "减持", "卖出"]
Action3 = Literal["买入", "观望", "卖出"]
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


class ResearchPlan(BaseModel):
    recommendation: Rating5 = Field(
        ...,
        description="研究经理的结论评级：买入/增持/观望/减持/卖出（五选一）。",
    )
    rationale: str = Field(
        ...,
        description="对多空双方观点的归纳总结，并说明为什么给出该评级（自然语言表达）。",
    )
    strategic_actions: List[str] = Field(
        ...,
        description="给交易员的执行层面建议（抽象规则/流程，不要给具体价格点位）。",
    )
    key_unknowns: List[str] = Field(
        ...,
        description="当前不确定性/需要进一步验证的关键问题（至少 3 条）。",
    )
    disclaimer: str = Field(
        ...,
        description="风险声明：必须明确不构成投资建议。",
    )
    not_investment_advice: Literal[False] = Field(
        False,
        description="必须为 False，用于强调不构成投资建议。",
    )


class TraderProposal(BaseModel):
    action: Action3 = Field(
        ...,
        description="交易员的方向性动作：买入/观望/卖出（三选一）。",
    )
    reasoning: str = Field(
        ...,
        description="为什么采取该动作的理由（基于研究计划与分析材料，2-5 句话）。",
    )
    entry_condition_template: List[str] = Field(
        ...,
        description="入场条件模板（抽象规则，不给具体价格/点位）。",
    )
    exit_condition_template: List[str] = Field(
        ...,
        description="离场条件模板（抽象规则，不给具体价格/点位）。",
    )
    position_sizing_rules: List[str] = Field(
        ...,
        description="仓位/资金管理规则（不包含具体仓位数值建议，可用相对规则）。",
    )
    stop_loss_framework: List[str] = Field(
        ...,
        description="止损/风控框架（规则化描述，不保证收益）。",
    )
    disclaimer: str = Field(
        ...,
        description="风险声明：必须明确不构成投资建议。",
    )
    not_investment_advice: Literal[False] = Field(
        False,
        description="必须为 False，用于强调不构成投资建议。",
    )


class PortfolioDecision(BaseModel):
    approved: bool = Field(
        ...,
        description="组合经理是否批准该提案（true/false）。",
    )
    rating: Rating5 = Field(
        ...,
        description="组合层面的最终评级：买入/增持/观望/减持/卖出（五选一）。",
    )
    executive_summary: str = Field(
        ...,
        description="两到四句话的执行摘要：风险约束、预期行为、复盘重点。",
    )
    investment_thesis: str = Field(
        ...,
        description="详细论证：引用上游材料中的关键依据与反方风险点，给出平衡后的结论。",
    )
    risk_constraints: List[str] = Field(
        ...,
        description="批准/否决的关键风控约束（至少 5 条）。",
    )
    monitoring_plan: List[str] = Field(
        ...,
        description="后续监控计划（至少 6 条），用于持续评估是否需要调整观点。",
    )
    disclaimer: str = Field(
        ...,
        description="风险声明：必须明确不构成投资建议。",
    )
    not_investment_advice: Literal[False] = Field(
        False,
        description="必须为 False，用于强调不构成投资建议。",
    )

    @field_validator("rating", mode="before")
    @classmethod
    def _normalize_rating(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, str):
            s = v.strip()
            mapping = {
                "买": "买入",
                "卖": "卖出",
                "持有": "观望",
                "中性": "观望",
            }
            return mapping.get(s, s)
        return v

    @field_validator("approved", mode="before")
    @classmethod
    def _normalize_approved(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "yes", "y", "批准", "通过"):
                return True
            if s in ("false", "no", "n", "拒绝", "否决"):
                return False
        return v
