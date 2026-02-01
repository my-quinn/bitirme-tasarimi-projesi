import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import os
from typing import Tuple

from constants import CONCRETE_FCK, STEEL_FYK
from struct_design import (
    oneway_smax_main, oneway_smax_dist, twoway_smax_short, twoway_smax_long,
    asb_min_area, split_duz_pilye, select_rebar_min_area, max_possible_area,
    rho_min_oneway
)
from slab_model import SlabSystem, Slab, color_for_id, clamp, rect_normalize
from dxf_out import export_to_dxf

# Yeni modüller - hesap ve raporlama
from oneway_slab import compute_oneway_report
from twoway_slab import compute_twoway_report
from moment_balance_slab import balance_support_moments
from balcony_slab import compute_balcony_report

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Döşeme Yerleşimi + Moment + As + Donatı Seçimi (TS500/Uygulama)")
        self.geometry("1600x900")

        self.Nx, self.Ny = 22, 12
        self.cell_px = 38
        self.system = SlabSystem(self.Nx, self.Ny)

        # inputs
        self.dx_m = tk.DoubleVar(value=0.25)
        self.dy_m = tk.DoubleVar(value=0.25)
        self.pd = tk.DoubleVar(value=10.0)
        self.b_width = tk.DoubleVar(value=1.0)
        self.bw = tk.DoubleVar(value=0.30)

        # rebar inputs
        self.conc = tk.StringVar(value="C25/30")
        self.steel = tk.StringVar(value="B420C")
        self.h_mm = tk.DoubleVar(value=120.0)
        self.cover_mm = tk.DoubleVar(value=25.0)

        self.mode = tk.StringVar(value="PLACE_ONEWAY")
        self.current_selection = None
        self.drag_start_cell = None
        self.last_design = {}

        self._build_ui()
        self.redraw()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        # Parameters
        prm = ttk.LabelFrame(top, text="Yeni Döşeme Parametreleri")
        prm.pack(side="left", fill="x", expand=True)

        r=0
        ttk.Label(prm, text="dx:").grid(row=r, column=0)
        ttk.Entry(prm, textvariable=self.dx_m, width=6).grid(row=r, column=1)
        ttk.Label(prm, text="dy:").grid(row=r, column=2)
        ttk.Entry(prm, textvariable=self.dy_m, width=6).grid(row=r, column=3)
        ttk.Label(prm, text="pd:").grid(row=r, column=4)
        ttk.Entry(prm, textvariable=self.pd, width=6).grid(row=r, column=5)
        ttk.Label(prm, text="b:").grid(row=r, column=6)
        ttk.Entry(prm, textvariable=self.b_width, width=6).grid(row=r, column=7)
        ttk.Label(prm, text="bw:").grid(row=r, column=8)
        ttk.Entry(prm, textvariable=self.bw, width=6).grid(row=r, column=9)

        # Materials
        reb = ttk.LabelFrame(top, text="Malzeme / h")
        reb.pack(side="left", padx=10)
        ttk.Combobox(reb, textvariable=self.conc, values=list(CONCRETE_FCK.keys()), width=8).grid(row=0, column=0)
        ttk.Combobox(reb, textvariable=self.steel, values=list(STEEL_FYK.keys()), width=8).grid(row=1, column=0)
        ttk.Entry(reb, textvariable=self.h_mm, width=6).grid(row=0, column=1)
        ttk.Label(reb, text="h(mm)").grid(row=0, column=2)
        ttk.Entry(reb, textvariable=self.cover_mm, width=6).grid(row=1, column=1)
        ttk.Label(reb, text="cover").grid(row=1, column=2)

        # Tools
        tools = ttk.LabelFrame(top, text="Araçlar")
        tools.pack(side="left", padx=10)
        modes = [
            ("Yerleştir: ONEWAY", "PLACE_ONEWAY"),
            ("Yerleştir: TWOWAY", "PLACE_TWOWAY"),
            ("Yerleştir: BALCONY", "PLACE_BALCONY"),
            ("Dikey Kiriş (V)", "VBEAM"),
            ("Yatay Kiriş (H)", "HBEAM"),
            ("Sil (Döşeme)", "ERASE")
        ]
        for i, (txt, val) in enumerate(modes):
            ttk.Radiobutton(tools, text=txt, variable=self.mode, value=val).grid(row=i//3, column=i%3, sticky="w")
        
        act = ttk.Frame(top)
        act.pack(side="right")
        ttk.Button(act, text="Hesapla", command=self.compute_and_report).pack(fill="x")
        ttk.Button(act, text="DXF", command=self.export_dxf_and_open).pack(fill="x")
        ttk.Button(act, text="Temizle", command=self.reset_all).pack(fill="x")

        # Main Area
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=8)

        self.canvas = tk.Canvas(mid, bg="white")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        right = ttk.Frame(mid, width=600)
        right.pack(side="left", fill="y", padx=10)
        
        self.slab_list = tk.Listbox(right, height=8)
        self.slab_list.pack(fill="x")
        ttk.Button(right, text="Seçiliyi Sil", command=self.delete_selected_slab).pack()
        
        self.output = tk.Text(right, wrap="word", height=30)
        self.output.pack(fill="both", expand=True, pady=5)

    def reset_all(self):
        self.system = SlabSystem(self.Nx, self.Ny)
        self.output.delete("1.0", "end")
        self.refresh_slab_list()
        self.redraw()

    def refresh_slab_list(self):
        self.slab_list.delete(0, "end")
        for sid in sorted(self.system.slabs.keys()):
            s = self.system.slabs[sid]
            nx, ny = s.size_cells()
            Lx_g, Ly_g = s.size_m_gross()
            self.slab_list.insert("end", f"{sid} ({s.kind}) {nx}x{ny} Lx={Lx_g:.2f}")

    def delete_selected_slab(self):
        idx = self.slab_list.curselection()
        if not idx: return
        sid = self.slab_list.get(idx[0]).split()[0]
        self.system.delete_slab(sid)
        self.refresh_slab_list()
        self.redraw()

    def redraw(self):
        self.canvas.delete("all")
        w = self.Nx * self.cell_px
        h = self.Ny * self.cell_px
        self.canvas.config(width=w, height=h)

        # slabs
        for (i, j), sid in self.system.cell_owner.items():
            x0, y0 = i*self.cell_px, j*self.cell_px
            self.canvas.create_rectangle(x0, y0, x0+self.cell_px, y0+self.cell_px, fill=color_for_id(sid), outline="")

        # grid
        for i in range(self.Nx + 1):
            x = i * self.cell_px
            self.canvas.create_line(x, 0, x, h, fill="#dddddd")
        for j in range(self.Ny + 1):
            y = j * self.cell_px
            self.canvas.create_line(0, y, w, y, fill="#dddddd")

        # beams
        for (i, j) in self.system.V_beam:
            x = (i+1)*self.cell_px
            y0, y1 = j*self.cell_px, (j+1)*self.cell_px
            self.canvas.create_line(x, y0, x, y1, width=4, fill="#111111")
        for (i, j) in self.system.H_beam:
            y = (j+1)*self.cell_px
            x0, x1 = i*self.cell_px, (i+1)*self.cell_px
            self.canvas.create_line(x0, y, x1, y, width=4, fill="#111111")

        # labels
        for sid, s in self.system.slabs.items():
            x0, y0 = s.i0 * self.cell_px, s.j0 * self.cell_px
            x1, y1 = (s.i1 + 1) * self.cell_px, (s.j1 + 1) * self.cell_px
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#000000", width=2)
            self.canvas.create_text((x0+x1)/2, (y0+y1)/2, text=f"{sid}\n{s.kind}", font=("Arial", 10, "bold"))

    def cell_from_xy(self, x, y):
        i = clamp(int(x // self.cell_px), 0, self.Nx - 1)
        j = clamp(int(y // self.cell_px), 0, self.Ny - 1)
        return i, j

    def get_edge_hit(self, x, y):
        i_f, j_f = x / self.cell_px, y / self.cell_px
        if self.mode.get() == "VBEAM":
            i_line = clamp(int(round(i_f)), 0, self.Nx)
            # between i_line-1 and i_line
            return "V", (clamp(i_line - 1, 0, self.Nx - 2), clamp(int(j_f), 0, self.Ny-1))
        if self.mode.get() == "HBEAM":
            j_line = clamp(int(round(j_f)), 0, self.Ny)
            return "H", (clamp(int(i_f), 0, self.Nx-1), clamp(j_line - 1, 0, self.Ny - 2))
        return None, None

    def on_mouse_down(self, evt):
        mode = self.mode.get()
        if mode.startswith("PLACE_"):
            self.drag_start_cell = self.cell_from_xy(evt.x, evt.y)
            i0, j0 = self.drag_start_cell
            x0, y0 = i0*self.cell_px, j0*self.cell_px
            self.current_selection = self.canvas.create_rectangle(x0, y0, x0+self.cell_px, y0+self.cell_px, outline="red", width=2)
        elif mode in ("VBEAM", "HBEAM"):
            t, key = self.get_edge_hit(evt.x, evt.y)
            if t == "V":
                if key in self.system.V_beam: self.system.V_beam.remove(key)
                else: self.system.V_beam.add(key)
            elif t == "H":
                if key in self.system.H_beam: self.system.H_beam.remove(key)
                else: self.system.H_beam.add(key)
            self.redraw()
        elif mode == "ERASE":
            i, j = self.cell_from_xy(evt.x, evt.y)
            sid = self.system.cell_owner.get((i, j))
            if sid:
                self.system.delete_slab(sid)
                self.refresh_slab_list()
                self.redraw()

    def on_mouse_drag(self, evt):
        if not self.drag_start_cell or not self.current_selection: return
        i1, j1 = self.cell_from_xy(evt.x, evt.y)
        i0, j0 = self.drag_start_cell
        (a0, b0), (a1, b1) = rect_normalize((i0, j0), (i1, j1))
        self.canvas.coords(self.current_selection, a0*self.cell_px, b0*self.cell_px, (a1+1)*self.cell_px, (b1+1)*self.cell_px)

    def on_mouse_up(self, evt):
        if not self.drag_start_cell or not self.current_selection: return
        
        i1, j1 = self.cell_from_xy(evt.x, evt.y)
        i0, j0 = self.drag_start_cell
        (a0, b0), (a1, b1) = rect_normalize((i0, j0), (i1, j1))
        
        self.canvas.delete(self.current_selection)
        self.current_selection = None; self.drag_start_cell = None

        sid = simpledialog.askstring("ID", "Döşeme ID:", parent=self)
        if not sid: return
        
        kind = "ONEWAY"
        if "TWOWAY" in self.mode.get(): kind = "TWOWAY"
        if "BALCONY" in self.mode.get(): kind = "BALCONY"

        if sid in self.system.slabs:
            if not messagebox.askyesno("Overwrite", f"{sid} zaten var. Ezilsin mi?"): return
            self.system.delete_slab(sid)

        # Check collision
        for i in range(a0, a1+1):
            for j in range(b0, b1+1):
                if (i, j) in self.system.cell_owner:
                    messagebox.showerror("Hata", "Çakışma var!")
                    return

        s = Slab(sid, a0, b0, a1, b1, kind, self.dx_m.get(), self.dy_m.get(), self.pd.get(), self.b_width.get())
        self.system.add_slab(s)
        self.refresh_slab_list()
        self.redraw()

    def compute_and_report(self):
        if not self.system.slabs: return
        
        self.output.delete("1.0", "end")
        conc = self.conc.get(); steel = self.steel.get()
        h = self.h_mm.get(); cover = self.cover_mm.get()
        bw = self.bw.get()
        
        self.output.insert("end", f"Hesap Raporu\nBeton: {conc}, Çelik: {steel}, h={h}mm, cover={cover}mm\n\n")
        self.last_design = {}
        
        # ==== İKİ GEÇİŞLİ HESAPLAMA ====
        # 1. Geçiş: Tüm döşemelerin temel donatılarını hesapla ve pilye alanlarını topla
        pilye_areas = {}  # {sid: pilye_area_mm2_per_m}
        moment_results = {}  # {sid: (res, steps)}
        
        for sid in sorted(self.system.slabs.keys()):
            s = self.system.slabs[sid]
            try:
                if s.kind == "ONEWAY":
                    res, steps = self.system.compute_oneway_per_slab(sid, bw)
                    moment_results[sid] = (res, steps)
                    # İlk geçişte sadece pilye hesabı için temel donatıyı bul
                    from oneway_slab import oneway_smax_main
                    from struct_design import split_duz_pilye, twoway_smax_short
                    Mpos = res["Mpos_max"] or 0.0
                    smax = oneway_smax_main(h)
                    As_main, ch_main, _ = self.system.design_main_rebar_from_M(
                        Mpos, conc, steel, h, cover, smax, label_prefix="")
                    _, pilye = split_duz_pilye(ch_main)
                    pilye_areas[sid] = pilye.area_mm2_per_m
                elif s.kind == "TWOWAY":
                    res, steps = self.system.compute_twoway_per_slab(sid, bw)
                    moment_results[sid] = (res, steps)
                    # TWOWAY için de pilye hesabı yap
                    from struct_design import split_duz_pilye, twoway_smax_short, twoway_smax_long
                    short_dir = res.get("short_dir", "X")
                    mxn, mxp = res["Mx"]
                    myn, myp = res["My"]
                    # Kısa yön donatısı (daha büyük moment)
                    if short_dir == "X":
                        Mpos_short = mxp or 0.0
                        smax_short = twoway_smax_short(h)
                    else:
                        Mpos_short = myp or 0.0
                        smax_short = twoway_smax_short(h)
                    As_main, ch_main, _ = self.system.design_main_rebar_from_M(
                        Mpos_short, conc, steel, h, cover, smax_short, label_prefix="")
                    _, pilye = split_duz_pilye(ch_main)
                    pilye_areas[sid] = pilye.area_mm2_per_m
                elif s.kind == "BALCONY":
                    res, steps = self.system.compute_balcony_per_slab(sid, bw)
                    moment_results[sid] = (res, steps)
            except Exception as e:
                moment_results[sid] = None
        
        # 1.5 Geçiş: TWOWAY döşemeler için mesnet dengelemesi (TS500)
        raw_twoway_moments = {sid: res for sid, (res, _) in moment_results.items() 
                              if res is not None and self.system.slabs.get(sid) and self.system.slabs[sid].kind == "TWOWAY"}
        
        # ONEWAY döşemeleri de ekle (TWOWAY-ONEWAY dengelemesi için)
        for sid, val in moment_results.items():
            if val is not None and self.system.slabs.get(sid) and self.system.slabs[sid].kind == "ONEWAY":
                raw_twoway_moments[sid] = val[0]
        
        balanced_moments = {}
        balance_log = []
        if raw_twoway_moments:
            balanced_moments, balance_log = balance_support_moments(self.system, raw_twoway_moments, bw)
        
        # Dengeleme logunu yazdır
        if balance_log:
            self.output.insert("end", "=== MESNET DENGELEMESİ (TS500) ===\n")
            for line in balance_log:
                self.output.insert("end", line + "\n")
            self.output.insert("end", "\n")
        
        # 2. Geçiş: Tüm döşemelerin tam donatı hesabını yap (pilye bilgileriyle)
        for sid in sorted(self.system.slabs.keys()):
            s = self.system.slabs[sid]
            self.output.insert("end", f"--- {sid} ({s.kind}) ---\n")
            try:
                if moment_results.get(sid) is None:
                    self.output.insert("end", "HATA: Moment hesabı başarısız\n\n")
                    continue
                    
                res, steps = moment_results[sid]
                design_res = {}
                
                if s.kind == "ONEWAY":
                    for l in steps:
                        self.output.insert("end", l + "\n")
                    
                    # Donatı hesabı ve raporlama (komşu pilye alanlarıyla)
                    design_res, report_lines = compute_oneway_report(
                        self.system, sid, res, conc, steel, h, cover, bw,
                        neighbor_pilye_areas=pilye_areas
                    )
                    for l in report_lines:
                        self.output.insert("end", l + "\n")

                elif s.kind == "TWOWAY":
                    for l in steps:
                        self.output.insert("end", l + "\n")
                    
                    # Dengelenmiş momentleri kullan
                    balanced_res = balanced_moments.get(sid, res)
                    if balanced_res:
                        # Dengelenmiş momentler varsa göster
                        mxn_bal, mxp_bal = balanced_res.get("Mx", (None, None))
                        myn_bal, myp_bal = balanced_res.get("My", (None, None))
                        mxn_orig, _ = res.get("Mx", (None, None))
                        myn_orig, _ = res.get("My", (None, None))
                        if mxn_bal != mxn_orig or myn_bal != myn_orig:
                            self.output.insert("end", f"Dengelenmiş momentler: Mx_neg={mxn_bal:.3f}, My_neg={myn_bal:.3f}\n")
                        res = balanced_res
                    
                    design_res, report_lines = compute_twoway_report(
                        self.system, sid, res, conc, steel, h, cover, bw,
                        neighbor_pilye_areas=pilye_areas
                    )
                    for l in report_lines:
                        self.output.insert("end", l + "\n")

                elif s.kind == "BALCONY":
                    for l in steps:
                        self.output.insert("end", l + "\n")
                    
                    design_res, report_lines = compute_balcony_report(
                        self.system, sid, res, conc, steel, h, cover, bw
                    )
                    for l in report_lines:
                        self.output.insert("end", l + "\n")

                self.last_design[sid] = design_res

            except Exception as e:
                self.output.insert("end", f"HATA: {e}\n\n")

    def export_dxf_and_open(self):
        if not self.last_design:
            self.compute_and_report()
        if not self.last_design: return # still empty?

        fname = simpledialog.askstring("DXF", "Dosya adı (örn: plan.dxf):", parent=self)
        if not fname: return
        if not fname.lower().endswith(".dxf"): fname += ".dxf"
        
        try:
            export_to_dxf(self.system, fname, self.last_design, self.bw.get())
            messagebox.showinfo("OK", f"Kaydedildi: {fname}")
            try:
                os.startfile(os.path.abspath(fname))
            except:
                pass
        except Exception as e:
            messagebox.showerror("Hata", str(e))
