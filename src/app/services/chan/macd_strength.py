"""笔级 MACD 力度（与 chanlun ICL _calculate_bi_strength 对齐）。"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import pandas as pd

from app.services.chan.types import MergedKline, SimpleBi

_MACD_FAST = 12
_MACD_SLOW = 26
_MACD_SIGNAL = 9


def compute_macd_hist(close: pd.Series) -> List[float]:
    """DIF/DEA 标准参数，柱 = (DIF - DEA) * 2。"""
    c = close.astype(float)
    ema_short = c.ewm(span=_MACD_FAST, adjust=False).mean()
    ema_long = c.ewm(span=_MACD_SLOW, adjust=False).mean()
    dif = ema_short - ema_long
    dea = dif.ewm(span=_MACD_SIGNAL, adjust=False).mean()
    return ((dif - dea) * 2).tolist()


def _raw_index_range(
    bi: SimpleBi,
    merged_by_idx: Dict[int, MergedKline],
) -> Optional[tuple[int, int]]:
    s, e = int(bi.start_index), int(bi.end_index)
    if s > e:
        s, e = e, s
    raw: List[int] = []
    for idx in range(s, e + 1):
        mk = merged_by_idx.get(idx)
        if mk is None:
            continue
        raw.extend(getattr(mk, "raw_indices", None) or [])
    if not raw:
        return None
    return min(raw), max(raw)


def _macd_strength_for_segment(hist: Sequence[float], bi_type: str) -> float:
    if bi_type == "up":
        return float(sum(abs(v) for v in hist if v > 0))
    return float(sum(abs(v) for v in hist if v < 0))


def attach_bi_macd_strength(
    df: pd.DataFrame,
    bis: List[SimpleBi],
    merged_by_idx: Dict[int, MergedKline],
) -> None:
    """为每笔写入 macd_strength，并更新综合 strength（MACD/价差/斜率加权）。"""
    if not bis or df is None or len(df) == 0 or "close" not in df.columns:
        return

    hist_values = compute_macd_hist(df["close"])
    n = len(hist_values)

    for bi in bis:
        span = _raw_index_range(bi, merged_by_idx)
        if span is None:
            continue
        raw_start, raw_end = span
        s = max(0, min(raw_start, raw_end))
        e = min(n - 1, max(raw_start, raw_end))
        segment = hist_values[s : e + 1]
        if not segment:
            continue

        bi.macd_strength = round(_macd_strength_for_segment(segment, bi.type), 2)

        if bi.price_strength <= 0:
            bi.price_strength = round(abs(bi.end_price - bi.start_price), 2)

        kline_count = abs(e - s) + 1
        slope_strength = bi.price_strength / max(kline_count, 1)
        bi.strength = round(
            0.5 * bi.macd_strength + 0.3 * bi.price_strength + 0.2 * slope_strength * 100,
            2,
        )
