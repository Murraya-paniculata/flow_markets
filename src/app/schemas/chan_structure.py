"""缠论结构快照 JSON 契约（供 get_chan_structure 工具与单测共用）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChanDataSize(BaseModel):
    kline: int = Field(..., description="参与计算的 K 线根数")
    bi: int = Field(..., description="引擎识别的笔总数")
    segment: int = Field(..., description="线段总数")
    center: int = Field(..., description="中枢条数（笔中枢+线段中枢）")


class ChanMeta(BaseModel):
    symbol: str
    interval: str
    timestamp: str
    engine: str = "structure-engine"
    engine_version: str = "flow-markets-v1"
    data_size: ChanDataSize
    trim: dict[str, int] | None = Field(
        default=None,
        description="若对 bi/segment 做了条数裁剪，记录 max 限制",
    )


class ChanMarket(BaseModel):
    latest_price: float
    trend_hint: Literal["range", "up", "down"] = "range"
    volatility_hint: Literal["low", "medium", "high"] = "medium"


class ChanBiItem(BaseModel):
    index: int
    direction: str
    is_done: bool = True
    start_time: str | None = None
    end_time: str | None = None
    start_price: float | None = None
    end_price: float | None = None
    buy_sell_point: str | None = None
    divergence: str | None = None
    strength: float | None = Field(None, description="综合力度（与 chanlun exporter 一致，有则导出）")
    macd_strength: float | None = Field(None, description="MACD 力度（有则导出）")
    price_strength: float | None = Field(
        None, description="价格幅度力度（|end-start| 或引擎 price_strength）"
    )


class ChanSegmentItem(BaseModel):
    index: int
    direction: str
    is_done: bool = True
    start_time: str | None = None
    end_time: str | None = None
    start_price: float | None = None
    end_price: float | None = None
    buy_sell_point: str | None = None
    divergence: str | None = None


class ChanCenterItem(BaseModel):
    index: int
    type: Literal["bi", "segment"] = "bi"
    zs_type: str = "standard"
    start_time: str | None = None
    end_time: str | None = None
    zg: float | None = None
    zd: float | None = None
    gg: float | None = None
    dd: float | None = None
    high: float | None = None
    low: float | None = None
    relation: str = "new"
    bi_count: int = 0
    level: int | None = Field(1, description="中枢级别（与 chanlun exporter 一致）")


class ChanSignal(BaseModel):
    buy_sell_points: list[str] = Field(default_factory=list)
    divergences: list[str] = Field(default_factory=list)
    last_signal_time: str | None = None


class ChanKeyLevels(BaseModel):
    zg: float = 0
    zd: float = 0
    gg: float = 0
    dd: float = 0


class ChanStructureSummary(BaseModel):
    trend: str = "unknown"
    price_position: str = "unknown"
    latest_bi_direction: str = "unknown"
    latest_bi_strength: float = 0
    prev_bi_strength: float = 0
    strength_comparison: str = "unknown"
    key_levels: ChanKeyLevels = Field(default_factory=ChanKeyLevels)
    trend_description: str = "未知"
    position_description: str = "未知"


class ChanContext(BaseModel):
    analysis_goal: str = "predict_next_move"
    market_type: str = "crypto"
    allowed_strategy: list[str] = Field(
        default_factory=lambda: ["trend_follow", "range_trade"]
    )


class ChanStructureSnapshot(BaseModel):
    """design.md §3.7.6 缠论结构快照顶层契约。"""

    meta: ChanMeta
    market: ChanMarket
    bi: list[ChanBiItem]
    segment: list[ChanSegmentItem]
    center: list[ChanCenterItem]
    signal: ChanSignal
    structure_summary: ChanStructureSummary
    context: ChanContext = Field(default_factory=ChanContext)


class AnalysisHistoryBlock(BaseModel):
    """get_chan_structure 返回的历史记忆块（结构事实仍在 data 内）。"""

    available: bool = False
    reason: str | None = None
    message: str | None = None
    db_samples_evaluated: int = 0
    context_match: dict[str, str] = Field(default_factory=dict)
    system_stats: dict[str, Any] = Field(default_factory=dict)
    state_machine_hints: dict[str, Any] = Field(default_factory=dict)
    similar_cases: dict[str, Any] = Field(default_factory=dict)
    learning_feedback: dict[str, Any] = Field(default_factory=dict)


class ChanToolSuccess(BaseModel):
    ok: Literal[True] = True
    partial: bool = False
    data: ChanStructureSnapshot
    history: AnalysisHistoryBlock = Field(default_factory=AnalysisHistoryBlock)


class ChanToolFailure(BaseModel):
    ok: Literal[False] = False
    partial: Literal[False] = False
    error_code: str
    message: str
    hint: str = ""


def snapshot_to_dict(snapshot: ChanStructureSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(mode="json")
