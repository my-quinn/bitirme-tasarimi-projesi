import math
from typing import List, Tuple, Optional
from slab_model import SlabSystem, Slab

class _DXFWriter:
    def __init__(self):
        self.layers = set()
        self.entities = []

    def add_layer(self, name: str):
        self.layers.add(name)

    def add_line(self, x1, y1, x2, y2, layer="0"):
        self.add_layer(layer)
        self.entities.append(("LINE", layer, (x1, y1, x2, y2)))

    def add_polyline(self, pts, layer="0", closed=False):
        self.add_layer(layer)
        self.entities.append(("POLYLINE", layer, (pts, closed)))

    def add_text(self, x, y, text, height=200.0, layer="TEXT", rotation=0.0):
        self.add_layer(layer)
        self.entities.append(("TEXT", layer, (x, y, height, text, rotation)))

    def _w(self, f, code, value):
        f.write(f"{code}\n{value}\n")

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            self._w(f, 0, "SECTION"); self._w(f, 2, "HEADER")
            self._w(f, 9, "$ACADVER"); self._w(f, 1, "AC1009")
            self._w(f, 0, "ENDSEC")

            self._w(f, 0, "SECTION"); self._w(f, 2, "TABLES")
            self._w(f, 0, "TABLE"); self._w(f, 2, "LAYER"); self._w(f, 70, len(self.layers) + 1)
            self._w(f, 0, "LAYER"); self._w(f, 2, "0"); self._w(f, 70, 0); self._w(f, 62, 7); self._w(f, 6, "CONTINUOUS")
            for ln in sorted(self.layers):
                if ln == "0": continue
                self._w(f, 0, "LAYER"); self._w(f, 2, ln); self._w(f, 70, 0); self._w(f, 62, 7); self._w(f, 6, "CONTINUOUS")
            self._w(f, 0, "ENDTAB")
            self._w(f, 0, "ENDSEC")

            self._w(f, 0, "SECTION"); self._w(f, 2, "ENTITIES")
            for ent in self.entities:
                etype, layer, data = ent
                if etype == "LINE":
                    x1, y1, x2, y2 = data
                    self._w(f, 0, "LINE"); self._w(f, 8, layer)
                    self._w(f, 10, float(x1)); self._w(f, 20, float(y1)); self._w(f, 30, 0.0)
                    self._w(f, 11, float(x2)); self._w(f, 21, float(y2)); self._w(f, 31, 0.0)
                elif etype == "POLYLINE":
                    pts, closed = data
                    self._w(f, 0, "POLYLINE"); self._w(f, 8, layer)
                    self._w(f, 66, 1); self._w(f, 70, 1 if closed else 0)
                    for (x, y) in pts:
                        self._w(f, 0, "VERTEX"); self._w(f, 8, layer)
                        self._w(f, 10, float(x)); self._w(f, 20, float(y)); self._w(f, 30, 0.0)
                    self._w(f, 0, "SEQEND")
                elif etype == "TEXT":
                    x, y, h, txt, rot = data
                    self._w(f, 0, "TEXT"); self._w(f, 8, layer)
                    self._w(f, 10, float(x)); self._w(f, 20, float(y)); self._w(f, 30, 0.0)
                    self._w(f, 40, float(h)); self._w(f, 1, txt)
                    if rot != 0.0:
                        self._w(f, 50, float(rot))
            self._w(f, 0, "ENDSEC")
            self._w(f, 0, "EOF")


# =========================================================
# Donatı Çizim Yardımcı Fonksiyonları
# =========================================================

