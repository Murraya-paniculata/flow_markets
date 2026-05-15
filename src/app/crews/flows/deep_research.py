"""深度调研 Flow：从 YAML 加载 Agent/Task，组装 Crew，执行并返回报告。"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task, tool
from crewai.tools import BaseTool
from crewai_tools import (
    FileReadTool as FileReadToolImpl,
    FileWriterTool as FileWriterToolImpl,
    ScrapeWebsiteTool as ScrapeWebsiteToolImpl,
)

from app.core.config import get_settings
from app.crews.llm import get_llm
from app.crews.tools import BaiduSearchTool as BaiduSearchToolImpl
from app.crews.tools import FixedDirectoryReadTool as FixedDirectoryReadToolImpl
from app.observability.logging import get_logger

logger = get_logger(__name__)

_FLOWS_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = _FLOWS_DIR.parent / "config"

def _safe_filename(s: str) -> str:
    """将主题转为安全文件名（去掉非法字符）。"""
    return re.sub(r'[<>:"/\\|?*]', "_", s).strip() or "report"


@CrewBase
class DeepResearchCrew:
    """深度调研 Crew：Agent/Task 从 config YAML 加载，参考官网 CrewBase 示例。"""

    agents_config = str(_CONFIG_DIR / "agents.yaml")
    tasks_config = str(_CONFIG_DIR / "tasks.yaml")

    @tool
    def BaiduSearchTool(self) -> BaseTool:
        return BaiduSearchToolImpl()

    @tool
    def FixedDirectoryReadTool(self) -> BaseTool:
        return FixedDirectoryReadToolImpl()

    @tool
    def FileReadTool(self) -> BaseTool:
        return FileReadToolImpl()

    @tool
    def FileWriterTool(self) -> BaseTool:
        return FileWriterToolImpl()

    @tool
    def ScrapeWebsiteTool(self) -> BaseTool:
        return ScrapeWebsiteToolImpl()

    @agent
    def researcher(self) -> Agent:
        cfg = self.agents_config["researcher"]  # type: ignore[index]
        return Agent(
            config=cfg,
            llm=get_llm(),
            verbose=cfg.get("verbose", True),
            allow_delegation=cfg.get("allow_delegation", False),
            memory=cfg.get("memory", False),
        )

    @agent
    def writer(self) -> Agent:
        cfg = self.agents_config["writer"]  # type: ignore[index]
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
        return Agent(**kwargs)

    @agent
    def searcher(self) -> Agent:
        cfg = self.agents_config["searcher"]  # type: ignore[index]
        kwargs: dict[str, Any] = {
            "config": cfg,
            "llm": get_llm(),
            "verbose": cfg.get("verbose", True),
            "allow_delegation": cfg.get("allow_delegation", False),
            "memory": cfg.get("memory", False),
            "cache": cfg.get("cache", False),
        }
        mi = cfg.get("max_iter")
        if mi is not None:
            kwargs["max_iter"] = int(mi)
        return Agent(**kwargs)

    @agent
    def editor(self) -> Agent:
        cfg = self.agents_config["editor"]  # type: ignore[index]
        return Agent(
            config=cfg,
            llm=get_llm(),
            verbose=cfg.get("verbose", True),
            allow_delegation=cfg.get("allow_delegation", False),
            memory=cfg.get("memory", False),
        )

    @task
    def task_plan(self) -> Task:
        return Task(config=self.tasks_config["task_plan"])  # type: ignore[index]

    @task
    def task_write(self) -> Task:
        return Task(config=self.tasks_config["task_write"])  # type: ignore[index]

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.researcher(),
                self.writer(),
                self.searcher(),
                self.editor(),
            ],
            tasks=[
                self.task_plan(),
                self.task_write(),
            ],
            process=Process.sequential,
            verbose=True,
        )


def _get_report_from_crew_result(result: Any) -> str | None:
    """从 Crew kickoff 的返回值中提取最终报告 Markdown，避免使用 str(result) 产生乱码。"""
    if result is None:
        return None
    # CrewOutput.raw 或最后一任务的 raw 为实际 Markdown 文本
    if hasattr(result, "raw") and getattr(result, "raw") and isinstance(result.raw, str):
        text = (result.raw or "").strip()
        if text:
            return text
    if hasattr(result, "tasks_output") and result.tasks_output:
        last = result.tasks_output[-1]
        if hasattr(last, "raw") and getattr(last, "raw") and isinstance(last.raw, str):
            text = (last.raw or "").strip()
            if text:
                return text
    return None


def _assemble_report_from_workdir(work_dir: Path, topic_safe: str) -> str | None:
    """用工作目录下已有的大纲与步骤 Markdown 文件组装为一份报告（最终报告未生成时的回退）。"""
    outline_path = work_dir / f"{topic_safe}-报告大纲.md"
    parts: list[str] = []
    if outline_path.exists():
        try:
            parts.append(outline_path.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    n = 1
    while True:
        step_path = work_dir / f"{topic_safe}-步骤{n}.md"
        if not step_path.exists():
            break
        try:
            parts.append(step_path.read_text(encoding="utf-8").strip())
        except Exception:
            pass
        n += 1
    if not parts:
        return None
    return "\n\n---\n\n".join(parts)


def run_deep_research(
    topic: str,
    extra_instructions: str | None = None,
    output_dir: str | None = None,
) -> tuple[str | None, str | None, str]:
    """
    执行深度调研流程：使用 DeepResearchCrew 组装 Crew，在 output_dir 下执行并读取最终报告。

    Returns:
        (report_content, report_path, error_message)
        success 时 error_message 为空；失败时 report_content 可为 None，error_message 为错误信息。
    """
    os.environ["CREWAI_TESTING"] = "true"
    settings = get_settings()
    run_id = str(uuid.uuid4())[:8]
    base_dir = Path(output_dir or settings.deep_research_output_dir).resolve()
    work_dir = base_dir / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    topic_safe = _safe_filename(topic)

    inputs: dict[str, Any] = {"topic": topic}
    if extra_instructions:
        inputs["extra_instructions"] = extra_instructions

    deep_crew = DeepResearchCrew()
    crew_obj = deep_crew.crew()

    old_cwd = os.getcwd()
    try:
        os.chdir(work_dir)
        logger.info("deep_research_start", topic=topic, run_id=run_id, work_dir=str(work_dir))
        result = crew_obj.kickoff(inputs=inputs)
    except Exception as e:
        logger.exception("deep_research_failed", topic=topic, run_id=run_id, error=str(e))
        return None, None, f"执行失败: {e}"
    finally:
        os.chdir(old_cwd)

    report_path = work_dir / f"{topic_safe}-最终报告.md"
    report_content: str | None = None
    report_path_str: str | None = None
    if report_path.exists():
        report_path_str = str(report_path)
        try:
            report_content = report_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("deep_research_read_report_failed", path=report_path_str, error=str(e))

    if report_content is None:
        # 优先用已有的大纲与步骤文件组装：LLM 最后一步可能因上下文过长返回乱码（见日志 llm_response），组装结果更可靠
        report_content = _assemble_report_from_workdir(work_dir, topic_safe)
        if report_content:
            logger.info(
                "deep_research_fallback_to_assembled",
                topic=topic,
                run_id=run_id,
                reason="最终报告文件未生成，使用大纲与步骤文件组装",
            )
        else:
            # 再回退：从 CrewOutput 取最后一任务 raw（可能为 LLM 乱码，仅作兜底）
            fallback = _get_report_from_crew_result(result)
            if fallback:
                report_content = fallback
                logger.info(
                    "deep_research_fallback_to_crew_output",
                    topic=topic,
                    run_id=run_id,
                    reason="无步骤文件，使用最后一任务输出",
                )
            else:
                report_content = "(未生成报告文件且无任务输出)"
                logger.warning(
                    "deep_research_no_report",
                    topic=topic,
                    run_id=run_id,
                    work_dir=str(work_dir),
                )

    return report_content, report_path_str, ""
