import math
import ezdxf
from typing import List, Tuple, Optional
from slab_model import SlabSystem, Slab

class _DXFWriter:
    """ezdxf kütüphanesi kullanarak DXF dosyası oluşturan sınıf."""
    
    def __init__(self, max_height=None):
        self.doc = ezdxf.new('R2010')  # AutoCAD 2010 formatı
        self.msp = self.doc.modelspace()
        self.layers_created = set()
        self.max_height = max_height

    def _fy(self, y):
        """Y koordinatını ters çevir (GUI -> DXF dönüşümü için)."""
        if self.max_height is not None:
            return self.max_height - y
        return y

    def add_layer(self, name: str):
        if name not in self.layers_created and name != "0":
            self.doc.layers.add(name)
            self.layers_created.add(name)

    def add_line(self, x1, y1, x2, y2, layer="0"):
        self.add_layer(layer)
        y1 = self._fy(y1)
        y2 = self._fy(y2)
        self.msp.add_line((x1, y1), (x2, y2), dxfattribs={'layer': layer})

    def add_polyline(self, pts, layer="0", closed=False):
        self.add_layer(layer)
        # pts listesi (x, y) tuple'larından oluşur
        new_pts = [(x, self._fy(y)) for x, y in pts]
        self.msp.add_lwpolyline(new_pts, dxfattribs={'layer': layer}, close=closed)

    def add_text(self, x, y, text, height=200.0, layer="TEXT", rotation=0.0, center=False):
        self.add_layer(layer)
        y = self._fy(y)
        # Rotation da bu dönüşümden etkilenebilir ama metin okuma yönü
        # genelde X eksenine göre olduğu için, sadece konumu değiştiriyoruz.
        # Ancak dikey (90 derece) metinler aşağıdan yukarı okunur (AutoCAD standartı).
        # Eğer GUI'de yukarıdan aşağı okunan bir metin varsa, burada -90 yapmak gerekebilir.
        # Şimdilik rotasyonu olduğu gibi bırakıyoruz, sadece konumu taşıyoruz.
        
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
    bw_mm: float,
    slab_index: int = 0
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
        
        # Stagger logic: Shift distribution bars by 200mm for odd slab indices
        stagger_offset = 200.0 if (slab_index % 2 != 0) else 0.0
        
        for i in range(1, dist_count + 1):
            base_y = iy0 + i * dy_dist
            y = base_y + stagger_offset
            
            # Ensure y is within bounds (optional checking, but usually slab is large enough)
            
            pts = []
            
            # Sol taraf (Check continuity)
            if not kisa_start_cont:
                # Discontinuous: Hook at start (inside beam)
                d_start = x0 - hook_ext
                pts.append((d_start, y - hook_ext)) # Kanca ucu (kiriş içinde, aşağı doğru)
                pts.append((d_start, y))            # Kanca dirsek
            else:
                # Continuous: Straight extension into beam (no hook)
                # Extend into beam by hook_ext
                d_start = x0 - hook_ext
                pts.append((d_start, y))
            
            # Sağ taraf (Check continuity)
            if not kisa_end_cont:
                # Discontinuous: Hook at end (inside beam)
                d_end = x1 + hook_ext
                pts.append((d_end, y))              # Dirsek
                pts.append((d_end, y - hook_ext))   # Kanca ucu
            else:
                # Continuous: Straight extension into beam (no hook)
                # Extend into beam by hook_ext
                d_end = x1 + hook_ext
                pts.append((d_end, y))
                
            w.add_polyline(pts, layer="REB_DIST")
        
        if ch_dist:
            w.add_text(midx, midy + 10, f"dağıtma {ch_dist.label()}", height=100, layer="TEXT", center=True)
            # w.add_text(midx, midy - 100, f"As/5", height=80, layer="TEXT", center=True)
        
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
            
            # _draw_dimension_line(w, ix0, iy1 + 80, end_x, iy1 + 80, "ln1/4", offset=40, layer="DIM")
            # w.add_text(ix0 + ext/2, midy + 10, "boyuna kenar mesnet minAs", height=70, layer="TEXT", center=True)
        
        # Sağ kenar (END) - süreksiz ise
        if ch_kenar_end and not kisa_end_cont:
            ext = Ln_short / 4.0
            # Sağ taraf mesnet
            start_x = ix1 - ext
            hook_x = x1 + hook_ext
            
            _draw_support_rebar_horizontal(w, start_x, iy0, hook_x, iy1, 2, "REB_KENAR", ch_kenar_end.label(),
                                           hook_end=True, hook_len=hook_ext)
            
            # _draw_dimension_line(w, start_x, iy1 + 80, ix1, iy1 + 80, "ln1/4", offset=40, layer="DIM")
        
        # --- 4. BOYUNA İÇ MESNET DONATISI (Sürekli Kısa Kenar) ---
        # Kısa kenar = L (ix0) ve R (ix1), donatı uzun kenara paralel → X yönünde (yatay)
        
        # Sol kenar (START) - sürekli ise
        if ch_ic_start and kisa_start_cont:
            L4 = Ln_short / 4.0
            L8 = Ln_short / 8.0
            d_crank = 200.0
            # Start at Beam Center (x0 - bw/2)
            start_x = x0 - (bw_mm / 2.0)
            
            count = 2
            dy = (y1 - y0) / (count + 1)
            
            for i in range(1, count + 1):
                y = y0 + i * dy
                pts = [
                    (start_x, y),              # Start at beam center
                    (x0 + L4, y),              # Straight past edge to Ln/4
                    (x0 + L4 + d_crank, y - d_crank), # Crank down 45 deg
                    (x0 + L4 + d_crank + L8, y - d_crank) # Straight Ln/8
                ]
                w.add_polyline(pts, layer="REB_IC_MESNET")

                w.add_polyline(pts, layer="REB_IC_MESNET")

            # _draw_dimension_line(w, ix0, iy1 + 80, ix0 + L4, iy1 + 80, "ln1/4", offset=40, layer="DIM")
            # w.add_text(ix0 + L4/2, midy + 10, "boyuna iç mesnet 0.6×As", height=70, layer="TEXT", center=True)
        
        # Sağ kenar (END) - sürekli ise
        if ch_ic_end and kisa_end_cont:
            L4 = Ln_short / 4.0
            L8 = Ln_short / 8.0
            d_crank = 200.0
            
            # Start at Beam Center (x1 + bw/2)
            start_x = x1 + (bw_mm / 2.0)
            
            count = 2
            dy = (y1 - y0) / (count + 1)
            
            for i in range(1, count + 1):
                y = y0 + i * dy
                pts = [
                    (start_x, y),              # Start at beam center
                    (x1 - L4, y),              # Straight Left past edge to Ln/4
                    (x1 - L4 - d_crank, y - d_crank), # Crank down
                    (x1 - L4 - d_crank - L8, y - d_crank) # Straight Left Ln/8
                ]
                w.add_polyline(pts, layer="REB_IC_MESNET")

                w.add_polyline(pts, layer="REB_IC_MESNET")

            # _draw_dimension_line(w, ix1 - L4, iy1 + 80, ix1, iy1 + 80, "ln2/4", offset=40, layer="DIM")
        
        # --- 5. MESNET EK DONATISI (Sürekli Uzun Kenar) ---
        # Uzun kenar = T (iy0) ve B (iy1), donatı kısa kenara paralel → Y yönünde (dikey)
        
        # Üst kenar (START) - sürekli ise
        if ch_ek_start and uzun_start_cont:
            L_ext = Ln_long / 5.0
            offset_val = 800.0
            _draw_support_extra_y(w, midx + offset_val, y0, bw_mm, ch_ek_start, L_ext, is_top=True)
        
        # Alt kenar (END) - sürekli ise
        if ch_ek_end and uzun_end_cont:
            L_ext = Ln_long / 5.0
            offset_val = 800.0
            _draw_support_extra_y(w, midx + offset_val, y1, bw_mm, ch_ek_end, L_ext, is_top=False)
    
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
        
        # Stagger logic: Shift distribution bars by 200mm for odd slab indices
        stagger_offset = 200.0 if (slab_index % 2 != 0) else 0.0
        
        for i in range(1, dist_count + 1):
            base_x = ix0 + i * dx_dist
            x = base_x + stagger_offset
            
            pts = []
            
            # Üst uç (START/Left in Y logic?) -> Top (Check continuity)
            if not kisa_start_cont:
                # Discontinuous: Hook at Top (inside beam, negative Y dir ref? No, y0 is top)
                d_start = y0 - hook_ext
                pts.append((x - hook_ext, d_start)) # Kanca ucu (kiriş içinde, sola/negatif x)
                pts.append((x, d_start))            # Kanca dirsek
            else:
                # Continuous: Straight extension into beam (no hook)
                # Extend into beam by hook_ext
                d_start = y0 - hook_ext
                pts.append((x, d_start))
                
            # Alt uç (END/Bottom) -> Bottom (Check continuity)
            if not kisa_end_cont:
                # Discontinuous: Hook at Bottom (inside beam)
                d_end = y1 + hook_ext
                pts.append((x, d_end))              # Dirsek
                pts.append((x - hook_ext, d_end))   # Kanca ucu
            else:
                # Continuous: Straight extension into beam (no hook)
                # Extend straight into beam by hook_ext
                d_end = y1 + hook_ext
                pts.append((x, d_end))
                
            w.add_polyline(pts, layer="REB_DIST")
        
        if ch_dist:
            w.add_text(midx + 10, midy, f"dağıtma {ch_dist.label()}", height=100, layer="TEXT", rotation=90, center=True)
            # w.add_text(midx - 100, midy, f"As/5", height=80, layer="TEXT", rotation=90, center=True)
        
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
            
            _draw_support_rebar_vertical(w, ix0, hook_y, ix1, end_y, 2, "REB_KENAR", ch_kenar_start.label(),
                                         hook_start=True, hook_len=hook_ext)
            
            # _draw_dimension_line(w, ix1 + 80, iy0, ix1 + 80, end_y, "ln1/4", offset=40, layer="DIM")
            # w.add_text(midx, iy0 + ext/2 + 10, "boyuna kenar mesnet minAs", height=70, layer="TEXT", rotation=90, center=True)
        
        # Alt kenar (END) - süreksiz ise
        if ch_kenar_end and not kisa_end_cont:
            ext = Ln_short / 4.0
            # Alt mesnet
            start_y = iy1 - ext
            hook_y = y1 + hook_ext
            
            _draw_support_rebar_vertical(w, ix0, start_y, ix1, hook_y, 2, "REB_KENAR", ch_kenar_end.label(),
                                         hook_end=True, hook_len=hook_ext)
            
            _draw_support_rebar_vertical(w, ix0, start_y, ix1, hook_y, 2, "REB_KENAR", ch_kenar_end.label(),
                                         hook_end=True, hook_len=hook_ext)
            
            # _draw_dimension_line(w, ix1 + 80, start_y, ix1 + 80, iy1, "ln2/4", offset=40, layer="DIM")
        
        # --- 4. BOYUNA İÇ MESNET DONATISI (Sürekli Kısa Kenar) ---
        # Kısa kenar = T (iy0) ve B (iy1), donatı uzun kenara paralel → Y yönünde (dikey)
        
        # Üst kenar (START) - sürekli ise
        if ch_ic_start and kisa_start_cont:
            L4 = Ln_short / 4.0
            L8 = Ln_short / 8.0
            d_crank = 200.0
            
            # Start at Beam Center (y0 - bw/2)
            start_y = y0 - (bw_mm / 2.0)
            
            count = 2
            dx = (x1 - x0) / (count + 1)
            
            for i in range(1, count + 1):
                x = x0 + i * dx
                pts = [
                    (x, start_y),                   # Start at beam center
                    (x, y0 + L4),              # Straight Down past edge to Ln/4
                    (x - d_crank, y0 + L4 + d_crank), # Crank Left/Down? 
                    # Vertical bar crank usually offsets in X. 
                    # Let's offset LEFT (-X) for consistency visualization
                    (x - d_crank, y0 + L4 + d_crank + L8) # Straight Down Ln/8
                ]
                w.add_polyline(pts, layer="REB_IC_MESNET")

                w.add_polyline(pts, layer="REB_IC_MESNET")

            # _draw_dimension_line(w, ix1 + 80, iy0, ix1 + 80, iy0 + L4, "ln1/4", offset=40, layer="DIM")
            # w.add_text(midx, iy0 + L4/2 + 10, "boyuna iç mesnet 0.6×As", height=70, layer="TEXT", rotation=90, center=True)
        
        # Alt kenar (END) - sürekli ise
        if ch_ic_end and kisa_end_cont:
            L4 = Ln_short / 4.0
            L8 = Ln_short / 8.0
            d_crank = 200.0

            # Start at Beam Center (y1 + bw/2)
            start_y = y1 + (bw_mm / 2.0)
            
            count = 2
            dx = (x1 - x0) / (count + 1)
            
            for i in range(1, count + 1):
                x = x0 + i * dx
                pts = [
                    (x, start_y),                   # Start at beam center
                    (x, y1 - L4),              # Straight Up past edge to Ln/4
                    (x - d_crank, y1 - L4 - d_crank), # Crank Left/Up
                    (x - d_crank, y1 - L4 - d_crank - L8) # Straight Up Ln/8
                ]
                w.add_polyline(pts, layer="REB_IC_MESNET")
            
                w.add_polyline(pts, layer="REB_IC_MESNET")
            
            # _draw_dimension_line(w, ix1 + 80, iy1 - L4, ix1 + 80, iy1, "ln2/4", offset=40, layer="DIM")
        
        # --- 5. MESNET EK DONATISI (Sürekli Uzun Kenar) ---
        # Uzun kenar = L (ix0) ve R (ix1), donatı kısa kenara paralel → X yönünde (yatay)
        
        # Sol kenar (START) - sürekli ise
        if ch_ek_start and uzun_start_cont:
            L_ext = Ln_long / 5.0
            offset_val = 800.0
            _draw_support_extra_x(w, x0, midy + offset_val, bw_mm, ch_ek_start, L_ext, is_left=True)
        
        # Sağ kenar (END) - sürekli ise
        if ch_ek_end and uzun_end_cont:
            L_ext = Ln_long / 5.0
            offset_val = 800.0
            _draw_support_extra_x(w, x1, midy + offset_val, bw_mm, ch_ek_end, L_ext, is_left=False)
    
    # Döşeme ID'si
    w.add_text(midx, midy, sid, height=150, layer="TEXT", center=True)


