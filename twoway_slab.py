"""
Çift Doğrultulu Döşeme Hesabı Modülü
====================================
Bu modül çift doğrultulu (two-way) döşemelerin moment hesabı ve donatı tasarımını içerir.
"""

from typing import Dict, Tuple, List, Optional
from constants import ALPHA_TABLE, M_POINTS, CASE_DESC
from struct_design import (
    interp_alpha, twoway_smax_short, twoway_smax_long,
    select_rebar_min_area, RebarChoice
)


def slab_edge_has_beam(system, sid: str, edge: str) -> bool:
    """
    Döşemenin belirli bir kenarında kiriş olup olmadığını kontrol eder.
    """
    s = system.slabs[sid]
    i0, j0, i1, j1 = s.bbox()
    edge = edge.upper()
    if edge == "LEFT":
        return (i0 != 0) and system.is_beam_gridline_for_slab(sid, "X", i0)
    if edge == "RIGHT":
        return (i1 < system.Nx - 1) and system.is_beam_gridline_for_slab(sid, "X", i1 + 1)
    if edge == "TOP":
        return (j0 != 0) and system.is_beam_gridline_for_slab(sid, "Y", j0)
    if edge == "BOTTOM":
        return (j1 < system.Ny - 1) and system.is_beam_gridline_for_slab(sid, "Y", j1 + 1)
    return False


def twoway_net_LxLy(system, sid: str, bw: float) -> Tuple[float, float, List[str]]:
    """
    Çift doğrultulu döşeme için net açıklıkları hesaplar.
    """
    steps = []
    s = system.slabs[sid]
    Lx_g, Ly_g = s.size_m_gross()
    left = slab_edge_has_beam(system, sid, "LEFT")
    right = slab_edge_has_beam(system, sid, "RIGHT")
    top = slab_edge_has_beam(system, sid, "TOP")
    bottom = slab_edge_has_beam(system, sid, "BOTTOM")

    steps.append(f"Brüt: Lx={Lx_g:.3f}, Ly={Ly_g:.3f}")
    Lx_n = max(0.05, Lx_g - (0.5*bw if left else 0.0) - (0.5*bw if right else 0.0))
    Ly_n = max(0.05, Ly_g - (0.5*bw if top else 0.0) - (0.5*bw if bottom else 0.0))
    steps.append(f"Lx_net = {Lx_n:.3f}, Ly_net = {Ly_n:.3f}")
    return Lx_n, Ly_n, steps


def twoway_edge_continuity_full(system, sid: str):
    """
    Döşemenin tüm kenarlarının süreklilik durumunu kontrol eder.
    """
    Lf, La, Lr = system.edge_neighbor_coverage(sid, "L")
    Rf, Ra, Rr = system.edge_neighbor_coverage(sid, "R")
    Tf, Ta, Tr = system.edge_neighbor_coverage(sid, "T")
    Bf, Ba, Br = system.edge_neighbor_coverage(sid, "B")
    return (Lf, Rf, Tf, Bf), (La, Ra, Ta, Ba), (Lr, Rr, Tr, Br)


def pick_two_way_case_exact(Lx_net: float, Ly_net: float,
                            cont_left: bool, cont_right: bool, 
                            cont_top: bool, cont_bottom: bool) -> int:
    """
    Çift doğrultulu döşeme için durum numarasını belirler (1-7).
    """
    disc = {"L": not cont_left, "R": not cont_right, "T": not cont_top, "B": not cont_bottom}
    n_disc = sum(disc.values())

    if n_disc == 0: return 1
    if n_disc == 4: return 7
    if n_disc == 1: return 2
    if n_disc == 3: return 6

    eps = 1e-9
    if abs(Lx_net - Ly_net) < eps:
        short_edges, long_edges = set(), set()
    elif Lx_net < Ly_net:
        short_edges, long_edges = {"T", "B"}, {"L", "R"}
    else:
        short_edges, long_edges = {"L", "R"}, {"T", "B"}

    disc_edges = {e for e, d in disc.items() if d}
    if len(disc_edges) != 2:
        return 3

    if short_edges and disc_edges == short_edges: return 4
    if long_edges and disc_edges == long_edges: return 5

    adjacent_pairs = [{"L", "T"}, {"T", "R"}, {"R", "B"}, {"B", "L"}]
    if any(disc_edges == p for p in adjacent_pairs):
        return 3

    if disc_edges == {"T", "B"}: return 4
    if disc_edges == {"L", "R"}: return 5
    return 3


