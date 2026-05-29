#!/usr/bin/env python3
"""查看 / 导出分析记忆库 analysis_snapshot（终端表格或 CSV）。

用法（flow_markets 根目录）:
  uv run python scripts/show_analysis_db.py
  uv run python scripts/show_analysis_db.py --id 2
  uv run python scripts/show_analysis_db.py --csv
  uv run python scripts/show_analysis_db.py --csv -o output/analysis_snapshots.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from app.analysis_store import get_db_conn, get_db_path, init_db, safe_json_loads
from app.analysis_store.stats_service import _is_scorable_outcome

CSV_COLUMNS = [
    "id",
    "symbol",
    "interval",
    "timestamp",
    "created_at",
    "price",
    "evaluated",
    "scorable",
    "state_machine",
    "direction",
    "trend",
    "price_position",
    "target_pct",
    "stop_pct",
    "brief_summary",
    "kline_count",
    "bi_count",
    "segment_count",
    "center_count",
    "buy_sell_points",
    "divergences",
    "outcome_status",
    "outcome_error",
    "hit_target",
    "hit_stop",
    "score",
    "enhanced_score",
    "outcome_target_pct",
    "outcome_stop_pct",
    "max_favorable_pct",
    "max_adverse_pct",
    "evaluated_bars",
    "required_bars",
    "final_price",
    "outcome_direction",
]


def _cell(value: Any, width: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > width:
        return text[: max(0, width - 1)] + "…"
    return text.ljust(width)


def _print_table(headers: list[str], rows: list[list[Any]]) -> None:
    if not rows:
        print("  (无记录)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    sep = "  ".join("-" * w for w in widths)
    print("  ".join(_cell(h, widths[i]) for i, h in enumerate(headers)))
    print(sep)
    for row in rows:
        print("  ".join(_cell(row[i], widths[i]) for i in range(len(headers))))


def _outcome_label(outcome: dict[str, Any] | None) -> str:
    if not outcome:
        return "待回填"
    if outcome.get("error"):
        err = str(outcome.get("error"))
        if err == "insufficient_data":
            bars = outcome.get("evaluated_bars", "?")
            req = outcome.get("required_bars", "?")
            return f"数据不足({bars}/{req})"
        return err
    if outcome.get("outcome") == "skipped":
        return f"跳过({outcome.get('error', '')})"
    hit = "命中" if outcome.get("hit_target") else "未中"
    return f"{outcome.get('outcome', '?')} {hit}"


def _scorable_label(outcome: dict[str, Any] | None, evaluated: int) -> str:
    if not evaluated:
        return "否(待评估)"
    if not outcome:
        return "否"
    return "是" if _is_scorable_outcome(outcome) else "否"


def _extract_ai_summary(ai: dict[str, Any] | None) -> dict[str, str]:
    if not ai:
        return {
            "state": "-",
            "direction": "-",
            "target_pct": "-",
            "stop_pct": "-",
            "signal": "-",
            "trend": "-",
            "position": "-",
            "brief_summary": "",
        }
    v2 = ai.get("chanlun_v2") or {}
    sm = v2.get("state_machine") or {}
    active = sm.get("active_strategy") or {}
    exec_ = active.get("execution") or {}
    sj = v2.get("structure_judgement") or {}
    meta = v2.get("meta") or {}
    price = float(meta.get("price") or 0)
    stop = exec_.get("stop_loss")
    target = exec_.get("target")
    target_pct = stop_pct = "-"
    if price and stop and target:
        try:
            stop_pct = f"{abs(float(stop) - price) / price * 100:.2f}"
            target_pct = f"{abs(float(target) - price) / price * 100:.2f}"
        except (TypeError, ValueError):
            pass
    signal = sj.get("signal_type") or "-"
    brief_summary = (ai.get("brief") or {}).get("summary", "") or ""
    if signal == "-" and brief_summary:
        signal = brief_summary[:14] + ("…" if len(brief_summary) > 14 else "")
    return {
        "state": sm.get("current_state") or "-",
        "direction": active.get("direction") or "-",
        "target_pct": target_pct,
        "stop_pct": stop_pct,
        "signal": str(signal),
        "trend": sj.get("trend") or "-",
        "position": sj.get("price_position") or "-",
        "brief_summary": brief_summary,
    }


def _flatten_snapshot(row: Any) -> dict[str, Any]:
    ai = safe_json_loads(row["ai_json"])
    chanlun = safe_json_loads(row["chanlun_json"])
    outcome = safe_json_loads(row["outcome_json"]) if row["outcome_json"] else None
    summary = _extract_ai_summary(ai)
    meta = chanlun.get("meta") or {}
    ds = meta.get("data_size") or {}
    ss = chanlun.get("structure_summary") or {}
    sig = chanlun.get("signal") or {}

    flat: dict[str, Any] = {
        "id": row["id"],
        "symbol": row["symbol"],
        "interval": row["interval"],
        "timestamp": row["timestamp"],
        "created_at": row["created_at"],
        "price": row["price"],
        "evaluated": row["evaluated"],
        "scorable": _scorable_label(outcome, int(row["evaluated"] or 0)),
        "state_machine": summary["state"],
        "direction": summary["direction"],
        "trend": summary["trend"],
        "price_position": summary["position"],
        "target_pct": summary["target_pct"],
        "stop_pct": summary["stop_pct"],
        "brief_summary": summary["brief_summary"],
        "kline_count": ds.get("kline"),
        "bi_count": ds.get("bi"),
        "segment_count": ds.get("segment"),
        "center_count": ds.get("center"),
        "buy_sell_points": ", ".join(sig.get("buy_sell_points") or []),
        "divergences": ", ".join(sig.get("divergences") or []),
        "outcome_status": _outcome_label(outcome),
        "outcome_error": outcome.get("error") if outcome else "",
        "hit_target": outcome.get("hit_target") if outcome else "",
        "hit_stop": outcome.get("hit_stop") if outcome else "",
        "score": outcome.get("score") if outcome else "",
        "enhanced_score": outcome.get("enhanced_score") if outcome else "",
        "outcome_target_pct": outcome.get("target_pct") if outcome else "",
        "outcome_stop_pct": outcome.get("stop_pct") if outcome else "",
        "max_favorable_pct": outcome.get("max_favorable_move") if outcome else "",
        "max_adverse_pct": outcome.get("max_adverse_move") if outcome else "",
        "evaluated_bars": outcome.get("evaluated_bars") if outcome else "",
        "required_bars": outcome.get("required_bars") if outcome else "",
        "final_price": outcome.get("final_price") if outcome else "",
        "outcome_direction": outcome.get("direction") if outcome else "",
    }
    if not ss.get("trend") and flat["trend"] == "-":
        flat["trend"] = ss.get("trend") or "-"
    if not ss.get("price_position") and flat["price_position"] == "-":
        flat["price_position"] = ss.get("price_position") or "-"
    return flat


def _fetch_snapshots(*, limit: int | None = None, snapshot_id: int | None = None) -> list[Any]:
    with get_db_conn() as conn:
        if snapshot_id is not None:
            row = conn.execute(
                """
                SELECT id, symbol, interval, timestamp, price, evaluated,
                       chanlun_json, ai_json, outcome_json, created_at
                FROM analysis_snapshot WHERE id = ?
                """,
                (snapshot_id,),
            ).fetchone()
            return [row] if row else []
        sql = """
            SELECT id, symbol, interval, timestamp, price, evaluated,
                   chanlun_json, ai_json, outcome_json, created_at
            FROM analysis_snapshot
            ORDER BY id DESC
        """
        if limit is not None:
            return conn.execute(sql + " LIMIT ?", (limit,)).fetchall()
        return conn.execute(sql).fetchall()


def list_flat_rows(*, limit: int | None = 50, snapshot_id: int | None = None) -> list[dict[str, Any]]:
    return [_flatten_snapshot(r) for r in _fetch_snapshots(limit=limit, snapshot_id=snapshot_id)]


def rows_to_csv_text(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})
    return buf.getvalue()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})
    return path.resolve()


def _print_summary_table(rows: list[dict[str, Any]]) -> None:
    table = [
        [
            r["id"],
            r["symbol"],
            r["interval"],
            (r["timestamp"] or "")[:19],
            f"{float(r['price']):.2f}" if r.get("price") else "-",
            r["state_machine"],
            r["direction"],
            r["trend"],
            r["price_position"],
            r["evaluated"],
            r["scorable"],
            r["outcome_status"],
            r["score"] if r.get("score") not in ("", None) else "-",
        ]
        for r in rows
    ]
    _print_table(
        [
            "ID",
            "标的",
            "周期",
            "分析时间",
            "价格",
            "状态机",
            "方向",
            "趋势",
            "位置",
            "已评估",
            "可计分",
            "回填结果",
            "得分",
        ],
        table,
    )


def _print_detail(flat: dict[str, Any]) -> None:
    print(f"\n{'=' * 72}")
    print(f"快照 #{flat['id']}  {flat['symbol']}  {flat['interval']}")
    print(f"{'=' * 72}")
    _print_table(
        ["字段", "值"],
        [
            ["分析时间", flat["timestamp"]],
            ["落库时间", flat["created_at"]],
            ["价格", flat["price"]],
            ["已评估", flat["evaluated"]],
            ["可计分", flat["scorable"]],
        ],
    )
    print("\n【AI 预测摘要】")
    _print_table(
        ["字段", "值"],
        [
            ["状态机", flat["state_machine"]],
            ["方向", flat["direction"]],
            ["目标幅度%", flat["target_pct"]],
            ["止损幅度%", flat["stop_pct"]],
            ["趋势", flat["trend"]],
            ["价格位置", flat["price_position"]],
        ],
    )
    if flat.get("brief_summary"):
        print("\n【brief.summary】")
        print(f"  {flat['brief_summary']}")
    print("\n【结构快照】")
    _print_table(
        ["字段", "值"],
        [
            ["K线", flat["kline_count"]],
            ["笔", flat["bi_count"]],
            ["段", flat["segment_count"]],
            ["中枢", flat["center_count"]],
            ["买卖点", flat["buy_sell_points"] or "-"],
            ["背驰", flat["divergences"] or "-"],
        ],
    )
    print("\n【回填 outcome】")
    if not flat.get("outcome_error") and flat.get("outcome_status") == "待回填":
        print("  (尚未回填)")
        return
    if flat.get("outcome_error"):
        _print_table(
            ["字段", "值"],
            [
                ["错误", flat["outcome_error"]],
                ["已有K线", flat["evaluated_bars"]],
                ["需要K线", flat["required_bars"]],
            ],
        )
        return
    _print_table(
        ["字段", "值"],
        [
            ["结果", flat["outcome_status"]],
            ["方向", flat["outcome_direction"]],
            ["命中目标", flat["hit_target"]],
            ["触及止损", flat["hit_stop"]],
            ["得分", flat["score"]],
            ["增强得分", flat["enhanced_score"]],
            ["最大有利%", flat["max_favorable_pct"]],
            ["最大不利%", flat["max_adverse_pct"]],
            ["评估K线数", flat["evaluated_bars"]],
            ["结束价", flat["final_price"]],
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="查看 / 导出分析记忆库")
    parser.add_argument("--id", type=int, default=None, help="查看单条详情")
    parser.add_argument("--limit", type=int, default=50, help="列表最多条数（0=全部）")
    parser.add_argument(
        "--csv",
        action="store_true",
        help="输出 CSV（可用 Excel / Numbers 打开）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="写入 CSV 文件路径（配合 --csv；默认 output/analysis_snapshots.csv）",
    )
    args = parser.parse_args()

    init_db()
    limit = None if args.limit == 0 else args.limit
    rows = list_flat_rows(limit=limit, snapshot_id=args.id)

    if args.csv:
        if args.output is not None:
            out = write_csv(args.output, rows)
            print(f"已导出 CSV: {out}  ({len(rows)} 行)")
            return 0
        if args.output is None and args.id is None:
            default_out = _ROOT / "output" / "analysis_snapshots.csv"
            out = write_csv(default_out, rows)
            print(f"已导出 CSV: {out}  ({len(rows)} 行)")
            return 0
        print(rows_to_csv_text(rows), end="")
        return 0

    db = get_db_path().resolve()
    print("=" * 72)
    print("FlowMarkets 分析记忆库")
    print("=" * 72)
    print(f"数据库: {db}")

    with get_db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM analysis_snapshot").fetchone()[0]
        evaluated = conn.execute(
            "SELECT COUNT(*) FROM analysis_snapshot WHERE evaluated = 1"
        ).fetchone()[0]
        scorable = 0
        for (raw,) in conn.execute(
            "SELECT outcome_json FROM analysis_snapshot WHERE evaluated = 1"
        ).fetchall():
            if _is_scorable_outcome(safe_json_loads(raw)):
                scorable += 1

    print(f"快照总数: {total}  |  已评估: {evaluated}  |  可计分: {scorable}")
    print("\n【快照列表】")
    _print_summary_table(rows)

    if args.id is not None and rows:
        _print_detail(rows[0])
    elif rows:
        print("\n提示:")
        print(f"  详情  → uv run python scripts/show_analysis_db.py --id {rows[0]['id']}")
        print("  CSV   → uv run python scripts/show_analysis_db.py --csv")
        print("  导出  → uv run python scripts/show_analysis_db.py --csv -o output/analysis_snapshots.csv")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
