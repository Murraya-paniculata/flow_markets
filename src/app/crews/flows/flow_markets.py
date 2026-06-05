"""FlowMarkets：交易研究 Crew（YAML Agent/Task + Sequential）。

默认 ``APP_FLOW_MARKETS_MODE=technical_only``（仅技术分析师）；``full`` 启用完整研究链。
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task, tool
from crewai.tools import BaseTool

from app.analysis_store import save_technical_deliverable, should_persist_analysis
from app.analysis_store.signal_quality import apply_signal_quality_to_deliverable
from app.analysis_store.history_builder import build_history_block
from app.analysis_store.history_enforcement import enforce_deliverable
from app.core.config import get_settings
from app.crews.flows.deep_research import _get_report_from_crew_result
from app.crews.llm import get_llm
from app.schemas.flow_markets_deliverables import (
    MarketStructureBrief,
    NarrativeBrief,
    PortfolioBrief,
    ResearchSynthesis,
    SentimentAssessment,
    TechnicalAnalysisDeliverable,
    TradingPlaybook,
    TradingPlaybook,
    assemble_flow_markets_report,
)
from app.crews.flows.flow_markets_mode import (
    flow_markets_metrics_flow_name,
    get_flow_markets_mode,
    is_flow_markets_full_mode,
)
from app.crews.tools import BaiduSearchTool as BaiduSearchToolImpl
from app.crews.tools import GetChanStructureTool as GetChanStructureToolImpl
from app.crews.tools import GetMarketTickerSummaryTool as GetMarketTickerSummaryToolImpl
from app.observability.logging import get_logger
from app.observability.metrics import crew_execution_seconds
from app.services.analysis_output import (
    should_write_output_artifacts,
    write_analyze_save_artifacts,
)
from app.services.synthesis_context import (
    build_full_downstream_injection_fields,
    check_trading_playbook_alignment,
)
from app.services.chan.multi_timeframe import (
    _SINGLE_MODE_CONTEXT,
    build_multi_timeframe_snapshot,
    format_multi_timeframe_for_prompt,
)
from app.services.chan.structure import build_chan_structure_snapshot

logger = get_logger(__name__)

_FLOWS_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = _FLOWS_DIR.parent / "config"
# CrewAI discover_skills 扫描子目录中的 SKILL.md（传 chan-analysis 单目录无效）
_SKILLS_DIR = _FLOWS_DIR.parent / "skills"
_DEFAULT_REPORT_DIR = "./data"
_REPORT_FILENAME_PREFIX = "flow_markets"


def flow_markets_report_path(
    output_dir: str | Path = _DEFAULT_REPORT_DIR,
    *,
    prefix: str = _REPORT_FILENAME_PREFIX,
) -> Path:
    """生成带时间戳的报告路径，例如 ``./data/flow_markets_20260515_153328.md``。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(output_dir) / f"{prefix}_{ts}.md"


def _flow_markets_agent(
    crew_base_instance: Any,
    key: str,
    *,
    tools: list[BaseTool] | None = None,
    skills: list[Any] | None = None,
) -> Agent:
    cfg: dict[str, Any] = crew_base_instance.agents_config[key]  # type: ignore[index]
    kwargs: dict[str, Any] = {
        "config": cfg,
        "llm": get_llm(),
        "verbose": cfg.get("verbose", True),
        "allow_delegation": cfg.get("allow_delegation", False),
        "memory": cfg.get("memory", False),
    }
    mi = cfg.get("max_iter")
    if mi is not None:
        kwargs["max_iter"] = int(mi)
    if tools is not None:
        kwargs["tools"] = tools
    if skills is not None:
        kwargs["skills"] = skills
    return Agent(**kwargs)


def _fm_task(crew_base: Any, key: str, output_model: type) -> Task:
    """YAML 里程碑描述 + Pydantic 结构化交付契约（见 08 模块 Task 课）。"""
    return Task(
        config=crew_base.tasks_config[key],  # type: ignore[index]
        output_pydantic=output_model,
    )


