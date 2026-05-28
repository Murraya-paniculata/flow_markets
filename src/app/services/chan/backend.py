"""内置缠论结构引擎：计算笔/段/中枢/买卖点并转为 API 用的结构对象。"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .types import (
    MergedKline,
    SimpleBi,
    SimpleFX,
    SimpleMMD,
    SimpleXD,
    SimpleZS,
)

logger = logging.getLogger(__name__)

_CHAN_ENGINE_ROOT: Optional[Path] = None
ENGINE_ID = "structure-engine"
# 内置计算库目录名（仓库内 vendored 包，业务代码不对外暴露实现名）
_BUNDLED_ENGINE_DIRNAME = "chanpy"

# Binance interval -> 引擎 KL_TYPE 枚举名
INTERVAL_TO_KL_TYPE: Dict[str, str] = {
    "5m": "K_5M",
    "15m": "K_15M",
    "30m": "K_30M",
    "60m": "K_60M",
    "1h": "K_60M",
    "4h": "K_60M",
    "240m": "K_60M",
    "1d": "K_DAY",
    "1w": "K_WEEK",
    "1M": "K_MON",
    "1mon": "K_MON",
}


def _is_engine_repo_dir(path: Path) -> bool:
    return path.is_dir() and (path / "Chan.py").is_file() and (path / "Common").is_dir()


def _bundled_engine_dir() -> Path:
    return Path(__file__).resolve().parents[4] / _BUNDLED_ENGINE_DIRNAME


def _legacy_engine_root_env() -> str:
    for key in (
        "CHAN_ENGINE_ROOT",
        "APP_CHAN_ENGINE_ROOT",
        "CHANPY_ROOT",
        "APP_CHANPY_ROOT",
    ):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def get_chan_engine_root() -> Path:
    global _CHAN_ENGINE_ROOT
    if _CHAN_ENGINE_ROOT is not None:
        return _CHAN_ENGINE_ROOT

    env_root = _legacy_engine_root_env()
    if env_root:
        root = Path(env_root).resolve()
        if _is_engine_repo_dir(root):
            _CHAN_ENGINE_ROOT = root
            return root

    bundled = _bundled_engine_dir()
    if _is_engine_repo_dir(bundled):
        _CHAN_ENGINE_ROOT = bundled
        return bundled

    raise ImportError(f"未找到缠论结构引擎目录: {bundled}")


def ensure_chan_engine_importable() -> Path:
    root = get_chan_engine_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def _import_chan_engine():
    ensure_chan_engine_importable()
    from Chan import CChan  # noqa: WPS433
    from ChanConfig import CChanConfig
    from Common.CEnum import AUTYPE, BI_DIR, BSP_TYPE, DATA_FIELD, DATA_SRC, FX_TYPE, KL_TYPE
    from Common.CTime import CTime
    from KLine.KLine_Unit import CKLine_Unit

    return (
        CChan, CChanConfig, AUTYPE, DATA_FIELD, DATA_SRC, FX_TYPE, KL_TYPE, CTime, CKLine_Unit,
        BI_DIR, BSP_TYPE,
    )


def ctime_to_datetime(t: Any) -> datetime:
    if isinstance(t, datetime):
        return t
    if hasattr(t, "ts"):
        return datetime.fromtimestamp(t.ts, tz=timezone.utc)
    s = str(t).replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19] if " " in s else s[:10], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(tz=timezone.utc)


def interval_to_kl_type(frequency: str) -> Any:
    KL_TYPE = _import_chan_engine()[6]
    key = INTERVAL_TO_KL_TYPE.get(frequency, "K_DAY")
    return getattr(KL_TYPE, key)


def _row_to_ctime(row: Any, CTime: Any) -> Any:  # noqa: N803
    dt = pd.to_datetime(row["date"], errors="coerce")
    if pd.isna(dt):
        raise ValueError(f"无效 date: {row['date']!r}")
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.to_pydatetime().astimezone(timezone.utc).replace(tzinfo=None)
    else:
        dt = dt.to_pydatetime()
    return CTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, auto=False)


def dataframe_to_ckline_units(df: pd.DataFrame) -> List[Any]:
    _, _, _, DATA_FIELD, _, _, _, CTime, CKLine_Unit, _, _ = _import_chan_engine()
    units = []
    for _, row in df.iterrows():
        t = _row_to_ctime(row, CTime)
        units.append(
            CKLine_Unit(
                {
                    DATA_FIELD.FIELD_TIME: t,
                    DATA_FIELD.FIELD_OPEN: float(row["open"]),
                    DATA_FIELD.FIELD_HIGH: float(row["high"]),
                    DATA_FIELD.FIELD_LOW: float(row["low"]),
                    DATA_FIELD.FIELD_CLOSE: float(row["close"]),
                },
                autofix=True,
            )
        )
    return units


def build_cchan(
    klu_list: List[Any],
    lv: Any,
    code: str,
    engine_options: Optional[Dict[str, Any]] = None,
) -> Any:
    CChan, CChanConfig, AUTYPE, _, DATA_SRC, _, _, _, _, _, _ = _import_chan_engine()
    opts = {
        "bi_strict": True,
        "trigger_step": True,
        "divergence_rate": float("inf"),
        "bsp2_follow_1": False,
        "bsp3_follow_1": False,
        "min_zs_cnt": 0,
        "bs1_peak": False,
        "macd_algo": "peak",
        "bs_type": "1,2,3a,1p,2s,3b",
        "print_warning": False,
        "zs_algo": "normal",
    }
    if engine_options:
        opts.update(engine_options)

    config = CChanConfig(opts)
    chan = CChan(
        code=code,
        begin_time=None,
        end_time=None,
        data_src=DATA_SRC.CSV,
        lv_list=[lv],
        config=config,
        autype=AUTYPE.QFQ,
    )
    for i, klu in enumerate(klu_list):
        klu.set_idx(i)
        chan.trigger_load({lv: [klu]})
    chan[0].cal_seg_and_zs()
    return chan


def _bsp_to_mmd(bsp: Any, zs_map: Dict[int, SimpleZS], BSP_TYPE: Any) -> SimpleMMD:
    suffix = "buy" if bsp.is_buy else "sell"
    parts = []
    for t in bsp.type:
        v = t.value if isinstance(t, BSP_TYPE) else str(t)
        if v in ("1", "2", "3a", "3b", "1p", "2s"):
            parts.append(f"{v}{suffix}")
        else:
            parts.append(f"{v}{suffix}")
    name = parts[0] if len(parts) == 1 else ",".join(parts)
    bi_idx = bsp.bi.idx
    zs = zs_map.get(bi_idx)
    return SimpleMMD(name=name, zs=zs, msg=bsp.type2str())


def _klu_merged_idx(klu_idx: int, merged_klines: List[MergedKline]) -> Optional[int]:
    for mk in merged_klines:
        raw = getattr(mk, "raw_indices", None) or []
        if klu_idx in raw:
            return int(getattr(mk, "index", 0))
    return None


def _bsp_chart_item(bsp: Any, merged_klines: List[MergedKline], *, is_seg: bool) -> Optional[Dict[str, Any]]:
    klu = getattr(bsp, "klu", None)
    if klu is None:
        return None
    mi = _klu_merged_idx(int(klu.idx), merged_klines)
    if mi is None:
        return None
    is_buy = bool(getattr(bsp, "is_buy", False))
    try:
        type_str = bsp.type2str()
    except Exception:
        type_str = str(getattr(bsp, "type", ""))
    prefix = "※" if is_seg else ""
    label = f"{prefix}{'b' if is_buy else 's'}{type_str}"
    return {
        "merged_idx": mi,
        "price": float(klu.low) if is_buy else float(klu.high),
        "is_buy": is_buy,
        "label": label,
        "is_seg": is_seg,
    }


def _collect_bsp_chart(kl_data: Any, merged_klines: List[MergedKline]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for bsp in kl_data.bs_point_lst.bsp_iter():
        item = _bsp_chart_item(bsp, merged_klines, is_seg=False)
        if item:
            out.append(item)
    for bsp in kl_data.seg_bs_point_lst.bsp_iter():
        item = _bsp_chart_item(bsp, merged_klines, is_seg=True)
        if item:
            out.append(item)
    return out


def _klc_to_merged(klc: Any, index: int) -> MergedKline:
    raw = [u.idx for u in klc.lst]
    return MergedKline(
        index=index,
        date=ctime_to_datetime(klc.time_end),
        high=float(klc.high),
        low=float(klc.low),
        open_price=float(klc.lst[0].open),
        close=float(klc.lst[-1].close),
        raw_indices=raw,
    )


def _convert_zs(
    czs: Any,
    index: int,
    zs_type: str,
    merged_klines: List[MergedKline],
) -> SimpleZS:
    zs = SimpleZS(
        index=index,
        zs_type=zs_type,
        direction="zd",
        start_time=ctime_to_datetime(czs.begin.time),
        end_time=ctime_to_datetime(czs.end.time),
        zg=float(czs.high),
        zd=float(czs.low),
        gg=float(czs.peak_high),
        dd=float(czs.peak_low),
        relation="new",
        bi_count=len(czs.bi_lst) if czs.bi_lst else 0,
    )
    begin_mi = _klu_merged_idx(int(czs.begin.idx), merged_klines)
    end_mi = _klu_merged_idx(int(czs.end.idx), merged_klines)
    zs.start_merged_idx = begin_mi if begin_mi is not None else int(czs.begin_bi.idx)
    zs.end_merged_idx = end_mi if end_mi is not None else int(czs.end_bi.idx)
    zs.is_sure = bool(getattr(czs, "is_sure", True))
    zs.high = float(zs.zg)
    zs.low = float(zs.zd)
    return zs


def _convert_bi(cbi: Any, merged_by_idx: Dict[int, MergedKline], FX_TYPE: Any) -> SimpleBi:
    start_klc = cbi.begin_klc
    end_klc = cbi.end_klc
    direction = "up" if cbi.is_up() else "down"

    def _fx(klc: Any, price: float, is_start: bool) -> SimpleFX:
        if klc.fx == FX_TYPE.TOP:
            fx_type = "ding"
        elif klc.fx == FX_TYPE.BOTTOM:
            fx_type = "di"
        else:
            fx_type = "ding" if direction == "up" and is_start else "di"
        mk = merged_by_idx.get(klc.idx)
        if mk is None:
            mk = _klc_to_merged(klc, klc.idx)
        return SimpleFX(
            fx_type=fx_type,
            index=klc.idx,
            kline=mk,
            price=price,
            time=ctime_to_datetime(klc.time_begin if is_start else klc.time_end),
            raw_index=klc.idx,
        )

    start_price = float(cbi.get_begin_val())
    end_price = float(cbi.get_end_val())
    start_fx = _fx(start_klc, start_price, True)
    end_fx = _fx(end_klc, end_price, False)

    bi = SimpleBi(
        index=cbi.idx,
        direction=direction,
        start_fx=start_fx,
        end_fx=end_fx,
        start_index=start_klc.idx,
        end_index=end_klc.idx,
        is_done=cbi.is_sure,
    )
    try:
        bi.high = float(cbi._high())
        bi.low = float(cbi._low())
    except Exception:
        pass
    try:
        amp = float(cbi.amp())
        bi.price_strength = round(amp, 2)
        bi.strength = round(amp, 2)
    except Exception:
        bi.price_strength = round(abs(bi.end_price - bi.start_price), 2)
        bi.strength = bi.price_strength
    return bi


def _convert_xd(seg: Any, bis: List[SimpleBi]) -> SimpleXD:
    direction = "up" if seg.is_up() else "down"
    s_idx = seg.start_bi.idx
    e_idx = seg.end_bi.idx
    bi_slice = bis[s_idx : e_idx + 1] if e_idx < len(bis) else bis[s_idx:]
    start_bi = bis[s_idx] if s_idx < len(bis) else bi_slice[0]
    end_bi = bis[e_idx] if e_idx < len(bis) else bi_slice[-1]
    return SimpleXD(
        index=seg.idx,
        direction=direction,
        start_bi=start_bi,
        end_bi=end_bi,
        bi_list=bi_slice,
        is_done=seg.is_sure,
    )


def _attach_bsp_mmds(
    kl_data: Any,
    bis: List[SimpleBi],
    xds: List[SimpleXD],
    zs_map: Dict[int, SimpleZS],
    BSP_TYPE: Any,
) -> None:
    for bsp in kl_data.bs_point_lst.bsp_iter():
        idx = bsp.bi.idx
        if idx < len(bis):
            bis[idx].mmds.append(_bsp_to_mmd(bsp, zs_map, BSP_TYPE))
    for bsp in kl_data.seg_bs_point_lst.bsp_iter():
        seg_idx = bsp.bi.idx
        if seg_idx < len(xds):
            xds[seg_idx].mmds.append(_bsp_to_mmd(bsp, zs_map, BSP_TYPE))


class ChanEngineICL:
    """缠论结构引擎计算结果封装（笔/段/中枢/买卖点）。"""

    def __init__(self, code: str, frequency: str, config: Optional[Dict[str, Any]] = None):
        self.code = code
        self.frequency = frequency
        self.config = config or {}
        self._chan = None
        self._raw_df: Optional[pd.DataFrame] = None
        self._bis: List[SimpleBi] = []
        self._xds: List[SimpleXD] = []
        self._bi_zss: List[SimpleZS] = []
        self._xd_zss: List[SimpleZS] = []
        self._zsd_zss: List[SimpleZS] = []
        self._merged_klines: List[MergedKline] = []
        self._fx_list: List[SimpleFX] = []
        self._bsp_chart: List[Dict[str, Any]] = []

    def process_klines(self, df: pd.DataFrame) -> "ChanEngineICL":
        if len(df) == 0:
            return self

        ensure_chan_engine_importable()
        _imp = _import_chan_engine()
        FX_TYPE = _imp[5]
        BSP_TYPE = _imp[10]

        self._raw_df = df.copy()
        lv = interval_to_kl_type(self.frequency)
        klu_list = dataframe_to_ckline_units(df)
        engine_opts = self.config.get("engine") if isinstance(self.config.get("engine"), dict) else {}
        self._chan = build_cchan(klu_list, lv, self.code, engine_opts)

        kl_data = self._chan[0]
        self._merged_klines = [_klc_to_merged(klc, klc.idx) for klc in kl_data.lst]
        merged_by_idx = {klc.idx: mk for klc, mk in zip(kl_data.lst, self._merged_klines)}

        self._fx_list = []
        for i, klc in enumerate(kl_data.lst):
            if klc.fx == FX_TYPE.TOP:
                self._fx_list.append(
                    SimpleFX("ding", i, merged_by_idx[klc.idx], float(klc.high), ctime_to_datetime(klc.time_begin), i)
                )
            elif klc.fx == FX_TYPE.BOTTOM:
                self._fx_list.append(
                    SimpleFX("di", i, merged_by_idx[klc.idx], float(klc.low), ctime_to_datetime(klc.time_begin), i)
                )

        self._bis = [_convert_bi(cbi, merged_by_idx, FX_TYPE) for cbi in kl_data.bi_list]
        self._xds = [_convert_xd(seg, self._bis) for seg in kl_data.seg_list]

        self._bi_zss = [
            _convert_zs(z, i, "bi", self._merged_klines)
            for i, z in enumerate(kl_data.zs_list.zs_lst)
        ]
        self._xd_zss = [
            _convert_zs(z, i, "xd", self._merged_klines)
            for i, z in enumerate(kl_data.segzs_list.zs_lst)
        ]
        self._zsd_zss = []

        zs_map = {
            z.begin_bi.idx: self._bi_zss[i]
            for i, z in enumerate(kl_data.zs_list.zs_lst)
            if i < len(self._bi_zss)
        }
        _attach_bsp_mmds(kl_data, self._bis, self._xds, zs_map, BSP_TYPE)
        self._bsp_chart = _collect_bsp_chart(kl_data, self._merged_klines)

        logger.info(
            "[chan-engine] %s %s: merged_k=%d bi=%d xd=%d bi_zs=%d",
            self.code,
            self.frequency,
            len(self._merged_klines),
            len(self._bis),
            len(self._xds),
            len(self._bi_zss),
        )
        return self

    def get_bis(self) -> List[SimpleBi]:
        return self._bis

    def get_xds(self) -> List[SimpleXD]:
        return self._xds

    def get_bi_zss(self, zs_type: Optional[str] = None) -> List[SimpleZS]:
        return self._bi_zss

    def get_xd_zss(self, zs_type: Optional[str] = None) -> List[SimpleZS]:
        return self._xd_zss

    def get_zsd_zss(self) -> List[SimpleZS]:
        return self._zsd_zss

    def get_merged_klines(self) -> List[MergedKline]:
        return self._merged_klines

    def get_fx_list(self) -> List[SimpleFX]:
        return self._fx_list

    def get_bsp_list(self) -> List[Dict[str, Any]]:
        return self._bsp_chart
