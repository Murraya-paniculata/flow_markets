#!/usr/bin/env python3
"""缠论验图：Binance K 线 → chanpy → PNG（用法见 README 缠论一节）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if not os.environ.get("MPLBACKEND"):
    try:
        import matplotlib

        matplotlib.use("Agg")
    except ImportError:
        pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from app.services.chan.backend import (  # noqa: E402
    build_cchan,
    dataframe_to_ckline_units,
    ensure_chanpy_importable,
    interval_to_kl_type,
)
from app.services.chan.kline import (  # noqa: E402
    fetch_klines_raw,
    get_klines_beijing,
    normalize_interval,
)

import pandas as pd  # noqa: E402

SYMBOL = os.environ.get("CHAN_SYMBOL", "BTCUSDT").upper()
INTERVAL = os.environ.get("CHAN_INTERVAL", "1d")
LIMIT = int(os.environ.get("CHAN_LIMIT", "500"))
USE_BEIJING = os.environ.get("CHAN_USE_BEIJING", "0").strip() in ("1", "true", "yes")
OUTPUT_DIR = Path(os.environ.get("CHAN_OUTPUT_DIR", _ROOT / "output" / "chan_charts"))
OUTPUT_IMG = OUTPUT_DIR / f"{SYMBOL.lower()}_{INTERVAL}_chan.png"
_DIRECT = frozenset({"5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"})


def _load_df() -> pd.DataFrame:
    if USE_BEIJING:
        raw = get_klines_beijing(SYMBOL, normalize_interval(INTERVAL), LIMIT)
    else:
        if INTERVAL not in _DIRECT:
            raise ValueError(f"不支持 {INTERVAL}，或设 CHAN_USE_BEIJING=1")
        raw = fetch_klines_raw(SYMBOL, INTERVAL, min(LIMIT, 1000))
    rows = [
        {"date": k["open_time"], "open": k["open"], "high": k["high"], "low": k["low"], "close": k["close"]}
        for k in raw
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def main() -> None:
    ensure_chanpy_importable()
    from Plot.PlotDriver import CPlotDriver  # noqa: WPS433

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mode = "5m聚合" if USE_BEIJING else "Binance直连"
    print(f"拉取 {SYMBOL} {INTERVAL} x{LIMIT}（{mode}）…")
    df = _load_df()
    print(f"共 {len(df)} 根")

    freq = normalize_interval(INTERVAL) if USE_BEIJING else INTERVAL
    klu_list = dataframe_to_ckline_units(df)
    chan = build_cchan(klu_list, interval_to_kl_type(freq), SYMBOL, {"print_warning": True})
    print(f"笔 {len(chan[0].bi_list)}，线段 {len(chan[0].seg_list)}")

    plot_driver = CPlotDriver(
        chan,
        plot_config={
            "plot_kline": True,
            "plot_kline_combine": True,
            "plot_bi": True,
            "plot_seg": True,
            "plot_zs": True,
            "plot_macd": True,
            "plot_bsp": True,
        },
        plot_para={"figure": {"x_range": min(200, len(klu_list))}},
    )
    plot_driver.save2img(str(OUTPUT_IMG))
    print(f"已保存: {OUTPUT_IMG.resolve()}")

    if os.environ.get("CHAN_SHOW", "").strip() in ("1", "true", "yes"):
        try:
            import matplotlib.pyplot as plt

            plt.switch_backend("MacOSX")
            plot_driver.figure.show()
        except Exception as exc:
            print(f"无法弹窗: {exc}")


if __name__ == "__main__":
    main()
