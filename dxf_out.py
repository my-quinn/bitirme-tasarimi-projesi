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

    def add_layer(self, name: str, color: int = 7, lineweight: int = -3):
        """
        color: AutoCAD Color Index (ACI). 1=Red, 2=Yellow, 3=Green, 4=Cyan, 5=Blue, 6=Magenta, 7=White/Black
        lineweight: mm * 100. e.g. 50 = 0.50mm. -3 = Default.
        """
        if name not in self.layers_created and name != "0":
            layer = self.doc.layers.add(name)
            layer.color = color
            layer.lineweight = lineweight
            self.layers_created.add(name)

    def add_line(self, x1, y1, x2, y2, layer="0"):
        if layer not in self.layers_created and layer != "0":
             self.add_layer(layer)

        y1 = self._fy(y1)
        y2 = self._fy(y2)
        self.msp.add_line((x1, y1), (x2, y2), dxfattribs={'layer': layer})

    def add_polyline(self, pts, layer="0", closed=False):
        if layer not in self.layers_created and layer != "0":
             self.add_layer(layer)

        # pts listesi (x, y) tuple'larından oluşur
        new_pts = [(x, self._fy(y)) for x, y in pts]
        self.msp.add_lwpolyline(new_pts, dxfattribs={'layer': layer}, close=closed)

    def add_text(self, x, y, text, height=200.0, layer="TEXT", rotation=0.0, center=False, align_code=None):
        if layer not in self.layers_created and layer != "0":
             self.add_layer(layer)

        y = self._fy(y)
        
        txt = self.msp.add_text(text, dxfattribs={
            'layer': layer,
            'height': height,
            'rotation': rotation
        })
        if align_code:
             txt.set_placement((x, y), align=align_code)
        elif center:
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
    - Ana donatı (düz + pilye): sadece 1'er adet çizilir.
    - Dağıtma donatısı: 1-2 adet.
    - Yazı konumları: Line'dan 30mm uzakta, başlangıçtan Ln/6 ötede.
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
        # X yönü kısa -> Ana donatı Dikey (Y boyunca)
        Ln_long = Ly
        
        # --- 1. ANA DONATI (DÜZ + PİLYE) - Dikey ---
        x_duz = midx - 150
        x_pilye = midx + 150
        
        # Düz
        if ch_duz:
            pts_duz = _draw_straight_hit_polyline(x_duz, iy0, x_duz, iy1, bw_mm, bw_mm)
            w.add_polyline(pts_duz, layer="REB_MAIN_DUZ")
            
            # Label: Line'dan 30mm solda, Başlangıçtan (iy0) Ln/6 aşağıda.
            lbl_y = iy0 + (Ln_long / 6.0)
            w.add_text(x_duz - 30, lbl_y, f"düz  {ch_duz.label()}", height=100, layer="TEXT", rotation=90)

        # Pilye
        if ch_pilye:
            pts = _pilye_polyline(x_pilye, iy0, x_pilye, iy1, d=200.0, kink="both", hook_len=bw_mm, beam_ext=bw_mm)
            w.add_polyline(pts, layer="REB_MAIN_PILYE")
            
            # Label: Line'dan 30mm sağda
            lbl_y = iy0 + (Ln_long / 6.0)
            w.add_text(x_pilye + 30, lbl_y, f"pilye {ch_pilye.label()}", height=100, layer="TEXT", rotation=90)
        
        # --- 2. DAĞITMA DONATISI - Yatay ---
        if ch_dist:
            # Shift +40mm to create gap from Edge Support (which we will shift -40mm)
            y_dist = midy + 40.0
            hook_ext = bw_mm - 30.0
            pts = []
            
            # Sol (Check continuity)
            if not kisa_start_cont:
                pts.append((x0 - hook_ext, y_dist - hook_ext))
                pts.append((x0 - hook_ext, y_dist))
            else:
                pts.append((x0 - hook_ext, y_dist))
            
            # Sağ (Check continuity)
            if not kisa_end_cont:
                pts.append((x1 + hook_ext, y_dist))
                pts.append((x1 + hook_ext, y_dist - hook_ext))
            else:
                pts.append((x1 + hook_ext, y_dist))
                
            w.add_polyline(pts, layer="REB_DIST")
            # Label: Line üstü (+30), Başlangıçtan (x0) Lx/6 sağda
            w.add_text(x0 + (Lx / 6.0), y_dist + 30, f"dağıtma {ch_dist.label()}", height=100, layer="TEXT")

        # --- 3. KENAR MESNET (Yatay) ---
        # Shift -40mm (Average Y will be midy - 40)
        offset_support = 40.0
        
        if ch_kenar_start and not kisa_start_cont:
            hook_ext = bw_mm - 30.0
            ext = Lx / 4.0
            hook_x = x0 - hook_ext
            end_x = ix0 + ext
            _draw_support_rebar_horizontal(w, hook_x, iy0+300-offset_support, end_x, iy1-300-offset_support, 1, "REB_KENAR", ch_kenar_start.label(),
                                           hook_start=True, hook_len=hook_ext)
            
        if ch_kenar_end and not kisa_end_cont:
            hook_ext = bw_mm - 30.0
            ext = Lx / 4.0
            start_x = ix1 - ext
            hook_x = x1 + hook_ext
            _draw_support_rebar_horizontal(w, start_x, iy0+300-offset_support, hook_x, iy1-300-offset_support, 1, "REB_KENAR", ch_kenar_end.label(),
                                           hook_end=True, hook_len=hook_ext)

        # --- 4. İÇ MESNET (Yatay) ---
        if ch_ic_start and kisa_start_cont:
            L4 = Lx / 4.0
            L8 = Lx / 8.0
            d_crank = 200.0
            start_x = x0 - (bw_mm / 2.0)
            y = midy - 300 
            pts = [
                (start_x, y),
                (x0 + L4, y),
                (x0 + L4 + d_crank, y - d_crank),
                (x0 + L4 + d_crank + L8, y - d_crank)
            ]
            w.add_polyline(pts, layer="REB_IC_MESNET")
            w.add_text(x0 + L4/2, y + 30, f"{ch_ic_start.label()}", height=80, layer="TEXT")

        if ch_ic_end and kisa_end_cont:
            L4 = Lx / 4.0
            L8 = Lx / 8.0
            d_crank = 200.0
            start_x = x1 + (bw_mm / 2.0)
            y = midy - 300
            pts = [
                (start_x, y),
                (x1 - L4, y),
                (x1 - L4 - d_crank, y - d_crank),
                (x1 - L4 - d_crank - L8, y - d_crank)
            ]
            w.add_polyline(pts, layer="REB_IC_MESNET")
            w.add_text(x1 - L4/2, y + 30, f"{ch_ic_end.label()}", height=80, layer="TEXT")

        # --- 5. MESNET EK (Dikey) ---
        if ch_ek_start and uzun_start_cont: # Top
            L_ext = Ln_long / 5.0
            offset_val = 600.0
            _draw_support_extra_y(w, midx + offset_val, y0, bw_mm, ch_ek_start, L_ext, is_top=True)
            
        if ch_ek_end and uzun_end_cont: # Bottom
            L_ext = Ln_long / 5.0
            offset_val = 600.0
            _draw_support_extra_y(w, midx + offset_val, y1, bw_mm, ch_ek_end, L_ext, is_top=False)
            
    else:  # auto_dir == "Y"
        Ln_long = Lx
        
        # --- 1. ANA DONATI (DÜZ + PİLYE) - Yatay ---
        y_duz = midy - 150
        y_pilye = midy + 150
        
        if ch_duz:
            pts_duz = _draw_straight_hit_polyline(ix0, y_duz, ix1, y_duz, bw_mm, bw_mm)
            w.add_polyline(pts_duz, layer="REB_MAIN_DUZ")
            w.add_text(x0 + (Ln_long / 6.0), y_duz + 30, f"düz {ch_duz.label()}", height=100, layer="TEXT")
            
        if ch_pilye:
            pts = _pilye_polyline(ix0, y_pilye, ix1, y_pilye, d=200.0, kink="both", hook_len=bw_mm, beam_ext=bw_mm)
            w.add_polyline(pts, layer="REB_MAIN_PILYE")
            w.add_text(x0 + (Ln_long / 6.0), y_pilye + 30, f"pilye {ch_pilye.label()}", height=100, layer="TEXT")

        # --- 2. DAĞITMA (Dikey) ---
        if ch_dist:
            # Shift +40mm from Center
            x_dist = midx + 40.0
            hook_ext = bw_mm - 30.0
            pts = []
            if not kisa_start_cont:
                 pts.append((x_dist - hook_ext, y0 - hook_ext))
                 pts.append((x_dist, y0 - hook_ext))
                 pts.append((x_dist, y0))
            else:
                 pts.append((x_dist, y0)) 
            
            if not kisa_end_cont:
                 pts.append((x_dist, y1))
                 pts.append((x_dist, y1 + hook_ext))
                 pts.append((x_dist - hook_ext, y1 + hook_ext))
            else:
                 pts.append((x_dist, y1))
            
            w.add_polyline(pts, layer="REB_DIST")
            lbl_y = y0 + (Ly / 6.0)
            w.add_text(x_dist + 30, lbl_y, f"dağıtma {ch_dist.label()}", height=100, layer="TEXT", rotation=90)

        # --- 3. KENAR MESNET (Dikey) ---
        # Shift -40mm from Center
        offset_support = 40.0
        
        if ch_kenar_start and not kisa_start_cont: # Top
            hook_ext = bw_mm - 30.0
            ext = Ly / 4.0
            hook_y = y0 - hook_ext
            end_y = iy0 + ext
            _draw_support_rebar_vertical(w, ix0+300-offset_support, hook_y, ix1-300-offset_support, end_y, 1, "REB_KENAR", ch_kenar_start.label(), hook_start=True, hook_len=hook_ext)
            
        if ch_kenar_end and not kisa_end_cont: # Bottom
            hook_ext = bw_mm - 30.0
            ext = Ly / 4.0
            start_y = iy1 - ext
            hook_y = y1 + hook_ext
            _draw_support_rebar_vertical(w, ix0+300-offset_support, start_y, ix1-300-offset_support, hook_y, 1, "REB_KENAR", ch_kenar_end.label(), hook_end=True, hook_len=hook_ext)

        # --- 4. İÇ MESNET (Dikey) ---
        if ch_ic_start and kisa_start_cont: # Top
            L4 = Ly / 4.0
            L8 = Ly / 8.0
            d_crank = 200.0
            start_y = y0 - (bw_mm / 2.0)
            x = midx - 300
            pts = [
                (x, start_y),
                (x, y0 + L4),
                (x - d_crank, y0 + L4 + d_crank),
                (x - d_crank, y0 + L4 + d_crank + L8)
            ]
            w.add_polyline(pts, layer="REB_IC_MESNET")
            w.add_text(x - 30, y0 + L4/2, f"{ch_ic_start.label()}", height=80, layer="TEXT", rotation=90)
            
        if ch_ic_end and kisa_end_cont: # Bottom
            L4 = Ly / 4.0
            L8 = Ly / 8.0
            d_crank = 200.0
            start_y = y1 + (bw_mm / 2.0)
            x = midx - 300
            pts = [
                (x, start_y),
                (x, y1 - L4),
                (x - d_crank, y1 - L4 - d_crank),
                (x - d_crank, y1 - L4 - d_crank - L8)
            ]
            w.add_polyline(pts, layer="REB_IC_MESNET")
            w.add_text(x - 30, y1 - L4/2, f"{ch_ic_end.label()}", height=80, layer="TEXT", rotation=90)

        # --- 5. EK MESNET (Yatay) ---
        if ch_ek_start and uzun_start_cont: # Left
            L_ext = Ln_long / 5.0
            offset_val = 600.0
            _draw_support_extra_x(w, x0, midy + offset_val, bw_mm, ch_ek_start, L_ext, is_left=True)
            
        if ch_ek_end and uzun_end_cont: # Right
            L_ext = Ln_long / 5.0
            offset_val = 600.0
            _draw_support_extra_x(w, x1, midy + offset_val, bw_mm, ch_ek_end, L_ext, is_left=False)


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
    # Renk Kodları (ACI): 1=Red, 2=Yellow, 3=Green, 4=Cyan, 5=Blue, 6=Magenta, 7=White
    layer_defs = [
        ("SLAB_EDGE", 7, 25),       # White, Thin
        ("BEAM", 7, 50),            # White, Thick (0.50mm)
        ("REB_MAIN_DUZ", 1, -3),    # Red
        ("REB_MAIN_PILYE", 1, -3),  # Red
        ("REB_DIST", 2, -3),        # Yellow
        ("REB_KENAR", 3, -3),       # Green
        ("REB_IC_MESNET", 5, -3),   # Blue
        ("REB_EK_MESNET", 4, -3),   # Cyan
        ("REB_BALCONY_MAIN", 6, -3),# Magenta
        ("REB_BALCONY_DIST", 30, -3),# Orange (30 is usually orange-ish)
        ("TEXT", 7, -3),
        ("DIM", 7, -3)
    ]
    
    for name, color, weight in layer_defs:
        w.add_layer(name, color=color, lineweight=weight)

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
    beam_ext_pilye = bw_mm - 30.0
    beam_ext_duz = bw_mm - 30.0 - 50.0

    # =========================================================
    # 1. X YÖNÜ DONATILARI (Yatay Çizilenler)
    # =========================================================
    ch_x_duz = choices.get("x_span_duz")
    ch_x_pilye = choices.get("x_span_pilye")
    ch_x_ek = choices.get("x_support_extra")

    # Spacing hesapla (Offset için)
    # Düz ve Pilye arası mesafe 's' kadar olsun. 
    sx = ch_x_pilye.s_mm if ch_x_pilye else 200.0
    if ch_x_duz: sx = ch_x_duz.s_mm
    
    # Y koordinatları: Pilye üstte (+), Düz altta (-)
    y_pilye_x = midy + (sx / 2.0)
    y_duz_x = midy - (sx / 2.0)

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

        w.add_polyline(pts, layer="REB_MAIN_DUZ")
        # Label: Line Altı (-30), Başlangıçtan (x0) Lx/6 sağda
        w.add_text(x0 + (Lx / 6.0), y_duz_x - 30, f"X düz {ch_x_duz.label()}", height=100, layer="TEXT", center=True)

    # X Yönü Pilye Donatı
    if ch_x_pilye:
        # Pilye kancaları: Pilye (üst), süreksiz kenarda kanca AŞAĞI.
        pts = _pilye_polyline(x0, y_pilye_x, x1, y_pilye_x, d=200.0, kink="both", hook_len=hook_len, beam_ext=beam_ext_pilye)
        w.add_polyline(pts, layer="REB_MAIN_PILYE")
        # Label: Line Üstü (+30), Başlangıçtan (x0) Lx/6 sağda
        w.add_text(x0 + (Lx / 6.0), y_pilye_x + 30, f"X pilye {ch_x_pilye.label()}", height=100, layer="TEXT", center=True)

    # X Yönü Mesnet Ek
    if ch_x_ek:
        # Mesnet ekleri: SADECE SAĞ (R) KENARDA ÇİZİLİR (Süreklilik varsa)
        if cont_R:
             # Sağ Komşuyu bul
            neighbor_id, neighbor_kind = _get_neighbor_id_on_edge(system, sid, "R")
            L_ext_self = Lx / 5.0
            L_ext_neigh = L_ext_self
            
            if neighbor_id and system:
                try:
                    ns = system.slabs[neighbor_id]
                    nLx_g, _ = ns.size_m_gross()
                    nLx = (nLx_g * 1000.0) - bw_mm 
                    if nLx > 0:
                        L_ext_neigh = nLx / 5.0
                except:
                    pass
            
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

        w.add_polyline(pts, layer="REB_MAIN_DUZ")
        # Label: Line Solu (-30), Başlangıçtan (y0) Ly/6 aşağıda
        lbl_y = y0 + (Ly / 6.0)
        w.add_text(x_duz_y - 30, lbl_y, f"Y düz {ch_y_duz.label()}", height=100, layer="TEXT", rotation=90, center=True)

    # Y Yönü Pilye Donatı
    if ch_y_pilye:
        pts = _pilye_polyline(x_pilye_y, y0, x_pilye_y, y1, d=200.0, kink="both", hook_len=hook_len, beam_ext=beam_ext_pilye)
        w.add_polyline(pts, layer="REB_MAIN_PILYE")
        # Label: Line Sağı (+60? -> 30?), Ly/6
        lbl_y = y0 + (Ly / 6.0)
        w.add_text(x_pilye_y + 30, lbl_y, f"Y pilye {ch_y_pilye.label()}", height=100, layer="TEXT", rotation=90, center=True)

    # Y Yönü Mesnet Ek
    if ch_y_ek:
        # Sadece ALT (B) Kenarda Çiz
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
            
            _draw_hat_bar(w, cx, cy, bw_mm, ch_y_ek, 
                          L_ext_left=L_ext_self, L_ext_right=L_ext_neigh, 
                          axis="Y")

    # Döşeme ID'si (Center) -> YANLIŞ. User "döşeme isimleri her tür döşeme için sadece kenarda yazılı kalsın... çift ve balkon döşemesi için ortaya yazılı oralak kroki çiziliyor onu kaldır."
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
    - Serbest kenarda kanca yapar (AŞAĞI/İÇE).
    - Dağıtma donatısı diğer yönde.
    """
    cover = float(dcache.get("cover_mm", 25.0))
    ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
    midx = (ix0 + ix1) / 2.0
    midy = (iy0 + iy1) / 2.0
    
    Lx = ix1 - ix0
    Ly = iy1 - iy0
    
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
        layer = "REB_BALCONY_MAIN"
        
        if fixed == "L":
            # Sol taraf sabit, Sağ taraf serbest
            y_pos = midy
            pts.append((x0 - L_anchor, y_pos)) # Komşu içi
            pts.append((x1 + beam_ext, y_pos)) # Sağ uç
            pts.append((x1 + beam_ext, y_pos + hook_len)) # Kanca AŞAĞI
            
            w.add_polyline(pts, layer=layer)
            # Label: Line Altı (-30), Başlangıç (x0) dan Lx/6 sağa? 
            # Balkon genelde kısa, Ln/6 uygun.
            w.add_text(x0 + (Lx / 6.0), y_pos - 30, f"Ana {ch_main.label()}", height=100, layer="TEXT")
            
            # Dağıtma (Dikey)
            if ch_dist:
                pts_dist = []
                x_dist = midx
                pts_dist.append((x_dist, iy0))
                pts_dist.append((x_dist, iy1))
                w.add_line(x_dist, iy0, x_dist, iy1, layer="REB_BALCONY_DIST")
                # Label
                w.add_text(x_dist + 30, iy0 + (Ly / 6.0), f"Dağ. {ch_dist.label()}", height=80, layer="TEXT", rotation=90)

        elif fixed == "R":
            # Sağ taraf sabit, Sol taraf serbest
            y_pos = midy
            pts.append((x1 + L_anchor, y_pos)) # Komşu içi
            pts.append((x0 - beam_ext, y_pos)) # Sol uç
            pts.append((x0 - beam_ext, y_pos + hook_len)) # Kanca AŞAĞI
            
            w.add_polyline(pts, layer=layer)
            w.add_text(x1 - (Lx / 6.0) - 100, y_pos - 30, f"Ana {ch_main.label()}", height=100, layer="TEXT") # Sağdan sola yaz?
            
             # Dağıtma (Dikey)
            if ch_dist:
                x_dist = midx
                w.add_line(x_dist, iy0, x_dist, iy1, layer="REB_BALCONY_DIST")
                w.add_text(x_dist + 30, iy0 + (Ly / 6.0), f"Dağ. {ch_dist.label()}", height=80, layer="TEXT", rotation=90)

        elif fixed == "T":
            # Üst taraf sabit, Alt taraf serbest
            x_pos = midx
            pts.append((x_pos, y0 - L_anchor)) # Komşu içi (Yukarı)
            pts.append((x_pos, y1 + beam_ext)) # Alt uç
            pts.append((x_pos + hook_len, y1 + beam_ext)) # Kanca Sağa
            
            w.add_polyline(pts, layer=layer)
            # Label
            w.add_text(x_pos + 30, y0 + (Ly / 6.0), f"Ana {ch_main.label()}", height=100, layer="TEXT", rotation=90)

            # Dağıtma (Yatay)
            if ch_dist:
                y_dist = midy
                w.add_line(ix0, y_dist, ix1, y_dist, layer="REB_BALCONY_DIST")
                w.add_text(ix0 + (Lx / 6.0), y_dist - 30, f"Dağ. {ch_dist.label()}", height=80, layer="TEXT")

        elif fixed == "B":
            # Alt taraf sabit, Üst taraf serbest
            x_pos = midx
            pts.append((x_pos, y1 + L_anchor)) # Komşu içi (Aşağı)
            pts.append((x_pos, y0 - beam_ext)) # Üst uç
            pts.append((x_pos + hook_len, y0 - beam_ext)) # Kanca "Sağa"
            
            w.add_polyline(pts, layer=layer)
            w.add_text(x_pos + 30, y1 - (Ly/6.0) - 200, f"Ana {ch_main.label()}", height=100, layer="TEXT", rotation=90)

             # Dağıtma (Yatay)
            if ch_dist:
                y_dist = midy
                w.add_line(ix0, y_dist, ix1, y_dist, layer="REB_BALCONY_DIST")
                w.add_text(ix0 + (Lx / 6.0), y_dist - 30, f"Dağ. {ch_dist.label()}", height=80, layer="TEXT")

    # w.add_text(midx, midy, sid, ...) # REMOVED CENTER TEXT


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