def export_to_dxf(system: SlabSystem, filename: str, design_cache: dict, bw_val: float,
                  real_slabs: dict = None):
    from twoway_slab import slab_edge_has_beam

    # Kiriş olan kenarlara bw/2 ekle → Lx = Lxnet + bw etkisi
    # ======================================================================
    # Çizilmiş kirişleri takip et (aynı kirişi iki kez çizmemek için)
    drawn_beams = set()

    # Toplam Yüksekliği Hesapla (Y ekseni simetrisi için)
    max_y_mm = 0.0
    if real_slabs:
        max_h = 0.0
        for rs in real_slabs.values():
            bottom = rs.y + rs.h
            if bottom > max_h:
                max_h = bottom
        max_y_mm = max_h * 1000.0
    else:
        # Fallback
        _, total_my = system.size_m_gross()
        max_y_mm = total_my * 1000.0

    # Margin ekle (isteğe bağlı, şimdilik tam sınır)
    max_y_mm += 0.0 

    w = _DXFWriter(max_height=max_y_mm)
    
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
            _draw_oneway_reinforcement_detail(w, sid, s, dcache, x0, y0, x1, y1, bw_mm, slab_index=idx)

        elif kind == "TWOWAY":
            _draw_twoway_reinforcement_detail(w, sid, s, dcache, x0, y0, x1, y1, bw_mm, slab_index=idx, system=system)

        elif kind == "BALCONY":
            _draw_balcony_reinforcement_detail(w, sid, s, dcache, x0, y0, x1, y1, bw_mm)

    w.save(filename)


