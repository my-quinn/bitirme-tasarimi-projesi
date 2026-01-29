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

        for sid in sorted(self.system.slabs.keys()):
            s = self.system.slabs[sid]
            self.output.insert("end", f"--- {sid} ({s.kind}) ---\n")
            try:
                design_res = {}
                if s.kind == "ONEWAY":
                    res, steps = self.system.compute_oneway_per_slab(sid, bw)
                    for l in steps: self.output.insert("end", l+"\n")
                    
                    Mpos = res["Mpos_max"] or 0.0
                    Mneg = res["Mneg_min"] or 0.0
                    smax = oneway_smax_main(h)
                    d_mm = h - cover  # efektif derinlik
                    
                    # Kenar süreklilik analizi - TÜM 4 KENAR BAĞIMSIZ KONTROL
                    chain = res.get("chain", [sid])
                    auto_dir = res.get("auto_dir", "X")
                    
                    # Tüm kenarların komşuluk durumunu al
                    # (Lf, Rf, Tf, Bf) = (Left_full, Right_full, Top_full, Bottom_full)
                    (Lf, Rf, Tf, Bf), (La, Ra, Ta, Ba), _ = self.system.twoway_edge_continuity_full(sid)
                    
                    # Her kenardaki süreklilik durumu (komşu döşeme var mı?)
                    kenar_L_surekli = Lf or La  # Sol kenarda herhangi bir komşu var mı
                    kenar_R_surekli = Rf or Ra  # Sağ kenarda herhangi bir komşu var mı
                    kenar_T_surekli = Tf or Ta  # Üst kenarda herhangi bir komşu var mı
                    kenar_B_surekli = Bf or Ba  # Alt kenarda herhangi bir komşu var mı
                    
                    self.output.insert("end", f"\n  Kenar Süreklilik Durumu:\n")
                    self.output.insert("end", f"    Sol (L): {'Sürekli' if kenar_L_surekli else 'Süreksiz'}\n")
                    self.output.insert("end", f"    Sağ (R): {'Sürekli' if kenar_R_surekli else 'Süreksiz'}\n")
                    self.output.insert("end", f"    Üst (T): {'Sürekli' if kenar_T_surekli else 'Süreksiz'}\n")
                    self.output.insert("end", f"    Alt (B): {'Sürekli' if kenar_B_surekli else 'Süreksiz'}\n")
                    
                    # Ana donatı doğrultusuna göre kenar sınıflandırması
                    # auto_dir = "X" → Ana donatı X yönünde → Mesnetler L ve R'de
                    # auto_dir = "Y" → Ana donatı Y yönünde → Mesnetler T ve B'de
                    if auto_dir == "X":
                        # Span X doğrultusunda: L ve R mesnet kenarları (kısa kenar)
                        # T ve B yan kenarlar (uzun kenar)
                        kisa_kenar_start_surekli = kenar_L_surekli
                        kisa_kenar_end_surekli = kenar_R_surekli
                        uzun_kenar_start_surekli = kenar_T_surekli
                        uzun_kenar_end_surekli = kenar_B_surekli
                    else:
                        # Span Y doğrultusunda: T ve B mesnet kenarları (kısa kenar)
                        # L ve R yan kenarlar (uzun kenar)
                        kisa_kenar_start_surekli = kenar_T_surekli
                        kisa_kenar_end_surekli = kenar_B_surekli
                        uzun_kenar_start_surekli = kenar_L_surekli
                        uzun_kenar_end_surekli = kenar_R_surekli
                    
                    # --- 1. ANA DONATI (Main Reinforcement) ---
                    # Mpos'tan hesaplanır, yarısı pilye yarısı düz
                    self.output.insert("end", "\n  === 1. ANA DONATI ===\n")
                    As_main, ch_main, st_main = self.system.design_main_rebar_from_M(
                        Mpos, conc, steel, h, cover, smax, label_prefix="    ")
                    for l in st_main: self.output.insert("end", l+"\n")
                    
                    duz, pilye = split_duz_pilye(ch_main)
                    self.output.insert("end", f"    Ana Donatı: {ch_main.label_with_area()}\n")
                    self.output.insert("end", f"    -> Düz: {duz.label()} (A={duz.area_mm2_per_m:.1f} mm²/m)\n")
                    self.output.insert("end", f"    -> Pilye: {pilye.label()} (A={pilye.area_mm2_per_m:.1f} mm²/m)\n")
                    
                    # --- 2. DAĞITMA DONATISI (Distribution Reinforcement) ---
                    # Ana donatı alanı / 5
                    self.output.insert("end", "\n  === 2. DAĞITMA DONATISI ===\n")
                    As_dist_req = ch_main.area_mm2_per_m / 5.0
                    self.output.insert("end", f"    As_dağıtma = As_ana / 5 = {ch_main.area_mm2_per_m:.1f} / 5 = {As_dist_req:.1f} mm²/m\n")
                    ch_dist = select_rebar_min_area(As_dist_req, oneway_smax_dist(), phi_min=8)
                    if ch_dist:
                        self.output.insert("end", f"    Seçim: {ch_dist.label_with_area()}\n")
                    else:
                        self.output.insert("end", "    HATA: Dağıtma donatısı seçilemedi!\n")
                    
                    # Minimum donatı hesabı (kenar donatıları için)
                    rho_min = rho_min_oneway(steel)
                    As_min = rho_min * 1000.0 * d_mm  # mm²/m
                    
                    # --- 3. SÜREKSİZ KISA KENAR: BOYUNA KENAR MESNET DONATISI ---
                    # Dağıtma doğrultusunda, minAs değeri kullanılır
                    ch_kenar_start = None
                    ch_kenar_end = None
                    
                    self.output.insert("end", "\n  === 3. SÜREKSİZ KISA KENAR: BOYUNA KENAR MESNET DONATISI ===\n")
                    self.output.insert("end", f"    ρ_min = {rho_min:.4f}, As_min = {As_min:.1f} mm²/m\n")
                    
                    if not kisa_kenar_start_surekli:
                        self.output.insert("end", f"    Kısa kenar START süreksiz -> Boyuna kenar donatısı gerekli\n")
                        ch_kenar_start = select_rebar_min_area(As_min, smax, phi_min=8)
                        if ch_kenar_start:
                            self.output.insert("end", f"    Seçim (START): {ch_kenar_start.label_with_area()}\n")
                    else:
                        self.output.insert("end", f"    Kısa kenar START sürekli -> Boyuna kenar donatısı gerekmiyor\n")
                    
                    if not kisa_kenar_end_surekli:
                        self.output.insert("end", f"    Kısa kenar END süreksiz -> Boyuna kenar donatısı gerekli\n")
                        ch_kenar_end = select_rebar_min_area(As_min, smax, phi_min=8)
                        if ch_kenar_end:
                            self.output.insert("end", f"    Seçim (END): {ch_kenar_end.label_with_area()}\n")
                    else:
                        self.output.insert("end", f"    Kısa kenar END sürekli -> Boyuna kenar donatısı gerekmiyor\n")
                    
                    # --- 4. SÜREKLİ KISA KENAR: BOYUNA İÇ MESNET DONATISI ---
                    # Dağıtma doğrultusunda, 0.6×As
                    ch_ic_mesnet_start = None
                    ch_ic_mesnet_end = None
                    
                    self.output.insert("end", "\n  === 4. SÜREKLİ KISA KENAR: BOYUNA İÇ MESNET DONATISI ===\n")
                    As_ic_mesnet = ch_main.area_mm2_per_m * 0.6
                    self.output.insert("end", f"    As_iç_mesnet = As_ana × 0.6 = {ch_main.area_mm2_per_m:.1f} × 0.6 = {As_ic_mesnet:.1f} mm²/m\n")
                    
                    if kisa_kenar_start_surekli:
                        self.output.insert("end", f"    Kısa kenar START sürekli -> Boyuna iç mesnet donatısı gerekli\n")
                        ch_ic_mesnet_start = select_rebar_min_area(As_ic_mesnet, smax, phi_min=8)
                        if ch_ic_mesnet_start:
                            self.output.insert("end", f"    Seçim (START): {ch_ic_mesnet_start.label_with_area()}\n")
                    else:
                        self.output.insert("end", f"    Kısa kenar START süreksiz -> İç mesnet donatısı gerekmiyor\n")
                    
                    if kisa_kenar_end_surekli:
                        self.output.insert("end", f"    Kısa kenar END sürekli -> Boyuna iç mesnet donatısı gerekli\n")
                        ch_ic_mesnet_end = select_rebar_min_area(As_ic_mesnet, smax, phi_min=8)
                        if ch_ic_mesnet_end:
                            self.output.insert("end", f"    Seçim (END): {ch_ic_mesnet_end.label_with_area()}\n")
                    else:
                        self.output.insert("end", f"    Kısa kenar END süreksiz -> İç mesnet donatısı gerekmiyor\n")
                    
                    # --- 5. SÜREKLİ UZUN KENAR: MESNET EK DONATISI ---
                    # Ana donatı doğrultusunda, pilye yetmezse ek donatı
                    ch_mesnet_ek_start = None
                    ch_mesnet_ek_end = None
                    
                    self.output.insert("end", "\n  === 5. SÜREKLİ UZUN KENAR: MESNET EK DONATISI ===\n")
                    As_mesnet_req = As_main
                    As_pilye = pilye.area_mm2_per_m
                    As_ek_req = max(0, As_mesnet_req - As_pilye)
                    self.output.insert("end", f"    As_mesnet = As_ana = {As_mesnet_req:.1f} mm²/m\n")
                    self.output.insert("end", f"    As_pilye (mevcut) = {As_pilye:.1f} mm²/m\n")
                    self.output.insert("end", f"    As_ek = max(0, {As_mesnet_req:.1f} - {As_pilye:.1f}) = {As_ek_req:.1f} mm²/m\n")
                    
                    if uzun_kenar_start_surekli:
                        self.output.insert("end", f"    Uzun kenar START sürekli -> Mesnet ek donatısı kontrolü\n")
                        if As_ek_req > 1e-6:
                            ch_mesnet_ek_start = select_rebar_min_area(As_ek_req, smax, phi_min=8)
                            if ch_mesnet_ek_start:
                                self.output.insert("end", f"    Seçim (START): {ch_mesnet_ek_start.label_with_area()}\n")
                        else:
                            self.output.insert("end", f"    Pilye yeterli, ek donatı gerekmiyor (START)\n")
                    else:
                        self.output.insert("end", f"    Uzun kenar START süreksiz -> Mesnet ek donatısı gerekmiyor\n")
                    
                    if uzun_kenar_end_surekli:
                        self.output.insert("end", f"    Uzun kenar END sürekli -> Mesnet ek donatısı kontrolü\n")
                        if As_ek_req > 1e-6:
                            ch_mesnet_ek_end = select_rebar_min_area(As_ek_req, smax, phi_min=8)
                            if ch_mesnet_ek_end:
                                self.output.insert("end", f"    Seçim (END): {ch_mesnet_ek_end.label_with_area()}\n")
                        else:
                            self.output.insert("end", f"    Pilye yeterli, ek donatı gerekmiyor (END)\n")
                    else:
                        self.output.insert("end", f"    Uzun kenar END süreksiz -> Mesnet ek donatısı gerekmiyor\n")
                    
                    # --- ÖZET ---
                    self.output.insert("end", "\n  === ÖZET ===\n")
                    self.output.insert("end", f"    Ana (Düz): {duz.label()}\n")
                    self.output.insert("end", f"    Ana (Pilye): {pilye.label()}\n")
                    self.output.insert("end", f"    Dağıtma: {ch_dist.label() if ch_dist else '-'}\n")
                    self.output.insert("end", f"    Boyuna Kenar Mesnet (süreksiz kısa): START={ch_kenar_start.label() if ch_kenar_start else '-'}, END={ch_kenar_end.label() if ch_kenar_end else '-'}\n")
                    self.output.insert("end", f"    Boyuna İç Mesnet (sürekli kısa): START={ch_ic_mesnet_start.label() if ch_ic_mesnet_start else '-'}, END={ch_ic_mesnet_end.label() if ch_ic_mesnet_end else '-'}\n")
                    self.output.insert("end", f"    Mesnet Ek (sürekli uzun): START={ch_mesnet_ek_start.label() if ch_mesnet_ek_start else '-'}, END={ch_mesnet_ek_end.label() if ch_mesnet_ek_end else '-'}\n\n")

                    design_res = {
                        "kind": "ONEWAY", "auto_dir": res.get("auto_dir"), "cover_mm": cover,
                        "choices": {
                            "main": ch_main, 
                            "duz": duz,
                            "pilye": pilye,
                            "dist": ch_dist, 
                            "kenar_mesnet_start": ch_kenar_start,
                            "kenar_mesnet_end": ch_kenar_end,
                            "ic_mesnet_start": ch_ic_mesnet_start,
                            "ic_mesnet_end": ch_ic_mesnet_end,
                            "mesnet_ek_start": ch_mesnet_ek_start,
                            "mesnet_ek_end": ch_mesnet_ek_end
                        },
                        "edge_continuity": {
                            "uzun_start": uzun_kenar_start_surekli,
                            "uzun_end": uzun_kenar_end_surekli,
                            "kisa_start": kisa_kenar_start_surekli,
                            "kisa_end": kisa_kenar_end_surekli
                        }
                    }

                elif s.kind == "TWOWAY":
                    res, steps = self.system.compute_twoway_per_slab(sid, bw)
                    for l in steps: self.output.insert("end", l+"\n")
                    
                    mxn, mxp = res["Mx"]
                    myn, myp = res["My"]
                    
                    smax_x = twoway_smax_short(h) if res["short_dir"]=="X" else twoway_smax_long(h)
                    smax_y = twoway_smax_long(h) if res["short_dir"]=="X" else twoway_smax_short(h)
                    
                    asx, ch_x, _ = self.system.design_main_rebar_from_M(mxp or 0, conc, steel, h, cover, smax_x, label_prefix="  X: ")
                    asy, ch_y, _ = self.system.design_main_rebar_from_M(myp or 0, conc, steel, h, cover, smax_y, label_prefix="  Y: ")
                    
                    asxn, ch_xn, _ = self.system.design_main_rebar_from_M(abs(mxn or 0), conc, steel, h, cover, smax_x, label_prefix="  Xneg: ")
                    asyn, ch_yn, _ = self.system.design_main_rebar_from_M(abs(myn or 0), conc, steel, h, cover, smax_y, label_prefix="  Yneg: ")

                    ch_x_il = select_rebar_min_area(max(0, ch_xn.area_mm2_per_m - ch_x.area_mm2_per_m), 330)
                    ch_y_il = select_rebar_min_area(max(0, ch_yn.area_mm2_per_m - ch_y.area_mm2_per_m), 330)

                    design_res = {
                        "kind": "TWOWAY", "short_dir": res["short_dir"], "cover_mm": cover,
                        "choices": {"x_span": ch_x, "y_span": ch_y, "x_support_extra": ch_x_il, "y_support_extra": ch_y_il}
                    }
                    self.output.insert("end", f"  X: {ch_x.label()} | Y: {ch_y.label()}\n\n")

                elif s.kind == "BALCONY":
                    res, steps = self.system.compute_balcony_per_slab(sid, bw)
                    for l in steps: self.output.insert("end", l+"\n")
                    
                    Mdes, std = self.system.get_balcony_design_moment(sid, res["Mneg"], bw)
                    for l in std: self.output.insert("end", l+"\n")
                    
                    asb, ch_main, _ = self.system.design_main_rebar_from_M(Mdes, conc, steel, h, cover, oneway_smax_main(h), label_prefix="  ")
                    asd = ch_main.area_mm2_per_m / 5.0
                    ch_dist = select_rebar_min_area(asd, oneway_smax_dist(), phi_min=8)
                    
                    fixed, _ = self.system.balcony_fixed_edge_guess(sid)
                    
                    design_res = {
                        "kind": "BALCONY", "cover_mm": cover, "fixed_edge": fixed,
                        "choices": {"main": ch_main, "dist": ch_dist}
                    }
                    self.output.insert("end", f"  Seçim: {ch_main.label()}\n\n")

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
