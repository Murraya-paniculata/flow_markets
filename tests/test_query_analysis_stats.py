"""Phase 4.3：query_analysis_stats CLI 逻辑。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.analysis_store import init_db
from app.analysis_store.query_stats_cli import (
    STATS_CSV_COLUMNS,
    export_stats_csv,
    print_accuracy_report,
    _row_for_stats_csv,
)
from app.core.config import Settings


def _seed(conn: sqlite3.Connection) -> None:
    outcome = {
        "direction": "up",
        "hit_target": True,
        "hit_stop": False,
        "score": 1.0,
        "outcome": "success",
        "target_pct": 2.0,
        "stop_pct": 1.0,
        "evaluated_bars": 48,
        "entry_price": 100.0,
        "max_high": 103.0,
        "min_low": 99.0,
        "structure_context": {
            "trend": "up_trend",
            "price_position": "below_zs",
            "signal_type": "1buy",
            "has_signal": True,
        },
    }
    chanlun = {
        "structure_summary": {"trend": "up_trend", "price_position": "below_zs"},
        "signal": {"buy_sell_points": ["1buy"], "divergences": []},
    }
    ai = {
        "brief": {"summary": "测试摘要"},
        "signal_quality": {
            "grade": "B",
            "total_score": 65.0,
            "action": "trade",
        },
        "chanlun_v2": {
            "meta": {"price": 100.0},
            "state_machine": {
                "current_state": "WAIT_CONFIRMATION",
                "active_strategy": {
                    "direction": "up",
                    "execution": {
                        "target": 102.0,
                        "stop_loss": 98.5,
                        "rr": 1.5,
                    },
                },
            },
        },
    }
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
        _seed(conn)
        conn.commit()
    return db_file


def test_row_for_stats_csv_includes_quality() -> None:
    ai = {
        "signal_quality": {"grade": "A", "total_score": 80, "action": "trade"},
        "chanlun_v2": {"state_machine": {"active_strategy": {"direction": "up"}}},
        "brief": {"summary": "x"},
    }
    outcome = {"direction": "up", "hit_target": True, "outcome": "success", "score": 1.0}
    chanlun = {
        "signal": {"buy_sell_points": ["1buy"], "divergences": []},
        "structure_summary": {"trend": "up_trend", "price_position": "below_zs"},
    }
    row = _row_for_stats_csv(1, "BTC/USDT", "1h", "t", 100.0, ai, outcome, chanlun)
    assert row is not None
    assert row["信号质量评级"] == "A-优质"
    assert row["信号类型"] == "一买"


def test_export_stats_csv(stats_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "export.csv"
    n = export_stats_csv(out)
    assert n == 1
    text = out.read_text(encoding="utf-8-sig")
    assert "信号质量评级" in text
    assert "一买" in text


def test_print_accuracy_report_smoke(stats_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    print_accuracy_report(symbol="BTC/USDT", interval="1h")
    captured = capsys.readouterr()
    assert "按趋势类型" in captured.out or "按信号类型" in captured.out
    assert "BTC/USDT" in captured.out or "总样本" in captured.out


def test_stats_csv_columns_complete() -> None:
    assert "信号质量得分" in STATS_CSV_COLUMNS
    assert "趋势类型" in STATS_CSV_COLUMNS
