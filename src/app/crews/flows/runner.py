"""编排执行器：按 flow 名称分发到具体实现（如深度调研）。"""

import asyncio

from app.crews.flows.deep_research import run_deep_research


async def run_flow(flow_name: str, input_data: dict) -> dict:
    """
    执行编排流程。支持 flow_name=deep_research，input_data 需含 topic，可选 extra_instructions。
    返回 {"success": bool, "report_content": str | None, "report_path": str | None, "error": str}。
    """
    if flow_name == "deep_research":
        topic = input_data.get("topic") or ""
        extra = input_data.get("extra_instructions")
        if not topic:
            return {"success": False, "report_content": None, "report_path": None, "error": "缺少 topic"}
        report_content, report_path, error = await asyncio.to_thread(
            run_deep_research,
            topic=topic,
            extra_instructions=extra,
            output_dir=None,
        )
        return {
            "success": not bool(error),
            "report_content": report_content,
            "report_path": report_path,
            "error": error or "",
        }
    return {"success": False, "report_content": None, "report_path": None, "error": f"未知 flow: {flow_name}"}
