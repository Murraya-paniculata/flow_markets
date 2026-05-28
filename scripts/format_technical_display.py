#!/usr/bin/env python3
"""将已保存的 TechnicalAnalysisDeliverable JSON 转为交易者可读文案。

  uv run python scripts/format_technical_display.py ./data/technical_analysis.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))


def main() -> int:
    _bootstrap()
    parser = argparse.ArgumentParser(description="JSON → 交易者可读文案")
    parser.add_argument("json_file", type=Path, help="TechnicalAnalysisDeliverable JSON 文件")
    args = parser.parse_args()

    from app.schemas.flow_markets_deliverables import TechnicalAnalysisDeliverable
    from app.schemas.technical_analysis_display import format_trader_display

    raw = json.loads(args.json_file.read_text(encoding="utf-8"))
    if "brief" not in raw and "symbol" in raw:
        print("提示：该文件像是旧版 TechnicalBrief，请使用含 brief+chanlun_v2 的 JSON。", file=sys.stderr)
    model = TechnicalAnalysisDeliverable.model_validate(raw)
    print(format_trader_display(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
