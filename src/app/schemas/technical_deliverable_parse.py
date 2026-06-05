"""从 LLM 文本解析 TechnicalAnalysisDeliverable（容错 JSON）。"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.observability.logging import get_logger
from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable

logger = get_logger(__name__)

_STANDBY_DIRECTIONS = frozenset({"up", "down", "range"})
_DEFAULT_DISCLAIMER = "历史形态不保证未来表现；不构成投资建议。"


def _extract_json_blob(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("LLM 输出为空")

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("输出中未找到 JSON 对象")
    return raw[start : end + 1]


def _fix_common_llm_json_glitches(blob: str) -> str:
    """修复模型偶发的重复花括号等语法错误。"""
    s = blob
    s = re.sub(r":\s*\{\s*\{", ": {", s)
    s = re.sub(r",\s*\{\s*\{", ", {", s)
    s = re.sub(r"\n\s*\{\s*\n", "\n", s)
    return s


def _loads_json(blob: str) -> Any:
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        try:
            import json_repair  # type: ignore[import-untyped]

            repaired = json_repair.repair_json(blob)
            return json.loads(repaired)
        except Exception as exc:
            raise ValueError(f"JSON 无法解析: {exc}") from exc


def _normalize_standby_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict) and item.get("direction"):
        direction = str(item.get("direction", "")).strip().lower()
        if direction not in _STANDBY_DIRECTIONS:
            direction = "range"
        activate = item.get("activate_if")
        if not isinstance(activate, list) or not activate:
            activate = ["structure_confirm"]
        activate = [str(x) for x in activate if x]
        if not activate:
            activate = ["structure_confirm"]
        return {"direction": direction, "activate_if": activate}
    if isinstance(item, str):
        direction = item.strip().lower()
        if direction in _STANDBY_DIRECTIONS:
            return {"direction": direction, "activate_if": ["structure_confirm"]}
    return None


def _sanitize_standby_strategies(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        one = _normalize_standby_item(raw)
        return [one] if one else []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        norm = _normalize_standby_item(item)
        if norm:
            out.append(norm)
    return out


def _sanitize_brief(brief: Any) -> dict[str, Any]:
    if not isinstance(brief, dict):
        raise ValueError("brief 必须是对象")
    out = dict(brief)
    if not (out.get("disclaimer") or "").strip():
        out["disclaimer"] = _DEFAULT_DISCLAIMER
    if not (out.get("missing_data_checklist") or []):
        out["missing_data_checklist"] = []
    if "analysis_markdown" not in out:
        out["analysis_markdown"] = ""
    if "structure_quickview" not in out:
        out["structure_quickview"] = ""
    return out


def _sanitize_chanlun_v2(v2: Any) -> dict[str, Any] | None:
    if v2 is None:
        return None
    if not isinstance(v2, dict):
        return None
    out = dict(v2)
    sm = out.get("state_machine")
    if isinstance(sm, dict):
        sm = dict(sm)
        sm["standby_strategies"] = _sanitize_standby_strategies(sm.get("standby_strategies"))
        out["state_machine"] = sm
    if not isinstance(out.get("risk_notes"), list):
        out["risk_notes"] = []
    return out


def _sanitize_deliverable_data(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    if "brief" in out:
        out["brief"] = _sanitize_brief(out["brief"])
    if "chanlun_v2" in out:
        out["chanlun_v2"] = _sanitize_chanlun_v2(out.get("chanlun_v2"))
    return out


def _validate_or_fallback_brief_only(data: dict[str, Any]) -> TechnicalAnalysisDeliverable:
    """chanlun_v2 校验失败时仍保留 brief（避免 4 分钟白跑）。"""
    brief_only = {**data, "chanlun_v2": None, "signal_quality": None}
    try:
        deliverable = TechnicalAnalysisDeliverable.model_validate(brief_only)
        logger.warning(
            "technical_deliverable_chanlun_v2_dropped",
            reason="chanlun_v2 字段校验失败，已保留 brief",
        )
        return deliverable
    except ValidationError as exc:
        raise ValueError(f"brief 校验失败: {exc}") from exc


def parse_technical_deliverable_text(text: str) -> TechnicalAnalysisDeliverable:
    """将 Task raw 输出解析为 TechnicalAnalysisDeliverable。"""
    blob = _fix_common_llm_json_glitches(_extract_json_blob(text))
    data = _loads_json(blob)
    if not isinstance(data, dict):
        raise ValueError("根节点必须是 JSON 对象")
    data = _sanitize_deliverable_data(data)
    try:
        return TechnicalAnalysisDeliverable.model_validate(data)
    except ValidationError as exc:
        if data.get("brief"):
            return _validate_or_fallback_brief_only(data)
        raise ValueError(f"TechnicalAnalysisDeliverable 校验失败: {exc}") from exc