def _draw_twoway_reinforcement_detail(
    w: _DXFWriter,
    sid: str,
    s: Slab,
    dcache: dict,
    x0: float, y0: float, x1: float, y1: float,
    bw_mm: float,
    slab_index: int = 0,
    system: "SlabSystem" = None
):
    """
    Çift doğrultulu döşeme için detaylı donatı krokisi çizer.
    Hem X hem Y yönünde ana donatı (düz + pilye) bulunur.
    
    YENİ DÜZEN (User Request):
    - Paralel donatılar (Düz/Pilye) aynı hizada olmayacak.
    - Aralarındaki mesafe donatı aralığı (s) kadar olacak.
    - Yazılar üst üste gelmeyecek (Staggered layout).
    - Kancalar çakışmayacak: Düz ve Pilye kancaları arasında 50mm fark olacak.
    """
    cover = float(dcache.get("cover_mm", 25.0))
    choices = dcache.get("choices", {})
    edge_cont = dcache.get("edge_continuity", {})

    # İç sınırlar (pas payı düşülmüş)
    ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
    if ix1 <= ix0 or iy1 <= iy0:
        return

    Lx = ix1 - ix0
    Ly = iy1 - iy0
    midx = (ix0 + ix1) / 2.0
    midy = (iy0 + iy1) / 2.0

    # Süreklilik durumları (True=Sürekli, False=Süreksiz)
    cont_L = edge_cont.get("L", False)
    cont_R = edge_cont.get("R", False)
    cont_T = edge_cont.get("T", False)
    cont_B = edge_cont.get("B", False)

    # Kanca uzunluğu (düz ve pilye için aynı kanca boyu)
    hook_len = bw_mm - 30.0 
    
    # Kiriş içine uzama (Staggered)
    # Pilye: bw - 30
    beam_ext_pilye = bw_mm - 30.0
    
    # Düz: bw - 30 - 50 (50mm daha kısa/geride kalsın)
    beam_ext_duz = bw_mm - 30.0 - 50.0

    # =========================================================
    # 1. X YÖNÜ DONATILARI (Yatay Çizilenler)
    # =========================================================
    ch_x_duz = choices.get("x_span_duz")
    ch_x_pilye = choices.get("x_span_pilye")
    ch_x_ek = choices.get("x_support_extra")

    # Spacing hesapla (Offset için)
    # Düz ve Pilye arası mesafe 's' kadar olsun. 
    # O zaman merkezden +s/2 ve -s/2 öteleyelim.
    sx = ch_x_pilye.s_mm if ch_x_pilye else 200.0
    if ch_x_duz: sx = ch_x_duz.s_mm
    
    # Y koordinatları: Pilye üstte (+), Düz altta (-)
    y_pilye_x = midy + (sx / 2.0)
    y_duz_x = midy - (sx / 2.0)

    # Text Offset (Staggered)
    # X donatısı metinleri yatay çizginin üstünde/altında olur.
    # Çakışmayı önlemek için X ekseninde de kaydıralım.
    # Pilye Yazısı: Sola kayık, Çizgi üstü
    # Düz Yazısı: Sağa kayık, Çizgi altı
    text_shift_x = Lx * 0.25  # Çeyrek açıklık kadar kaydır

    # X Yönü Düz Donatı
    if ch_x_duz:
        pts = []
        # Sol (L)
        if cont_L:
            pts.append((x0 - beam_ext_duz, y_duz_x))
        else:
            # Süreksiz: Kanca YUKARI (Düz donatı altta)
            pts.append((x0 - beam_ext_duz, y_duz_x + hook_len)) 
            pts.append((x0 - beam_ext_duz, y_duz_x))            
        
        # Sağ (R)
        if cont_R:
            pts.append((x1 + beam_ext_duz, y_duz_x))
        else:
            # Süreksiz: Kanca YUKARI
            pts.append((x1 + beam_ext_duz, y_duz_x))            
            pts.append((x1 + beam_ext_duz, y_duz_x + hook_len)) 

        w.add_polyline(pts, layer="REB_DUZ")
        # Label: Center + shift Right, Below line
        w.add_text(midx + text_shift_x, y_duz_x - 30, f"X düz {ch_x_duz.label()}", height=100, layer="TEXT", center=True)

    # X Yönü Pilye Donatı
    if ch_x_pilye:
        # Pilye kancaları: Pilye (üst), süreksiz kenarda kanca AŞAĞI.
        pts = _pilye_polyline(x0, y_pilye_x, x1, y_pilye_x, d=200.0, kink="both", hook_len=hook_len, beam_ext=beam_ext_pilye)
        w.add_polyline(pts, layer="REB_PILYE")
        # Label: Center - shift Left, Above line
        w.add_text(midx - text_shift_x, y_pilye_x + 30, f"X pilye {ch_x_pilye.label()}", height=100, layer="TEXT", center=True)

    # X Yönü Mesnet Ek
    if ch_x_ek:
        # Mesnet ekleri: SADECE SAĞ (R) KENARDA ÇİZİLİR (Süreklilik varsa)
        # Sol (L) kenar için, sol komşu (kendi R kenarı için) çizecek.
        
        # Sağ (R) - Eğer sürekliyse
        if cont_R:
             # Sağ Komşuyu bul
            neighbor_id, neighbor_kind = _get_neighbor_id_on_edge(system, sid, "R")
            
            # Mesafeler
            # Kendi tarafım (Sol tarafı çizimin): Ln/5
            L_ext_self = Lx / 5.0
            
            # Komşu tarafı (Sağ tarafı çizimin): Ln_neighbor / 5
            # Eğer komşu yoksa veya balcony ise?
            # Balcony ise, balkonun L_net'i yoktur (genelde 1.5m vs).
            # Güvenli olarak L_ext_self kullan.
            L_ext_neigh = L_ext_self
            
            if neighbor_id and system:
                try:
                    # Komşunun Lx değerini al
                    # twoway_net_LxLy(sid, bw) -> returns Lx_n, Ly_n, steps
                    # Ancak bu fonksiyon system.slabs[sid] gerektirir.
                    # Komşu Oneway de olabilir Twoway de.
                    # Basitçe bounding box'tan brüt alıp bw düşelim.
                    # Veya system.slabs[neighbor_id].size_m_gross()
                    ns = system.slabs[neighbor_id]
                    nLx_g, _ = ns.size_m_gross()
                    # Net yaklaşık Brüt - bw
                    nLx = (nLx_g * 1000.0) - bw_mm 
                    if nLx > 0:
                        L_ext_neigh = nLx / 5.0
                except:
                    pass
            
            # Hat Çiz
            # Merkez: x1 + bw/2 (Sağ kirişin ortası)
            cx = x1 + (bw_mm / 2.0)
            cy = midy + 800 # Y konumu
            
            _draw_hat_bar(w, cx, cy, bw_mm, ch_x_ek, 
                          L_ext_left=L_ext_self, L_ext_right=L_ext_neigh, 
                          axis="X")


    # =========================================================
    # 2. Y YÖNÜ DONATILARI (Dikey Çizilenler)
    # =========================================================
    ch_y_duz = choices.get("y_span_duz")
    ch_y_pilye = choices.get("y_span_pilye")
    ch_y_ek = choices.get("y_support_extra")

    # Spacing
    sy = ch_y_pilye.s_mm if ch_y_pilye else 200.0
    if ch_y_duz: sy = ch_y_duz.s_mm

    # X koordinatları (Dikey çizgiler için)
    # Pilye Sağda (+), Düz Solda (-)
    x_pilye_y = midx + (sy / 2.0)
    x_duz_y = midx - (sy / 2.0)

    # Text Offset (Staggered via Y axis)
    # Pilye Yazısı: Yukarı kayık, Çizgi Sağı
    # Düz Yazısı: Aşağı kayık, Çizgi Solu
    text_shift_y = Ly * 0.25

    # Y Yönü Düz Donatı
    if ch_y_duz:
        pts = []
        # Üst (T)
        if cont_T:
            pts.append((x_duz_y, y0 - beam_ext_duz))
        else:
            # Süreksiz: Kanca İÇE (SOLA)
            pts.append((x_duz_y - hook_len, y0 - beam_ext_duz))
            pts.append((x_duz_y, y0 - beam_ext_duz))
        
        # Alt (B)
        if cont_B:
            pts.append((x_duz_y, y1 + beam_ext_duz))
        else:
            pts.append((x_duz_y, y1 + beam_ext_duz))
            pts.append((x_duz_y - hook_len, y1 + beam_ext_duz))

        w.add_polyline(pts, layer="REB_DUZ")
        # Label: Center - shift Down, Left of line (Rotated 90)
        w.add_text(x_duz_y - 30, midy - text_shift_y, f"Y düz {ch_y_duz.label()}", height=100, layer="TEXT", rotation=90, center=True)

    # Y Yönü Pilye Donatı
    if ch_y_pilye:
        pts = _pilye_polyline(x_pilye_y, y0, x_pilye_y, y1, d=200.0, kink="both", hook_len=hook_len, beam_ext=beam_ext_pilye)
        w.add_polyline(pts, layer="REB_PILYE")
        # Label: Center + shift Up, Right of line
        w.add_text(x_pilye_y + 60, midy + text_shift_y, f"Y pilye {ch_y_pilye.label()}", height=100, layer="TEXT", rotation=90, center=True)

    # Y Yönü Mesnet Ek
    if ch_y_ek:
        # Sadece ALT (B) Kenarda Çiz
        
        # Alt (B) - Eğer sürekliyse
        if cont_B:
            # Alt Komşuyu bul
            neighbor_id, neighbor_kind = _get_neighbor_id_on_edge(system, sid, "B")
            
            L_ext_self = Ly / 5.0
            L_ext_neigh = L_ext_self
            
            if neighbor_id and system:
                try:
                    ns = system.slabs[neighbor_id]
                    _, nLy_g = ns.size_m_gross()
                    nLy = (nLy_g * 1000.0) - bw_mm
                    if nLy > 0:
                        L_ext_neigh = nLy / 5.0
                except:
                    pass
            
            # Hat Çiz
            # Merkez: y1 + bw/2 (Alt kirişin ortası)
            cx = midx - 800
            cy = y1 + (bw_mm / 2.0)
            
            # Axis Y:
            # L_ext_left -> correspond to Top (Self) -> negative Y relative to center?
            # Wait, _draw_hat_bar axis="Y":
            # Left arg -> Top (Negative Y direction from center? No, usually Top is Y0 < Y1)
            # Let's define: Left=Top(Negative/Smaller Y in GUI?), Right=Bottom(Positive/Larger Y)
            # In standard Math (Y up): Top is larger Y.
            # In our GUI (Y down): Top is smaller Y (y0).
            # Let's verify _draw_hat_bar implementation details below.
            
            _draw_hat_bar(w, cx, cy, bw_mm, ch_y_ek, 
                          L_ext_left=L_ext_self, L_ext_right=L_ext_neigh, 
                          axis="Y")

    w.add_text(midx, midy, sid, height=150, layer="TEXT", center=True)


