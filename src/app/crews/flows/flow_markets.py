"""FlowMarkets：交易研究 Crew（YAML Agent/Task + Sequential），对齐设计文档的编排层与 ApiResponse 契约。"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from app.core.config import get_settings
from app.crews.flows.deep_research import _get_report_from_crew_result
from app.crews.llm import get_llm
from app.observability.logging import get_logger
from app.observability.metrics import crew_execution_seconds

logger = get_logger(__name__)

_FLOWS_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = _FLOWS_DIR.parent / "config"
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


def _flow_markets_agent(crew_base_instance: Any, key: str) -> Agent:
    cfg: dict[str, Any] = crew_base_instance.agents_config[key]  # type: ignore[index]
    kwargs: dict[str, Any] = {
        "config": cfg,
        "llm": get_llm(),
        "verbose": cfg.get("verbose", True),
        "allow_delegation": cfg.get("allow_delegation", False),
        "memory": cfg.get("memory", False),
    }
    # CrewAI Agent 要求 max_iter 为 int；YAML 未配置时不要传 None
    mi = cfg.get("max_iter")
    if mi is not None:
        kwargs["max_iter"] = int(mi)
    return Agent(**kwargs)


@CrewBase
class FlowMarketsCrew:
    """FlowMarkets 多角色研究链：配置见 flow_markets_agents.yaml / flow_markets_tasks.yaml。"""

    agents_config = str(_CONFIG_DIR / "flow_markets_agents.yaml")
    tasks_config = str(_CONFIG_DIR / "flow_markets_tasks.yaml")

    @agent
    def market_analyst(self) -> Agent:
        return _flow_markets_agent(self, "market_analyst")

    @agent
    def narrative_analyst(self) -> Agent:
        return _flow_markets_agent(self, "narrative_analyst")

    @agent
    def sentiment_analyst(self) -> Agent:
        return _flow_markets_agent(self, "sentiment_analyst")

    @agent
    def technical_analyst(self) -> Agent:
        return _flow_markets_agent(self, "technical_analyst")

    @agent
    def bull_researcher(self) -> Agent:
        return _flow_markets_agent(self, "bull_researcher")

    @agent
    def bear_researcher(self) -> Agent:
        return _flow_markets_agent(self, "bear_researcher")

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
        return Task(config=self.tasks_config["task_fm_market"])  # type: ignore[index]

    @task
    def task_fm_narrative(self) -> Task:
        return Task(config=self.tasks_config["task_fm_narrative"])  # type: ignore[index]

    @task
    def task_fm_sentiment(self) -> Task:
        return Task(config=self.tasks_config["task_fm_sentiment"])  # type: ignore[index]

    @task
    def task_fm_technical(self) -> Task:
        return Task(config=self.tasks_config["task_fm_technical"])  # type: ignore[index]

    @task
    def task_fm_bull(self) -> Task:
        return Task(config=self.tasks_config["task_fm_bull"])  # type: ignore[index]

    @task
    def task_fm_bear(self) -> Task:
        return Task(config=self.tasks_config["task_fm_bear"])  # type: ignore[index]

    @task
    def task_fm_synthesis(self) -> Task:
        return Task(config=self.tasks_config["task_fm_synthesis"])  # type: ignore[index]

    @task
    def task_fm_trading(self) -> Task:
        return Task(config=self.tasks_config["task_fm_trading"])  # type: ignore[index]

    @task
    def task_fm_portfolio(self) -> Task:
        return Task(config=self.tasks_config["task_fm_portfolio"])  # type: ignore[index]

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.market_analyst(),
                self.narrative_analyst(),
                self.sentiment_analyst(),
                self.technical_analyst(),
                self.bull_researcher(),
                self.bear_researcher(),
                self.research_manager(),
                self.trader(),
                self.portfolio_manager(),
            ],
            tasks=[
                self.task_fm_market(),
                self.task_fm_narrative(),
                self.task_fm_sentiment(),
                self.task_fm_technical(),
                self.task_fm_bull(),
                self.task_fm_bear(),
                self.task_fm_synthesis(),
                self.task_fm_trading(),
                self.task_fm_portfolio(),
            ],
            process=Process.sequential,
            verbose=True,
        )


def run_flow_markets_analysis(
    user_query: str,
    symbol: str | None = None,
    notes: str | None = None,
    *,
    pipeline: str = "yaml",
    analysis_date: str | None = None,
    stage: str | None = None,
) -> tuple[str | None, str]:
    """
    执行 FlowMarkets 顺序研究链。

    Args:
        pipeline: ``yaml``（默认）或 ``trading_agents``（结构化 JSON 管线）。
        analysis_date: 仅 trading_agents；未传时默认当天本地日期（``YYYY-MM-DD``）。
        stage: 仅 trading_agents；覆盖 TA_STAGE。

    Returns:
        (report_markdown, error_message)；成功时 error_message 为空字符串。
    """
    settings = get_settings()
    if not (settings.llm_api_key or "").strip():
        return None, "未配置 APP_LLM_API_KEY（或 QWEN_API_KEY / DEEPSEEK_API_KEY），无法调用大模型"

    pl = (pipeline or "yaml").strip().lower()
    if pl == "trading_agents":
        try:
            from app.crews.flows.trading_agents_flow import run_trading_agents_analysis
        except ModuleNotFoundError:
            return None, (
                "trading_agents 管线未安装（缺少 app.crews.flows.trading_agents_flow），"
                "请使用 pipeline=yaml 或补全该模块"
            )
        ticker = (symbol or "").strip() or "（未指定标的，请结合 user_query 理解）"
        date_str = (analysis_date or "").strip() or datetime.now().strftime("%Y-%m-%d")
        user_intent = user_query.strip()
        if (notes or "").strip():
            user_intent = f"{user_intent}\n补充说明：{notes.strip()}"
        t0 = time.perf_counter()
        logger.info("flow_markets_trading_agents_start", ticker_preview=ticker[:80])
        report, err = run_trading_agents_analysis(
            ticker,
            date_str,
            user_intent,
            stage=stage,
        )
        elapsed = time.perf_counter() - t0
        try:
            crew_execution_seconds.labels(flow_name="trading_agents").observe(elapsed)
        except Exception:
            logger.warning("trading_agents_metrics_observe_failed", exc_info=True)
        logger.info("flow_markets_trading_agents_done", elapsed_seconds=round(elapsed, 3))
        return report, err

    if pl != "yaml":
        return None, f"不支持的 pipeline: {pipeline}，请使用 yaml 或 trading_agents"

    os.environ["CREWAI_TESTING"] = "true"
    inputs: dict[str, Any] = {
        "user_query": user_query.strip(),
        "symbol": (symbol or "").strip() or "（未指定）",
        "notes": (notes or "").strip() or "无",
    }

    flow = FlowMarketsCrew()
    crew_obj = flow.crew()
    t0 = time.perf_counter()
    logger.info("flow_markets_start", user_query_preview=user_query[:120])
    try:
        result = crew_obj.kickoff(inputs=inputs)
    except Exception as e:
        logger.exception("flow_markets_failed", error=str(e))
        return None, f"FlowMarkets 执行失败: {e}"
    finally:
        elapsed = time.perf_counter() - t0
        try:
            crew_execution_seconds.labels(flow_name="flow_markets").observe(elapsed)
        except Exception:
            logger.warning("flow_markets_metrics_observe_failed", exc_info=True)
        logger.info("flow_markets_done", elapsed_seconds=round(elapsed, 3))

    report = _get_report_from_crew_result(result)
    if not report:
        report = "(未从 Crew 输出解析到报告正文，请检查各任务输出或日志)"
    return report, ""


def analyze_flow_markets(
    user_query: str,
    *,
    symbol: str | None = None,
    notes: str | None = None,
    pipeline: Literal["yaml", "trading_agents"] = "yaml",
    analysis_date: str | None = None,
    stage: str | None = None,
    output_path: str | Path | None = None,
    save_report: bool = False,
) -> tuple[str | None, str]:
    """
    便捷入口：仅必填 ``user_query``，其余可选；可顺带写入 Markdown 报告文件。

    示例::

        report, err = analyze_flow_markets("BTC 波动与情绪", symbol="BTC")
        report, err = analyze_flow_markets(
            "研究 BTC 风险",
            symbol="BTC-USD",
            pipeline="trading_agents",
            stage="analysis",
            output_path="./data/report.md",
        )

    Returns:
        (report_markdown, error_message)；成功时 error_message 为空。
    """
    report, err = run_flow_markets_analysis(
        user_query=user_query,
        symbol=symbol,
        notes=notes,
        pipeline=pipeline,
        analysis_date=analysis_date,
        stage=stage,
    )
    out: Path | None = Path(output_path) if output_path else None
    if not err and report and out is None and save_report:
        out = flow_markets_report_path()
    if not err and report and out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
    return report, err