def _fm_task_technical(crew_base: Any) -> Task:
    """
    技术分析师 Task：不用 CrewAI 内置 output_pydantic 校验。

    大模型偶发 ``{ {`` 等非法 JSON 会在 kickoff 时抛 ValidationError；
    改由 ``parse_technical_deliverable_text`` 容错解析。
    """
    return Task(config=crew_base.tasks_config["task_fm_technical"])  # type: ignore[index]


@CrewBase
class FlowMarketsCrew:
    """FlowMarkets 多角色研究链：配置见 flow_markets_agents.yaml / flow_markets_tasks.yaml。"""

    agents_config = str(_CONFIG_DIR / "flow_markets_agents.yaml")
    tasks_config = str(_CONFIG_DIR / "flow_markets_tasks.yaml")

    @tool
    def GetChanStructureTool(self) -> BaseTool:
        return GetChanStructureToolImpl()

    @tool
    def BaiduSearchTool(self) -> BaseTool:
        return BaiduSearchToolImpl()

    @tool
    def GetMarketTickerSummaryTool(self) -> BaseTool:
        return GetMarketTickerSummaryToolImpl()

    @agent
    def market_analyst(self) -> Agent:
        return _flow_markets_agent(
            self,
            "market_analyst",
            tools=[
                self.GetMarketTickerSummaryTool(),
                self.BaiduSearchTool(),
            ],
        )

    @agent
    def narrative_analyst(self) -> Agent:
        return _flow_markets_agent(
            self,
            "narrative_analyst",
            tools=[self.BaiduSearchTool()],
        )

    @agent
    def sentiment_analyst(self) -> Agent:
        return _flow_markets_agent(
            self,
            "sentiment_analyst",
            tools=[
                self.GetMarketTickerSummaryTool(),
                self.BaiduSearchTool(),
            ],
        )

    @agent
    def technical_analyst(self) -> Agent:
        """技术分析师：GetChanStructureTool + 原生 Skill chan-analysis（单 Task 内先工具后研判）。"""
        cfg: dict[str, Any] = self.agents_config["technical_analyst"]  # type: ignore[index]
        kwargs: dict[str, Any] = {
            "config": cfg,
            "llm": get_llm(),
            "verbose": cfg.get("verbose", True),
            "allow_delegation": cfg.get("allow_delegation", False),
            "memory": cfg.get("memory", False),
            "skills": [_SKILLS_DIR],
            "tools": [self.GetChanStructureTool()],
        }
        mi = cfg.get("max_iter")
        if mi is not None:
            kwargs["max_iter"] = int(mi)
        return Agent(**kwargs)

    @agent
    def research_manager(self) -> Agent:
        return _flow_markets_agent(self, "research_manager")

    @agent
    def trader(self) -> Agent:
        return _flow_markets_agent(self, "trader")

    @agent
    def portfolio_manager(self) -> Agent:
        return _flow_markets_agent(self, "portfolio_manager")

    @task
    def task_fm_market(self) -> Task:
        return _fm_task(self, "task_fm_market", MarketStructureBrief)

    @task
    def task_fm_narrative(self) -> Task:
        return _fm_task(self, "task_fm_narrative", NarrativeBrief)

    @task
    def task_fm_sentiment(self) -> Task:
        return _fm_task(self, "task_fm_sentiment", SentimentAssessment)

    @task
    def task_fm_technical(self) -> Task:
        return _fm_task_technical(self)

    @task
    def task_fm_synthesis(self) -> Task:
        return _fm_task(self, "task_fm_synthesis", ResearchSynthesis)

    @task
    def task_fm_trading(self) -> Task:
        return _fm_task(self, "task_fm_trading", TradingPlaybook)

    @task
    def task_fm_portfolio(self) -> Task:
        return _fm_task(self, "task_fm_portfolio", PortfolioBrief)

    @crew
    def crew(self) -> Crew:
        """按 ``APP_FLOW_MARKETS_MODE`` 返回完整链或仅技术分析师链。"""
        if is_flow_markets_full_mode():
            return Crew(
                agents=[
                    self.market_analyst(),
                    self.narrative_analyst(),
                    self.sentiment_analyst(),
                    self.technical_analyst(),
                    self.research_manager(),
                    self.trader(),
                    self.portfolio_manager(),
                ],
                tasks=[
                    self.task_fm_market(),
                    self.task_fm_narrative(),
                    self.task_fm_sentiment(),
                    self.task_fm_technical(),
                    self.task_fm_synthesis(),
                    self.task_fm_trading(),
                    self.task_fm_portfolio(),
                ],
                process=Process.sequential,
                verbose=True,
            )
        return Crew(
            agents=[self.technical_analyst()],
            tasks=[self.task_fm_technical()],
            process=Process.sequential,
            verbose=True,
        )


