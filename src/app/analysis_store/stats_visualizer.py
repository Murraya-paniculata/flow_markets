"""统计图表可视化（Phase 4.4，移植 chanlun stats_visualizer，数据来自 StatsService）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.analysis_store.stats_formatter import _POSITION_ZH, _SIGNAL_ZH, _TREND_ZH
from app.analysis_store.stats_service import BucketStat, EvaluatedRecord, StatsService

_DEFAULT_OUTPUT = Path("output/stats")

_DIRECTION_ZH = {"up": "看涨", "down": "看跌", "unknown": "未知"}
_OUTCOME_ZH = {
    "success": "成功",
    "partial": "部分正确",
    "stopped": "止损",
    "failed": "失败",
    "unknown": "未知",
    "no_direction": "无方向",
}
_QUALITY_ZH = {
    "A": "A-优质",
    "B": "B-良好",
    "C": "C-一般",
    "D": "D-低质",
    "unknown": "未评级",
}


class MatplotlibNotAvailableError(ImportError):
    """未安装 matplotlib（需 uv sync --extra chart）。"""


def _load_plotting():
    try:
        import matplotlib

        if matplotlib.get_backend().lower() != "agg":
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
    except ImportError as exc:
        raise MatplotlibNotAvailableError(
            "未安装 matplotlib。请运行: uv sync --extra chart"
        ) from exc

    plt.rcParams["font.sans-serif"] = [
        "PingFang SC",
        "Arial Unicode MS",
        "Heiti SC",
        "STHeiti",
        "SimHei",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    return plt, mpatches, np


def _save_fig(plt, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    return path.resolve()


def _annotate_bars(ax, bars, totals: list[int]) -> None:
    for bar, total in zip(bars, totals):
        height = bar.get_height()
        ax.annotate(
            f"{height:.1f}%\n(n={total})",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )


def _plot_bucket_bars(
    ax,
    buckets: list[BucketStat],
    *,
    label_map: dict[str, str],
    title: str,
    color: str = "#3498db",
) -> None:
    if not buckets:
        ax.set_title(title)
        ax.axis("off")
        ax.text(0.5, 0.5, "无数据", ha="center", va="center", transform=ax.transAxes)
        return

    labels = [label_map.get(b.key, b.key) for b in buckets]
    rates = [b.win_rate * 100 for b in buckets]
    totals = [b.total for b in buckets]
    x = range(len(labels))
    bars = ax.bar(x, rates, color=color, edgecolor="black", linewidth=0.5)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
    ax.set_ylabel("胜率 (%)")
    ax.set_title(title)
    ax.set_ylim(0, 100)
    ax.axhline(y=50, color="gray", linestyle="--", alpha=0.5)
    _annotate_bars(ax, bars, totals)


def plot_win_rate_structure(
    svc: StatsService,
    records: list[EvaluatedRecord],
    output_dir: Path,
) -> Path | None:
    if not records:
        return None

    plt, _, _ = _load_plotting()
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("FlowMarkets · 结构维度胜率", fontsize=14, fontweight="bold")

    _plot_bucket_bars(
        axes[0, 0],
        svc.by_trend(records),
        label_map=_TREND_ZH,
        title="按趋势",
        color="#2ecc71",
    )
    _plot_bucket_bars(
        axes[0, 1],
        svc.by_position(records),
        label_map=_POSITION_ZH,
        title="按价格位置",
        color="#9b59b6",
    )
    _plot_bucket_bars(
        axes[1, 0],
        svc.by_signal_type(records),
        label_map=_SIGNAL_ZH,
        title="按信号类型",
        color="#e67e22",
    )

    quality = svc.by_signal_quality(records)
    has_quality = any(b.key not in ("unknown",) for b in quality)
    if has_quality:
        _plot_bucket_bars(
            axes[1, 1],
            quality,
            label_map=_QUALITY_ZH,
            title="按信号质量评级",
            color="#1abc9c",
        )
    else:
        _plot_bucket_bars(
            axes[1, 1],
            svc.by_has_signal(records),
            label_map={"has_signal": "有信号", "no_signal": "无信号"},
            title="按有无信号",
            color="#95a5a6",
        )

    plt.tight_layout()
    return _save_fig(plt, output_dir / "win_rate_structure.png")


def plot_win_rate_overview(
    svc: StatsService,
    stats: dict[str, Any],
    output_dir: Path,
) -> Path | None:
    if stats.get("total", 0) == 0:
        return None

    plt, _, _ = _load_plotting()
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("FlowMarkets · 预测维度胜率概览", fontsize=14, fontweight="bold")

    def _from_legacy(rows: list[tuple], label_map: dict[str, str]) -> list[BucketStat]:
        out: list[BucketStat] = []
        for key, total, hits, avg in rows:
            out.append(
                BucketStat(
                    key=key,
                    total=int(total),
                    hits=int(hits),
                    win_rate=round(hits / total, 4) if total else 0.0,
                    avg_score=float(avg),
                )
            )
        return out

    _plot_bucket_bars(
        axes[0, 0],
        _from_legacy(stats.get("by_direction", []), _DIRECTION_ZH),
        label_map=_DIRECTION_ZH,
        title="按预测方向",
        color="#3498db",
    )
    _plot_bucket_bars(
        axes[0, 1],
        _from_legacy(stats.get("by_interval", []), {}),
        label_map={},
        title="按周期",
        color="#3498db",
    )
    _plot_bucket_bars(
        axes[1, 0],
        _from_legacy(stats.get("by_symbol", []), {}),
        label_map={},
        title="按交易对",
        color="#9b59b6",
    )

    ax4 = axes[1, 1]
    outcomes = stats.get("by_outcome") or []
    if outcomes:
        labels = [_OUTCOME_ZH.get(k, k) for k, _ in outcomes]
        counts = [c for _, c in outcomes]
        colors = ["#2ecc71", "#f1c40f", "#e74c3c", "#c0392b", "#95a5a6", "#7f8c8d"]
        ax4.pie(
            counts,
            labels=labels,
            autopct="%1.1f%%",
            colors=colors[: len(counts)],
            startangle=90,
        )
        ax4.set_title("结果类型分布")
    else:
        ax4.axis("off")

    plt.tight_layout()
    return _save_fig(plt, output_dir / "win_rate_overview.png")


def plot_score_distribution(
    records: list[EvaluatedRecord],
    output_dir: Path,
) -> Path | None:
    if not records:
        return None

    plt, mpatches, np = _load_plotting()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("FlowMarkets · 得分与盈亏分布", fontsize=14, fontweight="bold")

    scores = [float(r.outcome.get("score", 0)) for r in records]
    enhanced = [
        float(r.outcome.get("enhanced_score", r.outcome.get("score", 0))) for r in records
    ]

    ax1 = axes[0]
    ax1.hist(scores, bins=min(20, max(5, len(scores))), color="#3498db", alpha=0.7, label="基础得分")
    ax1.hist(
        enhanced,
        bins=min(20, max(5, len(enhanced))),
        color="#e74c3c",
        alpha=0.45,
        label="增强得分",
    )
    ax1.set_xlabel("得分")
    ax1.set_ylabel("频次")
    ax1.set_title("得分分布")
    ax1.legend(fontsize=8)
    if scores:
        ax1.axvline(x=float(np.mean(scores)), color="#3498db", linestyle="--", alpha=0.8)

    ax2 = axes[1]
    favorable = [float(r.outcome.get("max_favorable_move") or 0) for r in records]
    adverse = [abs(float(r.outcome.get("max_adverse_move") or 0)) for r in records]
    colors = []
    for r in records:
        if r.outcome.get("hit_target"):
            colors.append("#2ecc71")
        elif r.outcome.get("hit_stop"):
            colors.append("#e74c3c")
        else:
            colors.append("#95a5a6")

    ax2.scatter(adverse, favorable, c=colors, alpha=0.65, edgecolors="black", linewidth=0.4)
    ax2.set_xlabel("最大不利变动 (%)")
    ax2.set_ylabel("最大有利变动 (%)")
    ax2.set_title("风险 vs 收益")
    if favorable and adverse:
        max_val = max(max(favorable), max(adverse), 1.0)
        ax2.plot([0, max_val], [0, max_val], "k--", alpha=0.3, label="1:1")
        ax2.plot([0, max_val], [0, max_val * 2], "g--", alpha=0.3, label="2:1")
    ax2.legend(
        handles=[
            mpatches.Patch(color="#2ecc71", label="命中目标"),
            mpatches.Patch(color="#e74c3c", label="触及止损"),
            mpatches.Patch(color="#95a5a6", label="其他"),
        ],
        loc="upper left",
        fontsize=8,
    )

    plt.tight_layout()
    return _save_fig(plt, output_dir / "score_distribution.png")


def _parse_ts(raw: str) -> datetime:
    text = (raw or "").strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.min


def plot_performance_over_time(
    records: list[EvaluatedRecord],
    output_dir: Path,
) -> Path | None:
    if len(records) < 2:
        return None

    plt, _, np = _load_plotting()
    ordered = sorted(records, key=lambda r: _parse_ts(r.timestamp))

    times: list[datetime] = []
    scores: list[float] = []
    cumulative_wins: list[int] = []
    win_count = 0

    for rec in ordered:
        times.append(_parse_ts(rec.timestamp))
        score = float(rec.outcome.get("score", 0))
        scores.append(score)
        if rec.outcome.get("hit_target"):
            win_count += 1
        cumulative_wins.append(win_count)

    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle("FlowMarkets · 时间序列表现", fontsize=14, fontweight="bold")

    cumulative_rate = [w / (i + 1) * 100 for i, w in enumerate(cumulative_wins)]
    axes[0].plot(times, cumulative_rate, color="#3498db", linewidth=2, label="累计胜率")
    axes[0].fill_between(times, cumulative_rate, alpha=0.25)
    axes[0].set_ylabel("累计胜率 (%)")
    axes[0].axhline(y=50, color="gray", linestyle="--", alpha=0.5)
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    window = min(10, len(scores))
    rolling = [float(np.mean(scores[max(0, i - window + 1) : i + 1])) for i in range(len(scores))]
    axes[1].plot(times, rolling, color="#e74c3c", linewidth=2, label=f"滚动均分 (窗口={window})")
    axes[1].scatter(times, scores, color="#95a5a6", alpha=0.5, s=18, label="单次得分")
    axes[1].set_xlabel("时间")
    axes[1].set_ylabel("得分")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    return _save_fig(plt, output_dir / "performance_over_time.png")


def generate_all_stats_charts(
    output_dir: Path | str = _DEFAULT_OUTPUT,
    *,
    symbol: str | None = None,
    interval: str | None = None,
) -> list[Path]:
    """生成全部统计 PNG，返回已写入路径列表。"""
    out = Path(output_dir)
    svc = StatsService()
    records = svc.fetch_evaluated_records(symbol=symbol, interval=interval)
    stats = svc.full_report(symbol=symbol, interval=interval)

    if not records:
        print("【警告】无可计分评估记录，请先 --save 分析并运行 evaluate_outcomes.py")
        return []

    print(f"【信息】共 {len(records)} 条可计分记录 → {out.resolve()}\n")

    paths: list[Path] = []
    for plot_fn, args in (
        (plot_win_rate_structure, (svc, records, out)),
        (plot_win_rate_overview, (svc, stats, out)),
        (plot_score_distribution, (records, out)),
        (plot_performance_over_time, (records, out)),
    ):
        try:
            path = plot_fn(*args)
            if path is not None:
                paths.append(path)
                print(f"【完成】{path.name} → {path}")
        except MatplotlibNotAvailableError:
            raise
        except Exception as exc:
            print(f"【跳过】{plot_fn.__name__}: {exc}")

    if paths:
        print(f"\n【完成】共生成 {len(paths)} 张图表")
    return paths