def compute_twoway_per_slab(system, sid: str, bw: float) -> Tuple[dict, List[str]]:
    """
    Çift doğrultulu döşeme için moment hesabı yapar.
    
    Args:
        system: SlabSystem nesnesi
        sid: Döşeme ID'si
        bw: Kiriş genişliği (m)
    
    Returns:
        (sonuç_dict, hesap_adımları_listesi)
    """
    steps = []
    s = system.slabs[sid]
    pd = s.pd
    Lx_n, Ly_n, st_net = twoway_net_LxLy(system, sid, bw)
    steps.extend(st_net)

    ll = max(Lx_n, Ly_n)
    ls = min(Lx_n, Ly_n)
    m = ll / ls if ls > 0 else 1.0
    steps.append(f"m = {ll:.3f}/{ls:.3f} = {m:.3f}")

    (Lf, Rf, Tf, Bf), *_ = twoway_edge_continuity_full(system, sid)
    steps.append(f"Full süreklilik: L={Lf}, R={Rf}, T={Tf}, B={Bf}")
    case = pick_two_way_case_exact(Lx_n, Ly_n, Lf, Rf, Tf, Bf)
    row = ALPHA_TABLE[case]
    steps.append(f"Case {case}: {CASE_DESC.get(case,'-')}")

    a_sn = interp_alpha(m, M_POINTS, row.short_neg) if row.short_neg is not None else None
    a_sp = interp_alpha(m, M_POINTS, row.short_pos) if row.short_pos is not None else None
    a_ln = row.long_neg
    a_lp = row.long_pos

    steps.append(f"Alphas: sn={a_sn}, sp={a_sp}, ln={a_ln}, lp={a_lp}")

    # Moment hesabı: M = α × pd × ls²
    ls_sq = ls ** 2
    steps.append(f"pd = {pd:.3f} kN/m², ls = {ls:.3f} m, ls² = {ls_sq:.4f} m²")
    
    M_sn = a_sn * pd * ls_sq if a_sn is not None else None
    M_sp = a_sp * pd * ls_sq if a_sp is not None else None
    M_ln = a_ln * pd * ls_sq if a_ln is not None else None
    M_lp = a_lp * pd * ls_sq if a_lp is not None else None

    # Moment değerlerini göster
    steps.append(f"M_sn = {a_sn}×{pd:.3f}×{ls_sq:.4f} = {M_sn:.3f} kNm/m" if M_sn is not None else "M_sn = -")
    steps.append(f"M_sp = {a_sp}×{pd:.3f}×{ls_sq:.4f} = {M_sp:.3f} kNm/m" if M_sp is not None else "M_sp = -")
    steps.append(f"M_ln = {a_ln}×{pd:.3f}×{ls_sq:.4f} = {M_ln:.3f} kNm/m" if M_ln is not None else "M_ln = -")
    steps.append(f"M_lp = {a_lp}×{pd:.3f}×{ls_sq:.4f} = {M_lp:.3f} kNm/m" if M_lp is not None else "M_lp = -")

    short_dir = "X" if Lx_n <= Ly_n else "Y"
    steps.append(f"Kısa doğrultu: {short_dir}")
    
    # Eksenlere atama
    if short_dir == "X":
        steps.append(f"  Mx_neg = M_sn = {M_sn:.3f}, Mx_pos = M_sp = {M_sp:.3f}" if M_sn and M_sp else "")
        steps.append(f"  My_neg = M_ln = {M_ln:.3f}, My_pos = M_lp = {M_lp:.3f}" if M_ln and M_lp else "")
    else:
        steps.append(f"  My_neg = M_sn = {M_sn:.3f}, My_pos = M_sp = {M_sp:.3f}" if M_sn and M_sp else "")
        steps.append(f"  Mx_neg = M_ln = {M_ln:.3f}, Mx_pos = M_lp = {M_lp:.3f}" if M_ln and M_lp else "")

    if short_dir == "X":
        Mx_neg, Mx_pos = M_sn, M_sp
        My_neg, My_pos = M_ln, M_lp
    else:
        My_neg, My_pos = M_sn, M_sp
        Mx_neg, Mx_pos = M_ln, M_lp

    return {
        "Lx_net": Lx_n, "Ly_net": Ly_n, "ls": ls, "m": m,
        "case": case, "Mx": (Mx_neg, Mx_pos), "My": (My_neg, My_pos),
        "short_dir": short_dir
    }, steps