def _draw_support_extra_x(w, x_ref, y_ref, bw_mm, choice, L_ext, is_left=True):
    """
    Mesnet Ek Donatısı (Yatay): 
    - Kiriş merkezinden başlar (veya komşudan gelir).
    - Kiriş yüzünden L_ext kadar içeri girer.
    - Uçta aşağı doğru kanca yapar.
    """
    hook_len = 100.0
    half = bw_mm / 2.0
    
    # x_ref: Kiriş YÜZÜ (Face) - veya sınır
    # Ancak OneWay fonksiyonu x_ref olarak bazen ortayı gönderiyor olabilir. 
    # Parametrelerin tutarlılığı için:
    # Bu fonksiyonda x_ref = Kiriş YÜZÜ (Döşeme Kenarı) varsayalım.
    # Ve beam_center buna göre hesaplansın.
    
    # DÜZELTME: Mevcut kodda çağrılan yerler:
    # TwoWay: x0 (Sol Face), x1 (Sağ Face) gönderiliyor.
    # OneWay: beam_center_x gönderiliyor olabilir mi? 
    # OneWay koduna bakalım: 
    #   beam_center_x = x0 - half; _draw_support_extra_x(..., beam_center_x? HAYIR)
    #   OneWay draw: pts = [... beam_center_x ...] kendisi çiziyor.
    #   OneWay, _draw_support_extra_x KULLANMIYOR. Kendisi polyline oluşturuyor.
    #   Sadece TwoWay kullanıyor. O yüzden rahatız.
    
    # TwoWay çağrısı: x_ref = x0 (Sol Kenar/Yüz) veya x1 (Sağ Kenar/Yüz)
    
    pts = []
    if is_left:
        # Sol kenar (x_ref = x0)
        # Donatı: Sol komşudan gelmeli (biz çiziyoruz), sağa uzamalı (bizim içimize).
        # Başlangıç: Kirişin diğer tarafı veya ortası?
        # Genelde süreklilik donatısı simetriktir. Kiriş ekseninden L_ext kadar her iki yana.
        # Biz sadece yarısını (bizim taraftakini) çiziyoruz gibi düşünebiliriz ama
        # çizimde bütünlük olması için kiriş ekseninden başlatıp bizim tarafa uzatmak mantıklı.
        
        x_beam_center = x_ref - half
        # Ancak komşu tarafını komşu çizecek. Biz sadece bizim tarafı çizelim?
        # User talebi: "iki döşemeye de kirişten itibaren Ln/5 kadar uzayacak"
        # Bu demek ki, her döşeme kendi tarafındaki Ln/5'i çizerse, ve bunlar birleşirse?
        # Veya tek bir çizgi mi olmalı?
        # Kiriş ortasından bölerek çizmek mantıklı.
        
        pts = [
            (x_beam_center, y_ref),           # Start at Beam Center
            (x_ref + L_ext, y_ref),           # Extend into slab (Ln/5)
            (x_ref + L_ext, y_ref - hook_len) # Hook Down
        ]
    else:
        # Sağ kenar (x_ref = x1)
        x_beam_center = x_ref + half
        
        pts = [
            (x_beam_center, y_ref),           # Start at Beam Center
            (x_ref - L_ext, y_ref),           # Extend into slab (Ln/5)
            (x_ref - L_ext, y_ref - hook_len) # Hook Down
        ]
    
    w.add_polyline(pts, layer="REB_EK_MESNET")
    # Label
    lbl_x = x_ref + (L_ext/2.0) if is_left else x_ref - (L_ext/2.0)
    w.add_text(lbl_x, y_ref + 20, f"Ek {choice.label()}", height=80, layer="TEXT", center=True)


