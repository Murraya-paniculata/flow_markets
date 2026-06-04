"""Phase 4.4：stats_visualizer PNG 生成。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.analysis_store import init_db
from app.core.config import Settings

pytest.importorskip("matplotlib")


def _seed(conn: sqlite3.Connection) -> None:
    outcome = {
        "direction": "up",
        "hit_target": True,
        "hit_stop": False,
        "score": 0.9,
        "enhanced_score": 0.95,
        "outcome": "success",
        "max_favorable_move": 3.0,
        "max_adverse_move": -1.0,
    }
    chanlun = {
        "structure_summary": {"trend": "up_trend", "price_position": "below_zs"},
        "signal": {"buy_sell_points": ["1buy"], "divergences": []},
    }
    ai = {
        "signal_quality": {"grade": "B", "total_score": 70, "action": "trade"},
        "chanlun_v2": {"state_machine": {"active_strategy": {"direction": "up"}}},
    }
    for i in range(8):
        conn.execute(
            """
            INSERT INTO analysis_snapshot
            (symbol, interval, timestamp, price, chanlun_json, ai_json, created_at, evaluated, outcome_json)
            VALUES ('BTC/USDT', '1h', ?, 100.0, ?, ?, '2026-01-01', 1, ?)
            """,
            (
                f"2026-01-{i + 1:02d}T00:00:00+00:00",
                json.dumps(chanlun),
                json.dumps(ai),
                json.dumps({**outcome, "score": 0.5 + i * 0.05}),
            ),
        )


@pytest.fixture
def viz_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "analysis.db"
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(analysis_db_url=str(db_file)),
    )
    init_db()
    with sqlite3.connect(db_file) as conn:
        _seed(conn)
        conn.commit()
    return db_file


def test_generate_all_stats_charts_writes_pngs(viz_db: Path, tmp_path: Path) -> None:
    from app.analysis_store.stats_visualizer import generate_all_stats_charts

    out = tmp_path / "stats"
    paths = generate_all_stats_charts(out)
    assert len(paths) >= 3
    names = {p.name for p in paths}
    assert "win_rate_structure.png" in names
    assert "score_distribution.png" in names
    assert "performance_over_time.png" in names
    for p in paths:
        assert p.stat().st_size > 500
