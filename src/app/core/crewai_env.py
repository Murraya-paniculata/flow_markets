"""CrewAI 运行时环境（须在 ``import crewai`` 之前生效）。"""
from __future__ import annotations

import os


def is_crewai_telemetry_enabled() -> bool:
    """显式 ``CREWAI_TELEMETRY=true`` 时保留出站遥测。"""
    return os.environ.get("CREWAI_TELEMETRY", "").strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )


def apply_crewai_runtime_env(*, testing: bool = True) -> None:
    """
    - ``CREWAI_TESTING``：关闭 Crew 交互式 trace 提示（服务端无 TTY）
    - ``CREWAI_DISABLE_TELEMETRY`` / ``OTEL_SDK_DISABLED``：避免 telemetry.crewai.com 超时
    """
    if testing:
        os.environ.setdefault("CREWAI_TESTING", "true")
    if is_crewai_telemetry_enabled():
        return
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