def _pilye_polyline(x0, y0, x1, y1, d=250.0, kink="both"):
    """Pilye çubuğu çizer - kıvrım yüksekliği d ile"""
    kink = (kink or "both").lower()
    if kink not in ("start", "end", "both", "none"): kink = "both"

    if abs(y1 - y0) < 1e-6:  # Horizontal
        if x1 < x0: x0, x1 = x1, x0; flip = True
        else: flip = False
        
        L = abs(x1 - x0)
        if L < 1e-6 or kink == "none": return [(x0, y0), (x1, y0)]
        
        dx = d / math.sqrt(2); dy = d / math.sqrt(2)
        want_start = kink in ("start", "both")
        want_end = kink in ("end", "both")
        if flip: want_start, want_end = want_end, want_start
        
        pts = [(x0, y0)]
        if want_start: pts.extend([(x0 + L/4.0, y0), (x0 + L/4.0 + dx, y0 + dy)])
        if want_end: pts.extend([(x1 - L/4.0 - dx, y0 + dy), (x1 - L/4.0, y0)])
        pts.append((x1, y0))
        return pts
        
    else:  # Vertical
        if y1 < y0: y0, y1 = y1, y0; flip = True
        else: flip = False
        
        L = abs(y1 - y0)
        if L < 1e-6 or kink == "none": return [(x0, y0), (x0, y1)]
        
        dx = d / math.sqrt(2); dy = d / math.sqrt(2)
        want_start = kink in ("start", "both")
        want_end = kink in ("end", "both")
        if flip: want_start, want_end = want_end, want_start
        
        pts = [(x0, y0)]
        if want_start: pts.extend([(x0, y0 + L/4.0), (x0 + dx, y0 + L/4.0 + dy)])
        if want_end: pts.extend([(x0 + dx, y1 - L/4.0 - dy), (x0, y1 - L/4.0)])
        pts.append((x0, y1))
        return pts


def _draw_dimension_line(w: _DXFWriter, x0, y0, x1, y1, label: str, offset=150.0, layer="DIM"):
    """Ölçü çizgisi çizer (çizgi + etiket)"""
    # Ana çizgi
    w.add_line(x0, y0, x1, y1, layer=layer)
    
    # Uç çizgiler (tick marks)
    if abs(y1 - y0) < 1e-6:  # Horizontal
        w.add_line(x0, y0 - 50, x0, y0 + 50, layer=layer)
        w.add_line(x1, y1 - 50, x1, y1 + 50, layer=layer)
        mid_x = (x0 + x1) / 2
        w.add_text(mid_x, y0 + offset, label, height=120, layer=layer)
    else:  # Vertical
        w.add_line(x0 - 50, y0, x0 + 50, y0, layer=layer)
        w.add_line(x1 - 50, y1, x1 + 50, y1, layer=layer)
        mid_y = (y0 + y1) / 2
        w.add_text(x0 + offset, mid_y, label, height=120, layer=layer, rotation=90)


def _draw_support_rebar_horizontal(w: _DXFWriter, x0, y0, x1, y1, count: int, layer: str, label: str = None):
    """Yatay mesnet donatısı çizer (birden fazla çizgi ile gösterir)"""
    if count < 1: count = 1
    if count > 5: count = 5  # Görsel için max 5 çizgi
    
    dy = (y1 - y0) / (count + 1)
    for i in range(1, count + 1):
        y = y0 + i * dy
        w.add_line(x0, y, x1, y, layer=layer)
    
    if label:
        mid_y = (y0 + y1) / 2
        w.add_text(x0 - 50, mid_y, label, height=100, layer="TEXT", rotation=90)


def _draw_support_rebar_vertical(w: _DXFWriter, x0, y0, x1, y1, count: int, layer: str, label: str = None):
    """Dikey mesnet donatısı çizer (birden fazla çizgi ile gösterir)"""
    if count < 1: count = 1
    if count > 5: count = 5  # Görsel için max 5 çizgi
    
    dx = (x1 - x0) / (count + 1)
    for i in range(1, count + 1):
        x = x0 + i * dx
        w.add_line(x, y0, x, y1, layer=layer)
    
    if label:
        mid_x = (x0 + x1) / 2
        w.add_text(mid_x, y1 + 50, label, height=100, layer="TEXT")