def compute_twoway_report(system, sid: str, res: dict, conc: str, steel: str,
                          h: float, cover: float, bw: float) -> Tuple[dict, List[str]]:
    """
    Çift doğrultulu döşeme için donatı hesabı ve raporlama yapar.
    
    Args:
        system: SlabSystem nesnesi
        sid: Döşeme ID'si
        res: compute_twoway_per_slab sonucu
        conc: Beton sınıfı
        steel: Çelik sınıfı
        h: Döşeme kalınlığı (mm)
        cover: Pas payı (mm)
        bw: Kiriş genişliği (m)
    
    Returns:
        (tasarım_sonucu_dict, rapor_satırları_listesi)
    """
    lines = []
    
    mxn, mxp = res["Mx"]
    myn, myp = res["My"]
    
    smax_x = twoway_smax_short(h) if res["short_dir"] == "X" else twoway_smax_long(h)
    smax_y = twoway_smax_long(h) if res["short_dir"] == "X" else twoway_smax_short(h)
    
    # X doğrultusu: d = h - cover (normal)
    # Y doğrultusu açıklık: d = h - cover - 10 (üst üste binen donatı için)
    # Y doğrultusu mesnet: d = h - cover (normal)
    asx, ch_x, _ = system.design_main_rebar_from_M(mxp or 0, conc, steel, h, cover, smax_x, label_prefix="  X: ", d_delta_mm=0.0)
    asy, ch_y, _ = system.design_main_rebar_from_M(myp or 0, conc, steel, h, cover, smax_y, label_prefix="  Y: ", d_delta_mm=-10.0)
    
    asxn, ch_xn, _ = system.design_main_rebar_from_M(abs(mxn or 0), conc, steel, h, cover, smax_x, label_prefix="  Xneg: ", d_delta_mm=0.0)
    asyn, ch_yn, _ = system.design_main_rebar_from_M(abs(myn or 0), conc, steel, h, cover, smax_y, label_prefix="  Yneg: ", d_delta_mm=0.0)

    ch_x_il = select_rebar_min_area(max(0, ch_xn.area_mm2_per_m - ch_x.area_mm2_per_m), 330)
    ch_y_il = select_rebar_min_area(max(0, ch_yn.area_mm2_per_m - ch_y.area_mm2_per_m), 330)

    design_res = {
        "kind": "TWOWAY", "short_dir": res["short_dir"], "cover_mm": cover,
        "choices": {"x_span": ch_x, "y_span": ch_y, "x_support_extra": ch_x_il, "y_support_extra": ch_y_il}
    }
    lines.append(f"  X: {ch_x.label()} | Y: {ch_y.label()}")
    lines.append("")
    
    return design_res, lines
