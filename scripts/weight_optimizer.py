#!/usr/bin/env python3
"""信号质量六维权重优化（Phase 4.5，对标 chanlun weight_optimizer.py）。

用法（flow_markets 根目录）:
  uv run python scripts/weight_optimizer.py
  uv run python scripts/weight_optimizer.py --save
  uv run python scripts/weight_optimizer.py --save --method predictive
  uv run python scripts/weight_optimizer.py --symbol BTC/USDT --interval 1h
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from app.analysis_store import init_db
from app.analysis_store.signal_quality import DEFAULT_WEIGHTS, reload_weights
from app.analysis_store.weight_optimizer import (
    DIM_NAMES,
    MIN_SAMPLES_HARD,
    MIN_SAMPLES_RECOMMENDED,
    run_weight_optimization,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="信号质量评分权重优化")
    parser.add_argument("--save", action="store_true", help="保存到 optimized_weights.json")
    parser.add_argument(
        "--method",
        choices=["correlation", "predictive", "mixed"],
        default="correlation",
        help="优化方法（默认 correlation）",
    )
    parser.add_argument("--symbol", type=str, default=None, help="筛选交易对")
    parser.add_argument("--interval", type=str, default=None, help="筛选周期")
    parser.add_argument(
        "--min-samples",
        type=int,
        default=MIN_SAMPLES_HARD,
        help=f"最少可计分样本（默认 {MIN_SAMPLES_HARD}；预览可设小一些，--save 仍建议 ≥{MIN_SAMPLES_RECOMMENDED}）",
    )
    args = parser.parse_args()

    init_db()
    symbol = (args.symbol or "").strip() or None
    interval = (args.interval or "").strip() or None

    print("=" * 60)
    print("  FlowMarkets 信号质量权重优化")
    print("=" * 60)

    count, report_or_msg, saved = run_weight_optimization(
        save=args.save,
        method=args.method,
        symbol=symbol,
        interval=interval,
        min_samples=max(1, args.min_samples),
    )

    if count < args.min_samples:
        print(f"\n[错误] {report_or_msg}\n")
        print("流程: analyze --save → evaluate_outcomes → 再运行本脚本\n")
        return 1

    if args.save and count < MIN_SAMPLES_HARD:
        print(
            f"\n[错误] --save 需要至少 {MIN_SAMPLES_HARD} 条可计分记录（当前 {count} 条）\n"
        )
        return 1

    if count < MIN_SAMPLES_RECOMMENDED:
        print(f"\n[警告] 样本 {count} 条，建议至少 {MIN_SAMPLES_RECOMMENDED} 条再 --save\n")

    print(report_or_msg)

    if args.save and saved:
        optimal = reload_weights()
        print(f"\n[完成] 已保存: {saved}")
        print("\n新旧权重对比:")
        print("-" * 50)
        for dim in DEFAULT_WEIGHTS:
            old = DEFAULT_WEIGHTS[dim]
            new = optimal.get(dim, old)
            change = new - old
            arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
            print(f"  {DIM_NAMES.get(dim, dim):<12}: {old:>5.0f} → {new:>5.1f}  {arrow} {change:+.1f}")
        print("\n下次 analyze 将自动使用 optimized_weights.json\n")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\n[中断] 用户取消\n")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n\n[错误] {exc}\n")
        traceback.print_exc()
        raise SystemExit(1)
