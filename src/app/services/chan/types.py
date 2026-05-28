"""chanpy 结构对象（笔/段/中枢/分型等）。"""
from __future__ import annotations

from typing import Any, List, Optional


class MergedKline:
    def __init__(
        self,
        index: int,
        date: Any,
        high: float,
        low: float,
        open_price: float,
        close: float,
        raw_indices: List[int] | None = None,
    ):
        self.index = index
        self.date = date
        self.high = high
        self.low = low
        self.open = open_price
        self.close = close
        self.raw_indices = raw_indices or [index]


class SimpleFX:
    def __init__(
        self,
        fx_type: str,
        index: int,
        kline: MergedKline,
        price: float,
        time: Any,
        raw_index: int | None = None,
    ):
        self.type = fx_type
        self.index = index
        self.k = kline
        self.val = price
        self.time = time
        self.raw_index = raw_index or index

    def is_done(self) -> bool:
        return True


class SimpleBi:
    def __init__(
        self,
        index: int,
        direction: str,
        start_fx: SimpleFX,
        end_fx: SimpleFX,
        start_index: int,
        end_index: int,
        is_done: bool = True,
    ):
        self.index = index
        self.type = direction
        self._is_done = is_done
        self.start_fx = start_fx
        self.end_fx = end_fx
        self.start_index = start_index
        self.end_index = end_index
        self.start_time = start_fx.time
        self.end_time = end_fx.time
        self.start_price = float(start_fx.val)
        self.end_price = float(end_fx.val)
        self.high = max(float(start_fx.val), float(end_fx.val))
        self.low = min(float(start_fx.val), float(end_fx.val))
        self.strength: float = 0.0
        self.macd_strength: float = 0.0
        self.price_strength: float = 0.0
        self.mmds: List[Any] = []
        self.bcs: List[Any] = []

    def is_done(self) -> bool:
        return self._is_done


class SimpleXD:
    def __init__(
        self,
        index: int,
        direction: str,
        start_bi: SimpleBi,
        end_bi: SimpleBi,
        bi_list: List[SimpleBi],
        is_done: bool = True,
    ):
        self.index = index
        self.type = direction
        self._is_done = is_done
        self.bi_list = bi_list
        self.start_bi_index = start_bi.index
        self.end_bi_index = end_bi.index
        self.start_time = start_bi.start_time
        self.end_time = end_bi.end_time
        self.start_price = start_bi.start_price
        self.end_price = end_bi.end_price
        self.mmds: List[Any] = []
        self.bcs: List[Any] = []

    def is_done(self) -> bool:
        return self._is_done


class SimpleZS:
    def __init__(
        self,
        index: int,
        zs_type: str,
        direction: str,
        start_time: Any,
        end_time: Any,
        zg: float,
        zd: float,
        gg: float,
        dd: float,
        relation: str = "new",
        bi_count: int = 0,
    ):
        self.index = index
        self.zs_type = zs_type
        self.direction = direction
        self.start_time = start_time
        self.end_time = end_time
        self.zg = zg
        self.zd = zd
        self.gg = gg
        self.dd = dd
        self.relation = relation
        self.bi_count = bi_count
        self.level = 1
        self.is_sure = True
        self.start_merged_idx: int | None = None
        self.end_merged_idx: int | None = None


class SimpleMMD:
    def __init__(self, name: str, zs: Optional[SimpleZS] = None, msg: Optional[str] = None):
        self.name = name
        self.zs = zs
        self.msg = msg
