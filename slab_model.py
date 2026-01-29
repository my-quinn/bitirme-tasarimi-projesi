from dataclasses import dataclass
from typing import Dict, Tuple, List, Set, Optional
import hashlib
from constants import ALPHA_TABLE, M_POINTS, CASE_DESC
from struct_design import (
    interp_alpha, one_span_coeff_by_fixity, one_way_coefficients,
    as_from_abacus_steps, rho_min_oneway, select_rebar_min_area,
    max_possible_area, RebarChoice
)

@dataclass
class Slab:
    slab_id: str
    i0: int
    j0: int
    i1: int
    j1: int
    kind: str  # ONEWAY / TWOWAY / BALCONY
    dx: float
    dy: float
    pd: float
    b: float

    def bbox(self):
        return self.i0, self.j0, self.i1, self.j1

    def size_cells(self):
        return (self.i1 - self.i0 + 1), (self.j1 - self.j0 + 1)

    def size_m_gross(self):
        nx, ny = self.size_cells()
        return nx * self.dx, ny * self.dy

def color_for_id(s: str) -> str:
    h = hashlib.md5(s.encode("utf-8")).hexdigest()
    r = 80 + int(h[0:2], 16) % 140
    g = 80 + int(h[2:4], 16) % 140
    b = 80 + int(h[4:6], 16) % 140
    return f"#{r:02x}{g:02x}{b:02x}"

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def rect_normalize(a, b):
    (x0, y0), (x1, y1) = a, b
    return (min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))

