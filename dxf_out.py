import math
from typing import List, Tuple
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

    def add_text(self, x, y, text, height=200.0, layer="TEXT"):
        self.add_layer(layer)
        self.entities.append(("TEXT", layer, (x, y, height, text)))

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
                    x, y, h, txt = data
                    self._w(f, 0, "TEXT"); self._w(f, 8, layer)
                    self._w(f, 10, float(x)); self._w(f, 20, float(y)); self._w(f, 30, 0.0)
                    self._w(f, 40, float(h)); self._w(f, 1, txt)
            self._w(f, 0, "ENDSEC")
            self._w(f, 0, "EOF")

def _pilye_polyline(x0, y0, x1, y1, d=250.0, kink="both"):
    kink = (kink or "both").lower()
    if kink not in ("start", "end", "both", "none"): kink = "both"

    if abs(y1 - y0) < 1e-6: # Horizontal
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
        
    else: # Vertical
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

def export_to_dxf(system: SlabSystem, filename: str, design_cache: dict, bw_val: float):
    w = _DXFWriter()
    for ln in ["SLAB_EDGE", "BEAM", "REB_MAIN_X", "REB_MAIN_Y", "REB_DIST", "REB_SUPPORT", "TEXT"]:
        w.add_layer(ln)

    gdx, gdy = 0.0, 0.0
    if system.slabs:
        s0 = list(system.slabs.values())[0]
        gdx, gdy = s0.dx, s0.dy
    else:
        gdx, gdy = 0.25, 0.25 # fallback

    bw_mm = bw_val * 1000.0
    half = bw_mm / 2.0

    # BEAMS
    # Vertical beams
    for (i, j) in system.V_beam:
        # Simplified: draw each segment
        x = (i + 1) * gdx * 1000.0
        y0 = j * gdy * 1000.0
        y1 = (j + 1) * gdy * 1000.0
        w.add_polyline([(x - half, y0), (x + half, y0), (x + half, y1), (x - half, y1)], layer="BEAM", closed=True)
    
    # Horizontal beams
    for (i, j) in system.H_beam:
        y = (j + 1) * gdy * 1000.0
        x0 = i * gdx * 1000.0
        x1 = (i + 1) * gdx * 1000.0
        w.add_polyline([(x0, y - half), (x1, y - half), (x1, y + half), (x0, y + half)], layer="BEAM", closed=True)

    # SLABS
    for sid, s in system.slabs.items():
        # Panel Rect
        x0 = s.i0 * s.dx * 1000.0
        y0 = s.j0 * s.dy * 1000.0
        x1 = (s.i1 + 1) * s.dx * 1000.0
        y1 = (s.j1 + 1) * s.dy * 1000.0
        
        # Adjust for beams
        if system.slab_edge_has_beam(sid, "LEFT"): x0 += half
        if system.slab_edge_has_beam(sid, "RIGHT"): x1 -= half
        if system.slab_edge_has_beam(sid, "TOP"): y0 += half
        if system.slab_edge_has_beam(sid, "BOTTOM"): y1 -= half
        
        w.add_polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer="SLAB_EDGE", closed=True)
        w.add_text((x0+x1)/2, (y0+y1)/2, sid, height=420.0, layer="TEXT")

        dcache = design_cache.get(sid)
        if not dcache: continue

        cover = float(dcache.get("cover_mm", 25.0))
        ix0, iy0, ix1, iy1 = x0 + cover, y0 + cover, x1 - cover, y1 - cover
        if ix1 <= ix0 or iy1 <= iy0: continue

        kind = dcache.get("kind")
        midx = (ix0 + ix1) / 2.0
        midy = (iy0 + iy1) / 2.0

        if kind == "ONEWAY":
            auto_dir = dcache.get("auto_dir", "X")
            ch_main = dcache["choices"]["main"]
            ch_dist = dcache["choices"]["dist"]
            
            if auto_dir == "X":
                # Main X
                pts = _pilye_polyline(ix0, midy, ix1, midy, d=250.0, kink='both')
                w.add_polyline(pts, layer="REB_MAIN_X")
                w.add_text(ix0, midy + 250, ch_main.label(), height=280, layer="TEXT")
                # Dist Y
                w.add_line(midx, iy0, midx, iy1, layer="REB_DIST")
                w.add_text(midx + 200, iy1 + 200, f"D {ch_dist.label()}", height=260, layer="TEXT")
            else:
                # Main Y
                pts = _pilye_polyline(midx, iy0, midx, iy1, d=250.0, kink='both')
                w.add_polyline(pts, layer="REB_MAIN_Y")
                w.add_text(midx + 200, iy0, ch_main.label(), height=280, layer="TEXT")
                # Dist X
                w.add_line(ix0, midy, ix1, midy, layer="REB_DIST")
                w.add_text(ix0, midy + 250, f"D {ch_dist.label()}", height=260, layer="TEXT")

        elif kind == "TWOWAY":
            chx = dcache["choices"]["x_span"]
            chy = dcache["choices"]["y_span"]
            
            ptsx = _pilye_polyline(ix0, midy, ix1, midy, d=250.0, kink='both')
            w.add_polyline(ptsx, layer="REB_MAIN_X")
            w.add_text(ix0, midy + 250, f"X {chx.label()}", height=280, layer="TEXT")

            ptsy = _pilye_polyline(midx, iy0, midx, iy1, d=250.0, kink='both')
            w.add_polyline(ptsy, layer="REB_MAIN_Y")
            w.add_text(midx + 200, iy1 + 200, f"Y {chy.label()}", height=280, layer="TEXT")

        elif kind == "BALCONY":
            ch_main = dcache["choices"]["main"]
            ch_dist = dcache["choices"]["dist"]
            fixed = dcache.get("fixed_edge", "L")
            
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

    w.save(filename)
