"""Phase 7：结构引擎与 zs_algo 策略。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.chan.backend import build_cchan
from app.services.chan.engine_policy import (
    ENGINE_CHANLUN_ICL,
    ENGINE_STRUCTURE,
    default_chanlun_repo_root,
    resolve_structure_engine,
    resolve_zs_algo,
)
from app.services.chan.structure import build_chan_structure_snapshot


def test_resolve_structure_engine_default():
    assert resolve_structure_engine(None) == ENGINE_STRUCTURE
    assert resolve_structure_engine("structure-engine") == ENGINE_STRUCTURE


def test_resolve_structure_engine_invalid():
    with pytest.raises(ValueError, match="不支持的 structure engine"):
        resolve_structure_engine("unknown")


def test_resolve_zs_algo_default_and_override():
    assert resolve_zs_algo(None) == "normal"
    assert resolve_zs_algo("over_seg") == "over_seg"


def test_default_chanlun_repo_points_to_sibling():
    root = default_chanlun_repo_root()
    assert root.name == "chanlun"
    assert root.parent.name in ("AI课程", "flow_markets") or (root.parent / "flow_markets").exists()


def test_build_cchan_merges_zs_algo_into_opts():
    seen: dict = {}

    class FakeConfig:
        def __init__(self, opts):
            seen["opts"] = opts

    class FakeChan:
        def __init__(self, **kwargs):
            self._lv = kwargs["lv_list"][0]

        def __getitem__(self, _i):
            kl = MagicMock()
            kl.lst = []
            kl.cal_seg_and_zs = MagicMock()
            return kl

        def trigger_load(self, _d):
            pass

    with patch("app.services.chan.backend._import_chan_engine") as imp:
        CChan = FakeChan
        CChanConfig = FakeConfig
        imp.return_value = (
            CChan,
            CChanConfig,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
        build_cchan([], MagicMock(), "BTC", {"zs_algo": "over_seg"})
    assert seen["opts"]["zs_algo"] == "over_seg"


@patch("app.services.chan.structure._run_chan_engine")
@patch("app.services.chan.structure.get_klines")
def test_snapshot_meta_includes_zs_algo(mock_klines, mock_engine) -> None:
    mock_klines.return_value = [
        {
            "open_time": "2024-01-01T00:00:00",
            "open": 1.0,
            "high": 1.1,
            "low": 0.9,
            "close": 1.0,
        }
    ] * 60
    icl = MagicMock()
    icl.get_bis.return_value = []
    icl.get_xds.return_value = []
    icl.get_bi_zss.return_value = []
    icl.get_xd_zss.return_value = []
    mock_engine.return_value = icl

    snap = build_chan_structure_snapshot(
        "BTCUSDT",
        "1h",
        lookback=60,
        zs_algo="over_seg",
    )
    assert snap.meta.engine == ENGINE_STRUCTURE
    assert snap.meta.zs_algo == "over_seg"
    mock_engine.assert_called_once()
    assert mock_engine.call_args.kwargs.get("zs_algo") == "over_seg"


@pytest.mark.skipif(
    not (default_chanlun_repo_root() / "chanlun_icl.py").is_file(),
    reason="chanlun 仓库未检出，跳过 ICL 对比集成",
)
@patch("app.services.chan.structure.get_klines")
def test_chanlun_icl_engine_meta(mock_klines) -> None:
    mock_klines.return_value = [
        {
            "open_time": "2024-01-01T00:00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "close_time": "2024-01-01T01:00:00",
        }
    ] * 80
    snap = build_chan_structure_snapshot(
        "BTCUSDT",
        "1h",
        lookback=80,
        engine_id=ENGINE_CHANLUN_ICL,
    )
    assert snap.meta.engine == ENGINE_CHANLUN_ICL
    assert snap.meta.zs_algo is None
