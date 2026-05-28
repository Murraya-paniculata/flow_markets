#!/usr/bin/env python3
"""手动验证 2.2 落库：结构重算 + deliverable 写入 + 读回。

用法（flow_markets 根目录）:
  PYTHONPATH=src python scripts/test_analysis_persist.py
  PYTHONPATH=src python scripts/test_analysis_persist.py --query-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from app.analysis_store import get_db_conn, get_db_path, init_db, safe_json_loads
from app.analysis_store.persist import save_technical_deliverable
from app.schemas.flow_markets_deliverables import (
    ChanlunStateMachineOutput,
    TechnicalAnalysisDeliverable,
    TechnicalBrief,
)


def _sample_deliverable(symbol: str, interval: str, price: float) -> TechnicalAnalysisDeliverable:
    return TechnicalAnalysisDeliverable(
        brief=TechnicalBrief(
            symbol=symbol,
            interval=interval,
            data_status="有足够K线",
            summary="persist 集成测试：结构+状态机落库。",
            analysis_markdown="# 一、技术形态概述\n集成测试占位。",
            disclaimer="历史形态不保证未来表现；不构成投资建议。",
        ),
        chanlun_v2=ChanlunStateMachineOutput.model_validate(
            {
                "meta": {
                    "symbol": symbol,
                    "interval": interval,
                    "price": price,
                    "timestamp": "2026-05-28T00:00:00+00:00",
                },
                "state_machine": {
                    "current_state": "WAIT_CONFIRMATION",
                    "active_strategy": {
                        "direction": "up",
                        "status": "WAIT",
                        "entry_gate": {
                            "price_zone": [price * 0.99, price * 1.01],
                            "structure_required": ["price_hold_zd"],
                        },
                        "execution": {
                            "entry_type": "limit",
                            "stop_loss": price * 0.97,
                            "target": price * 1.03,
                            "rr": 1.5,
                        },
                    },
                    "invalidation": {
                        "invalidate_active_if": ["price_break_zd"],
                        "next_state": "OBSERVE_ONLY",
                    },
                    "standby_strategies": [],
                },
                "structure_judgement": {
                    "trend": "consolidation",
                    "price_position": "inside_zs",
                    "zs": {
                        "zg": price * 1.02,
                        "zd": price * 0.98,
                        "gg": price * 1.03,
                        "dd": price * 0.97,
                    },
                },
                "risk_notes": ["集成测试"],
            }
        ),
    )


def _print_rows() -> None:
    with get_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol, interval, price, evaluated,
                   length(chanlun_json) AS struct_len,
                   length(ai_json) AS ai_len,
                   created_at
            FROM analysis_snapshot
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()
    print(f"\n数据库: {get_db_path().resolve()}")
    print(f"最近 {len(rows)} 条 snapshot:")
    if not rows:
        print("  (空)")
        return
    for r in rows:
        print(
            f"  id={r['id']} {r['symbol']} {r['interval']} "
            f"price={r['price']} evaluated={r['evaluated']} "
            f"struct_bytes={r['struct_len']} ai_bytes={r['ai_len']} "
            f"at={r['created_at']}"
        )
    last = rows[0]
    with get_db_conn() as conn:
        raw = conn.execute(
            "SELECT ai_json FROM analysis_snapshot WHERE id=?",
            (last["id"],),
        ).fetchone()
    ai = safe_json_loads(raw["ai_json"])
    keys = list(ai.keys()) if isinstance(ai, dict) else []
    v2 = (ai.get("chanlun_v2") or {}).get("state_machine", {}).get("current_state")
    print(f"\n最新一条 ai_json 顶层键: {keys}")
    print(f"  chanlun_v2.state_machine.current_state = {v2}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--query-only",
        action="store_true",
        help="只查询库内记录，不写入",
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--lookback", type=int, default=200)
    args = parser.parse_args()

    init_db()
    if args.query_only:
        _print_rows()
        return 0

    from app.services.chan.structure import build_chan_structure_snapshot

    print(f"1) 拉结构 {args.symbol} {args.interval} lookback={args.lookback} …")
    snap = build_chan_structure_snapshot(
        args.symbol, args.interval, lookback=args.lookback
    )
    price = float(snap.market.latest_price)
    sym = snap.meta.symbol
    iv = snap.meta.interval
    print(f"   ✓ {sym} {iv} latest_price={price} klines={snap.meta.data_size.kline}")

    print("2) save_technical_deliverable …")
    sid = save_technical_deliverable(
        _sample_deliverable(sym, iv, price),
        timeframe=iv,
        lookback=args.lookback,
        symbol_hint=args.symbol,
    )
    if sid is None:
        print("   ✗ 写入失败（见日志）")
        return 1
    print(f"   ✓ snapshot_id={sid}")

    _print_rows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
