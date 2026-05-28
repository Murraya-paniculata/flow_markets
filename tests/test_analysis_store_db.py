"""analysis_store：表结构与连接（Phase 2.1）。"""

import sqlite3
from pathlib import Path

import pytest

from app.analysis_store import (
    get_db_conn,
    init_db,
    resolve_analysis_db_path,
    safe_json_dumps,
    safe_json_loads,
)
from app.core.config import Settings


def test_resolve_analysis_db_path_sqlite_relative() -> None:
    p = resolve_analysis_db_path("sqlite:///./data/analysis.db")
    assert p == Path("./data/analysis.db")


def test_resolve_analysis_db_path_bare() -> None:
    p = resolve_analysis_db_path("/tmp/fm_test_analysis.db")
    assert p == Path("/tmp/fm_test_analysis.db")


def test_init_db_creates_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "analysis.db"
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(analysis_db_url=str(db_file)),
    )

    path = init_db()
    assert path == db_file
    assert db_file.is_file()

    with get_db_conn() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "analysis_snapshot" in tables
    assert "analysis_outcome" in tables

    with sqlite3.connect(db_file) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(analysis_snapshot)")]
    assert "chanlun_json" in cols
    assert "outcome_json" in cols
    assert "evaluated" in cols


def test_safe_json_helpers() -> None:
    assert safe_json_loads('{"a": 1}') == {"a": 1}
    assert safe_json_loads("{bad") == {}
    assert safe_json_dumps({"x": "中文"}) == '{"x": "中文"}'