class SlabSystem:
    def __init__(self, nx: int, ny: int):
        self.Nx = nx
        self.Ny = ny
        self.slabs: Dict[str, Slab] = {}
        self.cell_owner: Dict[Tuple[int, int], str] = {}
        self.V_beam: Set[Tuple[int, int]] = set()
        self.H_beam: Set[Tuple[int, int]] = set()

    def add_slab(self, s: Slab):
        self.slabs[s.slab_id] = s
        for i in range(s.i0, s.i1 + 1):
            for j in range(s.j0, s.j1 + 1):
                self.cell_owner[(i, j)] = s.slab_id

    def delete_slab(self, sid: str):
        if sid not in self.slabs:
            return
        s = self.slabs[sid]
        for i in range(s.i0, s.i1 + 1):
            for j in range(s.j0, s.j1 + 1):
                if self.cell_owner.get((i, j)) == sid:
                    del self.cell_owner[(i, j)]
        del self.slabs[sid]

    def neighbor_slabs_on_side(self, sid: str, direction: str, side: str) -> set:
        s = self.slabs[sid]
        i0, j0, i1, j1 = s.bbox()
        direction = direction.upper()
        side = side.upper()
        neigh = set()

        if direction == "X":
            if side == "START":
                if i0 == 0: return neigh
                ii = i0 - 1
                for j in range(j0, j1 + 1):
                    nb = self.cell_owner.get((ii, j))
                    if nb and nb != sid: neigh.add(nb)
            else:
                if i1 >= self.Nx - 1: return neigh
                ii = i1 + 1
                for j in range(j0, j1 + 1):
                    nb = self.cell_owner.get((ii, j))
                    if nb and nb != sid: neigh.add(nb)
        else:
            if side == "START":
                if j0 == 0: return neigh
                jj = j0 - 1
                for i in range(i0, i1 + 1):
                    nb = self.cell_owner.get((i, jj))
                    if nb and nb != sid: neigh.add(nb)
            else:
                if j1 >= self.Ny - 1: return neigh
                jj = j1 + 1
                for i in range(i0, i1 + 1):
                    nb = self.cell_owner.get((i, jj))
                    if nb and nb != sid: neigh.add(nb)
        return neigh

    def edge_neighbor_coverage(self, sid: str, edge: str) -> Tuple[bool, bool, float]:
        s = self.slabs[sid]
        i0, j0, i1, j1 = s.bbox()
        edge = edge.upper()
        total, found = 0, 0

        if edge == "L":
            if i0 == 0: return (False, False, 0.0)
            for j in range(j0, j1 + 1):
                total += 1
                nb = self.cell_owner.get((i0 - 1, j))
                if nb and nb != sid: found += 1
        elif edge == "R":
            if i1 >= self.Nx - 1: return (False, False, 0.0)
            for j in range(j0, j1 + 1):
                total += 1
                nb = self.cell_owner.get((i1 + 1, j))
                if nb and nb != sid: found += 1
        elif edge == "T":
            if j0 == 0: return (False, False, 0.0)
            for i in range(i0, i1 + 1):
                total += 1
                nb = self.cell_owner.get((i, j0 - 1))
                if nb and nb != sid: found += 1
        elif edge == "B":
            if j1 >= self.Ny - 1: return (False, False, 0.0)
            for i in range(i0, i1 + 1):
                total += 1
                nb = self.cell_owner.get((i, j1 + 1))
                if nb and nb != sid: found += 1

        any_ = found > 0
        full = (total > 0 and found == total)
        ratio = (found / total) if total > 0 else 0.0
        return (full, any_, ratio)

    def twoway_edge_continuity_full(self, sid: str):
        Lf, La, Lr = self.edge_neighbor_coverage(sid, "L")
        Rf, Ra, Rr = self.edge_neighbor_coverage(sid, "R")
        Tf, Ta, Tr = self.edge_neighbor_coverage(sid, "T")
        Bf, Ba, Br = self.edge_neighbor_coverage(sid, "B")
        return (Lf, Rf, Tf, Bf), (La, Ra, Ta, Ba), (Lr, Rr, Tr, Br)

    def pick_two_way_case_exact(self, Lx_net: float, Ly_net: float,
                               cont_left: bool, cont_right: bool, cont_top: bool, cont_bottom: bool) -> int:
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

    # =========================================================
    # Beam line detection
    # =========================================================
    def is_beam_gridline_for_slab(self, sid: str, direction: str, g: int) -> bool:
        s = self.slabs[sid]
        i0, j0, i1, j1 = s.bbox()
        direction = direction.upper()

        if direction == "X":
            if g <= 0 or g >= self.Nx: return False
            k = g - 1
            return all((k, j) in self.V_beam for j in range(j0, j1 + 1))
        else:
            if g <= 0 or g >= self.Ny: return False
            k = g - 1
            return all((i, k) in self.H_beam for i in range(i0, i1 + 1))

    def slab_support_gridlines_from_drawn_beams(self, sid: str, direction: str) -> List[int]:
        s = self.slabs[sid]
        i0, j0, i1, j1 = s.bbox()
        direction = direction.upper()
        if direction == "X":
            return [g for g in range(i0 + 1, i1 + 1) if self.is_beam_gridline_for_slab(sid, "X", g)]
        else:
            return [g for g in range(j0 + 1, j1 + 1) if self.is_beam_gridline_for_slab(sid, "Y", g)]

    # =========================================================
    # ONEWAY logic
    # =========================================================
    def build_oneway_chain(self, sid: str, direction: str) -> List[str]:
        direction = direction.upper()
        if self.slabs[sid].kind != "ONEWAY":
            return [sid]

        stack = [sid]
        seen = {sid}
        chain = []
        while stack:
            u = stack.pop()
            if self.slabs[u].kind != "ONEWAY":
                continue
            chain.append(u)
            for side in ("START", "END"):
                for nb in self.neighbor_slabs_on_side(u, direction, side):
                    if nb in seen: continue
                    seen.add(nb)
                    if nb in self.slabs and self.slabs[nb].kind == "ONEWAY":
                        stack.append(nb)

        if direction == "X":
            chain.sort(key=lambda x: self.slabs[x].i0)
        else:
            chain.sort(key=lambda x: self.slabs[x].j0)
        return chain

    def chain_panel_boundary_supports(self, chain: List[str], direction: str) -> List[int]:
        direction = direction.upper()
        if len(chain) < 2: return []
        supports = []
        for a, b in zip(chain[:-1], chain[1:]):
            sa, sb = self.slabs[a], self.slabs[b]
            if direction == "X":
                g = sa.i1 + 1
                if sb.i0 == g: supports.append(g)
            else:
                g = sa.j1 + 1
                if sb.j0 == g: supports.append(g)
        return supports

    def chain_end_fixity(self, chain: List[str], direction: str) -> Tuple[bool, bool]:
        direction = direction.upper()
        first, last = chain[0], chain[-1]
        start_neigh = self.neighbor_slabs_on_side(first, direction, "START")
        end_neigh = self.neighbor_slabs_on_side(last, direction, "END")
        # Herhangi bir döşeme komşusu varsa sürekli kabul et
        # (ONEWAY-ONEWAY, ONEWAY-TWOWAY, ONEWAY-BALCONY, TWOWAY-TWOWAY, TWOWAY-BALCONY)
        fixed_start = any(n in self.slabs for n in start_neigh)
        fixed_end = any(n in self.slabs for n in end_neigh)
        return fixed_start, fixed_end

    def net_span(self, Lgross: float, left_is_beam: bool, right_is_beam: bool, bw: float) -> float:
        if left_is_beam and right_is_beam:
            Lnet = Lgross - bw
        elif left_is_beam or right_is_beam:
            Lnet = Lgross - 0.5 * bw
        else:
            Lnet = Lgross
        return max(0.05, Lnet)

    def owner_slab_for_segment(self, chain: List[str], direction: str, g_mid: float) -> str:
        direction = direction.upper()
        for sid in chain:
            s = self.slabs[sid]
            if direction == "X":
                if s.i0 <= g_mid <= (s.i1 + 1): return sid
            else:
                if s.j0 <= g_mid <= (s.j1 + 1): return sid
        return chain[0]

    def compute_oneway_per_slab(self, sid: str, bw_val: float) -> Tuple[dict, List[str]]:
        steps = []
        s0 = self.slabs[sid]
        w = s0.pd * s0.b
        steps.append(f"w = pd*b = {s0.pd:.3f}*{s0.b:.3f} = {w:.3f} kN/m")

        Lx_g, Ly_g = s0.size_m_gross()
        direction = "Y" if Lx_g < Ly_g else "X"
        steps.append(f"Otomatik açıklık yönü: Lx={Lx_g:.3f}, Ly={Ly_g:.3f} -> yön={direction}")

        chain = self.build_oneway_chain(sid, direction)
        steps.append(f"Zincir: {chain}")

        fixed_start, fixed_end = self.chain_end_fixity(chain, direction)
        steps.append(f"Uç ankastre: START={fixed_start}, END={fixed_end}")

        if direction == "X":
            start_g = min(self.slabs[x].i0 for x in chain)
            end_g = max(self.slabs[x].i1 + 1 for x in chain)
        else:
            start_g = min(self.slabs[x].j0 for x in chain)
            end_g = max(self.slabs[x].j1 + 1 for x in chain)

        supports = [start_g, end_g]
        supports.extend(self.chain_panel_boundary_supports(chain, direction))
        for x in chain:
            supports.extend(self.slab_support_gridlines_from_drawn_beams(x, direction))
        supports = sorted(set(supports))
        steps.append(f"Mesnet gridline listesi: {supports}")

        spans = []
        for a, b_g in zip(supports[:-1], supports[1:]):
            mid_g = 0.5 * (a + b_g)
            owner = self.owner_slab_for_segment(chain, direction, mid_g)
            s_owner = self.slabs[owner]
            # Kısa açıklık uzunluğunu kullan (taşıma doğrultusu)
            Lx_owner, Ly_owner = s_owner.size_m_gross()
            L_short = min(Lx_owner, Ly_owner)
            left_is_beam = self.is_beam_gridline_for_slab(owner, direction, a)
            right_is_beam = self.is_beam_gridline_for_slab(owner, direction, b_g)
            Lnet = self.net_span(L_short, left_is_beam, right_is_beam, bw_val)
            # Tek doğrultuda her zaman kısa açıklık üzerinden hesap yapılıyor
            spans.append((L_short, owner, Lnet))
            steps.append(f"Span [{a}->{b_g}] owner={owner}: L_short={L_short:.3f} (hesapta kullanılan), Lnet={Lnet:.3f}")

        n_spans = len(spans)
        steps.append(f"Toplam span: {n_spans}")

        if n_spans == 1:
            (c_start, c_end), c_pos = one_span_coeff_by_fixity(fixed_start, fixed_end)
            L = spans[0][0]
            Mpos = c_pos * w * L**2
            Mneg_start = c_start * w * L**2
            Mneg_end = c_end * w * L**2
            steps.append(f"M+ = {Mpos:.3f}, M-start={Mneg_start:.3f}, M-end={Mneg_end:.3f}")
            return {
                "auto_dir": direction, "chain": chain,
                "fixed_start": fixed_start, "fixed_end": fixed_end,
                "w": w, "Mpos_max": Mpos, "Mneg_min": min(Mneg_start, Mneg_end)
            }, steps

        support_c, span_c = one_way_coefficients(n_spans)
        Ls = [L for (L, *_rest) in spans]
        owners = [o for (_L, o, *_rest) in spans]

        span_Mpos = []
        for i in range(n_spans):
            M = span_c[i] * w * (Ls[i] ** 2)
            span_Mpos.append(M)
            steps.append(f"Span{i+1} M+ = {M:.3f}")

        support_Mneg = []
        for i in range(n_spans + 1):
            if i == 0: L2 = Ls[0] ** 2
            elif i == n_spans: L2 = Ls[-1] ** 2
            else: L2 = 0.5 * (Ls[i-1] ** 2 + Ls[i] ** 2)
            M = support_c[i] * w * L2
            support_Mneg.append(M)
            steps.append(f"Mesnet{i} M- = {M:.3f}")

        owned_span_idx = [i for i, o in enumerate(owners) if o == sid]
        Mpos_max = max(span_Mpos[i] for i in owned_span_idx) if owned_span_idx else None

        touching = set()
        for i in owned_span_idx:
            touching.add(i); touching.add(i+1)
        Mneg_min = min(support_Mneg[i] for i in touching) if touching else None

        return {
            "auto_dir": direction, "chain": chain,
            "w": w, "Mpos_max": Mpos_max, "Mneg_min": Mneg_min
        }, steps

    # =========================================================
    # TWOWAY logic
    # =========================================================
    def slab_edge_has_beam(self, sid: str, edge: str) -> bool:
        s = self.slabs[sid]
        i0, j0, i1, j1 = s.bbox()
        edge = edge.upper()
        if edge == "LEFT":
            return (i0 != 0) and self.is_beam_gridline_for_slab(sid, "X", i0)
        if edge == "RIGHT":
            return (i1 < self.Nx - 1) and self.is_beam_gridline_for_slab(sid, "X", i1 + 1)
        if edge == "TOP":
            return (j0 != 0) and self.is_beam_gridline_for_slab(sid, "Y", j0)
        if edge == "BOTTOM":
            return (j1 < self.Ny - 1) and self.is_beam_gridline_for_slab(sid, "Y", j1 + 1)
        return False

    def twoway_net_LxLy(self, sid: str, bw: float) -> Tuple[float, float, List[str]]:
        steps = []
        s = self.slabs[sid]
        Lx_g, Ly_g = s.size_m_gross()
        left = self.slab_edge_has_beam(sid, "LEFT")
        right = self.slab_edge_has_beam(sid, "RIGHT")
        top = self.slab_edge_has_beam(sid, "TOP")
        bottom = self.slab_edge_has_beam(sid, "BOTTOM")

        steps.append(f"Brüt: Lx={Lx_g:.3f}, Ly={Ly_g:.3f}")
        Lx_n = max(0.05, Lx_g - (0.5*bw if left else 0.0) - (0.5*bw if right else 0.0))
        Ly_n = max(0.05, Ly_g - (0.5*bw if top else 0.0) - (0.5*bw if bottom else 0.0))
        steps.append(f"Lx_net = {Lx_n:.3f}, Ly_net = {Ly_n:.3f}")
        return Lx_n, Ly_n, steps

    def compute_twoway_per_slab(self, sid: str, bw: float) -> Tuple[dict, List[str]]:
        steps = []
        s = self.slabs[sid]
        pd = s.pd
        Lx_n, Ly_n, st_net = self.twoway_net_LxLy(sid, bw)
        steps.extend(st_net)

        ll = max(Lx_n, Ly_n)
        ls = min(Lx_n, Ly_n)
        m = ll / ls if ls > 0 else 1.0
        steps.append(f"m = {ll:.3f}/{ls:.3f} = {m:.3f}")

        (Lf, Rf, Tf, Bf), *_ = self.twoway_edge_continuity_full(sid)
        steps.append(f"Full süreklilik: L={Lf}, R={Rf}, T={Tf}, B={Bf}")
        case = self.pick_two_way_case_exact(Lx_n, Ly_n, Lf, Rf, Tf, Bf)
        row = ALPHA_TABLE[case]
        steps.append(f"Case {case}: {CASE_DESC.get(case,'-')}")

        a_sn = interp_alpha(m, M_POINTS, row.short_neg) if row.short_neg is not None else None
        a_sp = interp_alpha(m, M_POINTS, row.short_pos) if row.short_pos is not None else None
        a_ln = row.long_neg
        a_lp = row.long_pos

        steps.append(f"Alphas: sn={a_sn}, sp={a_sp}, ln={a_ln}, lp={a_lp}")

        M_sn = a_sn * pd * (ls**2) if a_sn is not None else None
        M_sp = a_sp * pd * (ls**2) if a_sp is not None else None
        M_ln = a_ln * pd * (ls**2) if a_ln is not None else None
        M_lp = a_lp * pd * (ls**2) if a_lp is not None else None

        short_dir = "X" if Lx_n <= Ly_n else "Y"
        steps.append(f"Kısa doğrultu: {short_dir}")

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

    # =========================================================
    # BALCONY logic
    # =========================================================
    def compute_balcony_per_slab(self, sid: str, bw: float) -> Tuple[dict, List[str]]:
        steps = []
        s = self.slabs[sid]
        w = s.pd * s.b
        Lx_g, Ly_g = s.size_m_gross()
        direction = "Y" if Lx_g < Ly_g else "X"
        Lg = min(Lx_g, Ly_g)
        Lnet = max(0.05, Lg - 0.5 * bw)
        
        steps.append(f"w={w:.3f}")
        steps.append(f"Lg={Lg:.3f}, Lnet={Lnet:.3f}")
        Mneg = 0.5 * w * Lnet**2
        steps.append(f"M- = {Mneg:.3f}")
        return {"dir": direction, "w": w, "L_net": Lnet, "Mneg": Mneg}, steps

    def balcony_fixed_edge_guess(self, sid: str) -> Tuple[str, List[str]]:
        steps = []
        ratios = {}
        for e in ["L", "R", "T", "B"]:
            _full, any_, ratio = self.edge_neighbor_coverage(sid, e)
            ratios[e] = ratio if any_ else 0.0
            steps.append(f"{e} ratio: {ratios[e]:.3f}")
        fixed = max(ratios.items(), key=lambda kv: kv[1])[0]
        steps.append(f"Selected fixed edge: {fixed}")
        return fixed, steps

    def neighbor_support_moment_for_edge(self, neighbor_id: str, edge: str, bw: float) -> float:
        if neighbor_id not in self.slabs: return 0.0
        k = self.slabs[neighbor_id].kind
        if k == "TWOWAY":
            r, _ = self.compute_twoway_per_slab(neighbor_id, bw)
            mxn, _ = r["Mx"]
            myn, _ = r["My"]
            if edge in ("L", "R"): return abs(mxn) if mxn else 0.0
            else: return abs(myn) if myn else 0.0
        if k == "ONEWAY":
            r, _ = self.compute_oneway_per_slab(neighbor_id, bw)
            return abs(r["Mneg_min"]) if r.get("Mneg_min") is not None else 0.0
        if k == "BALCONY":
            r, _ = self.compute_balcony_per_slab(neighbor_id, bw)
            return abs(r["Mneg"]) if r.get("Mneg") is not None else 0.0
        return 0.0

    def get_balcony_design_moment(self, sid: str, Mbal: float, bw: float) -> Tuple[float, List[str]]:
        steps = []
        fixed_edge, st = self.balcony_fixed_edge_guess(sid)
        steps.extend(st)
        
        s = self.slabs[sid]
        i0, j0, i1, j1 = s.bbox()
        neigh = set()
        # simplified neighborhood collection based on edge
        if fixed_edge == "L" and i0 > 0:
            for j in range(j0, j1 + 1):
                nb = self.cell_owner.get((i0 - 1, j))
                if nb and nb != sid: neigh.add(nb)
        elif fixed_edge == "R" and i1 < self.Nx - 1:
            for j in range(j0, j1 + 1):
                nb = self.cell_owner.get((i1 + 1, j))
                if nb and nb != sid: neigh.add(nb)
        elif fixed_edge == "T" and j0 > 0:
            for i in range(i0, i1 + 1):
                nb = self.cell_owner.get((i, j0 - 1))
                if nb and nb != sid: neigh.add(nb)
        elif fixed_edge == "B" and j1 < self.Ny - 1:
            for i in range(i0, i1 + 1):
                nb = self.cell_owner.get((i, j1 + 1))
                if nb and nb != sid: neigh.add(nb)

        if not neigh:
            steps.append("No neighbor on fixed edge.")
            return abs(Mbal), steps

        m_nb = 0.0
        for nb in neigh:
            mn = self.neighbor_support_moment_for_edge(nb, fixed_edge, bw)
            steps.append(f"Neighbor {nb} M={mn:.3f}")
            m_nb = max(m_nb, mn)
        
        Mdesign = max(abs(Mbal), m_nb)
        steps.append(f"M_design = max(|Mbal|={abs(Mbal):.3f}, neighbor_max={m_nb:.3f}) = {Mdesign:.3f}")
        return Mdesign, steps

    # =========================================================
    # Design Wrapper
    # =========================================================
    def design_main_rebar_from_M(
        self,
        M_kNm: float,
        conc: str,
        steel: str,
        h_mm: float,
        cover_mm: float,
        s_max: int,
        As_min_override: Optional[float] = None,
        label_prefix: str = "",
        d_delta_mm: float = 0.0
    ) -> Tuple[float, RebarChoice, List[str]]:
        steps = []
        d_nom = h_mm - cover_mm
        d_eff = d_nom + d_delta_mm
        if d_delta_mm != 0.0:
            steps.append(f"{label_prefix}d düzeltmesi: {d_nom:.1f} -> {d_eff:.1f}")

        As_raw, st_as = as_from_abacus_steps(M_kNm, conc, steel, h_mm, cover_mm, d_override_mm=d_eff)
        steps.extend([label_prefix + x for x in st_as])
        
        As_req = As_raw if As_raw is not None else 0.0
        d_mm = max(1.0, d_eff)
        As_min = As_min_override if As_min_override is not None else rho_min_oneway(steel) * 1000.0 * d_mm
        
        As_req2 = max(As_req, As_min)
        if As_req2 > As_req + 1e-9:
            steps.append(f"{label_prefix}As_min kontrolü: {As_req:.1f} -> {As_req2:.1f}")
        
        cand = select_rebar_min_area(As_req2, s_max, phi_min=8)
        if cand is None:
            raise ValueError(f"Donatı bulunamadı: As={As_req2:.1f}, s_max={s_max}")
        
        steps.append(f"{label_prefix}Seçim: {cand.label_with_area()}")
        return As_req2, cand, steps
