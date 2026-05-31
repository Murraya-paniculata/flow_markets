"""Phase 2.6：learning_feedback + history_builder。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.analysis_store import init_db
from app.analysis_store.history_builder import build_history_block
from app.analysis_store.learning_feedback import (
    MIN_BUCKET_SAMPLES,
    analyze_learning_feedback,
    build_learning_feedback_block,
    format_learning_prompt,
)
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


def _insert_scorable(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    hit: bool,
    direction: str = "up",
    signal: str = "1buy",
) -> None:
    chanlun = {
        "structure_summary": {
            "trend": "consolidation",
            "price_position": "inside_zs",
            "strength_comparison": "similar",
        },
        "signal": {"buy_sell_points": [signal], "divergences": []},
    }
    outcome = {
        "direction": direction,
        "hit_target": hit,
        "hit_stop": False,
        "score": 1.0 if hit else 0.0,
        "outcome": "success" if hit else "failed",
        "target_pct": 3.0,
        "stop_pct": 1.5,
        "max_favorable_move": 2.5 if hit else 0.4,
        "max_adverse_move": 0.5 if hit else 2.0,
        "entry_price": 100.0,
    }
    ai = {
        "brief": {"summary": "test"},
        "chanlun_v2": {
            "meta": {"symbol": "BTC/USDT", "interval": "1h", "price": 100.0, "timestamp": timestamp},
            "state_machine": {
                "current_state": "WAIT_CONFIRMATION",
                "active_strategy": {
                    "direction": direction,
                    "status": "WAIT",
                    "entry_gate": {"price_zone": [99, 101], "structure_required": ["x"]},
                    "execution": {"entry_type": "limit", "stop_loss": 98.5, "target": 103.0, "rr": 2.0},
                },
                "invalidation": {"invalidate_active_if": ["x"], "next_state": "OBSERVE_ONLY"},
                "standby_strategies": [],
            },
            "structure_judgement": {
                "trend": "consolidation",
                "price_position": "inside_zs",
                "zs": {"zg": 102, "zd": 98, "gg": 103, "dd": 97},
            },
            "risk_notes": ["test"],
        },
    }
    conn.execute(
        """
        INSERT INTO analysis_snapshot
        (symbol, interval, timestamp, price, chanlun_json, ai_json, created_at, evaluated, outcome_json)
        VALUES ('BTC/USDT', '1h', ?, 100.0, ?, ?, ?, 1, ?)
        """,
        (timestamp, json.dumps(chanlun), json.dumps(ai), timestamp, json.dumps(outcome)),
    )


@pytest.fixture
def learning_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "analysis.db"
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(analysis_db_url=str(db_file)),
    )
    init_db()
    now = datetime.now(timezone.utc)
    with sqlite3.connect(db_file) as conn:
        for i, hit in enumerate([True, False, False, True, False, True]):
            ts = (now - timedelta(days=i + 1)).isoformat()
            _insert_scorable(conn, timestamp=ts, hit=hit, direction="up" if hit else "down")
        conn.commit()
    return db_file


def _snapshot() -> ChanStructureSnapshot:
    return ChanStructureSnapshot(
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
        signal=ChanSignal(buy_sell_points=["1buy"]),
        structure_summary=ChanStructureSummary(
            trend="consolidation",
            price_position="inside_zs",
            strength_comparison="similar",
        ),
    )


def test_analyze_learning_feedback(learning_db: Path) -> None:
    report = analyze_learning_feedback(days=30, symbol="BTC/USDT", interval="1h")
    assert report.total_predictions == 6
    assert 0.0 <= report.overall_win_rate <= 1.0
    assert "up" in report.by_direction or "down" in report.by_direction


def test_build_learning_feedback_block(learning_db: Path) -> None:
    block = build_learning_feedback_block(_snapshot())
    assert block["has_data"] is True
    assert block["total_predictions"] >= MIN_BUCKET_SAMPLES
    assert "prompt_text" in block
    assert "自我认知" in block["prompt_text"]


def test_format_learning_prompt_insufficient() -> None:
    from app.analysis_store.learning_feedback import LearningReport

    text = format_learning_prompt(LearningReport(total_predictions=2))
    assert "样本不足" in text


def test_history_includes_learning_feedback(learning_db: Path) -> None:
    hist = build_history_block(_snapshot())
    lf = hist["learning_feedback"]
    assert lf["has_data"] is True
    assert "overall_win_rate" in lf
    assert hist["available"] is True
