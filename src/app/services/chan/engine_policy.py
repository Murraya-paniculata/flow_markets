"""结构引擎选择（Phase 7）：默认 structure-engine，可选 chanlun_icl 对比。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from app.core.config import get_settings

ENGINE_STRUCTURE = "structure-engine"
ENGINE_CHANLUN_ICL = "chanlun_icl"

StructureEngineId = Literal["structure-engine", "chanlun_icl"]
ZsAlgo = Literal["normal", "over_seg", "auto"]

VALID_ENGINES: frozenset[str] = frozenset({ENGINE_STRUCTURE, ENGINE_CHANLUN_ICL})
VALID_ZS_ALGOS: frozenset[str] = frozenset({"normal", "over_seg", "auto"})


def default_chanlun_repo_root() -> Path:
    """flow_markets 与 chanlun 同级目录时的默认路径。"""
    fm_root = Path(__file__).resolve().parents[4]
    return (fm_root.parent / "chanlun").resolve()


def resolve_structure_engine(override: str | None = None) -> StructureEngineId:
    raw = (
        (override or "").strip().lower()
        or (get_settings().chan_structure_engine or "").strip().lower()
        or os.environ.get("CHAN_STRUCTURE_ENGINE", "").strip().lower()
        or ENGINE_STRUCTURE
    )
    if raw not in VALID_ENGINES:
        raise ValueError(
            f"不支持的 structure engine: {raw!r}，可选: {', '.join(sorted(VALID_ENGINES))}"
        )
    return raw  # type: ignore[return-value]


def resolve_zs_algo(override: str | None = None) -> ZsAlgo:
    raw = (
        (override or "").strip().lower()
        or (get_settings().chan_zs_algo or "").strip().lower()
        or os.environ.get("CHAN_ZS_ALGO", "").strip().lower()
        or "normal"
    )
    if raw not in VALID_ZS_ALGOS:
        raise ValueError(
            f"不支持的 zs_algo: {raw!r}，可选: {', '.join(sorted(VALID_ZS_ALGOS))}"
        )
    return raw  # type: ignore[return-value]


def resolve_chanlun_repo_root(override: str | None = None) -> Path:
    raw = (
        (override or "").strip()
        or (get_settings().chanlun_repo_root or "").strip()
        or os.environ.get("CHANLUN_REPO_ROOT", "").strip()
        or os.environ.get("APP_CHANLUN_REPO_ROOT", "").strip()
    )
    root = Path(raw).resolve() if raw else default_chanlun_repo_root()
    if not (root / "chanlun_icl.py").is_file():
        raise ImportError(
            f"未找到 chanlun 仓库（缺少 chanlun_icl.py）: {root}。"
            "请设置 APP_CHANLUN_REPO_ROOT 或 CHANLUN_REPO_ROOT。"
        )
    return root