def _extract_deliverable_by_type(
    result: Any,
    model_type: type,
) -> Any | None:
    """从 kickoff 的 tasks_output 中按 Pydantic 类型取首个匹配交付物。"""
    tasks_out = getattr(result, "tasks_output", None) or []
    for out in tasks_out:
        p = getattr(out, "pydantic", None)
        if isinstance(p, model_type):
            return p
    return None


def _merge_kickoff_results(upstream: Any, downstream: Any) -> Any:
    """合并两段 Crew 的 tasks_output，供 ``assemble_flow_markets_report`` 使用。"""

    class _Merged:
        pass

    merged = _Merged()
    up_out = list(getattr(upstream, "tasks_output", None) or [])
    down_out = list(getattr(downstream, "tasks_output", None) or [])
    merged.tasks_output = up_out + down_out  # type: ignore[attr-defined]
    return merged


def _patch_governed_technical_in_merged_result(
    merged: Any,
    governed: TechnicalAnalysisDeliverable,
) -> None:
    """报告中的技术章使用治理后交付物，而非链内原始 technical 输出。"""
    for out in getattr(merged, "tasks_output", None) or []:
        if isinstance(getattr(out, "pydantic", None), TechnicalAnalysisDeliverable):
            try:
                out.pydantic = governed  # type: ignore[attr-defined]
            except Exception:
                pass


def _create_upstream_crew(flow: FlowMarketsCrew) -> Crew:
    """full 模式第一段：market → narrative → sentiment → technical。"""
    return Crew(
        agents=[
            flow.market_analyst(),
            flow.narrative_analyst(),
            flow.sentiment_analyst(),
            flow.technical_analyst(),
        ],
        tasks=[
            flow.task_fm_market(),
            flow.task_fm_narrative(),
            flow.task_fm_sentiment(),
            flow.task_fm_technical(),
        ],
        process=Process.sequential,
        verbose=True,
    )


def _downstream_synthesis_task(flow: FlowMarketsCrew) -> Task:
    """synthesis 无 Crew context，依赖服务端注入的四域 + 治理后 technical + stats。"""
    cfg = dict(flow.tasks_config["task_fm_synthesis"])  # type: ignore[index]
    cfg["context"] = []
    return Task(config=cfg, output_pydantic=ResearchSynthesis)


def _create_downstream_crew(flow: FlowMarketsCrew) -> Crew:
    """full 模式第二段：synthesis → trading → portfolio。"""
    return Crew(
        agents=[
            flow.research_manager(),
            flow.trader(),
            flow.portfolio_manager(),
        ],
        tasks=[
            _downstream_synthesis_task(flow),
            flow.task_fm_trading(),
            flow.task_fm_portfolio(),
        ],
        process=Process.sequential,
        verbose=True,
    )


def _govern_technical_deliverable(
    deliverable: TechnicalAnalysisDeliverable | dict[str, Any] | None,
    *,
    timeframe: str,
    lookback: int,
    symbol_hint: str | None,
) -> TechnicalAnalysisDeliverable | dict[str, Any] | None:
    deliverable = _apply_history_enforcement(
        deliverable,
        timeframe=timeframe,
        lookback=lookback,
        symbol_hint=symbol_hint,
    )
    return _apply_signal_quality(
        deliverable,
        timeframe=timeframe,
        lookback=lookback,
        symbol_hint=symbol_hint,
    )


