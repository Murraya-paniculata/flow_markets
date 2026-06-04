"""chanlun 原工程 ICL → FlowMarkets ChanStructureSnapshot（Phase 7.2，仅对比）。"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from app.schemas.chan_structure import ChanStructureSnapshot
from app.services.chan.engine_policy import (
    ENGINE_CHANLUN_ICL,
    resolve_chanlun_repo_root,
)

_CHANLUN_PATH: Path | None = None

# flow_markets interval → chanlun ICL frequency
_INTERVAL_TO_CHANLUN_FREQ: Dict[str, str] = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "60m": "60m",
    "4h": "240m",
    "240m": "240m",
    "1d": "1440m",
    "1440m": "1440m",
}


def ensure_chanlun_importable(repo_root: Path | None = None) -> Path:
    global _CHANLUN_PATH
    root = (repo_root or resolve_chanlun_repo_root()).resolve()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    _CHANLUN_PATH = root
    return root


def _chanlun_frequency(interval: str) -> str:
    key = (interval or "1h").strip().lower()
    return _INTERVAL_TO_CHANLUN_FREQ.get(key, key)


def build_snapshot_via_chanlun_icl(
    *,
    display_symbol: str,
    interval: str,
    raw_klines: List[Dict[str, Any]],
    repo_root: Path | None = None,
    max_bi: int = 15,
    max_segment: int = 5,
) -> ChanStructureSnapshot:
    """
    使用 chanlun 仓库 ICL + ChanlunAIExporter 生成与 structure.py 同契约的快照。

    Raises:
        ImportError: chanlun 仓库不可用
        ValueError: 数据不足
    """
    if len(raw_klines) < 50:
        raise ValueError(f"K 线不足：chanlun ICL 至少需要 50 根，当前 {len(raw_klines)} 根")

    root = ensure_chanlun_importable(repo_root)
    from chanlun_adapter import convert_to_chanlun_bars  # noqa: WPS433
    from chanlun_icl import ICL  # noqa: WPS433
    from chanlun_ai_exporter import ChanlunAIExporter  # noqa: WPS433

    bars = convert_to_chanlun_bars(raw_klines)
    df = pd.DataFrame(bars).rename(
        columns={
            "date": "date",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "a": "volume",
        }
    )
    frequency = _chanlun_frequency(interval)
    icl = ICL(code=display_symbol, frequency=frequency, config=None)
    icl = icl.process_klines(df)

    exporter = ChanlunAIExporter()
    payload = exporter.export(
        icl=icl,
        symbol=display_symbol,
        interval=interval,
        klines=raw_klines,
    )
    meta = dict(payload.get("meta") or {})
    meta["engine"] = ENGINE_CHANLUN_ICL
    meta["engine_version"] = f"chanlun-repo@{root.name}"
    meta["zs_algo"] = None
    if max_bi and isinstance(payload.get("bi"), list) and len(payload["bi"]) > max_bi:
        total_bi = meta.get("data_size", {}).get("bi", len(payload["bi"]))
        payload["bi"] = payload["bi"][-max_bi:]
        meta["trim"] = {
            "max_bi": max_bi,
            "total_bi": int(total_bi) if total_bi else len(payload["bi"]),
            "max_segment": max_segment,
        }
    if max_segment and isinstance(payload.get("segment"), list):
        segs = payload["segment"]
        if len(segs) > max_segment:
            total_seg = meta.get("data_size", {}).get("segment", len(segs))
            payload["segment"] = segs[-max_segment:]
            trim = meta.get("trim") or {}
            trim["max_segment"] = max_segment
            trim["total_segment"] = int(total_seg) if total_seg else len(segs)
            meta["trim"] = trim
    payload["meta"] = meta
    payload["meta"]["timestamp"] = datetime.now(timezone.utc).isoformat()

    return ChanStructureSnapshot.model_validate(payload)