def _draw_support_extra_y(w, x_ref, y_ref, bw_mm, choice, L_ext, is_top=True):
    """
    Mesnet Ek Donatısı (Dikey)
    """
    hook_len = 100.0
    half = bw_mm / 2.0
    
    pts = []
    if is_top:
        # Üst kenar (y_ref = y0)
        y_beam_center = y_ref - half
        
        pts = [
            (x_ref, y_beam_center),           # Start at Beam Center
            (x_ref, y_ref + L_ext),           # Extend Down into slab
            (x_ref - hook_len, y_ref + L_ext) # Hook Left (or Right?) - Standard Left for vertical
        ]
    else:
        # Alt kenar (y_ref = y1)
        y_beam_center = y_ref + half
        
        pts = [
            (x_ref, y_beam_center),           # Start at Beam Center
            (x_ref, y_ref - L_ext),           # Extend Up into slab
            (x_ref - hook_len, y_ref - L_ext) # Hook Left
        ]
    
    w.add_polyline(pts, layer="REB_EK_MESNET")
    lbl_y = y_ref + (L_ext/2.0) if is_top else y_ref - (L_ext/2.0)
    w.add_text(x_ref + 20, lbl_y, f"Ek {choice.label()}", height=80, layer="TEXT", rotation=90, center=True)