def _kickoff_full_flow_markets_split(
    flow: FlowMarketsCrew,
    inputs: dict[str, Any],
    *,
    persist_tf: str,
    lookback: int,
    symbol_hint: str | None,
) -> tuple[Any, TechnicalAnalysisDeliverable | dict[str, Any] | None]:
    """
    Phase 6.3：上游 Crew → 治理 technical → 注入 stats → 下游 Crew。
    """
    upstream = _create_upstream_crew(flow)
    logger.info("flow_markets_full_upstream_start")
    upstream_result = upstream.kickoff(inputs=inputs)
    logger.info("flow_markets_full_upstream_done")

    raw_technical = _extract_deliverable_by_type(
        upstream_result,
        TechnicalAnalysisDeliverable,
    )
    governed = _govern_technical_deliverable(
        raw_technical,
        timeframe=persist_tf,
        lookback=lookback,
        symbol_hint=symbol_hint,
    )

    synthesis_fields = build_full_downstream_injection_fields(
        governed_technical=governed if isinstance(governed, TechnicalAnalysisDeliverable) else None,
        market=_extract_deliverable_by_type(upstream_result, MarketStructureBrief),
        narrative=_extract_deliverable_by_type(upstream_result, NarrativeBrief),
        sentiment=_extract_deliverable_by_type(upstream_result, SentimentAssessment),
        symbol_hint=symbol_hint,
        timeframe=persist_tf,
    )
    downstream_inputs = {**inputs, **synthesis_fields}

    downstream = _create_downstream_crew(flow)
    logger.info("flow_markets_full_downstream_start")
    downstream_result = downstream.kickoff(inputs=downstream_inputs)
    logger.info("flow_markets_full_downstream_done")

    synthesis_out = _extract_deliverable_by_type(downstream_result, ResearchSynthesis)
    trading_out = _extract_deliverable_by_type(downstream_result, TradingPlaybook)
    if isinstance(trading_out, TradingPlaybook) and isinstance(governed, TechnicalAnalysisDeliverable):
        for warn in check_trading_playbook_alignment(
            trading_out,
            governed,
            synthesis=synthesis_out if isinstance(synthesis_out, ResearchSynthesis) else None,
        ):
            logger.warning("trading_playbook_alignment", message=warn)

    merged = _merge_kickoff_results(upstream_result, downstream_result)
    if isinstance(governed, TechnicalAnalysisDeliverable):
        _patch_governed_technical_in_merged_result(merged, governed)
    return merged, governed


def _execute_flow_markets_crew(
    flow: FlowMarketsCrew,
    inputs: dict[str, Any],
    *,
    persist_tf: str,
    lookback: int,
    symbol_hint: str | None,
) -> tuple[Any, TechnicalAnalysisDeliverable | dict[str, Any] | None, str]:
    """执行 Crew；full 模式为两段链，返回 (kickoff_result, 治理后 technical, metrics_name)。"""
    if is_flow_markets_full_mode():
        merged, governed = _kickoff_full_flow_markets_split(
            flow,
            inputs,
            persist_tf=persist_tf,
            lookback=lookback,
            symbol_hint=symbol_hint,
        )
        return merged, governed, "flow_markets_full"

    crew_obj, metrics_name = create_flow_markets_crew_for_run(
        flow,
        force_technical_only=True,
    )
    result = crew_obj.kickoff(inputs=inputs)
    governed = _govern_technical_deliverable(
        _extract_technical_deliverable(result),
        timeframe=persist_tf,
        lookback=lookback,
        symbol_hint=symbol_hint,
    )
    if isinstance(governed, TechnicalAnalysisDeliverable):
        _patch_governed_technical_in_merged_result(result, governed)
    return result, governed, metrics_name


def _parse_technical_task_output(out: Any) -> TechnicalAnalysisDeliverable | None:
    from app.schemas.technical_deliverable_parse import parse_technical_deliverable_text

    p = getattr(out, "pydantic", None)
    if isinstance(p, TechnicalAnalysisDeliverable):
        return p
    raw = getattr(out, "raw", None) or getattr(out, "output", None)
    if not raw:
        return None
    try:
        return parse_technical_deliverable_text(str(raw))
    except Exception as exc:
        logger.warning(
            "technical_deliverable_parse_failed",
            error=str(exc)[:300],
            raw_preview=str(raw)[:200],
        )
        return None


