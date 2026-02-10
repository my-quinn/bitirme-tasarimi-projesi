import math
import ezdxf
from typing import List, Tuple, Optional
from slab_model import SlabSystem, Slab

class _DXFWriter:
    """ezdxf kütüphanesi kullanarak DXF dosyası oluşturan sınıf."""
    
    def __init__(self):
        self.doc = ezdxf.new('R2010')  # AutoCAD 2010 formatı
        self.msp = self.doc.modelspace()
        self.layers_created = set()

    def add_layer(self, name: str):
        if name not in self.layers_created and name != "0":
            self.doc.layers.add(name)
            self.layers_created.add(name)

    def add_line(self, x1, y1, x2, y2, layer="0"):
        self.add_layer(layer)
        self.msp.add_line((x1, y1), (x2, y2), dxfattribs={'layer': layer})

    def add_polyline(self, pts, layer="0", closed=False):
        self.add_layer(layer)
        self.msp.add_lwpolyline(pts, dxfattribs={'layer': layer}, close=closed)

    def add_text(self, x, y, text, height=200.0, layer="TEXT", rotation=0.0, center=False):
        self.add_layer(layer)
        txt = self.msp.add_text(text, dxfattribs={
            'layer': layer,
            'height': height,
            'rotation': rotation
        })
        if center:
            txt.set_placement((x, y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
        else:
            txt.set_placement((x, y))

    def save(self, path: str):
        self.doc.saveas(path)


# =========================================================
# Donatı Çizim Yardımcı Fonksiyonları
# =========================================================

def _pilye_polyline(x0, y0, x1, y1, d=250.0, kink="both", hook_len=100.0, beam_ext=0.0):
    """
    Pilye çubuğu çizer:
    - Üst seviyede Ln/5 + beam_ext kadar düz gider (beam_ext kısmı kirişin içinde)
    - Ln/5 noktasında 45 derece kırılır
    - Alt seviyede düz devam eder
    - Uçlarda kiriş içine doğru kanca yapar
    
    kink parametresi:
    - "start": sol/alt tarafta kırılma
    - "end": sağ/üst tarafta kırılma
    - "both": her iki tarafta kırılma
    - "none": düz çubuk
    
    d: pilye kırılma yüksekliği (45 derece için dx=dy=d)
    hook_len: kanca uzunluğu (kiriş içine doğru)
    beam_ext: kiriş içine uzanma mesafesi (kanca kırılma noktası kirişin içinde olur)
    """
    kink = (kink or "both").lower()
    if kink not in ("start", "end", "both", "none"): kink = "both"

    if abs(y1 - y0) < 1e-6:  # Horizontal bar (X yönünde)
        if x1 < x0: x0, x1 = x1, x0; flip = True
        else: flip = False
        
        L = abs(x1 - x0)
        if L < 1e-6 or kink == "none": return [(x0, y0), (x1, y0)]
        
        want_start = kink in ("start", "both")
        want_end = kink in ("end", "both")
        if flip: want_start, want_end = want_end, want_start
        
        # Ln/5 mesafesi (pilye kırılma noktası - kirişten uzaklık)
        Ln5 = L / 5.0
        
        pts = []
        
        if want_start:
            # Sol taraf: kanca kirişin içinde, beam_ext kadar sola uzanır
            pts.append((x0 - beam_ext, y0 - hook_len))  # Kanca ucu (kiriş içinde)
            pts.append((x0 - beam_ext, y0))              # Kanca dönüşü (kiriş içinde)
            pts.append((x0 + Ln5 - d, y0))               # Üstte düz git
            pts.append((x0 + Ln5, y0 - d))               # 45 derece aşağı kırıl
        else:
            pts.append((x0, y0 - d))              # Altta düz başla
        
        if want_end:
            # Sağ taraf: altta düz git, yukarı kırıl, beam_ext kadar sağa uzanır
            pts.append((x1 - Ln5, y0 - d))               # Altta düz kısım sonu
            pts.append((x1 - Ln5 + d, y0))               # 45 derece yukarı kırıl
            pts.append((x1 + beam_ext, y0))               # Üstte düz bit (kiriş içine)
            pts.append((x1 + beam_ext, y0 - hook_len))   # Kanca ucu (kiriş içinde)
        else:
            pts.append((x1, y0 - d))              # Altta düz bit
        
        return pts
        
    else:  # Vertical bar (Y yönünde)
        if y1 < y0: y0, y1 = y1, y0; flip = True
        else: flip = False
        
        L = abs(y1 - y0)
        if L < 1e-6 or kink == "none": return [(x0, y0), (x0, y1)]
        
        want_start = kink in ("start", "both")
        want_end = kink in ("end", "both")
        if flip: want_start, want_end = want_end, want_start
        
        # Ln/5 mesafesi (pilye kırılma noktası - kirişten uzaklık)
        Ln5 = L / 5.0
        
        pts = []
        
        if want_start:
            # Alt taraf: kanca kirişin içinde, beam_ext kadar aşağı uzanır
            pts.append((x0 + hook_len, y0 - beam_ext))  # Kanca ucu (kiriş içinde)
            pts.append((x0, y0 - beam_ext))              # Kanca dönüşü (kiriş içinde)
            pts.append((x0, y0 + Ln5 - d))               # Solda düz git
            pts.append((x0 + d, y0 + Ln5))               # 45 derece sağa kırıl
        else:
            pts.append((x0 + d, y0))              # Sağda düz başla
        
        if want_end:
            # Üst taraf: sağda düz git, sola kırıl, beam_ext kadar yukarı uzanır
            pts.append((x0 + d, y1 - Ln5))               # Sağda düz kısım sonu
            pts.append((x0, y1 - Ln5 + d))               # 45 derece sola kırıl
            pts.append((x0, y1 + beam_ext))               # Solda düz bit (kiriş içine)
            pts.append((x0 + hook_len, y1 + beam_ext))   # Kanca ucu (kiriş içinde)
        else:
            pts.append((x0 + d, y1))              # Sağda düz bit
        
        return pts


def _draw_straight_hit_polyline(x0, y0, x1, y1, ext, hook):
    """
    Düz donatı için kancalı çizim (Plan görünüşte sembolik).
    - Kiriş içine 'ext' kadar girer.
    - Sonra 90 derece 'hook' kadar kırılır.
    - Yön: 'Legs down' (negatif yön).
    """
    if abs(y1 - y0) < 1e-6: # Horizontal (X yönünde)
        if x1 < x0: x0, x1 = x1, x0
        # Legs down -> -Y yönünde kanca
        return [
            (x0 - ext, y0 - hook),
            (x0 - ext, y0),
            (x1 + ext, y0),
            (x1 + ext, y0 - hook)
        ]
    else: # Vertical (Y yönünde)
        if y1 < y0: y0, y1 = y1, y0
        # Legs down -> -X yönünde kanca (veya +X? Pilye çizimine uyumlu olsun)
        # Pilye vb. genelde sağa/sola kırılır. 
        # Referans "rotated 180 degrees" -> horizontal için bariz "aşağı".
        # Vertical için "negatif X" (sola) seçelim.
        return [
            (x0 - hook, y0 - ext),
            (x0, y0 - ext),
            (x0, y1 + ext),
            (x0 - hook, y1 + ext)
        ]



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


def _draw_support_rebar_horizontal(w: _DXFWriter, x0, y0, x1, y1, count: int, layer: str, label: str = None, 
                                   hook_start=False, hook_end=False, hook_len=100.0):
    """
    Yatay mesnet donatısı çizer (birden fazla çizgi ile gösterir).
    hook_start: Sol uçta kanca (aşağı doğru)
    hook_end: Sağ uçta kanca (aşağı doğru)
    """
    if count < 1: count = 1
    if count > 5: count = 5
    
    dy = (y1 - y0) / (count + 1)
    
    for i in range(1, count + 1):
        y = y0 + i * dy
        pts = []
        if hook_start:
            pts.append((x0, y - hook_len))
            pts.append((x0, y))
        else:
            pts.append((x0, y))
            
        if hook_end:
            pts.append((x1, y))
            pts.append((x1, y - hook_len))
        else:
            pts.append((x1, y))
            
        w.add_polyline(pts, layer=layer)
    
    if label:
        mid_y = (y0 + y1) / 2
        w.add_text(x0 - 50, mid_y, label, height=100, layer="TEXT", rotation=90)


def _draw_support_rebar_vertical(w: _DXFWriter, x0, y0, x1, y1, count: int, layer: str, label: str = None,
                                 hook_start=False, hook_end=False, hook_len=100.0):
    """
    Dikey mesnet donatısı çizer (birden fazla çizgi ile gösterir).
    hook_start: Üst uçta kanca (sola/ters yöne doğru - kullanıcı isteğine göre ayarlanabilir, şimdilik sol)
    hook_end: Alt uçta kanca (sola/ters yöne doğru)
    """
    if count < 1: count = 1
    if count > 5: count = 5
    
    dx = (x1 - x0) / (count + 1)
    
    for i in range(1, count + 1):
        x = x0 + i * dx
        pts = []
        # Dikeyde "start" üst (küçük y?), "end" alt (büyük y?)
        # Parametreler y0 (üst), y1 (alt) varsayımıyla:
        
        if hook_start:
            pts.append((x - hook_len, y0)) # Sola kıvrık
            pts.append((x, y0))
        else:
            pts.append((x, y0))
            
        if hook_end:
            pts.append((x, y1))
            pts.append((x - hook_len, y1)) # Sola kıvrık
        else:
            pts.append((x, y1))
            
        w.add_polyline(pts, layer=layer)
    
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
        # auto_dir == "X" → Lx < Ly → X yönü kısa
        # Kısa kenar = L/R (sol/sağ, Y eksenine paralel kenarlar)
        # Ana donatı kısa kenara paralel → Y yönünde (dikey)
        # Dağıtma donatısı uzun kenara paralel → X yönünde (yatay)
        # Uzun kenar = T/B (üst/alt, X eksenine paralel kenarlar)
        Ln_short = Lx  # Kısa açıklık
        Ln_long = Ly   # Uzun açıklık
        
        # --- 1. ANA DONATI (DÜZ + PİLYE) - Dikey (kısa kenara paralel) ---
        rebar_count = 3
        spacing = Lx / (rebar_count + 1)
        
        # Düz-pilye arası offset (aralık değeri kadar)
        rebar_offset = ch_duz.s_mm if ch_duz else (ch_pilye.s_mm if ch_pilye else 60)
        
        for i in range(1, rebar_count + 1):
            x = ix0 + i * spacing
            # Düz demir
            pts_duz = _draw_straight_hit_polyline(x - rebar_offset, iy0, x - rebar_offset, iy1, bw_mm, bw_mm)
            w.add_polyline(pts_duz, layer="REB_DUZ")
            # Pilye demir
            pts = _pilye_polyline(x + rebar_offset, iy0, x + rebar_offset, iy1, d=200.0, kink="both", hook_len=bw_mm, beam_ext=bw_mm)
            w.add_polyline(pts, layer="REB_PILYE")
        
        # Etiketler - orta çubuğun tam ortasında, 10mm sağında
        if ch_duz:
            w.add_text(midx - rebar_offset + 10, midy, f"düz {ch_duz.label()}", height=100, layer="TEXT", rotation=90, center=True)
        if ch_pilye:
            w.add_text(midx + rebar_offset + 10, midy, f"pilye {ch_pilye.label()}", height=100, layer="TEXT", rotation=90, center=True)
        
        # --- 2. DAĞITMA DONATISI - Yatay (uzun kenara paralel) ---
        dist_count = 3
        dy_dist = Ly / (dist_count + 1)
        hook_ext = bw_mm - 30.0
        
        for i in range(1, dist_count + 1):
            y = iy0 + i * dy_dist
            pts = []
            
            # Sol taraf (Check continuity)
            if not kisa_start_cont:
                # Discontinuous: Hook at start (inside beam)
                d_start = x0 - hook_ext
                pts.append((d_start, y - hook_ext)) # Kanca ucu (kiriş içinde, aşağı doğru)
                pts.append((d_start, y))            # Kanca dirsek
            else:
                # Continuous: Start at inner edge (no hook)
                d_start = ix0 # Use slab edge
                pts.append((d_start, y))
            
            # Sağ taraf (Check continuity)
            if not kisa_end_cont:
                # Discontinuous: Hook at end (inside beam)
                d_end = x1 + hook_ext
                pts.append((d_end, y))              # Dirsek
                pts.append((d_end, y - hook_ext))   # Kanca ucu
            else:
                # Continuous: End at inner edge (no hook)
                d_end = ix1 # Use slab edge
                pts.append((d_end, y))
                
            w.add_polyline(pts, layer="REB_DIST")
        
        if ch_dist:
            w.add_text(midx, midy + 10, f"dağıtma {ch_dist.label()}", height=100, layer="TEXT", center=True)
            w.add_text(midx, midy - 100, f"As/5", height=80, layer="TEXT", center=True)
        
        # --- 3. BOYUNA KENAR MESNET DONATISI (Süreksiz Kısa Kenar) ---
        # Kısa kenar = L (ix0) ve R (ix1), donatı uzun kenara paralel → X yönünde (yatay)
        
        # Sol kenar (START) - süreksiz ise
        if ch_kenar_start and not kisa_start_cont:
            ext = Ln_short / 4.0  # ln/4 uzunluk
            # Sol taraf mesnet (kiriş): Kanca kirişin içinde bitmeli.
            # Döşeme kenarı: x0. Kanca kırımı x0 - (bw-30) de olacak.
            hook_x = x0 - hook_ext
            end_x = ix0 + ext
            
            _draw_support_rebar_horizontal(w, hook_x, iy0, end_x, iy1, 2, "REB_KENAR", ch_kenar_start.label(),
                                           hook_start=True, hook_len=hook_ext)
            
            _draw_dimension_line(w, ix0, iy1 + 80, end_x, iy1 + 80, "ln1/4", offset=40, layer="DIM")
            w.add_text(ix0 + ext/2, midy + 10, "boyuna kenar mesnet minAs", height=70, layer="TEXT", center=True)
        
        # Sağ kenar (END) - süreksiz ise
        if ch_kenar_end and not kisa_end_cont:
            ext = Ln_short / 4.0
            # Sağ taraf mesnet
            start_x = ix1 - ext
            hook_x = x1 + hook_ext
            
            _draw_support_rebar_horizontal(w, start_x, iy0, hook_x, iy1, 2, "REB_KENAR", ch_kenar_end.label(),
                                           hook_end=True, hook_len=hook_ext)
            
            _draw_dimension_line(w, start_x, iy1 + 80, ix1, iy1 + 80, "ln1/4", offset=40, layer="DIM")
        
        # --- 4. BOYUNA İÇ MESNET DONATISI (Sürekli Kısa Kenar) ---
        # Kısa kenar = L (ix0) ve R (ix1), donatı uzun kenara paralel → X yönünde (yatay)
        # İç mesnetlerde kanca istenmedi, sadece "sürekli" olduğu için düz geçiş varsayılır veya kanca gerekmez.
        # "boyuna kenar mesnet donatısının kancasını çiz" dendi. İç mesnet için özel bir kanca isteği yok.
        # Mevcut düz çizgi yeterli.
        
        # Sol kenar (START) - sürekli ise
        if ch_ic_start and kisa_start_cont:
            ext = Ln_short / 4.0
            # İç mesnet, düz devam eder. Ancak çizim sınırlarını x0 yapalım ki tam birleşsin.
            _draw_support_rebar_horizontal(w, x0, iy0, ix0 + ext, iy1, 2, "REB_IC_MESNET", ch_ic_start.label())
            _draw_dimension_line(w, ix0, iy1 + 80, ix0 + ext, iy1 + 80, "ln1/4", offset=40, layer="DIM")
            w.add_text(ix0 + ext/2, midy + 10, "boyuna iç mesnet 0.6×As", height=70, layer="TEXT", center=True)
        
        # Sağ kenar (END) - sürekli ise
        if ch_ic_end and kisa_end_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_horizontal(w, ix1 - ext, iy0, x1, iy1, 2, "REB_IC_MESNET", ch_ic_end.label())
            _draw_dimension_line(w, ix1 - ext, iy1 + 80, ix1, iy1 + 80, "ln2/4", offset=40, layer="DIM")
        
        # --- 5. MESNET EK DONATISI (Sürekli Uzun Kenar) ---
        # Uzun kenar = T (iy0) ve B (iy1), donatı kısa kenara paralel → Y yönünde (dikey)
        
        # Üst kenar (START) - sürekli ise
        if ch_ek_start and uzun_start_cont:
            L5 = Ln_long / 5.0
            L10 = Ln_long / 10.0
            d_crank = 200.0
            half = bw_mm / 2.0
            offset_val = 800.0  # Offset to clear overlap
            
            # Start from Beam Center (y0 - half)
            # Pass Beam Face (y0)
            # Extend L5 from Face (y0 + L5)
            # Crank (45 degrees)
            # Extend L10
            
            # Note: y0 passed to this function is the slab edge (face of beam if present)
            beam_center_y = y0 - half
            
            # Polyline points
            # Offset midx by offset_val
            # Flip crank direction (-d_crank instead of +d_crank)
            base_x = midx + offset_val
            
            pts = [
                (base_x, beam_center_y),           # Start at beam center
                (base_x, y0 + L5),                 # To L/5 mark (straight)
                (base_x - d_crank, y0 + L5 + d_crank), # Crank 45 deg (Flipped: -d_crank)
                (base_x - d_crank, y0 + L5 + d_crank + L10) # Continue L/10
            ]
            
            w.add_polyline(pts, layer="REB_EK_MESNET")
            ek_mid_y = (beam_center_y + y0 + L5 + d_crank + L10) / 2.0
            w.add_text(base_x + 10, ek_mid_y, f"{ch_ek_start.label()}", height=100, layer="TEXT", rotation=90, center=True)
            _draw_dimension_line(w, ix1 + 80, y0, ix1 + 80, y0 + L5, "ln1/5", offset=40, layer="DIM")
        
        # Alt kenar (END) - sürekli ise
        if ch_ek_end and uzun_end_cont:
            L5 = Ln_long / 5.0
            L10 = Ln_long / 10.0
            d_crank = 200.0
            half = bw_mm / 2.0
            offset_val = 800.0
            
            beam_center_y = y1 + half
            base_x = midx + offset_val
            
            # Polyline points (Going Up/Negative Y direction effectively for visual layout, but coordinates decrease)
            # Flip crank direction (-d_crank instead of +d_crank)
            pts = [
                (base_x, beam_center_y),           # Start at beam center
                (base_x, y1 - L5),                 # To L/5 mark
                (base_x - d_crank, y1 - L5 - d_crank), # Crank (Flipped: -d_crank)
                (base_x - d_crank, y1 - L5 - d_crank - L10) # Continue
            ]
            
            w.add_polyline(pts, layer="REB_EK_MESNET")
            ek_mid_y = (beam_center_y + y1 - L5 - d_crank - L10) / 2.0
            w.add_text(base_x + 10, ek_mid_y, f"{ch_ek_end.label()}", height=100, layer="TEXT", rotation=90, center=True)
            _draw_dimension_line(w, ix1 + 80, y1 - L5, ix1 + 80, y1, "ln2/5", offset=40, layer="DIM")
    
    else:  # auto_dir == "Y"
        # auto_dir == "Y" → Ly < Lx → Y yönü kısa
        # Kısa kenar = T/B (üst/alt, X eksenine paralel kenarlar)
        # Ana donatı kısa kenara paralel → X yönünde (yatay)
        # Dağıtma donatısı uzun kenara paralel → Y yönünde (dikey)
        # Uzun kenar = L/R (sol/sağ, Y eksenine paralel kenarlar)
        Ln_short = Ly  # Kısa açıklık
        Ln_long = Lx   # Uzun açıklık
        
        # --- 1. ANA DONATI (DÜZ + PİLYE) - Yatay (kısa kenara paralel) ---
        rebar_count = 3
        spacing = Ly / (rebar_count + 1)
        
        # Düz-pilye arası offset (aralık değeri kadar)
        rebar_offset = ch_duz.s_mm if ch_duz else (ch_pilye.s_mm if ch_pilye else 60)
        
        for i in range(1, rebar_count + 1):
            y = iy0 + i * spacing
            # Düz demir
            pts_duz = _draw_straight_hit_polyline(ix0, y - rebar_offset, ix1, y - rebar_offset, bw_mm, bw_mm)
            w.add_polyline(pts_duz, layer="REB_DUZ")
            # Pilye demir
            pts = _pilye_polyline(ix0, y + rebar_offset, ix1, y + rebar_offset, d=200.0, kink="both", hook_len=bw_mm, beam_ext=bw_mm)
            w.add_polyline(pts, layer="REB_PILYE")
        
        if ch_duz:
            w.add_text(midx, midy - rebar_offset + 10, f"düz {ch_duz.label()}", height=100, layer="TEXT", center=True)
        if ch_pilye:
            w.add_text(midx, midy + rebar_offset + 10, f"pilye {ch_pilye.label()}", height=100, layer="TEXT", center=True)
        
        # --- 2. DAĞITMA DONATISI - Dikey (uzun kenara paralel) ---
        dist_count = 3
        dx_dist = Lx / (dist_count + 1)
        hook_ext = bw_mm - 30.0
        
        for i in range(1, dist_count + 1):
            x = ix0 + i * dx_dist
            pts = []
            
            # Üst uç (START/Left in Y logic?) -> Top (Check continuity)
            if not kisa_start_cont:
                # Discontinuous: Hook at Top (inside beam, negative Y dir ref? No, y0 is top)
                d_start = y0 - hook_ext
                pts.append((x - hook_ext, d_start)) # Kanca ucu (kiriş içinde, sola/negatif x)
                pts.append((x, d_start))            # Kanca dirsek
            else:
                # Continuous: Start at inner edge (no hook)
                d_start = iy0
                pts.append((x, d_start))
                
            # Alt uç (END/Bottom) -> Bottom (Check continuity)
            if not kisa_end_cont:
                # Discontinuous: Hook at Bottom (inside beam)
                d_end = y1 + hook_ext
                pts.append((x, d_end))              # Dirsek
                pts.append((x - hook_ext, d_end))   # Kanca ucu
            else:
                # Continuous: End at inner edge (no hook)
                d_end = iy1
                pts.append((x, d_end))
                
            w.add_polyline(pts, layer="REB_DIST")
        
        if ch_dist:
            w.add_text(midx + 10, midy, f"dağıtma {ch_dist.label()}", height=100, layer="TEXT", rotation=90, center=True)
            w.add_text(midx - 100, midy, f"As/5", height=80, layer="TEXT", rotation=90, center=True)
        
        # --- 3. BOYUNA KENAR MESNET DONATISI (Süreksiz Kısa Kenar) ---
        # Kısa kenar = T (iy0) ve B (iy1), donatı uzun kenara paralel → Y yönünde (dikey)
        
        # Üst kenar (START) - süreksiz ise
        if ch_kenar_start and not kisa_start_cont:
            ext = Ln_short / 4.0
            # Üst mesnet (kiriş)
            hook_y = y0 - hook_ext
            end_y = iy0 + ext
            
            _draw_support_rebar_vertical(w, ix0, hook_y, ix1, end_y, 2, "REB_KENAR", ch_kenar_start.label(),
                                         hook_start=True, hook_len=hook_ext)
            
            _draw_dimension_line(w, ix1 + 80, iy0, ix1 + 80, end_y, "ln1/4", offset=40, layer="DIM")
            w.add_text(midx, iy0 + ext/2 + 10, "boyuna kenar mesnet minAs", height=70, layer="TEXT", rotation=90, center=True)
        
        # Alt kenar (END) - süreksiz ise
        if ch_kenar_end and not kisa_end_cont:
            ext = Ln_short / 4.0
            # Alt mesnet
            start_y = iy1 - ext
            hook_y = y1 + hook_ext
            
            _draw_support_rebar_vertical(w, ix0, start_y, ix1, hook_y, 2, "REB_KENAR", ch_kenar_end.label(),
                                         hook_end=True, hook_len=hook_ext)
            
            _draw_dimension_line(w, ix1 + 80, start_y, ix1 + 80, iy1, "ln2/4", offset=40, layer="DIM")
        
        # --- 4. BOYUNA İÇ MESNET DONATISI (Sürekli Kısa Kenar) ---
        # Kısa kenar = T (iy0) ve B (iy1), donatı uzun kenara paralel → Y yönünde (dikey)
        
        # Üst kenar (START) - sürekli ise
        if ch_ic_start and kisa_start_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_vertical(w, ix0, y0, ix1, iy0 + ext, 2, "REB_IC_MESNET", ch_ic_start.label())
            _draw_dimension_line(w, ix1 + 80, iy0, ix1 + 80, iy0 + ext, "ln1/4", offset=40, layer="DIM")
            w.add_text(midx, iy0 + ext/2 + 10, "boyuna iç mesnet 0.6×As", height=70, layer="TEXT", rotation=90, center=True)
        
        # Alt kenar (END) - sürekli ise
        if ch_ic_end and kisa_end_cont:
            ext = Ln_short / 4.0
            _draw_support_rebar_vertical(w, ix0, iy1 - ext, ix1, y1, 2, "REB_IC_MESNET", ch_ic_end.label())
            _draw_dimension_line(w, ix1 + 80, iy1 - ext, ix1 + 80, iy1, "ln2/4", offset=40, layer="DIM")
        
        # --- 5. MESNET EK DONATISI (Sürekli Uzun Kenar) ---
        # Uzun kenar = L (ix0) ve R (ix1), donatı kısa kenara paralel → X yönünde (yatay)
        
        # Sol kenar (START) - sürekli ise
        if ch_ek_start and uzun_start_cont:
            L5 = Ln_long / 5.0
            L10 = Ln_long / 10.0
            d_crank = 200.0
            half = bw_mm / 2.0
            offset_val = 800.0
            
            beam_center_x = x0 - half
            base_y = midy + offset_val
            
            pts = [
                (beam_center_x, base_y),           # Start at beam center
                (x0 + L5, base_y),                 # To L/5 mark
                (x0 + L5 + d_crank, base_y - d_crank), # Crank (Flipped: -d_crank)
                (x0 + L5 + d_crank + L10, base_y - d_crank) # Continue
            ]
            
            w.add_polyline(pts, layer="REB_EK_MESNET")
            ek_mid_x = (beam_center_x + x0 + L5 + d_crank + L10) / 2.0
            w.add_text(ek_mid_x, base_y + 10, f"{ch_ek_start.label()}", height=100, layer="TEXT", center=True)
            _draw_dimension_line(w, x0, iy1 + 80, x0 + L5, iy1 + 80, "ln1/5", offset=40, layer="DIM")
        
        # Sağ kenar (END) - sürekli ise
        if ch_ek_end and uzun_end_cont:
            L5 = Ln_long / 5.0
            L10 = Ln_long / 10.0
            d_crank = 200.0
            half = bw_mm / 2.0
            offset_val = 800.0
            
            beam_center_x = x1 + half
            base_y = midy + offset_val
            
            pts = [
                (beam_center_x, base_y),           # Start at beam center
                (x1 - L5, base_y),                 # To L/5 mark
                (x1 - L5 - d_crank, base_y - d_crank), # Crank (Flipped: -d_crank)
                (x1 - L5 - d_crank - L10, base_y - d_crank) # Continue
            ]
            
            w.add_polyline(pts, layer="REB_EK_MESNET")
            ek_mid_x = (beam_center_x + x1 - L5 - d_crank - L10) / 2.0
            w.add_text(ek_mid_x, base_y + 10, f"{ch_ek_end.label()}", height=100, layer="TEXT", center=True)
            _draw_dimension_line(w, x1 - L5, iy1 + 80, x1, iy1 + 80, "ln2/5", offset=40, layer="DIM")
    
    # Döşeme ID'si
    w.add_text(midx, midy, sid, height=150, layer="TEXT", center=True)


def export_to_dxf(system: SlabSystem, filename: str, design_cache: dict, bw_val: float,
                  real_slabs: dict = None):
    from twoway_slab import slab_edge_has_beam

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

    bw_mm = bw_val * 1000.0
    half = bw_mm / 2.0

    if not system.slabs:
        w.save(filename)
        return

    # Döşemeleri pozisyonuna göre sırala (soldan sağa)
    sorted_sids = sorted(system.slabs.keys(),
                         key=lambda sid: (system.slabs[sid].i0, system.slabs[sid].j0))

    # ======================================================================
    # Her döşemeyi gerçek konumuna göre yerleştir
    # Kiriş olan kenarlara bw/2 ekle → Lx = Lxnet + bw etkisi
    # ======================================================================
    # Çizilmiş kirişleri takip et (aynı kirişi iki kez çizmemek için)
    drawn_beams = set()

    for idx, sid in enumerate(sorted_sids):
        s = system.slabs[sid]
        Lx_m, Ly_m = s.size_m_gross()

        # Kenar kiriş durumlarını kontrol et
        if s.kind == "BALCONY":
            has_left = False
            has_right = False
            has_top = False
            has_bottom = False
        else:
            has_left = True
            has_right = True
            has_top = True
            has_bottom = True


            
        # =========================================================
        # Yeni Mantık (Kullanıcı İsteği):
        # Girdi Lx/Ly = Aks-aks mesafesi (brüt) kabul edilir.
        # Net döşeme = Brüt - (varsa kiriş/2)
        # Kirişler = Akslar üzerine oturtulur.
        # =========================================================
        
        # Grid hatları (Brüt sınırlar) - mm cinsinden
        if real_slabs and sid in real_slabs:
            rs = real_slabs[sid]
            grid_x0 = rs.x * 1000.0
            grid_y0 = rs.y * 1000.0
            grid_x1 = grid_x0 + (rs.w * 1000.0)
            grid_y1 = grid_y0 + (rs.h * 1000.0)
        else:
            # Fallback (yan yana diz)
            # Bu modda Lx net kabul ediliyordu eskiden, ama tutarlılık için
            # burayı da brüt gibi düşünebiliriz veya olduğu gibi bırakabiliriz.
            # Şimdilik basitçe yan yana koyuyoruz.
            grid_x0 = idx * (Lx_m * 1000.0) 
            grid_y0 = 0.0
            grid_x1 = grid_x0 + (Lx_m * 1000.0)
            grid_y1 = grid_y0 + (Ly_m * 1000.0)

        # Net Döşeme Koordinatları (Shrink)
        # Kiriş olan kenarlardan içeri çek
        x0 = grid_x0 + (half if has_left else 0)
        y0 = grid_y0 + (half if has_top else 0)
        x1 = grid_x1 - (half if has_right else 0)
        y1 = grid_y1 - (half if has_bottom else 0)

        # Döşeme sınır çizgisi
        w.add_polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                       layer="SLAB_EDGE", closed=True)

        # Kirişleri Çiz (Grid hatları üzerine ortalanmış)
        # Her kiriş, aks boyunca (grid_x/y) tam boyutta çizilir.
        # Kesişim noktalarında üst üste binmeleri sağlamak için uzatmalar (extensions) eklenir.
        
        ext_left = half if has_left else 0.0
        ext_right = half if has_right else 0.0
        ext_top = half if has_top else 0.0
        ext_bottom = half if has_bottom else 0.0

        if has_left:
            # Sol Dikey Kiriş: grid_x0 üzerinde
            # Yukarı ve aşağı uzantılar: Top/Bottom kiriş varsa onların içine kadar uzan
            # Aslında köşe birleşiminde "kimin üstte olduğu" DXF'de önemli değil,
            # sadece taranmış alanın (hatch/solid) veya sınırların birleşimi önemli.
            # Biz polyline çiziyoruz. Köşede L birleşim varsa:
            # V-kiriş: [y0 - half, y1 + half] (eğer üst/alt kiriş varsa)
            # H-kiriş: [x0 - half, x1 + half] (eğer sol/sağ kiriş varsa)
            # Böylece (x0,y0) köşesinde tam bir kare (w*w) örtüşme olur.
            
            y_start = grid_y0 - ext_top
            y_end = grid_y1 + ext_bottom
            
            beam_key = ("V", round(grid_x0, 1), round(y_start, 1), round(y_end, 1))
            if beam_key not in drawn_beams:
                drawn_beams.add(beam_key)
                w.add_polyline([
                    (grid_x0 - half, y_start), (grid_x0 + half, y_start),
                    (grid_x0 + half, y_end), (grid_x0 - half, y_end)
                ], layer="BEAM", closed=True)

        if has_right:
            # Sağ Dikey Kiriş: grid_x1 üzerinde
            y_start = grid_y0 - ext_top
            y_end = grid_y1 + ext_bottom
            
            beam_key = ("V", round(grid_x1, 1), round(y_start, 1), round(y_end, 1))
            if beam_key not in drawn_beams:
                drawn_beams.add(beam_key)
                w.add_polyline([
                    (grid_x1 - half, y_start), (grid_x1 + half, y_start),
                    (grid_x1 + half, y_end), (grid_x1 - half, y_end)
                ], layer="BEAM", closed=True)

        if has_top:
            # Üst Yatay Kiriş: grid_y0 üzerinde
            x_start = grid_x0 - ext_left
            x_end = grid_x1 + ext_right
            
            beam_key = ("H", round(x_start, 1), round(grid_y0, 1), round(x_end, 1))
            if beam_key not in drawn_beams:
                drawn_beams.add(beam_key)
                w.add_polyline([
                    (x_start, grid_y0 - half), (x_end, grid_y0 - half),
                    (x_end, grid_y0 + half), (x_start, grid_y0 + half)
                ], layer="BEAM", closed=True)

        if has_bottom:
            # Alt Yatay Kiriş: grid_y1 üzerinde
            x_start = grid_x0 - ext_left
            x_end = grid_x1 + ext_right
            
            beam_key = ("H", round(x_start, 1), round(grid_y1, 1), round(x_end, 1))
            if beam_key not in drawn_beams:
                drawn_beams.add(beam_key)
                w.add_polyline([
                    (x_start, grid_y1 - half), (x_end, grid_y1 - half),
                    (x_end, grid_y1 + half), (x_start, grid_y1 + half)
                ], layer="BEAM", closed=True)

        # Döşeme ismi - sol üst köşeden 50mm sağ, 100mm aşağı
        w.add_text(x0 + 50, y1 - 100, sid, height=125, layer="TEXT")

        dcache = design_cache.get(sid)
        if not dcache:
            continue

        kind = dcache.get("kind")

        if kind == "ONEWAY":
            _draw_oneway_reinforcement_detail(w, sid, s, dcache, x0, y0, x1, y1, bw_mm)

        elif kind == "TWOWAY":
            cover = float(dcache.get("cover_mm", 25.0))
            ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
            if ix1 <= ix0 or iy1 <= iy0:
                continue

            midx = (ix0 + ix1) / 2.0
            midy = (iy0 + iy1) / 2.0

            chx = dcache["choices"].get("x_span")
            chy = dcache["choices"].get("y_span")

            if chx:
                ptsx = _pilye_polyline(ix0, midy, ix1, midy, d=250.0, kink='both')
                w.add_polyline(ptsx, layer="REB_MAIN_X")
                # Etiket: orta noktadan 500mm sola
                w.add_text(midx - 500, midy + 10, f"X {chx.label()}", height=125,
                           layer="TEXT", center=True)

            if chy:
                ptsy = _pilye_polyline(midx, iy0, midx, iy1, d=250.0, kink='both')
                w.add_polyline(ptsy, layer="REB_MAIN_Y")
                # Etiket: orta noktadan 500mm sola, dikey yazı
                w.add_text(midx - 500, midy, f"Y {chy.label()}", height=125,
                           layer="TEXT", rotation=90, center=True)

        elif kind == "BALCONY":
            cover = float(dcache.get("cover_mm", 25.0))
            ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
            if ix1 <= ix0 or iy1 <= iy0:
                continue

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
                    # Etiket: orta noktadan 500mm sola
                    w.add_text(midx - 500, midy + 10, f"ana {ch_main.label()}",
                               height=125, layer="TEXT", center=True)
                    w.add_line(midx, iy0, midx, iy1, layer="REB_DIST")
                else:
                    kink = "end" if fixed == "T" else "start"
                    pts = _pilye_polyline(midx, iy0, midx, iy1, d=250.0, kink=kink)
                    w.add_polyline(pts, layer="REB_SUPPORT")
                    # Etiket: orta noktadan 500mm sola, dikey yazı
                    w.add_text(midx - 500, midy, f"ana {ch_main.label()}",
                               height=125, layer="TEXT", rotation=90, center=True)
                    w.add_line(ix0, midy, ix1, midy, layer="REB_DIST")

    w.save(filename)