def _draw_balcony_reinforcement_detail(
    w: _DXFWriter,
    sid: str,
    s: Slab,
    dcache: dict,
    x0: float, y0: float, x1: float, y1: float,
    bw_mm: float
):
    """
    Balkon donatısı:
    - Mesnet (sabit) kenarda komşuya uzanır (üst donatı).
    - Serbest kenarda kanca yapar (AŞAĞI).
    - Dağıtma donatısı diğer yönde.
    """
    cover = float(dcache.get("cover_mm", 25.0))
    ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
    midx = (ix0 + ix1) / 2.0
    midy = (iy0 + iy1) / 2.0
    
    choices = dcache.get("choices", {})
    ch_main = choices.get("main")
    ch_dist = choices.get("dist")
    fixed = dcache.get("fixed_edge", "L") # Hangi kenar ankastre (bina tarafı)

    beam_ext = bw_mm - 30.0
    hook_len = bw_mm - 30.0
    L_anchor = 1000.0 # Komşuya uzama boyu (temsili)

    # 1. ANA DONATI (ÜST)
    if ch_main:
        pts = []
        layer = "REB_SUPPORT"
        lbl_rot = 0
        lbl_pos = (midx, midy)

        if fixed == "L":
            # Sol taraf sabit, Sağ taraf serbest
            # Solda komşuya uzan (düz)
            # Sağda kanca AŞAĞI
            y_pos = midy
            pts.append((x0 - L_anchor, y_pos)) # Komşu içi
            pts.append((x1 + beam_ext, y_pos)) # Sağ uç (kiriş/döşeme ucu)
            pts.append((x1 + beam_ext, y_pos + hook_len)) # Kanca AŞAĞI (Y artıyor -> ekran koordinatında aşağı)
            
            w.add_polyline(pts, layer=layer)
            w.add_text(midx, y_pos - 20, f"Ana {ch_main.label()}", height=100, layer="TEXT", center=True)
            
            # Dağıtma (Dikey)
            if ch_dist:
                count = 3
                dx = (x1 - x0) / (count + 1)
                for i in range(1, count + 1):
                    xi = x0 + i * dx
                    # Düz çubuk
                    w.add_line(xi, iy0, xi, iy1, layer="REB_DIST")
                w.add_text(midx, midy + 100, f"Dağ. {ch_dist.label()}", height=80, layer="TEXT", center=True)

        elif fixed == "R":
            # Sağ taraf sabit, Sol taraf serbest
            y_pos = midy
            pts.append((x1 + L_anchor, y_pos)) # Komşu içi
            pts.append((x0 - beam_ext, y_pos)) # Sol uç
            pts.append((x0 - beam_ext, y_pos + hook_len)) # Kanca AŞAĞI
            
            w.add_polyline(pts, layer=layer)
            w.add_text(midx, y_pos - 20, f"Ana {ch_main.label()}", height=100, layer="TEXT", center=True)
             # Dağıtma (Dikey)
            if ch_dist:
                count = 3
                dx = (x1 - x0) / (count + 1)
                for i in range(1, count + 1):
                    xi = x0 + i * dx
                    w.add_line(xi, iy0, xi, iy1, layer="REB_DIST")

        elif fixed == "T":
            # Üst taraf sabit, Alt taraf serbest
            x_pos = midx
            pts.append((x_pos, y0 - L_anchor)) # Komşu içi (Yukarı)
            pts.append((x_pos, y1 + beam_ext)) # Alt uç
            # Vertical çizimde kanca "Sağa" kıvrılsın (Aşağı temsili)
            pts.append((x_pos + hook_len, y1 + beam_ext)) 
            
            w.add_polyline(pts, layer=layer)
            w.add_text(x_pos + 20, midy, f"Ana {ch_main.label()}", height=100, layer="TEXT", rotation=90, center=True)

            # Dağıtma (Yatay)
            if ch_dist:
                count = 3
                dy = (y1 - y0) / (count + 1)
                for i in range(1, count + 1):
                    yi = y0 + i * dy
                    w.add_line(ix0, yi, ix1, yi, layer="REB_DIST")

        elif fixed == "B":
            # Alt taraf sabit, Üst taraf serbest
            x_pos = midx
            pts.append((x_pos, y1 + L_anchor)) # Komşu içi (Aşağı)
            pts.append((x_pos, y0 - beam_ext)) # Üst uç
            pts.append((x_pos + hook_len, y0 - beam_ext)) # Kanca "Sağa"
            
            w.add_polyline(pts, layer=layer)
            w.add_text(x_pos + 20, midy, f"Ana {ch_main.label()}", height=100, layer="TEXT", rotation=90, center=True)

             # Dağıtma (Yatay)
            if ch_dist:
                count = 3
                dy = (y1 - y0) / (count + 1)
                for i in range(1, count + 1):
                    yi = y0 + i * dy
                    w.add_line(ix0, yi, ix1, yi, layer="REB_DIST")

    w.add_text(midx, midy, sid, height=150, layer="TEXT", center=True)