def _draw_oneway_reinforcement_detail(
    w: _DXFWriter,
    sid: str,
    s: Slab,
    dcache: dict,
    x0: float, y0: float, x1: float, y1: float,
    bw_mm: float
):
    """
    Tek doğrultulu döşeme için detaylı donatı krokisi çizer.
    
    Referans görüntüdeki gibi:
    - Ana donatı (düz + pilye): kısa kenara paralel
    - Dağıtma donatısı: uzun kenara paralel, As/5
    - Boyuna kenar mesnet: süreksiz kısa kenarlarda, minAs
    - Boyuna iç mesnet: sürekli kısa kenarlarda, 0.6×As
    - Mesnet ek donatısı: sürekli uzun kenarlarda
    """
    cover = float(dcache.get("cover_mm", 25.0))
    auto_dir = dcache.get("auto_dir", "X")
    choices = dcache.get("choices", {})
    edge_cont = dcache.get("edge_continuity", {})
    
    # İç sınırlar (pas payı düşülmüş)
    ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
    if ix1 <= ix0 or iy1 <= iy0:
        return
    
    Lx = ix1 - ix0  # mm
    Ly = iy1 - iy0  # mm
    
    # Donatı seçimleri
    ch_duz = choices.get("duz")
    ch_pilye = choices.get("pilye")
    ch_dist = choices.get("dist")
    ch_kenar_start = choices.get("kenar_mesnet_start")
    ch_kenar_end = choices.get("kenar_mesnet_end")
    ch_ic_start = choices.get("ic_mesnet_start")
    ch_ic_end = choices.get("ic_mesnet_end")
    ch_ek_start = choices.get("mesnet_ek_start")
    ch_ek_end = choices.get("mesnet_ek_end")
    
    # Kenar süreklilik durumları
    uzun_start_cont = edge_cont.get("uzun_start", False)
    uzun_end_cont = edge_cont.get("uzun_end", False)
    kisa_start_cont = edge_cont.get("kisa_start", False)
    kisa_end_cont = edge_cont.get("kisa_end", False)
    
    # Orta noktalar
    midx = (ix0 + ix1) / 2.0
    midy = (iy0 + iy1) / 2.0
    
    # =========================================================
    # Ana Donatı Doğrultusu: Kısa kenara paralel
    # =========================================================
    if auto_dir == "X":
        # Ana donatı X yönünde (yatay), kısa kenar = L/R
        # Uzun kenar = T/B (Y yönünde)
        Ln_short = Lx  # Kısa açıklık (X yönünde)
        Ln_long = Ly   # Uzun açıklık (Y yönünde)
        
        # --- 1. ANA DONATI (DÜZ + PİLYE) - Yatay ---
        # Birkaç temsili çizgi çiz
        rebar_count = 3
        spacing = Ly / (rebar_count + 1)
        
        for i in range(1, rebar_count + 1):
            y = iy0 + i * spacing
            # Düz demir - alt, tam açıklık
            w.add_line(ix0, y - 30, ix1, y - 30, layer="REB_DUZ")
            # Pilye demir - pilye yaparak
            pts = _pilye_polyline(ix0, y, ix1, y, d=200.0, kink="both")
            w.add_polyline(pts, layer="REB_PILYE")
        
        # Etiketler
        if ch_duz:
            w.add_text(ix0 + 100, midy - 150, f"düz {ch_duz.label()}", height=100, layer="TEXT")
        if ch_pilye:
            w.add_text(ix0 + 100, midy + 100, f"pilye {ch_pilye.label()}", height=100, layer="TEXT")
        
        # --- 2. DAĞITMA DONATISI - Dikey (uzun kenara paralel) ---
        dist_count = 3
        dx_dist = Lx / (dist_count + 1)
        for i in range(1, dist_count + 1):
            x = ix0 + i * dx_dist
            w.add_line(x, iy0, x, iy1, layer="REB_DIST")
        
        if ch_dist:
            w.add_text(midx + 50, iy1 - 150, f"dağıtma {ch_dist.label()}", height=100, layer="TEXT", rotation=90)
            w.add_text(midx - 200, iy1 - 150, f"As/5", height=80, layer="TEXT", rotation=90)
        
        # --- 3. BOYUNA KENAR MESNET DONATISI (Süreksiz Kısa Kenar) ---
        # Kısa kenar = L (ix0) ve R (ix1), donatı Y yönünde (dikey)
        
        # Sol kenar (START) - süreksiz ise
        if ch_kenar_start and not kisa_start_cont:
            ext = Ln_short / 4.0  # ln/4 uzunluk
            _draw_support_rebar_vertical(w, ix0, iy0, ix0 + ext, iy1, 2, "REB_KENAR", ch_kenar_start.label())
            _draw_dimension_line(w, ix0, iy1 + 80, ix0 + ext, iy1 + 80, "ln1/4", offset=40, layer="DIM")
            w.add_text(ix0 + 20, midy, "boyuna kenar\nmesnet donatısı\nminAs", height=70, layer="TEXT", rotation=90)
        
        # Sağ kenar (END) - süreksiz ise
        if ch_kenar_end and not kisa_end_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_vertical(w, ix1 - ext, iy0, ix1, iy1, 2, "REB_KENAR", ch_kenar_end.label())
            _draw_dimension_line(w, ix1 - ext, iy1 + 80, ix1, iy1 + 80, "ln1/4", offset=40, layer="DIM")
        
        # --- 4. BOYUNA İÇ MESNET DONATISI (Sürekli Kısa Kenar) ---
        # Kısa kenar = L (ix0) ve R (ix1), donatı Y yönünde (dikey)
        
        # Sol kenar (START) - sürekli ise
        if ch_ic_start and kisa_start_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_vertical(w, ix0, iy0, ix0 + ext, iy1, 2, "REB_IC_MESNET", ch_ic_start.label())
            _draw_dimension_line(w, ix0, iy1 + 80, ix0 + ext, iy1 + 80, "ln1/4", offset=40, layer="DIM")
            w.add_text(ix0 + 20, midy, "boyuna iç mesnet\ndonatısı 0.6×As", height=70, layer="TEXT", rotation=90)
        
        # Sağ kenar (END) - sürekli ise
        if ch_ic_end and kisa_end_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_vertical(w, ix1 - ext, iy0, ix1, iy1, 2, "REB_IC_MESNET", ch_ic_end.label())
            _draw_dimension_line(w, ix1 - ext, iy1 + 80, ix1, iy1 + 80, "ln2/4", offset=40, layer="DIM")
        
        # --- 5. MESNET EK DONATISI (Sürekli Uzun Kenar) ---
        # Uzun kenar = T (iy0) ve B (iy1), donatı X yönünde (yatay)
        
        # Üst kenar (START) - sürekli ise
        if ch_ek_start and uzun_start_cont:
            ext = Ln_long / 5.0  # ln/5 uzunluk
            _draw_support_rebar_horizontal(w, ix0, iy0, ix1, iy0 + ext, 2, "REB_EK_MESNET", ch_ek_start.label())
            _draw_dimension_line(w, ix1 + 80, iy0, ix1 + 80, iy0 + ext, "ln1/5", offset=40, layer="DIM")
            w.add_text(midx, iy0 + 50, "mesnet ek\ndonatısı", height=70, layer="TEXT")
        
        # Alt kenar (END) - sürekli ise
        if ch_ek_end and uzun_end_cont:
            ext = Ln_long / 5.0
            _draw_support_rebar_horizontal(w, ix0, iy1 - ext, ix1, iy1, 2, "REB_EK_MESNET", ch_ek_end.label())
            _draw_dimension_line(w, ix1 + 80, iy1 - ext, ix1 + 80, iy1, "ln2/5", offset=40, layer="DIM")
    
    else:  # auto_dir == "Y"
        # Ana donatı Y yönünde (dikey), kısa kenar = T/B
        # Uzun kenar = L/R (X yönünde)
        Ln_short = Ly  # Kısa açıklık (Y yönünde)
        Ln_long = Lx   # Uzun açıklık (X yönünde)
        
        # --- 1. ANA DONATI (DÜZ + PİLYE) - Dikey ---
        rebar_count = 3
        spacing = Lx / (rebar_count + 1)
        
        for i in range(1, rebar_count + 1):
            x = ix0 + i * spacing
            # Düz demir
            w.add_line(x - 30, iy0, x - 30, iy1, layer="REB_DUZ")
            # Pilye demir
            pts = _pilye_polyline(x, iy0, x, iy1, d=200.0, kink="both")
            w.add_polyline(pts, layer="REB_PILYE")
        
        if ch_duz:
            w.add_text(midx - 150, iy0 + 100, f"düz {ch_duz.label()}", height=100, layer="TEXT", rotation=90)
        if ch_pilye:
            w.add_text(midx + 100, iy0 + 100, f"pilye {ch_pilye.label()}", height=100, layer="TEXT", rotation=90)
        
        # --- 2. DAĞITMA DONATISI - Yatay (uzun kenara paralel) ---
        dist_count = 3
        dy_dist = Ly / (dist_count + 1)
        for i in range(1, dist_count + 1):
            y = iy0 + i * dy_dist
            w.add_line(ix0, y, ix1, y, layer="REB_DIST")
        
        if ch_dist:
            w.add_text(ix0 + 100, midy + 50, f"dağıtma {ch_dist.label()}", height=100, layer="TEXT")
            w.add_text(ix0 + 100, midy - 100, f"As/5", height=80, layer="TEXT")
        
        # --- 3. BOYUNA KENAR MESNET DONATISI (Süreksiz Kısa Kenar) ---
        # Kısa kenar = T (iy0) ve B (iy1), donatı X yönünde (yatay)
        
        # Üst kenar (START) - süreksiz ise
        if ch_kenar_start and not kisa_start_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_horizontal(w, ix0, iy0, ix1, iy0 + ext, 2, "REB_KENAR", ch_kenar_start.label())
            _draw_dimension_line(w, ix1 + 80, iy0, ix1 + 80, iy0 + ext, "ln1/4", offset=40, layer="DIM")
            w.add_text(midx, iy0 + 20, "boyuna kenar\nmesnet donatısı\nminAs", height=70, layer="TEXT")
        
        # Alt kenar (END) - süreksiz ise
        if ch_kenar_end and not kisa_end_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_horizontal(w, ix0, iy1 - ext, ix1, iy1, 2, "REB_KENAR", ch_kenar_end.label())
            _draw_dimension_line(w, ix1 + 80, iy1 - ext, ix1 + 80, iy1, "ln2/4", offset=40, layer="DIM")
        
        # --- 4. BOYUNA İÇ MESNET DONATISI (Sürekli Kısa Kenar) ---
        # Kısa kenar = T (iy0) ve B (iy1), donatı X yönünde (yatay)
        
        # Üst kenar (START) - sürekli ise
        if ch_ic_start and kisa_start_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_horizontal(w, ix0, iy0, ix1, iy0 + ext, 2, "REB_IC_MESNET", ch_ic_start.label())
            _draw_dimension_line(w, ix1 + 80, iy0, ix1 + 80, iy0 + ext, "ln1/4", offset=40, layer="DIM")
            w.add_text(midx, iy0 + 20, "boyuna iç mesnet\ndonatısı 0.6×As", height=70, layer="TEXT")
        
        # Alt kenar (END) - sürekli ise
        if ch_ic_end and kisa_end_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_horizontal(w, ix0, iy1 - ext, ix1, iy1, 2, "REB_IC_MESNET", ch_ic_end.label())
            _draw_dimension_line(w, ix1 + 80, iy1 - ext, ix1 + 80, iy1, "ln2/4", offset=40, layer="DIM")
        
        # --- 5. MESNET EK DONATISI (Sürekli Uzun Kenar) ---
        # Uzun kenar = L (ix0) ve R (ix1), donatı Y yönünde (dikey)
        
        # Sol kenar (START) - sürekli ise
        if ch_ek_start and uzun_start_cont:
            ext = Ln_long / 5.0
            _draw_support_rebar_vertical(w, ix0, iy0, ix0 + ext, iy1, 2, "REB_EK_MESNET", ch_ek_start.label())
            _draw_dimension_line(w, ix0, iy1 + 80, ix0 + ext, iy1 + 80, "ln1/5", offset=40, layer="DIM")
            w.add_text(ix0 + 20, midy, "mesnet ek\ndonatısı", height=70, layer="TEXT", rotation=90)
        
        # Sağ kenar (END) - sürekli ise
        if ch_ek_end and uzun_end_cont:
            ext = Ln_long / 5.0
            _draw_support_rebar_vertical(w, ix1 - ext, iy0, ix1, iy1, 2, "REB_EK_MESNET", ch_ek_end.label())
            _draw_dimension_line(w, ix1 - ext, iy1 + 80, ix1, iy1 + 80, "ln2/5", offset=40, layer="DIM")
    
    # Döşeme ID'si
    w.add_text(midx, midy, sid, height=150, layer="TEXT")


