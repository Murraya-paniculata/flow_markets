"""Phase 4.2：StatsService 分维度胜率。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.analysis_store.stats_formatter import format_enhanced_report, format_stats_for_prompt
from app.analysis_store.stats_service import StatsService, calculate_accuracy, is_scorable_outcome
from app.core.config import Settings
from app.analysis_store import init_db


def _insert(
    conn: sqlite3.Connection,
    *,
    trend: str = "consolidation",
    position: str = "inside_zs",
    signal_points: list[str] | None = None,
    hit: bool = True,
    direction: str = "up",
    grade: str | None = None,
) -> None:
    signal_points = signal_points or []
    outcome = {
        "direction": direction,
        "hit_target": hit,
        "hit_stop": False,
        "score": 1.0 if hit else 0.0,
        "outcome": "success" if hit else "failed",
        "structure_context": {
            "trend": trend,
            "price_position": position,
            "signal_type": "none",
        },
    }
    chanlun = {
        "structure_summary": {"trend": trend, "price_position": position},
        "signal": {"buy_sell_points": signal_points, "divergences": []},
    }
    ai: dict = {
        "brief": {},
        "chanlun_v2": {
            "state_machine": {
                "active_strategy": {"direction": direction},
            }
        },
    }
    if grade:
        ai["signal_quality"] = {"grade": grade, "total_score": 80, "action": "trade"}

    conn.execute(
        """
        INSERT INTO analysis_snapshot
        (symbol, interval, timestamp, price, chanlun_json, ai_json, created_at, evaluated, outcome_json)
        VALUES ('BTC/USDT', '1h', '2026-01-01T00:00:00+00:00', 100.0, ?, ?, '2026-01-01', 1, ?)
        """,
        (json.dumps(chanlun), json.dumps(ai), json.dumps(outcome)),
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
        for _ in range(4):
            _insert(conn, trend="up_trend", hit=True)
        for _ in range(2):
            _insert(conn, trend="down_trend", hit=False)
        for _ in range(3):
            _insert(conn, position="above_zs", hit=True)
        for _ in range(2):
            _insert(conn, position="below_zs", hit=False)
        for _ in range(5):
            _insert(conn, signal_points=["1buy"], hit=True, direction="up")
        _insert(conn, signal_points=["1sell"], hit=False, direction="down")
        _insert(
            conn,
            trend="consolidation",
            hit=True,
            grade="A",
        )
        _insert(
            conn,
            trend="consolidation",
            hit=False,
            grade="D",
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


def test_stats_service_by_trend_win_rate(stats_db: Path) -> None:
    svc = StatsService()
    records = svc.fetch_evaluated_records()
    assert len(records) == 19

    trends = {b.key: b for b in svc.by_trend(records)}
    assert trends["up_trend"].total == 4
    assert trends["up_trend"].win_rate == 1.0
    assert trends["down_trend"].total == 2
    assert trends["down_trend"].win_rate == 0.0


def test_stats_service_by_position_and_signal(stats_db: Path) -> None:
    svc = StatsService()
    records = svc.fetch_evaluated_records()
    positions = {b.key: b for b in svc.by_position(records)}
    assert positions["above_zs"].win_rate == 1.0
    assert positions["below_zs"].win_rate == 0.0

    signals = {b.key: b for b in svc.by_signal_type(records)}
    assert signals["1buy"].total == 5
    assert signals["1buy"].win_rate == 1.0
    assert signals["1sell"].win_rate == 0.0


def test_stats_service_signal_quality_grade(stats_db: Path) -> None:
    svc = StatsService()
    records = svc.fetch_evaluated_records()
    grades = {b.key: b for b in svc.by_signal_quality(records)}
    assert grades["A"].hits == 1
    assert grades["D"].hits == 0


def test_calculate_accuracy_backward_compat(stats_db: Path) -> None:
    stats = calculate_accuracy()
    assert stats["total"] == 19
    assert stats["win_rate"] > 0
    assert len(stats["by_trend"]) >= 2
    assert "buckets" in stats
    assert stats["buckets"]["by_trend"][0]["win_rate"] is not None


def test_format_enhanced_report(stats_db: Path) -> None:
    text = format_enhanced_report()
    assert "按趋势类型" in text
    assert "按信号类型" in text


def test_format_stats_for_prompt_includes_structure_buckets(stats_db: Path) -> None:
    stats = calculate_accuracy()
    prompt = format_stats_for_prompt(stats, "BTC/USDT", "1h")
    assert "按趋势统计" in prompt
    assert "按价格位置统计" in prompt
    assert "按信号类型统计" in prompt


def test_is_scorable_outcome() -> None:
    assert is_scorable_outcome({"hit_target": True}) is True
    assert is_scorable_outcome({"error": "insufficient_data"}) is False
