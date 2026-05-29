"""Phase 2.4：stats_service + history_builder。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.analysis_store import calculate_accuracy, init_db
from app.analysis_store.history_builder import build_history_block, compute_state_machine_hints
from app.analysis_store.stats_formatter import get_stats_summary
from app.core.config import Settings
from app.schemas.chan_structure import (
    ChanCenterItem,
    ChanDataSize,
    ChanMarket,
    ChanMeta,
    ChanSignal,
    ChanStructureSnapshot,
    ChanStructureSummary,
)


def _insert_evaluated(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    interval: str,
    hit: bool,
    direction: str = "up",
) -> None:
    outcome = {
        "direction": direction,
        "hit_target": hit,
        "hit_stop": False,
        "score": 1.0 if hit else 0.0,
        "outcome": "success" if hit else "failed",
        "structure_context": {
            "trend": "consolidation",
            "price_position": "inside_zs",
            "signal_type": "none",
        },
    }
    chanlun = {
        "structure_summary": {"trend": "consolidation", "price_position": "inside_zs"},
        "signal": {"buy_sell_points": [], "divergences": []},
    }
    ai = {"brief": {}, "chanlun_v2": {"state_machine": {"current_state": "WAIT_CONFIRMATION"}}}
    conn.execute(
        """
        INSERT INTO analysis_snapshot
        (symbol, interval, timestamp, price, chanlun_json, ai_json, created_at, evaluated, outcome_json)
        VALUES (?, ?, '2026-01-01T00:00:00+00:00', 100.0, ?, ?, '2026-01-01T00:00:00+00:00', 1, ?)
        """,
        (symbol, interval, json.dumps(chanlun), json.dumps(ai), json.dumps(outcome)),
    )


@pytest.fixture
def stats_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "analysis.db"
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(analysis_db_url=str(db_file)),
    )
    init_db()
    with sqlite3.connect(db_file) as conn:
        for i in range(6):
            _insert_evaluated(
                conn,
                symbol="BTC/USDT",
                interval="1h",
                hit=(i == 0),
            )
        _insert_evaluated(
            conn, symbol="ETH/USDT", interval="1h", hit=True, direction="down"
        )
        conn.execute(
            """
            INSERT INTO analysis_snapshot
            (symbol, interval, timestamp, price, chanlun_json, ai_json, created_at, evaluated, outcome_json)
            VALUES ('BTC/USDT', '1h', '2026-01-02', 100, '{}', '{}', '2026-01-02', 1,
                    '{"error":"insufficient_data","outcome":"failed"}')
            """
        )
        conn.commit()
    return db_file


def test_calculate_accuracy_excludes_insufficient_data(stats_db: Path) -> None:
    stats = calculate_accuracy()
    assert stats["total"] == 7
    assert stats["hit_count"] == 2
    sym = next(s for s in stats["by_symbol"] if s[0] == "BTC/USDT")
    assert sym[1] == 6


def test_state_machine_hints_low_win_rate(stats_db: Path) -> None:
    stats = calculate_accuracy()
    hints = compute_state_machine_hints(stats, "BTC/USDT", "1h")
    assert hints["basis"] == "for_symbol"
    assert hints["basis_hit_rate"] is not None
    assert hints["recommended_floor"] == "OBSERVE_ONLY"


def test_build_history_block_on_snapshot(stats_db: Path) -> None:
    snap = ChanStructureSnapshot(
        meta=ChanMeta(
            symbol="BTC/USDT",
            interval="1h",
            timestamp="2026-05-28T00:00:00+00:00",
            data_size=ChanDataSize(kline=100, bi=5, segment=1, center=1),
        ),
        market=ChanMarket(latest_price=70000.0),
        bi=[],
        segment=[],
        center=[ChanCenterItem(index=0, zg=71000, zd=69000, relation="extend")],
        signal=ChanSignal(),
        structure_summary=ChanStructureSummary(
            trend="consolidation",
            price_position="inside_zs",
        ),
    )
    hist = build_history_block(snap)
    assert hist["available"] is True
    assert hist["system_stats"]["has_data"] is True
    assert hist["system_stats"]["for_symbol"]["key"] == "BTC/USDT"
    assert "prompt_text" in hist["system_stats"]
    assert hist["state_machine_hints"]["recommended_floor"] in (
        "OBSERVE_ONLY",
        "WAIT_CONFIRMATION",
        None,
    )
