"""交易者展示：analysis_markdown 对齐 chanlun --table 输出。"""
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
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
)
from app.schemas.technical_analysis_display import format_trader_display

_SAMPLE_MD = """### 一、技术形态概述
测试概述。

### 六、风险提示
- 不构成投资建议。
"""


def test_trader_display_prints_chanlun_style_analysis_block():
    brief = TechnicalBrief(
        symbol="BTC/USDT",
        interval="1h",
        data_status="有足够K线",
        summary="震荡偏空。",
        structure_quickview="ZG=1",
        analysis_markdown=_SAMPLE_MD,
        disclaimer="历史形态不保证未来表现。",
    )
    chanlun = ChanlunStateMachineOutput(
        meta=ChanlunAnalysisMeta(
            symbol="BTC/USDT",
            interval="1h",
            price=73000.0,
            timestamp="2026-01-01T00:00:00Z",
        ),
        state_machine=ChanlunStateMachine(
            current_state="OBSERVE_ONLY",
            active_strategy=ChanlunActiveStrategy(
                direction="down",
                status="WAIT",
                entry_gate=ChanlunEntryGate(
                    price_zone=[72000.0, 73000.0],
                    structure_required=["price_hold_dd"],
                ),
                execution=ChanlunExecution(
                    entry_type="market",
                    stop_loss=78000.0,
                    target=72000.0,
                    rr=1.5,
                ),
            ),
            invalidation=ChanlunInvalidation(
                invalidate_active_if=["price_break_zg"],
                next_state="OBSERVE_ONLY",
            ),
        ),
        structure_judgement=ChanlunStructureJudgement(
            trend="consolidation",
            price_position="below_zs",
            zs=ChanlunStructureJudgementZs(zg=77500, zd=76400, gg=77900, dd=76100),
        ),
    )
    text = format_trader_display(
        TechnicalAnalysisDeliverable(brief=brief, chanlun_v2=chanlun)
    )
    assert "【AI 缠论分析】" in text
    assert "### 一、技术形态概述" in text
    assert "策略概率分布" not in text
    assert "🎯 策略与执行要点" not in text
