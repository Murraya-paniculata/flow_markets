"""get_chan_structure：为技术分析师提供缠论结构快照（design.md §3.7.6）。"""

from __future__ import annotations

import json
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from app.observability.logging import get_logger
from app.schemas.chan_structure import ChanToolFailure, ChanToolSuccess
from app.services.chan.structure import (
    DEFAULT_LOOKBACK,
    build_chan_structure_snapshot,
)

logger = get_logger(__name__)

SUPPORTED_TIMEFRAMES = "5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M"


class GetChanStructureInput(BaseModel):
    """缠论结构工具输入（面向 Agent 的极简参数）。"""

    symbol: str = Field(
        ...,
        description=(
            "交易对，如 BTCUSDT 或 BTC/USDT。"
            "将自动映射到 Binance 现货符号。"
        ),
    )
    timeframe: str = Field(
        "1h",
        description=f"K 线周期。支持: {SUPPORTED_TIMEFRAMES}。",
    )
    lookback: int = Field(
        DEFAULT_LOOKBACK,
        ge=50,
        le=800,
        description=(
            "回溯 K 线根数（经服务端按周期封顶）。"
            "缠论计算至少需要 50 根；建议 200–350。"
        ),
    )

    @field_validator("symbol")
    @classmethod
    def strip_symbol(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("symbol 不能为空")
        return s

    @field_validator("timeframe")
    @classmethod
    def strip_timeframe(cls, v: str) -> str:
        return (v or "1h").strip()


class GetChanStructureTool(BaseTool):
    """
    获取缠论结构快照 JSON（笔/线段/中枢/买卖点/structure_summary）。

    内部流程：拉取 K 线 → chanpy 计算 → 裁剪为 Agent 可消费的紧凑 JSON。
    禁止 Agent 自行编造笔、中枢或买卖点；解读须引用本工具返回字段。
    """

    name: str = "get_chan_structure"
    description: str = (
        "获取指定交易对与周期的缠论结构快照（ChanStructureSnapshot JSON）。"
        "返回内容包括：meta（标的/周期/数据条数）、market.latest_price、"
        "最近若干笔(bi)、线段(segment)、中枢(center)、买卖点汇总(signal)、"
        "以及 structure_summary（趋势/价格相对中枢位置/力度对比/关键价位）。"
        "技术分析师应优先依据本工具输出撰写结构结论，不得虚构工具未返回的笔或中枢。"
        f"参数：symbol（必填）、timeframe（默认 1h，支持 {SUPPORTED_TIMEFRAMES}）、"
        f"lookback（默认 {DEFAULT_LOOKBACK}，≥50）。"
        "失败时返回 ok=false 与 error_code，须按 FR-33 声明缠论结构暂不可用。"
    )
    args_schema: type[BaseModel] = GetChanStructureInput

    def _run(
        self,
        symbol: str,
        timeframe: str = "1h",
        lookback: int = DEFAULT_LOOKBACK,
    ) -> str:
        logger.info(
            "get_chan_structure_start",
            symbol=symbol,
            timeframe=timeframe,
            lookback=lookback,
        )
        try:
            snapshot = build_chan_structure_snapshot(
                symbol=symbol,
                timeframe=timeframe,
                lookback=lookback,
            )
            envelope = ChanToolSuccess(data=snapshot)
            payload = envelope.model_dump(mode="json")
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            logger.info(
                "get_chan_structure_success",
                symbol=snapshot.meta.symbol,
                interval=snapshot.meta.interval,
                bi_exported=len(snapshot.bi),
                chars=len(text),
            )
            return text
        except ValueError as exc:
            return self._fail("INSUFFICIENT_DATA", str(exc), _hint_for_value_error(exc))
        except RuntimeError as exc:
            return self._fail("UPSTREAM_ERROR", str(exc), "请检查网络或稍后重试 Binance/chanpy。")
        except Exception as exc:
            logger.exception("get_chan_structure_error", error=str(exc))
            return self._fail(
                "ENGINE_ERROR",
                str(exc),
                "缠论引擎异常；技术分析师应声明结构暂不可用，勿手写替代结构。",
            )

    @staticmethod
    def _fail(error_code: str, message: str, hint: str = "") -> str:
        envelope = ChanToolFailure(
            error_code=error_code,
            message=message,
            hint=hint,
        )
        logger.warning(
            "get_chan_structure_failed",
            error_code=error_code,
            message=message[:200],
        )
        return json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _hint_for_value_error(exc: ValueError) -> str:
    msg = str(exc)
    if "不支持" in msg or "周期" in msg:
        return f"请使用支持的 timeframe：{SUPPORTED_TIMEFRAMES}。"
    if "K 线" in msg or "不足" in msg:
        return "增大 lookback，或换更长周期（如 4h/1d）。"
    return "请检查 symbol 与 timeframe 参数。"
