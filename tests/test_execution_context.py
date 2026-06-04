"""Phase 6.4：trader/portfolio 状态机与 stats 注入。"""

from __future__ import annotations

from app.schemas.flow_markets_deliverables import (
    ChanlunActiveStrategy,
    ChanlunAnalysisMeta,
    ChanlunEntryGate,
    ChanlunExecution,
    ChanlunInvalidation,
    ChanlunStateMachine,
    ChanlunStateMachineOutput,
    ChanlunStructureJudgement,
    ChanlunStructureJudgementZs,
    ResearchSynthesis,
    ScenarioOutlook,
    SignalQualitySummary,
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
    TradingPlaybook,
)
from app.services.synthesis_context import (
    build_execution_context_fields,
    build_full_downstream_injection_fields,
    build_state_machine_summary,
    check_trading_playbook_alignment,
)


def _deliverable_observe_only() -> TechnicalAnalysisDeliverable:
    return TechnicalAnalysisDeliverable(
        brief=TechnicalBrief(
            symbol="BTCUSDT",
            interval="1h",
            data_status="有足够K线",
            summary="s",
            structure_quickview="q",
            analysis_markdown="# md",
            disclaimer="不构成投资建议",
        ),
        chanlun_v2=ChanlunStateMachineOutput(
            meta=ChanlunAnalysisMeta(
                symbol="BTCUSDT",
                interval="1h",
                price=100000.0,
                timestamp="2026-01-01T00:00:00",
            ),
            state_machine=ChanlunStateMachine(
                current_state="OBSERVE_ONLY",
                active_strategy=ChanlunActiveStrategy(
                    direction="up",
                    status="WAIT",
                    entry_gate=ChanlunEntryGate(
                        price_zone=[99000.0, 101000.0],
                        structure_required=["bi_complete"],
                    ),
                    execution=ChanlunExecution(
                        entry_type="limit",
                        stop_loss=98000.0,
                        target=105000.0,
                        rr=2.0,
                    ),
                ),
                invalidation=ChanlunInvalidation(
                    invalidate_active_if=["break_zd"],
                    next_state="WAIT_CONFIRMATION",
                ),
                standby_strategies=[],
            ),
            structure_judgement=ChanlunStructureJudgement(
                trend="consolidation",
                price_position="inside_zs",
                zs=ChanlunStructureJudgementZs(zg=101000, zd=99000, gg=102000, dd=98000),
            ),
            risk_notes=["[历史约束] 样本不足"],
        ),
        signal_quality=SignalQualitySummary(
            total_score=45.0,
            grade="D",
            grade_name="弱信号",
            action="skip",
            action_name="建议跳过",
            scores={},
            max_scores={},
            reasons={},
            advice="观望",
            signal_type="none",
            direction="unknown",
        ),
    )


def test_build_state_machine_summary_contains_state() -> None:
    text = build_state_machine_summary(_deliverable_observe_only())
    assert "OBSERVE_ONLY" in text
    assert "current_state" in text
    assert "历史约束" in text or "risk_notes" in text


def test_build_execution_context_fields_keys() -> None:
    fields = build_execution_context_fields(_deliverable_observe_only(), symbol_hint="BTCUSDT")
    assert "state_machine_summary" in fields
    assert "signal_quality_summary" in fields
    assert "execution_stats_context" in fields
    assert "skip" in fields["signal_quality_summary"]


def test_build_full_downstream_includes_synthesis_and_execution() -> None:
    fields = build_full_downstream_injection_fields(
        governed_technical=_deliverable_observe_only(),
        symbol_hint="BTCUSDT",
    )
    assert "governed_technical_context" in fields
    assert "state_machine_summary" in fields
    assert fields["analysis_stats_context"] == fields["execution_stats_context"]


def test_check_trading_playbook_alignment_warns_on_observe_only_aggressive() -> None:
    playbook = TradingPlaybook(
        symbol="BTCUSDT",
        time_horizon="波段",
        stance="偏多思路",
        entry_logic_types=["突破回踩"],
        risk_and_position_rules=["单笔风险上限"],
        reduce_or_exit_logic=["止损触发减仓"],
        watch_triggers=["等待确认"],
        execution_discipline=["先模拟"],
        high_risk_warnings=["合约高杠杆"],
        disclaimer="不构成投资建议",
    )
    warns = check_trading_playbook_alignment(
        playbook,
        _deliverable_observe_only(),
        synthesis=ResearchSynthesis(
            symbol="BTCUSDT",
            main_conclusion="观望为主",
            scenarios=[
                ScenarioOutlook(
                    name="延续震荡",
                    probability_note="约 60%",
                    triggers=["未突破 ZG"],
                    narrative="区间震荡",
                ),
            ],
            information_gaps=["样本少"],
            next_research_steps=["继续观察"],
            disclaimer="不构成投资建议",
        ),
    )
    assert any("OBSERVE_ONLY" in w for w in warns)
