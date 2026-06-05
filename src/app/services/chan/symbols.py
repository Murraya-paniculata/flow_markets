"""Binance 现货交易对 symbol 规范化（get_klines / get_chan_structure 共用）。"""
from __future__ import annotations

import re

# 常见计价货币后缀（现货 U 本位研究默认 USDT）
_QUOTE_SUFFIXES: tuple[str, ...] = ("USDT", "USDC", "BUSD", "FDUSD", "TUSD")

_PLACEHOLDER_EXACT: frozenset[str] = frozenset(
    {
        "",
        "未指定",
        "(未指定)",
        "（未指定）",
        "UNSPECIFIED",
        "UNKNOWN",
        "N/A",
        "NA",
        "NONE",
        "NULL",
        "TBD",
        "待定",
        "无",
        "无标的",
    }
)

# Agent 偶发传入的中文说明，非交易对
_PLACEHOLDER_SUBSTR: tuple[str, ...] = ("未指定", "未提供", "unknown symbol")


def _strip_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper().replace("/", "").replace("-", "").replace("_", "")


def is_placeholder_symbol(symbol: str) -> bool:
    raw = (symbol or "").strip()
    if not raw:
        return True
    if raw in _PLACEHOLDER_EXACT:
        return True
    compact = _strip_symbol(raw)
    if compact in _PLACEHOLDER_EXACT:
        return True
    for frag in _PLACEHOLDER_SUBSTR:
        if frag in raw:
            return True
    return False


def normalize_binance_symbol(symbol: str, *, default_quote: str = "USDT") -> tuple[str, str]:
    """
    返回 ``(binance_symbol, display_symbol)``。

    - ``BTC`` / ``BTC/USDT`` → ``BTCUSDT``, ``BTC/USDT``
    - 已是 ``ETHUSDT`` 等则保持不变
    - 占位符（未指定等）抛出 ``ValueError``
    """
    if is_placeholder_symbol(symbol):
        raise ValueError(
            "symbol 无效或未指定，请提供 Binance 现货交易对，如 BTCUSDT、ETHUSDT。"
        )

    raw = _strip_symbol(symbol)
    if not raw:
        raise ValueError("symbol 不能为空")

    quote = (default_quote or "USDT").strip().upper()
    for q in _QUOTE_SUFFIXES:
        if len(raw) > len(q) and raw.endswith(q):
            base = raw[: -len(q)]
            if not base:
                raise ValueError(f"symbol 格式无效: {symbol!r}")
            return raw, f"{base}/{q}"

    # 仅 base（如 BTC、ETH、SOL）→ 默认拼 USDT
    if re.fullmatch(r"[A-Z0-9]{2,20}", raw):
        binance = f"{raw}{quote}"
        return binance, f"{raw}/{quote}"

    raise ValueError(
        f"无法识别的交易对: {symbol!r}，请使用如 BTCUSDT 或 BTC。"
    )