def export_to_dxf(system: SlabSystem, filename: str, design_cache: dict, bw_val: float):
    w = _DXFWriter()
    
    # Katmanları ekle
    layers = [
        "SLAB_EDGE", "BEAM", 
        "REB_MAIN_X", "REB_MAIN_Y", "REB_DIST", "REB_SUPPORT",
        "REB_DUZ", "REB_PILYE", "REB_KENAR", "REB_IC_MESNET", "REB_EK_MESNET",
        "TEXT", "DIM"
    ]
    for ln in layers:
        w.add_layer(ln)

    gdx, gdy = 0.0, 0.0
    if system.slabs:
        s0 = list(system.slabs.values())[0]
        gdx, gdy = s0.dx, s0.dy
    else:
        gdx, gdy = 0.25, 0.25  # fallback

    bw_mm = bw_val * 1000.0
    half = bw_mm / 2.0

    # BEAMS - Kiriş çizimi
    for (i, j) in system.V_beam:
        x = (i + 1) * gdx * 1000.0
        y0 = j * gdy * 1000.0
        y1 = (j + 1) * gdy * 1000.0
        w.add_polyline([(x - half, y0), (x + half, y0), (x + half, y1), (x - half, y1)], layer="BEAM", closed=True)
    
    for (i, j) in system.H_beam:
        y = (j + 1) * gdy * 1000.0
        x0 = i * gdx * 1000.0
        x1 = (i + 1) * gdx * 1000.0
        w.add_polyline([(x0, y - half), (x1, y - half), (x1, y + half), (x0, y + half)], layer="BEAM", closed=True)

    # SLABS - Döşeme çizimi
    for sid, s in system.slabs.items():
        # Panel sınırları
        x0 = s.i0 * s.dx * 1000.0
        y0 = s.j0 * s.dy * 1000.0
        x1 = (s.i1 + 1) * s.dx * 1000.0
        y1 = (s.j1 + 1) * s.dy * 1000.0
        
        # Kiriş için düzeltme
        if system.slab_edge_has_beam(sid, "LEFT"): x0 += half
        if system.slab_edge_has_beam(sid, "RIGHT"): x1 -= half
        if system.slab_edge_has_beam(sid, "TOP"): y0 += half
        if system.slab_edge_has_beam(sid, "BOTTOM"): y1 -= half
        
        # Döşeme sınır çizgisi
        w.add_polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer="SLAB_EDGE", closed=True)

        dcache = design_cache.get(sid)
        if not dcache:
            w.add_text((x0+x1)/2, (y0+y1)/2, sid, height=300.0, layer="TEXT")
            continue

        kind = dcache.get("kind")
        
        if kind == "ONEWAY":
            # Detaylı tek doğrultulu döşeme çizimi
            _draw_oneway_reinforcement_detail(w, sid, s, dcache, x0, y0, x1, y1, bw_mm)
        
        elif kind == "TWOWAY":
            # İki doğrultulu döşeme - mevcut basit çizim
            cover = float(dcache.get("cover_mm", 25.0))
            ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
            if ix1 <= ix0 or iy1 <= iy0: continue
            
            midx = (ix0 + ix1) / 2.0
            midy = (iy0 + iy1) / 2.0
            
            chx = dcache["choices"].get("x_span")
            chy = dcache["choices"].get("y_span")
            
            if chx:
                ptsx = _pilye_polyline(ix0, midy, ix1, midy, d=250.0, kink='both')
                w.add_polyline(ptsx, layer="REB_MAIN_X")
                w.add_text(ix0, midy + 250, f"X {chx.label()}", height=280, layer="TEXT")
            
            if chy:
                ptsy = _pilye_polyline(midx, iy0, midx, iy1, d=250.0, kink='both')
                w.add_polyline(ptsy, layer="REB_MAIN_Y")
                w.add_text(midx + 200, iy1 + 200, f"Y {chy.label()}", height=280, layer="TEXT")
            
            w.add_text(midx, midy, sid, height=300, layer="TEXT")

        elif kind == "BALCONY":
            # Balkon - mevcut basit çizim
            cover = float(dcache.get("cover_mm", 25.0))
            ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
            if ix1 <= ix0 or iy1 <= iy0: continue
            
            midx = (ix0 + ix1) / 2.0
            midy = (iy0 + iy1) / 2.0
            
            ch_main = dcache["choices"].get("main")
            ch_dist = dcache["choices"].get("dist")
            fixed = dcache.get("fixed_edge", "L")
            
            if ch_main:
                if fixed in ("L", "R"):
                    kink = "start" if fixed == "L" else "end"
                    pts = _pilye_polyline(ix0, midy, ix1, midy, d=250.0, kink=kink)
                    w.add_polyline(pts, layer="REB_SUPPORT")
                    w.add_text(ix0, midy + 250, f"ana {ch_main.label()}", height=280, layer="TEXT")
                    w.add_line(midx, iy0, midx, iy1, layer="REB_DIST")
                else:
                    kink = "end" if fixed == "T" else "start"
                    pts = _pilye_polyline(midx, iy0, midx, iy1, d=250.0, kink=kink)
                    w.add_polyline(pts, layer="REB_SUPPORT")
                    w.add_text(midx + 200, iy0, f"ana {ch_main.label()}", height=280, layer="TEXT")
                    w.add_line(ix0, midy, ix1, midy, layer="REB_DIST")
            
            w.add_text(midx, midy, sid, height=300, layer="TEXT")
        
        else:
            # Bilinmeyen tip - sadece ID yaz
            w.add_text((x0+x1)/2, (y0+y1)/2, sid, height=300.0, layer="TEXT")

    w.save(filename)