def _extract_technical_deliverable(
    result: Any,
) -> TechnicalAnalysisDeliverable | dict[str, Any] | None:
    """从 Crew kickoff 结果解析 TechnicalAnalysisDeliverable。"""
    pydantic_out = getattr(result, "pydantic", None)
    if isinstance(pydantic_out, TechnicalAnalysisDeliverable):
        return pydantic_out

    tasks_out = getattr(result, "tasks_output", None) or []
    for out in reversed(tasks_out):
        parsed = _parse_technical_task_output(out)
        if parsed is not None:
            return parsed

    raw = getattr(result, "raw", None)
    if raw:
        parsed = _parse_technical_task_output(
            type("_RawOut", (), {"raw": raw, "pydantic": None, "output": None})()
        )
        if parsed is not None:
            return parsed
        return {"raw": str(raw)}
    return None


def _maybe_persist_technical_deliverable(
    deliverable: TechnicalAnalysisDeliverable | dict[str, Any] | None,
    *,
    timeframe: str,
    lookback: int,
    symbol_hint: str | None,
    save: bool | None,
) -> int | None:
    if not should_persist_analysis(save=save):
        return None
    if not isinstance(deliverable, TechnicalAnalysisDeliverable):
        return None
    return save_technical_deliverable(
        deliverable,
        timeframe=timeframe,
        lookback=lookback,
        symbol_hint=symbol_hint,
    )


def _resolve_history_hints(
    deliverable: TechnicalAnalysisDeliverable,
    *,
    timeframe: str,
    lookback: int,
    symbol_hint: str | None,
) -> dict[str, Any]:
    if deliverable.chanlun_v2 is None:
        return {}
    symbol = (
        deliverable.chanlun_v2.meta.symbol
        or deliverable.brief.symbol
        or symbol_hint
        or ""
    ).strip()
    interval = (
        deliverable.chanlun_v2.meta.interval
        or deliverable.brief.interval
        or timeframe
    ).strip()
    if not symbol:
        return {}
    try:
        snapshot = build_chan_structure_snapshot(symbol, interval, lookback=lookback)
        history = build_history_block(snapshot)
        return history.get("state_machine_hints") or {}
    except Exception as exc:
        logger.warning("resolve_history_hints_failed", error=str(exc))
        return {}


def _apply_history_enforcement(
    deliverable: TechnicalAnalysisDeliverable | dict[str, Any] | None,
    *,
    timeframe: str,
    lookback: int,
    symbol_hint: str | None,
) -> TechnicalAnalysisDeliverable | dict[str, Any] | None:
    if not isinstance(deliverable, TechnicalAnalysisDeliverable):
        return deliverable
    if deliverable.chanlun_v2 is None:
        return deliverable
    hints = _resolve_history_hints(
        deliverable,
        timeframe=timeframe,
        lookback=lookback,
        symbol_hint=symbol_hint,
    )
    enforced, result = enforce_deliverable(deliverable, hints)
    if result.get("applied"):
        logger.info(
            "history_enforcement_applied",
            original_state=result.get("original_state"),
            new_state=result.get("new_state"),
            recommended_floor=result.get("recommended_floor"),
        )
    return enforced


def _apply_signal_quality(
    deliverable: TechnicalAnalysisDeliverable | dict[str, Any] | None,
    *,
    timeframe: str,
    lookback: int,
    symbol_hint: str | None,
) -> TechnicalAnalysisDeliverable | dict[str, Any] | None:
    if not isinstance(deliverable, TechnicalAnalysisDeliverable):
        return deliverable
    if deliverable.chanlun_v2 is None:
        return deliverable

    symbol = (
        deliverable.chanlun_v2.meta.symbol
        or deliverable.brief.symbol
        or symbol_hint
        or ""
    ).strip()
    interval = (
        deliverable.chanlun_v2.meta.interval
        or deliverable.brief.interval
        or timeframe
    ).strip()
    if not symbol:
        return deliverable

    try:
        snapshot = build_chan_structure_snapshot(symbol, interval, lookback=lookback)
        return apply_signal_quality_to_deliverable(
            deliverable,
            snapshot.model_dump(mode="json"),
        )
    except Exception as exc:
        logger.warning("signal_quality_failed", error=str(exc))
        return deliverable


