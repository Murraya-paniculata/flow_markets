"""analysis_store.persist：save_analysis_run / save_technical_deliverable。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.analysis_store import (
    init_db,
    save_analysis_run,
    save_technical_deliverable,
    should_persist_analysis,
)
from app.analysis_store.db_manager import safe_json_loads
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
from app.schemas.flow_markets_deliverables import (
    ChanlunStateMachineOutput,
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
)


def _minimal_snapshot() -> ChanStructureSnapshot:
    return ChanStructureSnapshot(
        meta=ChanMeta(
            symbol="BTC/USDT",
            interval="1h",
            timestamp="2026-01-01T00:00:00+00:00",
            data_size=ChanDataSize(kline=200, bi=10, segment=2, center=1),
        ),
        market=ChanMarket(latest_price=70000.0),
        bi=[],
        segment=[],
        center=[
            ChanCenterItem(
                index=0,
                zg=71000.0,
                zd=69000.0,
                relation="extend",
            )
        ],
        signal=ChanSignal(buy_sell_points=[], divergences=[]),
        structure_summary=ChanStructureSummary(
            trend="consolidation",
            price_position="inside_zs",
            strength_comparison="similar",
        ),
    )


def _minimal_deliverable() -> TechnicalAnalysisDeliverable:
    return TechnicalAnalysisDeliverable(
        brief=TechnicalBrief(
            symbol="BTC/USDT",
            interval="1h",
            data_status="有足够K线",
            summary="测试摘要",
            analysis_markdown="# 一、技术形态概述\n测试",
            disclaimer="历史形态不保证未来表现；不构成投资建议。",
        ),
        chanlun_v2=ChanlunStateMachineOutput.model_validate(
            {
                "meta": {
                    "symbol": "BTC/USDT",
                    "interval": "1h",
                    "price": 70000.0,
                    "timestamp": "2026-01-01T00:00:00+00:00",
                },
                "state_machine": {
                    "current_state": "WAIT_CONFIRMATION",
                    "active_strategy": {
                        "direction": "up",
                        "status": "WAIT",
                        "entry_gate": {
                            "price_zone": [69500.0, 70100.0],
                            "structure_required": ["price_hold_zd"],
                        },
                        "execution": {
                            "entry_type": "limit",
                            "stop_loss": 68500.0,
                            "target": 72000.0,
                            "rr": 1.5,
                        },
                    },
                    "invalidation": {
                        "invalidate_active_if": ["price_break_zd"],
                        "next_state": "OBSERVE_ONLY",
                    },
                    "standby_strategies": [],
                },
                "structure_judgement": {
                    "trend": "consolidation",
                    "price_position": "inside_zs",
                    "zs": {"zg": 71000, "zd": 69000, "gg": 71500, "dd": 68500},
                },
                "risk_notes": ["测试风险"],
            }
        ),
    )


@pytest.fixture
def analysis_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "analysis.db"
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(analysis_db_url=str(db_file), analysis_save=False),
    )
    init_db()
    return db_file


def test_save_analysis_run_inserts_row(analysis_db: Path) -> None:
    sid = save_analysis_run(
        symbol="BTC/USDT",
        interval="1h",
        price=70000.0,
        chanlun_json={"structure_summary": {"trend": "consolidation"}},
        ai_json={"brief": {"summary": "x"}, "chanlun_v2": {"version": "2.0"}},
    )
    assert sid == 1

    with sqlite3.connect(analysis_db) as conn:
        row = conn.execute(
            "SELECT symbol, evaluated, chanlun_json, ai_json FROM analysis_snapshot WHERE id=1"
        ).fetchone()
    assert row[0] == "BTC/USDT"
    assert row[1] == 0
    assert safe_json_loads(row[2])["structure_summary"]["trend"] == "consolidation"
    assert "chanlun_v2" in safe_json_loads(row[3])


def test_save_technical_deliverable_skips_without_v2(analysis_db: Path) -> None:
    d = _minimal_deliverable()
    d = d.model_copy(update={"chanlun_v2": None})
    assert save_technical_deliverable(d, timeframe="1h", lookback=200) is None
    with sqlite3.connect(analysis_db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM analysis_snapshot").fetchone()[0]
    assert n == 0


def test_save_technical_deliverable_with_mock_structure(
    analysis_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snap = _minimal_snapshot()

    def _fake_build(symbol: str, timeframe: str, lookback: int = 300, **_: Any) -> ChanStructureSnapshot:
        return snap

    monkeypatch.setattr(
        "app.analysis_store.persist.build_chan_structure_snapshot",
        _fake_build,
    )
    sid = save_technical_deliverable(
        _minimal_deliverable(),
        timeframe="1h",
        lookback=200,
    )
    assert sid == 1

    with sqlite3.connect(analysis_db) as conn:
        row = conn.execute(
            "SELECT chanlun_json, ai_json FROM analysis_snapshot WHERE id=1"
        ).fetchone()
    struct = json.loads(row[0])
    ai = json.loads(row[1])
    assert struct["meta"]["symbol"] == "BTC/USDT"
    assert ai["chanlun_v2"]["version"] == "2.0"
    assert "brief" in ai


def test_should_persist_analysis_explicit_and_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(_env_file=None, analysis_save=False),
    )
    assert should_persist_analysis(save=True) is True
    assert should_persist_analysis(save=False) is False
    assert should_persist_analysis(save=None) is False

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(_env_file=None, analysis_save=True),
    )
    assert should_persist_analysis(save=None) is True
    assert should_persist_analysis(save=False) is False
