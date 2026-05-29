"""缠论分析记忆库（快照 + outcome），与业务主库 APP_DATABASE_URL 分离。"""

from app.analysis_store.db_manager import (
    get_db_conn,
    get_db_conn_no_context,
    get_db_path,
    init_db,
    resolve_analysis_db_path,
    safe_json_dumps,
    safe_json_loads,
)
from app.analysis_store.history_builder import build_history_block
from app.analysis_store.outcome import (
    evaluate_outcome,
    evaluate_pending_snapshots,
    extract_scenario_for_eval,
)
from app.analysis_store.persist import (
    save_analysis_run,
    save_technical_deliverable,
    should_persist_analysis,
)

from app.analysis_store.stats_formatter import (
    format_stats_for_prompt,
    get_stats_summary,
)
from app.analysis_store.stats_service import calculate_accuracy, count_evaluated_samples

__all__ = [
    "get_db_conn",
    "get_db_conn_no_context",
    "get_db_path",
    "init_db",
    "resolve_analysis_db_path",
    "safe_json_dumps",
    "safe_json_loads",
    "save_analysis_run",
    "save_technical_deliverable",
    "should_persist_analysis",
    "evaluate_outcome",
    "evaluate_pending_snapshots",
    "extract_scenario_for_eval",
    "build_history_block",
    "calculate_accuracy",
    "count_evaluated_samples",
    "format_stats_for_prompt",
    "get_stats_summary",
]