def _get_neighbor_id_on_edge(system, sid, edge):
    """Yardımcı: Belirtilen kenardaki komşunun ID'sini döndürür."""
    if not system: return None, None
    try:
        # twoway_slab.get_neighbor_on_edge_twoway fonksiyonunu kullanabiliriz
        # ama o fonksiyon sistem importu gerektirir.
        # Burada manuel yapalım veya sistemi kullanalım.
        # system.cell_owner vs.
        neigh_set = system.neighbor_slabs_on_side(sid, "X" if edge in "LR" else "Y", "START" if edge in "LT" else "END")
        # Genelde 1 komşu vardır ama set döner. İlkini alalım.
        if neigh_set:
            nid = list(neigh_set)[0]
            nkind = system.slabs[nid].kind
            return nid, nkind
    except:
        pass
    return None, None


def _draw_hat_bar(w, cx, cy, bw_mm, choice, L_ext_left, L_ext_right, axis="X"):
    """
    Hat (Pilye) Şeklinde Mesnet Ek Donatısı Çizer.
    
    Tasarım:
    - Merkez (cx, cy) kiriş ekseni üzerindedir.
    - Donatı, kirişin soluna/üstüne ve sağına/altına doğru uzanır.
    - Şekil:
      - Sol/Üst Kuyruk (Tail)
      - Sol/Üst Kırılma (Crank Up)
      - Sol/Üst Düz (Top - beam üstü)
      - Sağ/Alt Düz (Top)
      - Sağ/Alt Kırılma (Crank Down)
      - Sağ/Alt Kuyruk (Tail)
    
    Parametreler:
    - L_ext_left: Sol/Üst döşemedeki DÜZ kısmın uzunluğu (Lb/5)
    - L_ext_right: Sağ/Alt döşemedeki DÜZ kısmın uzunluğu (Ln/5)
    - Kuyruklar: Lb/4 kadar uzatılır (sabit kabul veya parametrik).
    - d_crank: Kırılma yüksekliği (200mm)
    """
    
    d = 200.0  # Crank height/depth
    tail_factor = 1.25 # Tail = 1.25 * L_ext (approx Ln/4 if L_ext=Ln/5)
    # Ln/5 * 1.25 = Ln/4. Correct.
    
    tail_left = L_ext_left * tail_factor
    tail_right = L_ext_right * tail_factor
    
    half = bw_mm / 2.0
    
    # Koordinatlar (Merkeze göre)
    # Sol taraf (Left/Top)
    # Düz kısım bitişi (Start of Crank): Center - half - L_ext_left
    # Kuyruk başlangıcı (End of Crank): Start_Crank - d
    # Kuyruk ucu: End_Crank - tail_left
    
    pts = []
    
    if axis == "X":
        # Yatay Çizim
        # Sol Taraf
        x_flat_start = cx - half - L_ext_left
        x_crank_end = x_flat_start - d
        x_tail_end = x_crank_end - tail_left
        
        # Sağ Taraf
        x_flat_end = cx + half + L_ext_right
        x_crank_start_R = x_flat_end + d
        x_tail_end_R = x_crank_start_R + tail_right
        
        # Y koordinatları
        # Üst (Flat kısım): cy (veya cy + offset?) -> Merkezde olsun
        # Alt (Kuyruklar): cy - d (Aşağı kırılma) - User isteği: 45 derece
        
        # Noktalar (Soldan Sağa)
        pts.append((x_tail_end, cy - d))        # Sol Kuyruk Ucu
        pts.append((x_crank_end, cy - d))       # Sol Kırılma Alt
        pts.append((x_flat_start, cy))          # Sol Kırılma Üst
        pts.append((x_flat_end, cy))            # Sağ Kırılma Üst
        pts.append((x_crank_start_R, cy - d))   # Sağ Kırılma Alt
        pts.append((x_tail_end_R, cy - d))      # Sağ Kuyruk Ucu
        
        # Layer
        w.add_polyline(pts, layer="REB_EK_MESNET")
        
        # Text
        w.add_text(cx, cy + 30, f"Ek {choice.label()}", height=100, layer="TEXT", center=True)
        # Boyut çizgisi eklenebilir
        
    else: # Axis Y (Dikey)
        # Dikey Çizim (Y-axis down in GUI, but let's think logic)
        # Left arg -> Top (Smaller Y)
        # Right arg -> Bottom (Larger Y)
        
        # Üst Taraf (Top / Negative rel to center)
        y_flat_start = cy - half - L_ext_left
        y_crank_end = y_flat_start - d
        y_tail_end = y_crank_end - tail_left
        
        # Alt Taraf (Bottom / Positive rel to center)
        y_flat_end = cy + half + L_ext_right
        y_crank_start_B = y_flat_end + d
        y_tail_end_B = y_crank_start_B + tail_right
        
        # X koordinatları
        # Flat (Center): cx
        # Tail (Offset): cx - d (Sola kırılma? veya Sağa?)
        # Genelde pilye görünüşü: Kesit gibi.
        # Plan görünüşte: Pilye yatırılır.
        # Dikey donatı pilyesi X yönünde kırılır.
        # Sağa mı sola mı? 
        # Standart: Sağa kır (cx + d)
        
        x_main = cx
        x_shifted = cx + d # Sağa kırılmış hali (altta kalan kısım)
        
        # Noktalar (Üstten Alta)
        pts.append((x_shifted, y_tail_end))      # Üst Kuyruk Ucu
        pts.append((x_shifted, y_crank_end))     # Üst Kırılma Alt
        pts.append((x_main, y_flat_start))       # Üst Kırılma Üst
        pts.append((x_main, y_flat_end))         # Alt Kırılma Üst
        pts.append((x_shifted, y_crank_start_B)) # Alt Kırılma Alt
        pts.append((x_shifted, y_tail_end_B))    # Alt Kuyruk Ucu
        
        w.add_polyline(pts, layer="REB_EK_MESNET")
        w.add_text(x_main - 30, cy, f"Ek {choice.label()}", height=100, layer="TEXT", rotation=90, center=True)
