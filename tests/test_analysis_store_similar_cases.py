"""Phase 2.5：similar_cases + history_builder 合并 hints。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.analysis_store import init_db
from app.analysis_store.history_builder import compute_state_machine_hints
from app.analysis_store.similar_cases import (
    analyze_similar_cases,
    build_similar_cases_block,
    calculate_similarity,
    calculate_time_decay,
    context_match_to_similarity_ctx,
    search_similar_cases,
    similar_cases_floor,
    SimilarCase,
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


def _insert_similar_row(
    conn: sqlite3.Connection,
    *,
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    timestamp: str,
    hit: bool,
    signal: str = "1buy",
    trend: str = "consolidation",
    position: str = "inside_zs",
    strength: str = "similar",
    direction: str = "up",
) -> None:
    chanlun = {
        "structure_summary": {
            "trend": trend,
            "price_position": position,
            "strength_comparison": strength,
        },
        "signal": {"buy_sell_points": [signal], "divergences": []},
    }
    outcome = {
        "direction": direction,
        "hit_target": hit,
        "hit_stop": False,
        "score": 1.0 if hit else 0.0,
        "outcome": "success" if hit else "failed",
        "max_favorable_move": 2.5 if hit else 0.5,
        "max_adverse_move": 0.5 if hit else 2.0,
    }
    ai = {"primary_scenario": {"target_pct": 3.0, "stop_pct": 1.5}}
    conn.execute(
        """
        INSERT INTO analysis_snapshot
        (symbol, interval, timestamp, price, chanlun_json, ai_json, created_at, evaluated, outcome_json)
        VALUES (?, ?, ?, 100.0, ?, ?, ?, 1, ?)
        """,
        (
            symbol,
            interval,
            timestamp,
            json.dumps(chanlun),
            json.dumps(ai),
            timestamp,
            json.dumps(outcome),
        ),
    )


@pytest.fixture
def similar_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "analysis.db"
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(analysis_db_url=str(db_file)),
    )
    init_db()
    now = datetime.now(timezone.utc)
    with sqlite3.connect(db_file) as conn:
        for i, hit in enumerate([True, False, False, False]):
            ts = (now - timedelta(days=i + 1)).isoformat()
            _insert_similar_row(
                conn,
                timestamp=ts,
                hit=hit,
            )
        _insert_similar_row(
            conn,
            symbol="ETH/USDT",
            timestamp=(now - timedelta(days=5)).isoformat(),
            hit=True,
            signal="1sell",
            trend="down_trend",
            position="below_zs",
        )
        conn.commit()
    return db_file


def _current_ctx() -> dict[str, str]:
    return {
        "signal_type": "1buy",
        "trend": "consolidation",
        "position": "inside_zs",
        "strength": "similar",
    }


def test_calculate_similarity_weights() -> None:
    current = _current_ctx()
    hist = dict(current)
    score = calculate_similarity(
        current,
        hist,
        symbol_match=True,
        interval_match=True,
    )
    assert score == 100.0


def test_calculate_time_decay_recent() -> None:
    decay = calculate_time_decay(
        "2026-05-25T00:00:00+00:00",
        "2026-05-28T00:00:00+00:00",
        half_life_days=30,
    )
    assert 0.9 <= decay <= 1.0


def test_search_similar_cases_filters_mismatch(similar_db: Path) -> None:
    cases, threshold = search_similar_cases(
        "BTC/USDT",
        "1h",
        _current_ctx(),
        enable_time_decay=False,
    )
    assert threshold == 40.0
    assert len(cases) >= 3
    assert all(c.symbol == "BTC/USDT" for c in cases)
    assert all(c.signal_type == "1buy" for c in cases)


def test_analyze_similar_cases_win_rate() -> None:
    cases = [
        SimilarCase(
            snapshot_id=1,
            symbol="BTC/USDT",
            interval="1h",
            timestamp="2026-01-01",
            direction="up",
            signal_type="1buy",
            trend="consolidation",
            position="inside_zs",
            hit_target=True,
            score=1.0,
            target_pct=3.0,
            stop_pct=1.5,
            max_favorable=2.0,
            max_adverse=0.5,
            similarity_score=90.0,
        ),
        SimilarCase(
            snapshot_id=2,
            symbol="BTC/USDT",
            interval="1h",
            timestamp="2026-01-02",
            direction="up",
            signal_type="1buy",
            trend="consolidation",
            position="inside_zs",
            hit_target=False,
            score=0.0,
            target_pct=3.0,
            stop_pct=1.5,
            max_favorable=0.5,
            max_adverse=2.0,
            similarity_score=85.0,
        ),
    ]
    stats = analyze_similar_cases(cases)
    assert stats["has_data"] is True
    assert stats["total"] == 2
    assert stats["win_rate"] == 0.5
    assert stats["confidence"] == "high"


def test_build_similar_cases_block(similar_db: Path) -> None:
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
        signal=ChanSignal(buy_sell_points=["1buy"]),
        structure_summary=ChanStructureSummary(
            trend="consolidation",
            price_position="inside_zs",
            strength_comparison="similar",
        ),
    )
    block = build_similar_cases_block(snap)
    assert block["has_data"] is True
    assert block["count"] >= 3
    assert 0.0 <= block["win_rate"] <= 1.0
    assert "prompt_text" in block
    assert len(block["top_cases"]) <= 5


def test_similar_cases_floor() -> None:
    assert similar_cases_floor(0.1, 5) == "OBSERVE_ONLY"
    assert similar_cases_floor(0.3, 5) == "WAIT_CONFIRMATION"
    assert similar_cases_floor(0.5, 5) is None
    assert similar_cases_floor(0.5, 2) is None


def test_merge_hints_similar_more_conservative(similar_db: Path) -> None:
    from app.analysis_store import calculate_accuracy

    stats = calculate_accuracy()
    similar_block = {
        "has_data": True,
        "count": 4,
        "win_rate": 0.25,
    }
    hints = compute_state_machine_hints(
        stats,
        "BTC/USDT",
        "1h",
        similar_cases=similar_block,
    )
    assert hints["similar_cases_floor"] == "WAIT_CONFIRMATION"
    assert hints["recommended_floor"] in ("OBSERVE_ONLY", "WAIT_CONFIRMATION")


def test_context_match_to_similarity_ctx() -> None:
    ctx = context_match_to_similarity_ctx(
        {
            "signal_type": "1buy",
            "trend": "up_trend",
            "price_position": "above_zs",
            "strength_comparison": "weakening",
        }
    )
    assert ctx["position"] == "above_zs"
    assert ctx["strength"] == "weakening"
