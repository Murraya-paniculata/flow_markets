"""TechnicalAnalysisDeliverable 容错 JSON 解析。"""
from __future__ import annotations

import json

import pytest

from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable
from app.schemas.technical_deliverable_parse import parse_technical_deliverable_text


def _minimal_payload() -> dict:
    return {
        "brief": {
            "symbol": "BTC/USDT",
            "interval": "1h",
            "data_status": "有足够K线",
            "summary": "测试摘要",
            "analysis_markdown": "## 一、结构\n测试",
            "missing_data_checklist": [],
            "disclaimer": "历史形态不保证未来表现；不构成投资建议。",
        },
        "chanlun_v2": None,
    }


def test_parse_valid_json():
    text = "```json\n" + __import__("json").dumps(_minimal_payload(), ensure_ascii=False) + "\n```"
    d = parse_technical_deliverable_text(text)
    assert isinstance(d, TechnicalAnalysisDeliverable)
    assert d.brief.symbol == "BTC/USDT"


def test_parse_double_brace_glitch():
    broken = __import__("json").dumps(_minimal_payload(), ensure_ascii=False)
    broken = broken.replace('"brief": {', '"brief": { {', 1)
    d = parse_technical_deliverable_text(broken)
    assert d.brief.summary == "测试摘要"


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        parse_technical_deliverable_text("")


def test_sanitize_standby_strategies_string_items():
    payload = _minimal_payload()
    payload["chanlun_v2"] = {
        "meta": {
            "symbol": "BTC/USDT",
            "interval": "1h",
            "price": 62000.0,
            "timestamp": "2026-01-01T00:00:00",
        },
        "version": "2.0",
        "output_mode": "state_machine",
        "state_machine": {
            "current_state": "OBSERVE_ONLY",
            "active_strategy": {
                "direction": "down",
                "status": "WAIT",
                "entry_gate": {
                    "price_zone": [61000.0, 62000.0],
                    "structure_required": ["15m_break_zd"],
                },
                "execution": {
                    "entry_type": "limit",
                    "stop_loss": 63000.0,
                    "target": 60000.0,
                    "rr": 1.5,
                },
            },
            "invalidation": {
                "invalidate_active_if": ["price_above_zg"],
                "next_state": "OBSERVE_ONLY",
            },
            "standby_strategies": ["direction", "range"],
        },
        "structure_judgement": {
            "trend": "down_trend",
            "price_position": "below_zs",
            "zs": {"zg": 64000.0, "zd": 62000.0, "gg": 64500.0, "dd": 61500.0},
        },
        "risk_notes": [],
    }
    text = json.dumps(payload, ensure_ascii=False)
    d = parse_technical_deliverable_text(text)
    assert d.chanlun_v2 is not None
    assert len(d.chanlun_v2.state_machine.standby_strategies) >= 1
    assert all(s.direction in ("up", "down", "range") for s in d.chanlun_v2.state_machine.standby_strategies)


def test_fallback_brief_when_chanlun_v2_invalid():
    payload = _minimal_payload()
    payload["chanlun_v2"] = {"state_machine": {"standby_strategies": ["broken"]}}
    text = json.dumps(payload, ensure_ascii=False)
    d = parse_technical_deliverable_text(text)
    assert d.brief.summary == "测试摘要"
    assert d.chanlun_v2 is None
