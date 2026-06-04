"""分析结果写入 output/（Phase 5.5：与 --save / save=true 对齐）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.observability.logging import get_logger
from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable
from app.schemas.technical_analysis_display import format_trader_display
from app.services.chan.multi_timeframe import (
    build_multi_timeframe_snapshot,
    format_multi_timeframe_for_prompt,
)
from app.services.chan.structure import build_chan_structure_snapshot

logger = get_logger(__name__)


def project_root_from_services() -> Path:
    """``src/app/services/analysis_output.py`` → ``flow_markets/`` 项目根。"""
    return Path(__file__).resolve().parents[3]


def should_write_output_artifacts(*, save: bool | None) -> bool:
    """仅显式 ``save=true`` 时写 output/；``APP_ANALYSIS_SAVE``  alone 只落库不写盘。"""
    return save is True


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper().replace("/", "").replace("-", "")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def write_structure_only_artifacts(
    *,
    symbol: str,
    structure_payload: dict[str, Any],
    multi_tf: bool = False,
    interval: str = "1h",
    project_root: Path | None = None,
) -> list[str]:
    """no_ai / structure 子命令：仅写结构 JSON。"""
    root = project_root or project_root_from_services()
    out_dir = root / "output"
    sym = _normalize_symbol(symbol)
    ts = _timestamp()
    if multi_tf:
        path = out_dir / f"multi_timeframe_{sym}_{ts}.json"
    else:
        iv = (interval or "1h").lower().strip()
        path = out_dir / f"{sym}_{iv}_{ts}_structure.json"
    _write_json(path, structure_payload)
    rel = _rel(path, root)
    logger.info("structure_artifacts_written", path=rel)
    return [rel]


def write_analyze_save_artifacts(
    *,
    symbol: str,
    timeframe: str,
    lookback: int,
    deliverable: TechnicalAnalysisDeliverable,
    multi_tf: bool = False,
    project_root: Path | None = None,
) -> list[str]:
    """
    full 分析且 save=true：写 output/ 结构 + 分析 JSON + 终端文案（与 CLI 命名一致）。

    落库仍由 ``save_technical_deliverable`` 负责；本函数只写磁盘。
    """
    root = project_root or project_root_from_services()
    out_dir = root / "output"
    sym = _normalize_symbol(symbol)
    ts = _timestamp()
    paths: list[Path] = []

    if multi_tf:
        mtf_snap = build_multi_timeframe_snapshot(sym, lookback=lookback)
        stem = f"multi_timeframe_{sym}_{ts}"
        paths.append(out_dir / f"{stem}.json")
        _write_json(paths[-1], format_multi_timeframe_for_prompt(mtf_snap))
        interval = "1h"
    else:
        iv = (timeframe or "1h").lower().strip()
        stem = f"{sym}_{iv}_{ts}"
        snap = build_chan_structure_snapshot(sym, iv, lookback=lookback)
        paths.append(out_dir / f"{stem}_structure.json")
        _write_json(paths[-1], snap.model_dump(mode="json"))

    stem_analysis = (
        f"multi_timeframe_{sym}_{ts}" if multi_tf else f"{sym}_{(timeframe or '1h').lower()}_{ts}"
    )
    analysis_path = out_dir / f"{stem_analysis}_analysis.json"
    _write_json(analysis_path, deliverable.model_dump(mode="json"))
    paths.append(analysis_path)

    report_path = out_dir / f"{stem_analysis}_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(format_trader_display(deliverable), encoding="utf-8")
    paths.append(report_path)

    rel_paths = [_rel(p, root) for p in paths]
    logger.info("analyze_artifacts_written", paths=rel_paths, symbol=sym, multi_tf=multi_tf)
    return rel_paths
