"""chanlun_fm 统一 CLI 测试（Phase 5.3）。"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _load_chanlun_fm():
    path = _ROOT / "scripts" / "chanlun_fm.py"
    spec = importlib.util.spec_from_file_location("chanlun_fm_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parser_subcommands() -> None:
    fm = _load_chanlun_fm()
    parser = fm._build_parser()
    args = parser.parse_args(["analyze", "BTCUSDT", "1h", "--limit", "200"])
    assert args.command == "analyze"
    assert args.symbol == "BTCUSDT"
    assert args.interval == "1h"
    assert args.limit == 200
    assert args.multi_tf is False

    args_m = parser.parse_args(["analyze", "BTCUSDT", "1h", "--multi-tf", "--save"])
    assert args_m.multi_tf is True
    assert args_m.save is True

    args_s = parser.parse_args(["structure", "ETHUSDT", "4h", "--json"])
    assert args_s.command == "structure"
    assert args_s.json is True

    args_st = parser.parse_args(["stats", "--accuracy", "--symbol", "BTC/USDT"])
    assert args_st.command == "stats"
    assert args_st.accuracy is True


def test_main_routes_analyze(monkeypatch: pytest.MonkeyPatch) -> None:
    fm = _load_chanlun_fm()
    called: dict = {}

    def fake_analyze(args, *, root):
        called["command"] = "analyze"
        called["symbol"] = args.symbol
        called["multi_tf"] = args.multi_tf
        return 0

    monkeypatch.setattr("app.cli.analyze_cmd.run_analyze", fake_analyze)
    monkeypatch.setattr("app.cli.structure_cmd.run_structure", lambda *a, **k: 99)
    monkeypatch.setattr("app.cli.stats_cmd.run_stats", lambda *a, **k: 99)

    rc = fm.main(["analyze", "BTCUSDT", "1h", "--multi-tf"])
    assert rc == 0
    assert called["command"] == "analyze"
    assert called["symbol"] == "BTCUSDT"
    assert called["multi_tf"] is True


def test_main_routes_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    fm = _load_chanlun_fm()
    called: dict = {}

    def fake_structure(args, *, root):
        called["interval"] = args.interval
        return 0

    monkeypatch.setattr("app.cli.structure_cmd.run_structure", fake_structure)
    monkeypatch.setattr("app.cli.analyze_cmd.run_analyze", lambda *a, **k: 99)

    rc = fm.main(["structure", "BTCUSDT", "1h"])
    assert rc == 0
    assert called["interval"] == "1h"


def test_main_routes_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    fm = _load_chanlun_fm()
    called: dict = {}

    def fake_stats(args, *, root):
        called["accuracy"] = args.accuracy
        return 0

    monkeypatch.setattr("app.cli.stats_cmd.run_stats", fake_stats)

    rc = fm.main(["stats", "--accuracy"])
    assert rc == 0
    assert called["accuracy"] is True


def test_structure_single_mock(capsys: pytest.CaptureFixture[str]) -> None:
    from app.cli.common import bootstrap
    from app.cli.structure_cmd import run_structure

    root = bootstrap()
    fake = MagicMock()
    fake.meta.data_size.kline = 100
    fake.meta.data_size.bi = 5
    fake.meta.data_size.segment = 2
    fake.meta.data_size.center = 1
    fake.meta.symbol = "BTCUSDT"
    fake.meta.interval = "1h"
    fake.market.latest_price = 1.0
    fake.center = []
    fake.bi = []
    fake.signal.buy_sell_points = []
    fake.signal.divergences = []
    fake.structure_summary.trend_description = "升"
    fake.structure_summary.position_description = "上"
    fake.structure_summary.key_levels.zg = 0
    fake.structure_summary.key_levels.zd = 0
    fake.structure_summary.key_levels.gg = 0
    fake.structure_summary.key_levels.dd = 0
    fake.model_dump.return_value = {"ok": True}

    args = argparse.Namespace(
        symbol="BTCUSDT",
        interval="1h",
        limit=200,
        multi_tf=False,
        save=False,
        json=False,
    )

    with patch(
        "app.services.chan.structure.build_chan_structure_snapshot",
        return_value=fake,
    ):
        rc = run_structure(args, root=root)

    assert rc == 0
    out = capsys.readouterr().out
    assert "结构分析完成" in out