_ANALYSIS_MODE_SINGLE = "single"
_ANALYSIS_MODE_MULTI = "multi_timeframe"
_PRIMARY_TF_MULTI = "1h"


def _build_technical_crew_inputs(
    *,
    user_query: str,
    symbol: str | None,
    notes: str | None,
    timeframe: str,
    lookback: int,
    analysis_mode: str,
    multi_timeframe_context: str | None = None,
) -> dict[str, Any]:
    mode = analysis_mode if analysis_mode in (_ANALYSIS_MODE_SINGLE, _ANALYSIS_MODE_MULTI) else _ANALYSIS_MODE_SINGLE
    primary_tf = _PRIMARY_TF_MULTI if mode == _ANALYSIS_MODE_MULTI else timeframe
    mtf_ctx = multi_timeframe_context if multi_timeframe_context is not None else _SINGLE_MODE_CONTEXT
    return {
        "user_query": user_query.strip(),
        "symbol": (symbol or "").strip() or "（未指定）",
        "notes": (notes or "").strip() or "无",
        "analysis_mode": mode,
        "multi_timeframe_context": mtf_ctx,
        "primary_timeframe": primary_tf,
        "lookback": str(lookback),
    }


def _resolve_multi_timeframe_context(
    symbol: str | None,
    *,
    lookback: int,
    prebuilt: str | None = None,
) -> tuple[str, str]:
    """返回 (context_json, error_message)。"""
    if prebuilt is not None:
        return prebuilt, ""
    sym = (symbol or "").strip()
    if not sym or sym == "（未指定）":
        return "", "多级别模式需要有效 symbol"
    try:
        snap = build_multi_timeframe_snapshot(sym, lookback=lookback)
    except Exception as exc:
        return "", f"多级别结构计算失败: {exc}"
    ok_count = sum(1 for lv in snap.levels.values() if lv.ok)
    if ok_count == 0:
        return "", "多级别结构：所有周期均失败"
    return format_multi_timeframe_for_prompt(snap), ""


def _standalone_technical_task(flow: FlowMarketsCrew) -> Task:
    """技术分析师单跑：与 task_fm_technical 同源，无上游 context，可改周期/回溯/分析模式。"""
    cfg = dict(flow.tasks_config["task_fm_technical"])  # type: ignore[index]
    cfg["context"] = []
    return Task(config=cfg)


def create_flow_markets_crew_for_run(
    flow: FlowMarketsCrew,
    *,
    force_technical_only: bool = False,
) -> tuple[Crew, str]:
    """
    构建待 kickoff 的 Crew（流式等仍可用）。

    - ``technical_only``：独立 technical Task
    - ``full``：返回上游 4 Task Crew；完整两段链请用 ``_execute_flow_markets_crew``
    """
    if force_technical_only or not is_flow_markets_full_mode():
        agent = flow.technical_analyst()
        task = _standalone_technical_task(flow)
        return (
            Crew(agents=[agent], tasks=[task], verbose=True),
            "flow_markets",
        )
    return _create_upstream_crew(flow), "flow_markets_full_upstream"


