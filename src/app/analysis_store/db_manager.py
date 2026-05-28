"""分析记忆库：SQLite 连接与表结构（与 chanlun db_manager 对齐）。

表：analysis_snapshot、analysis_outcome。
路径由 APP_ANALYSIS_DB_URL 配置，与 APP_DATABASE_URL 独立。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_db_lock = threading.Lock()

_DEFAULT_URL = "sqlite:///./data/analysis.db"


def resolve_analysis_db_path(url: str | None = None) -> Path:
    """将 APP_ANALYSIS_DB_URL 解析为本地 SQLite 文件路径。

    支持：
    - ``sqlite:///./data/analysis.db``（相对当前工作目录）
    - ``sqlite:////absolute/path.db``
    - 裸路径 ``./data/analysis.db``
    """
    raw = (url or "").strip() or _DEFAULT_URL
    if raw.startswith("sqlite:////"):
        return Path(raw[11:])
    if raw.startswith("sqlite:///"):
        return Path(raw[10:])
    return Path(raw)


def get_db_path() -> Path:
    """当前配置下的数据库文件路径。"""
    from app.core.config import get_settings

    return resolve_analysis_db_path(get_settings().analysis_db_url)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db_conn() -> Iterator[sqlite3.Connection]:
    """线程安全的 SQLite 连接（自动提交/回滚/关闭）。"""
    db_path = get_db_path()
    with _db_lock:
        conn = _connect(db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_db_conn_no_context() -> sqlite3.Connection:
    """非上下文连接（调用方须自行 close）。兼容 chanlun 脚本风格。"""
    return _connect(get_db_path())


def init_db() -> Path:
    """创建表与索引（幂等）。返回数据库文件路径。"""
    db_path = get_db_path()
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                chanlun_json TEXT NOT NULL,
                ai_json TEXT,
                created_at TEXT NOT NULL,
                evaluated INTEGER DEFAULT 0,
                outcome_json TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_outcome (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                check_after_minutes INTEGER NOT NULL,
                future_price REAL NOT NULL,
                max_price REAL NOT NULL,
                min_price REAL NOT NULL,
                result_direction TEXT NOT NULL,
                hit_scenario_rank INTEGER,
                note TEXT,
                checked_at TEXT NOT NULL,
                FOREIGN KEY(snapshot_id) REFERENCES analysis_snapshot(id)
            )
            """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_snapshot_evaluated
            ON analysis_snapshot(evaluated)
            """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_snapshot_symbol_interval
            ON analysis_snapshot(symbol, interval)
            """
        )
    return db_path


def safe_json_loads(json_str: str | None, default: Any = None) -> Any:
    """安全 JSON 反序列化。"""
    if default is None:
        default = {}
    if not json_str or not isinstance(json_str, str):
        return default
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def safe_json_dumps(obj: Any, *, ensure_ascii: bool = False) -> str:
    """安全 JSON 序列化。"""
    try:
        return json.dumps(obj, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError):
        return json.dumps({}, ensure_ascii=ensure_ascii)
