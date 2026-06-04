"""Phase 4.5：weight_optimizer 与 optimized_weights.json。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.analysis_store import init_db
from app.analysis_store.signal_quality import DEFAULT_WEIGHTS, reload_weights
from app.analysis_store.weight_optimizer import (
    MIN_SAMPLES_HARD,
    WeightOptimizer,
    dimension_ratios_for_record,
    run_weight_optimization,
)
from app.core.config import Settings


def _seed(conn: sqlite3.Connection, n: int = 25) -> None:
    outcome_base = {
        "direction": "up",
        "hit_target": True,
        "hit_stop": False,
        "score": 0.85,
        "enhanced_score": 0.9,
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
        "primary_scenario": {"direction": "up", "target_pct": 3.0, "stop_pct": 1.5},
    }
    for i in range(n):
        hit = i % 3 != 0
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
                json.dumps({**outcome_base, "hit_target": hit, "score": 0.5 + (i % 5) * 0.1}),
            ),
        )


@pytest.fixture
def opt_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "analysis.db"
    weights_file = tmp_path / "optimized_weights.json"
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(analysis_db_url=str(db_file)),
    )
    monkeypatch.setattr("app.analysis_store.signal_quality._weights_path", lambda: weights_file)
    monkeypatch.setattr("app.analysis_store.weight_optimizer._weights_path", lambda: weights_file)
    init_db()
    with sqlite3.connect(db_file) as conn:
        _seed(conn)
        conn.commit()
    return weights_file


def test_dimension_ratios_in_unit_range() -> None:
    chanlun = {
        "structure_summary": {"trend": "up_trend", "price_position": "below_zs"},
        "signal": {"buy_sell_points": ["1buy"], "divergences": ["bc"]},
    }
    ai = {"primary_scenario": {"direction": "up", "target_pct": 3.0, "stop_pct": 1.0}}
    ratios = dimension_ratios_for_record(chanlun, ai)
    assert set(ratios.keys()) == set(DEFAULT_WEIGHTS.keys())
    assert all(0 <= v <= 1.0 for v in ratios.values())


def test_load_and_report(opt_db: Path) -> None:
    opt = WeightOptimizer()
    count = opt.load_historical_data()
    assert count >= MIN_SAMPLES_HARD
    opt.analyze_dimensions()
    report = opt.generate_report()
    assert "权重优化分析报告" in report
    assert "信号类型" in report


def test_save_and_reload_weights(opt_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opt = WeightOptimizer()
    opt.load_historical_data()
    opt.analyze_dimensions()
    path = opt.save_optimized_weights("correlation")
    assert path == opt_db.resolve()
    assert opt_db.exists()
    data = json.loads(opt_db.read_text(encoding="utf-8"))
    assert data["method"] == "correlation"
    assert abs(sum(data["weights"].values()) - 100) < 0.01

    reloaded = reload_weights()
    assert set(reloaded.keys()) == set(DEFAULT_WEIGHTS.keys())
    assert reloaded == {k: float(v) for k, v in data["weights"].items()}


def test_run_weight_optimization_insufficient_samples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "small.db"
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(analysis_db_url=str(db_file)),
    )
    init_db()
    with sqlite3.connect(db_file) as conn:
        _seed(conn, n=5)
        conn.commit()

    count, msg, saved = run_weight_optimization(save=False)
    assert count < MIN_SAMPLES_HARD
    assert "样本太少" in msg
    assert saved is None