def run_technical_analyst_only(
    user_query: str,
    symbol: str | None = None,
    notes: str | None = None,
    *,
    timeframe: str = "1h",
    lookback: int = 300,
    save: bool | None = None,
    analysis_mode: str = _ANALYSIS_MODE_SINGLE,
    multi_timeframe_context: str | None = None,
) -> tuple[TechnicalAnalysisDeliverable | dict[str, Any] | None, str]:
    """
    仅运行技术分析师（Tool + Skill → TechnicalAnalysisDeliverable）。

    analysis_mode:
    - ``single``（默认）：单周期，结构来自 get_chan_structure
    - ``multi_timeframe``：服务端预注入 4h/1h/15m JSON，AI 联立分析；history 仍走 1h 工具

    Returns:
        (双交付 JSON：brief + chanlun_v2；失败时可能为 dict/raw, error_message)
    """
    settings = get_settings()
    if not (settings.llm_api_key or "").strip():
        return None, "未配置 APP_LLM_API_KEY（或 QWEN_API_KEY / DEEPSEEK_API_KEY），无法调用大模型"

    mode = analysis_mode if analysis_mode in (_ANALYSIS_MODE_SINGLE, _ANALYSIS_MODE_MULTI) else _ANALYSIS_MODE_SINGLE
    persist_tf = _PRIMARY_TF_MULTI if mode == _ANALYSIS_MODE_MULTI else timeframe
    mtf_ctx = multi_timeframe_context
    if mode == _ANALYSIS_MODE_MULTI and mtf_ctx is None:
        mtf_ctx, mtf_err = _resolve_multi_timeframe_context(symbol, lookback=lookback)
        if mtf_err:
            return None, mtf_err

    from app.core.crewai_env import apply_crewai_runtime_env

    apply_crewai_runtime_env()
    inputs = _build_technical_crew_inputs(
        user_query=user_query,
        symbol=symbol,
        notes=notes,
        timeframe=timeframe,
        lookback=lookback,
        analysis_mode=mode,
        multi_timeframe_context=mtf_ctx,
    )

    flow = FlowMarketsCrew()
    crew_obj, _metrics_name = create_flow_markets_crew_for_run(
        flow,
        force_technical_only=True,
    )

    t0 = time.perf_counter()
    logger.info(
        "technical_analyst_only_start",
        symbol=inputs["symbol"],
        timeframe=persist_tf,
        lookback=lookback,
        analysis_mode=mode,
        flow_markets_mode=get_flow_markets_mode(),
    )
    try:
        result = crew_obj.kickoff(inputs=inputs)
    except Exception as e:
        logger.exception("technical_analyst_only_failed", error=str(e))
        return None, f"技术分析师执行失败: {e}"
    finally:
        logger.info(
            "technical_analyst_only_done",
            elapsed_seconds=round(time.perf_counter() - t0, 3),
        )

    deliverable = _extract_technical_deliverable(result)
    deliverable = _apply_history_enforcement(
        deliverable,
        timeframe=persist_tf,
        lookback=lookback,
        symbol_hint=symbol,
    )
    deliverable = _apply_signal_quality(
        deliverable,
        timeframe=persist_tf,
        lookback=lookback,
        symbol_hint=symbol,
    )
    _maybe_persist_technical_deliverable(
        deliverable,
        timeframe=persist_tf,
        lookback=lookback,
        symbol_hint=symbol,
        save=save,
    )
    if deliverable is not None:
        if isinstance(deliverable, TechnicalAnalysisDeliverable):
            return deliverable, ""
        return deliverable, "未解析到 TechnicalAnalysisDeliverable，见 raw 字段"
    return None, "未解析到 TechnicalAnalysisDeliverable 输出"


