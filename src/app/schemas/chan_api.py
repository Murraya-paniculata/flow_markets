"""缠论图表 API 响应模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChanKlineChartMeta(BaseModel):
    symbol: str
    interval: str
    timezone: str = "Asia/Shanghai"
    base_interval: str = "5m"
    chart_axis: str = "merged"
    merged_count: int = 0
    count: int = 0
    limit: int = 0
    engine: str = "structure-engine"


class ChanKlineChartResponse(BaseModel):
    meta: ChanKlineChartMeta
    klines: list[dict[str, Any]] = Field(default_factory=list)
    merged_klines: list[dict[str, Any]] = Field(default_factory=list)
    bi: list[dict[str, Any]] = Field(default_factory=list)
    xd: list[dict[str, Any]] = Field(default_factory=list)
    zs: list[dict[str, Any]] = Field(default_factory=list)
    fx: list[dict[str, Any]] = Field(default_factory=list)
    bsp: list[dict[str, Any]] = Field(default_factory=list)
