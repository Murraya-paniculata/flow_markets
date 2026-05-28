"""背驰（BC）附着：结构引擎 BSP + 力度比较，供 structure 导出 divergences。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.chan.types import SimpleBC, SimpleBi, SimpleXD, SimpleZS

# 引擎 BSP 类型 → 导出背驰类型（与 chanlun bc.type 一致）
_BSP_VALUE_TO_BC: Dict[str, str] = {
    "1": "bi",
    "1p": "pz",
}

_STRENGTH_RATIO_MAX = 0.8


def _bsp_type_values(bsp: Any) -> List[str]:
    out: List[str] = []
    for t in getattr(bsp, "type", []) or []:
        v = t.value if hasattr(t, "value") else str(t)
        out.append(v)
    return out


def _bc_types_from_bsp(bsp: Any) -> List[str]:
    types: List[str] = []
    for v in _bsp_type_values(bsp):
        mapped = _BSP_VALUE_TO_BC.get(v)
        if mapped and mapped not in types:
            types.append(mapped)
    return types


def _append_bc(
    entity: SimpleBi | SimpleXD,
    bc_type: str,
    zs: Optional[SimpleZS] = None,
) -> None:
    for existing in entity.bcs or []:
        if getattr(existing, "bc", False) and getattr(existing, "type", "") == bc_type:
            return
    entity.bcs.append(SimpleBC(bc_type=bc_type, is_bc=True, zs=zs))


def _find_related_zs(
    start_time: Any,
    end_time: Any,
    zss: List[SimpleZS],
) -> Optional[SimpleZS]:
    for zs in reversed(zss):
        if start_time <= zs.end_time and end_time >= zs.start_time:
            return zs
        if start_time > zs.end_time:
            return zs
    return None


def attach_bcs_from_engine_bsp(
    kl_data: Any,
    bis: List[SimpleBi],
    xds: List[SimpleXD],
    bi_zss: List[SimpleZS],
    xd_zss: List[SimpleZS],
    zs_map: Dict[int, SimpleZS],
) -> None:
    """从结构引擎一类买卖点（bsp1）提取盘整/趋势背驰标记。"""
    for bsp in getattr(kl_data.bs_point_lst, "bsp1_list", []) or []:
        idx = int(bsp.bi.idx)
        if idx >= len(bis):
            continue
        zs = zs_map.get(idx) or _find_related_zs(bis[idx].start_time, bis[idx].end_time, bi_zss)
        for bc_type in _bc_types_from_bsp(bsp):
            _append_bc(bis[idx], bc_type, zs)

    for bsp in getattr(kl_data.seg_bs_point_lst, "bsp1_list", []) or []:
        seg_idx = int(bsp.bi.idx)
        if seg_idx >= len(xds):
            continue
        xd = xds[seg_idx]
        zs = _find_related_zs(xd.start_time, xd.end_time, xd_zss)
        for bc_type in _bc_types_from_bsp(bsp):
            # 线段级一类背驰在导出契约中为 xd
            _append_bc(xd, "xd" if bc_type == "bi" else bc_type, zs)


def _bi_strength(bi: SimpleBi) -> float:
    s = float(getattr(bi, "strength", 0) or 0)
    if s > 0:
        return s
    return float(getattr(bi, "price_strength", 0) or 0)


def _check_bi_divergence(prev: SimpleBi, curr: SimpleBi) -> bool:
    if prev.type != curr.type:
        return False
    prev_s = _bi_strength(prev)
    curr_s = _bi_strength(curr)
    if prev_s <= 0:
        return False
    if curr_s <= 0:
        curr_s = abs(curr.end_price - curr.start_price)
        prev_s = abs(prev.end_price - prev.start_price)
        if prev_s <= 0:
            return False
    ratio = curr_s / prev_s
    if prev.type == "up":
        return curr.end_price > prev.end_price and ratio < _STRENGTH_RATIO_MAX
    return curr.end_price < prev.end_price and ratio < _STRENGTH_RATIO_MAX


def _xd_strength(xd: SimpleXD) -> float:
    total = 0.0
    for bi in xd.bi_list or []:
        total += _bi_strength(bi)
    if total > 0:
        return total
    return abs(xd.end_price - xd.start_price)


def _check_xd_divergence(prev: SimpleXD, curr: SimpleXD) -> bool:
    if prev.type != curr.type:
        return False
    prev_s = _xd_strength(prev)
    curr_s = _xd_strength(curr)
    if prev_s <= 0:
        return False
    ratio = curr_s / prev_s
    if prev.type == "up":
        return curr.end_price > prev.end_price and ratio < _STRENGTH_RATIO_MAX
    return curr.end_price < prev.end_price and ratio < _STRENGTH_RATIO_MAX


def attach_strength_divergences(
    bis: List[SimpleBi],
    xds: List[SimpleXD],
    bi_zss: List[SimpleZS],
    xd_zss: List[SimpleZS],
) -> None:
    """同向笔/线段力度减弱背驰（与 chanlun ICL 规则对齐，补充无 BSP 的情形）。"""
    if len(bis) >= 5:
        for i in range(4, len(bis)):
            current = bis[i]
            if any(getattr(bc, "bc", False) for bc in current.bcs or []):
                continue
            for j in range(i - 2, -1, -2):
                prev = bis[j]
                if current.type != prev.type:
                    continue
                if _check_bi_divergence(prev, current):
                    zs = _find_related_zs(current.start_time, current.end_time, bi_zss)
                    _append_bc(current, "bi", zs)
                break

    if len(xds) >= 3:
        for i in range(2, len(xds)):
            current = xds[i]
            if any(getattr(bc, "bc", False) for bc in current.bcs or []):
                continue
            for j in range(i - 2, -1, -2):
                prev = xds[j]
                if current.type != prev.type:
                    continue
                if _check_xd_divergence(prev, current):
                    zs = _find_related_zs(current.start_time, current.end_time, xd_zss)
                    _append_bc(current, "xd", zs)
                break