def run_flow_markets_analysis(
    user_query: str,
    symbol: str | None = None,
    notes: str | None = None,
    *,
    timeframe: str = "1h",
    lookback: int = 300,
    save: bool | None = None,
    analysis_mode: str = _ANALYSIS_MODE_SINGLE,
    multi_timeframe_context: str | None = None,
) -> tuple[str | None, str, list[str]]:
    """
    执行 FlowMarkets 编排。

    ``APP_FLOW_MARKETS_MODE=technical_only``（默认）时仅技术分析师；
    ``full`` 时两段链：上游四域 → 治理 technical → 注入 stats → synthesis/trader/portfolio。

    Returns:
        (report_markdown, error_message, output_files)；成功时 error_message 为空。
        ``save=true`` 时 ``output_files`` 为写入的相对路径列表。
    """
    settings = get_settings()
    if not (settings.llm_api_key or "").strip():
        return None, "未配置 APP_LLM_API_KEY（或 QWEN_API_KEY / DEEPSEEK_API_KEY），无法调用大模型", []

    mode = analysis_mode if analysis_mode in (_ANALYSIS_MODE_SINGLE, _ANALYSIS_MODE_MULTI) else _ANALYSIS_MODE_SINGLE
    persist_tf = _PRIMARY_TF_MULTI if mode == _ANALYSIS_MODE_MULTI else timeframe
    mtf_ctx = multi_timeframe_context
    if mode == _ANALYSIS_MODE_MULTI and mtf_ctx is None:
        mtf_ctx, mtf_err = _resolve_multi_timeframe_context(symbol, lookback=lookback)
        if mtf_err:
            return None, mtf_err, []

    from app.core.crewai_env import apply_crewai_runtime_env

    apply_crewai_runtime_env()
    inputs = _build_technical_crew_inputs(
        user_query=user_query,
        symbol=symbol,
        notes=notes,
        timeframe=timeframe,
        lookback=lookback,
        analysis_mode=mode,
        multi_timeframe_context=mtf_ctx,
    )

    flow = FlowMarketsCrew()
    metrics_name = "flow_markets"
    t0 = time.perf_counter()
    logger.info(
        "flow_markets_start",
        user_query_preview=user_query[:120],
        flow_markets_mode=get_flow_markets_mode(),
        timeframe=persist_tf,
        lookback=lookback,
        analysis_mode=mode,
    )
    try:
        result, deliverable, metrics_name = _execute_flow_markets_crew(
            flow,
            inputs,
            persist_tf=persist_tf,
            lookback=lookback,
            symbol_hint=symbol,
        )
    except Exception as e:
        logger.exception("flow_markets_failed", error=str(e))
        return None, f"FlowMarkets 执行失败: {e}", []
    finally:
        elapsed = time.perf_counter() - t0
        try:
            crew_execution_seconds.labels(flow_name=metrics_name).observe(elapsed)
        except Exception:
            logger.warning("flow_markets_metrics_observe_failed", exc_info=True)
        logger.info("flow_markets_done", elapsed_seconds=round(elapsed, 3))

    _maybe_persist_technical_deliverable(
        deliverable,
        timeframe=persist_tf,
        lookback=lookback,
        symbol_hint=symbol,
        save=save,
    )

    output_files: list[str] = []
    if (
        should_write_output_artifacts(save=save)
        and isinstance(deliverable, TechnicalAnalysisDeliverable)
        and symbol
        and (symbol or "").strip()
    ):
        sym = (symbol or "").strip()
        try:
            output_files = write_analyze_save_artifacts(
                symbol=sym,
                timeframe=persist_tf if mode == _ANALYSIS_MODE_SINGLE else "1h",
                lookback=lookback,
                deliverable=deliverable,
                multi_tf=mode == _ANALYSIS_MODE_MULTI,
            )
        except Exception as exc:
            logger.warning("write_analyze_save_artifacts_failed", error=str(exc))

    report = assemble_flow_markets_report(
        result,
        user_query=inputs["user_query"],
        symbol=inputs["symbol"],
    )
    if not report:
        report = _get_report_from_crew_result(result)
    if not report:
        report = "(未从 Crew 输出解析到报告正文，请检查各任务输出或日志)"
    return report, "", output_files


def analyze_flow_markets(
    user_query: str,
    *,
    symbol: str | None = None,
    notes: str | None = None,
    output_path: str | Path | None = None,
    save_report: bool = False,
    save: bool | None = None,
) -> tuple[str | None, str]:
    """
    便捷入口：仅必填 ``user_query``，其余可选；可顺带写入 Markdown 报告文件。

    示例::

        report, err = analyze_flow_markets("BTC 波动与情绪", symbol="BTC")
        report, err = analyze_flow_markets(
            "研究 BTC 风险",
            symbol="BTC-USD",
            output_path="./data/report.md",
        )

    Returns:
        (report_markdown, error_message)；成功时 error_message 为空。
    """
    persist = save if save is not None else save_report
    report, err, _output_files = run_flow_markets_analysis(
        user_query=user_query,
        symbol=symbol,
        notes=notes,
        save=persist,
    )
    out: Path | None = Path(output_path) if output_path else None
    if not err and report and out is None and save_report:
        out = flow_markets_report_path()
    if not err and report and out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
    return report, err
