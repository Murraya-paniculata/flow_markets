#!/usr/bin/env python3
"""回填 analysis_snapshot 预测结果（Phase 2.3）。

用法（flow_markets 项目根目录）:
  PYTHONPATH=src python scripts/evaluate_outcomes.py
  PYTHONPATH=src python scripts/evaluate_outcomes.py --dry-run
  PYTHONPATH=src python scripts/evaluate_outcomes.py --id 2
  PYTHONPATH=src python scripts/evaluate_outcomes.py --min-bars 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from app.analysis_store import evaluate_pending_snapshots, get_db_path, init_db


def main() -> int:
    parser = argparse.ArgumentParser(description="回填 AI 预测 outcome_json")
    parser.add_argument("--dry-run", action="store_true", help="只列出待评估项，不写库")
    parser.add_argument("--id", type=int, default=None, help="只处理指定 snapshot id")
    parser.add_argument(
        "--min-bars",
        type=int,
        default=None,
        help="最少未来 K 线根数（默认按周期配置，如 1h=48）",
    )
    args = parser.parse_args()

    init_db()
    print("=" * 60)
    print("FlowMarkets 预测结果回填")
    print("=" * 60)
    print(f"数据库: {get_db_path().resolve()}\n")

    run = evaluate_pending_snapshots(
        snapshot_id=args.id,
        min_required_bars=args.min_bars,
        dry_run=args.dry_run,
    )

    for line in run.details or []:
        print(line)
    print()
    print(
        f"完成: 成功 {run.success}, 失败 {run.failed}, 跳过 {run.skipped}"
        + (" (dry-run)" if args.dry_run else "")
    )
    return 0 if run.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
