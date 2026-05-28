"""分析快照写入（Phase 2.2，对齐 chanlun save_snapshot）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.analysis_store.db_manager import get_db_conn, safe_json_dumps
from app.observability.logging import get_logger
from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable
from app.services.chan.structure import build_chan_structure_snapshot

logger = get_logger(__name__)

_INVALID_SYMBOL_MARKERS = ("（未指定）", "未指定", "unknown", "n/a")


def save_analysis_run(
    *,
    symbol: str,
    interval: str,
    price: float,
    chanlun_json: dict[str, Any],
    ai_json: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> int | None:
    """写入 ``analysis_snapshot``，返回 ``snapshot_id``；失败返回 ``None``（不抛错）。"""
    now = timestamp or datetime.now(timezone.utc).isoformat()
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO analysis_snapshot
                (symbol, interval, timestamp, price, chanlun_json, ai_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    interval,
                    now,
                    float(price),
                    safe_json_dumps(chanlun_json),
                    safe_json_dumps(ai_json) if ai_json is not None else None,
                    now,
                ),
            )
            return int(cur.lastrowid)
    except sqlite3.Error as exc:
        logger.warning("save_analysis_run_db_error", error=str(exc))
        return None
    except Exception as exc:
        logger.warning("save_analysis_run_failed", error=str(exc))
        return None


def _pick_symbol(*candidates: str | None) -> str | None:
    for raw in candidates:
        s = (raw or "").strip()
        if not s:
            continue
        if any(m in s for m in _INVALID_SYMBOL_MARKERS):
            continue
        return s
    return None


def save_technical_deliverable(
    deliverable: TechnicalAnalysisDeliverable,
    *,
    timeframe: str,
    lookback: int,
    symbol_hint: str | None = None,
) -> int | None:
    """落库一次 technical 分析：重算结构快照 + 整份治理后交付物 JSON。

    - ``chanlun_json``：``build_chan_structure_snapshot`` 全量导出
    - ``ai_json``：``TechnicalAnalysisDeliverable.model_dump()``（含 brief + chanlun_v2）
  - 仅当 ``chanlun_v2`` 非空时写入
    """
    if deliverable.chanlun_v2 is None:
        logger.info("save_technical_deliverable_skipped", reason="chanlun_v2_null")
        return None

    symbol = _pick_symbol(
        deliverable.chanlun_v2.meta.symbol,
        deliverable.brief.symbol,
        symbol_hint,
    )
    if not symbol:
        logger.warning("save_technical_deliverable_skipped", reason="invalid_symbol")
        return None

    interval = (
        deliverable.chanlun_v2.meta.interval
        or deliverable.brief.interval
        or timeframe
    ).strip() or timeframe

    try:
        snapshot = build_chan_structure_snapshot(
            symbol=symbol,
            timeframe=interval,
            lookback=lookback,
        )
    except Exception as exc:
        logger.warning(
            "save_technical_deliverable_structure_failed",
            symbol=symbol,
            interval=interval,
            error=str(exc),
        )
        return None

    price = float(deliverable.chanlun_v2.meta.price or snapshot.market.latest_price)
    display_symbol = snapshot.meta.symbol
    display_interval = snapshot.meta.interval

    snapshot_id = save_analysis_run(
        symbol=display_symbol,
        interval=display_interval,
        price=price,
        chanlun_json=snapshot.model_dump(mode="json"),
        ai_json=deliverable.model_dump(mode="json"),
    )
    if snapshot_id is not None:
        logger.info(
            "save_technical_deliverable_ok",
            snapshot_id=snapshot_id,
            symbol=display_symbol,
            interval=display_interval,
        )
    return snapshot_id


def should_persist_analysis(*, save: bool | None = None) -> bool:
    """是否写入分析库：显式 ``save`` 优先，否则读 ``APP_ANALYSIS_SAVE``。"""
    if save is not None:
        return save
    from app.core.config import get_settings

    return get_settings().analysis_save
