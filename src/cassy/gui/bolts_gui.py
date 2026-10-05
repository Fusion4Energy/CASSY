"""GUI for configuring bolts assessments in cassy.

Workflow (tabs in order):
  1. General          — run options (fatigue, material library, output folder)
  2. Geometries       — bolt/insert geometry definitions (import/export as separate library file)
  3. Flanges          — flange definitions (name, design code, actions CSV)
  4. Bolt Specs       — bolt and insert specifications per flange
                        (insert always defined alongside its bolt)
  5. Ref. Events      — reference events shared by all flanges and bolts
  6. Fat. Ref. Events — fatigue reference events shared by all flanges and bolts
  7. T & DPA          — temperature and irradiation table (flange × bolt × RE)
  8. T & DPA Fatigue  — same table for fatigue reference events

The project state is saved/loaded as JSON.
The geometry library can additionally be exported/imported as a standalone JSON file
so that a shared bolt geometry library can be maintained across projects.
"""

from __future__ import annotations

import copy
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from cassy.gui.bolts_model import (  # noqa: F401  (re-exported)
    BOLT_DESIGN_CODES,
    EMPTY_BOLT_PROJECT,
    LOAD_CATEGORIES,
    SERVICE_LEVELS,
)
from cassy.gui.bolts_model import build_bolts_from_project as _build_bolts_from_project
from cassy.gui.bolts_model import fresh_project as _fresh_project
from cassy.gui.bolts_model import get_analysis_names as _get_analysis_names
from cassy.gui.bolts_model import get_material_names as _get_material_names
from cassy.gui.common import BG, GroupedTableTab, ProjectApp, RunTab, TDPAGridTab
from cassy.gui.common import Dialog as _Dialog
from cassy.gui.common import TableTab as _TableTab

# ── Geometry field definitions ────────────────────────────────────────────────

# Bolt geometry field definitions: (key, label, default)
_BOLT_REQ_FIELDS = [
    ("p", "Thread pitch (p) [mm] *", "0"),
    ("d", "Nominal diameter (d) [mm] *", "0"),
    ("Le", "Insertion length (Le) [mm] *", "0"),
    ("d_vh", "Venting hole diam. (d_vh) [mm]", "0"),
    ("f", "Thread friction (f)", "0.15"),
    ("f_prime", "Friction under head (f')", "0.15"),
    ("B", "Washer inside diam. (B) [mm]", "0"),
    ("C", "Washer thickness (C) [mm]", "0"),
    ("KF", "Fatigue stress red. factor (KF)", "4"),
]
_BOLT_AUTO_FIELDS = [
    ("dn", "Core diameter (dn) [mm]"),
    ("df", "Pitch diameter (df) [mm]"),
    ("D", "Tapping minor diam. (D) [mm]"),
    ("d1", "Shank diameter (d1) [mm]"),
    ("H", "Head height (H) [mm]"),
    ("a", "Head diameter (a) [mm]"),
    ("Dm", "Mean diam. under head (Dm) [mm]"),
    ("Dp", "Drilling circle diam. (Dp) [mm]"),
]
_BOLT_REQUIRED = {"p", "d", "Le"}

# Insert geometry field definitions: (key, label, default)
_INSERT_REQ_FIELDS = [
    ("p", "Thread pitch (p) [mm] *", "0"),
    ("d", "Nominal diameter (d) [mm] *", "0"),
    ("Le", "Insertion length (Le) [mm] *", "0"),
    ("d_vh", "Venting hole diam. (d_vh) [mm]", "0"),
    ("f", "Thread friction (f)", "0.15"),
]
_INSERT_AUTO_FIELDS = [
    ("dn", "Core diameter (dn) [mm]"),
    ("df", "Pitch diameter (df) [mm]"),
    ("D", "Tapping minor diam. (D) [mm]"),
]
_INSERT_REQUIRED = {"p", "d", "Le"}


# ── Geometry dialog ───────────────────────────────────────────────────────────


class GeomDialog(_Dialog):
    """Dialog for adding/editing a bolt geometry and its optional insert.

    Bolt and insert are configured together as a single unit; on the backend
    they become two separate geometry objects sharing the same base name.
    The insert section is collapsed by default and can be expanded via a
    checkbox.  Each section has an *Auto-compute* button that fills derived
    fields from the ``BoltGeom`` / ``InsertGeom`` dataclass logic; the
    resulting values remain fully editable.
    """

    def __init__(
        self,
        parent: tk.Widget,
        mat_names: list[str],
        existing_bolt: dict | None = None,
        existing_insert: dict | None = None,
    ) -> None:
        self._ex_bolt = existing_bolt or {}
        self._ex_ins = existing_insert or {}
        self._mat_names = mat_names
        super().__init__(parent, "Add / Edit Geometry")

    def _configure_window(self) -> None:
        self.resizable(True, True)
        self.geometry("500x760")

    def _build(self) -> None:
        eb = self._ex_bolt
        ei = self._ex_ins

        # ── Scrollable canvas ──────────────────────────────────────────────
        canvas = tk.Canvas(
            self._body, borderwidth=0, highlightthickness=0, background=BG
        )
        vsb = ttk.Scrollbar(self._body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_frame_configure(_evt):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(evt):
            canvas.itemconfig(inner_id, width=evt.width)

        inner.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(evt):
            canvas.yview_scroll(-1 * (evt.delta // 120), "units")

        canvas.bind(
            "<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel)
        )
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))

        # ── Identity ───────────────────────────────────────────────────────
        id_frm = ttk.LabelFrame(inner, text="Identity")
        id_frm.pack(fill="x", padx=8, pady=6)
        base_name_val = eb.get("base_name") or ei.get("base_name") or ""
        self._base_name = self._entry(id_frm, "Base name *", 0, base_name_val)

        # ── Bolt section ───────────────────────────────────────────────────
        bolt_outer = ttk.LabelFrame(inner, text="Bolt Geometry")
        bolt_outer.pack(fill="x", padx=8, pady=6)

        default_bolt_mat = eb.get(
            "material", self._mat_names[0] if self._mat_names else ""
        )
        self._bolt_mat = self._combo(
            bolt_outer, "Material *", 0, self._mat_names, default_bolt_mat
        )

        self._bolt_vars: dict[str, tk.StringVar] = {}
        for row_i, (key, label, default_val) in enumerate(_BOLT_REQ_FIELDS, start=1):
            stored = eb.get(key)
            default = str(stored) if stored is not None else default_val
            self._bolt_vars[key] = self._entry(bolt_outer, label, row_i, default)

        sep_row = 1 + len(_BOLT_REQ_FIELDS)
        ttk.Separator(bolt_outer, orient="horizontal").grid(
            row=sep_row, column=0, columnspan=2, sticky="ew", padx=6, pady=4
        )
        ttk.Label(bolt_outer, text="Auto-computed (editable after compute):").grid(
            row=sep_row + 1, column=0, columnspan=2, sticky="w", padx=6, pady=2
        )
        for i, (key, label) in enumerate(_BOLT_AUTO_FIELDS):
            val = eb.get(key)
            default = str(val) if val is not None else ""
            self._bolt_vars[key] = self._entry(
                bolt_outer, label, sep_row + 2 + i, default
            )

        btn_row_bolt = sep_row + 2 + len(_BOLT_AUTO_FIELDS)
        ttk.Button(
            bolt_outer,
            text="Auto-compute from p, d, B",
            command=self._autocompute_bolt,
        ).grid(row=btn_row_bolt, column=0, columnspan=2, pady=6)

        # ── Base Material Thread section ────────────────────────────────────
        ins_outer = ttk.LabelFrame(inner, text="Base Material Thread")
        ins_outer.pack(fill="x", padx=8, pady=6)

        # Material is always required — often different from the bolt material
        default_ins_mat = ei.get(
            "material", self._mat_names[0] if self._mat_names else ""
        )
        self._ins_mat = self._combo(
            ins_outer, "Material *", 0, self._mat_names, default_ins_mat
        )

        # Geometry fields are optional; if omitted the bolt geometry is used
        self._has_insert = tk.BooleanVar(value=bool(self._ex_ins))
        ttk.Checkbutton(
            ins_outer,
            text="Has dedicated insert geometry",
            variable=self._has_insert,
            command=self._toggle_insert,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=3)

        ttk.Label(
            ins_outer,
            text="If unchecked, bolt geometry dimensions are used for thread check.",
            style="Muted.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))

        self._ins_fields_frm = ttk.Frame(ins_outer)
        self._ins_fields_frm.grid(row=3, column=0, columnspan=2, sticky="ew")

        self._ins_vars: dict[str, tk.StringVar] = {}
        for row_i, (key, label, default_val) in enumerate(_INSERT_REQ_FIELDS):
            stored = ei.get(key)
            default = str(stored) if stored is not None else default_val
            self._ins_vars[key] = self._entry(
                self._ins_fields_frm, label, row_i, default
            )

        ins_sep_row = len(_INSERT_REQ_FIELDS)
        ttk.Separator(self._ins_fields_frm, orient="horizontal").grid(
            row=ins_sep_row, column=0, columnspan=2, sticky="ew", padx=6, pady=4
        )
        ttk.Label(
            self._ins_fields_frm, text="Auto-computed (editable after compute):"
        ).grid(row=ins_sep_row + 1, column=0, columnspan=2, sticky="w", padx=6, pady=2)
        for i, (key, label) in enumerate(_INSERT_AUTO_FIELDS):
            val = ei.get(key)
            default = str(val) if val is not None else ""
            self._ins_vars[key] = self._entry(
                self._ins_fields_frm, label, ins_sep_row + 2 + i, default
            )

        btn_row_ins = ins_sep_row + 2 + len(_INSERT_AUTO_FIELDS)
        ttk.Button(
            self._ins_fields_frm,
            text="Auto-compute from p, d",
            command=self._autocompute_insert,
        ).grid(row=btn_row_ins, column=0, columnspan=2, pady=6)

        self._toggle_insert()

    # -- auto-compute helpers -------------------------------------------------

    def _toggle_insert(self) -> None:
        if self._has_insert.get():
            self._ins_fields_frm.grid()
        else:
            self._ins_fields_frm.grid_remove()

    def _autocompute_bolt(self) -> None:
        from cassy.bolts.geometry import BoltGeom

        try:
            p = float(self._bolt_vars["p"].get())
            d = float(self._bolt_vars["d"].get())
            B_raw = self._bolt_vars["B"].get().strip()
            B = float(B_raw) if B_raw else 0.0
        except ValueError:
            messagebox.showerror(
                "Auto-compute", "p, d and B must be valid numbers.", parent=self
            )
            return
        geom = BoltGeom(name="", material=None, p=p, d=d, Le=0.0, B=B)  # type: ignore[arg-type]
        mapping = {
            "dn": geom.dn,
            "df": geom.df,
            "D": geom.D,
            "d1": geom.d1,
            "H": geom.H,
            "a": geom.a,
            "Dm": geom.Dm,
            "Dp": geom.Dp,
        }
        for key, val in mapping.items():
            self._bolt_vars[key].set(f"{val:.4g}")

    def _autocompute_insert(self) -> None:
        from cassy.bolts.geometry import InsertGeom

        try:
            p = float(self._ins_vars["p"].get())
            d = float(self._ins_vars["d"].get())
        except ValueError:
            messagebox.showerror(
                "Auto-compute", "p and d must be valid numbers.", parent=self
            )
            return
        geom = InsertGeom(name="", material=None, p=p, d=d, Le=0.0)  # type: ignore[arg-type]
        for key, val in [("dn", geom.dn), ("df", geom.df), ("D", geom.D)]:
            self._ins_vars[key].set(f"{val:.4g}")

    # -- collect --------------------------------------------------------------

    def _collect(self) -> dict | None:
        base_name = self._base_name.get().strip()
        if not base_name:
            messagebox.showerror("Validation", "Base name is required.", parent=self)
            return None

        # ---- bolt ----
        if not self._bolt_mat.get():
            messagebox.showerror(
                "Validation", "Bolt material is required.", parent=self
            )
            return None
        bolt: dict = {
            "base_name": base_name,
            "type": "bolt",
            "material": self._bolt_mat.get(),
        }
        for key, label, _default in _BOLT_REQ_FIELDS:
            raw = self._bolt_vars[key].get().strip()
            if key in _BOLT_REQUIRED and not raw:
                messagebox.showerror(
                    "Validation", f"Bolt '{label}' is required.", parent=self
                )
                return None
            try:
                bolt[key] = float(raw) if raw else 0.0
            except ValueError:
                messagebox.showerror(
                    "Validation", f"Bolt '{label}' must be a number.", parent=self
                )
                return None
        for key, _label in _BOLT_AUTO_FIELDS:
            raw = self._bolt_vars[key].get().strip()
            bolt[key] = float(raw) if raw else None

        # ---- insert (base material thread) — always produced ----
        ins_mat = self._ins_mat.get()
        if not ins_mat:
            messagebox.showerror(
                "Validation",
                "Base material thread material is required.",
                parent=self,
            )
            return None

        insert: dict = {
            "base_name": base_name,
            "type": "insert",
            "material": ins_mat,
        }

        if self._has_insert.get():
            # Dedicated insert geometry specified
            for key, label, _default in _INSERT_REQ_FIELDS:
                raw = self._ins_vars[key].get().strip()
                if key in _INSERT_REQUIRED and not raw:
                    messagebox.showerror(
                        "Validation", f"Insert '{label}' is required.", parent=self
                    )
                    return None
                try:
                    insert[key] = float(raw) if raw else 0.0
                except ValueError:
                    messagebox.showerror(
                        "Validation",
                        f"Insert '{label}' must be a number.",
                        parent=self,
                    )
                    return None
            for key, _label in _INSERT_AUTO_FIELDS:
                raw = self._ins_vars[key].get().strip()
                insert[key] = float(raw) if raw else None
        else:
            # No dedicated geometry — copy bolt dimensions for thread check
            for key in [f[0] for f in _INSERT_REQ_FIELDS]:
                insert[key] = bolt.get(key, 0.0)
            for key in [f[0] for f in _INSERT_AUTO_FIELDS]:
                insert[key] = bolt.get(key)

        return {"bolt": bolt, "insert": insert}


# ── Flange dialog ─────────────────────────────────────────────────────────────


class FlangeDialog(_Dialog):
    def __init__(self, parent: tk.Widget, existing: dict | None = None) -> None:
        self._ex = existing or {}
        super().__init__(parent, "Add / Edit Flange")

    def _build(self) -> None:
        ex = self._ex
        frm = ttk.LabelFrame(self._body, text="Flange definition")
        frm.pack(fill="both")
        self._name = self._entry(frm, "Name *", 0, ex.get("name", ""))
        default_code = ex.get(
            "design_code", BOLT_DESIGN_CODES[0] if BOLT_DESIGN_CODES else ""
        )
        self._code = self._combo(frm, "Design Code", 1, BOLT_DESIGN_CODES, default_code)
        self._actions = self._file_entry(
            frm,
            "Actions CSV",
            2,
            ex.get("actions_file", ""),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )

    def _collect(self) -> dict | None:
        name = self._name.get().strip()
        if not name:
            messagebox.showerror("Validation", "Name is required.", parent=self)
            return None
        return {
            "name": name,
            "design_code": self._code.get(),
            "actions_file": self._actions.get().strip(),
            "bolts_spec": self._ex.get("bolts_spec", []),
        }


# ── Bolt Spec dialog ──────────────────────────────────────────────────────────


class BoltSpecDialog(_Dialog):
    """Dialog for adding/editing a bolt specification (ID, geometry, preload).

    Thread-verification geometry and base-material are part of the geometry
    library definition (see GeomDialog); they need not be repeated here.
    """

    def __init__(
        self,
        parent: tk.Widget,
        bolt_geom_names: list[str],
        existing: dict | None = None,
    ) -> None:
        self._ex = existing or {}
        self._bolt_geom_names = bolt_geom_names
        super().__init__(parent, "Add / Edit Bolt Entry")

    def _build(self) -> None:
        ex = self._ex
        frm = ttk.LabelFrame(self._body, text="Bolt")
        frm.pack(fill="x", pady=(0, 4))
        self._bolt_id = self._entry(frm, "Bolt ID *", 0, str(ex.get("bolt_id", "")))
        default_geom = ex.get(
            "geom_data", self._bolt_geom_names[0] if self._bolt_geom_names else ""
        )
        if self._bolt_geom_names:
            self._geom_data = self._combo(
                frm, "Geometry *", 1, self._bolt_geom_names, default_geom
            )
        else:
            self._geom_data = self._entry(frm, "Geometry *", 1, default_geom)
        self._preload = self._entry(frm, "Preload [N] *", 2, str(ex.get("preload", "")))

    def _collect(self) -> dict | None:
        bolt_id = self._bolt_id.get().strip()
        if not bolt_id:
            messagebox.showerror("Validation", "Bolt ID is required.", parent=self)
            return None
        geom_data = self._geom_data.get().strip()
        if not geom_data:
            messagebox.showerror("Validation", "Geometry is required.", parent=self)
            return None
        try:
            preload = float(self._preload.get().strip())
        except ValueError:
            messagebox.showerror("Validation", "Preload must be a number.", parent=self)
            return None
        return {"bolt_id": bolt_id, "geom_data": geom_data, "preload": preload}


# ── Bolt RE dialog ────────────────────────────────────────────────────────────


class BoltREDialog(_Dialog):
    """Dialog for adding/editing a bolt reference event."""

    def __init__(
        self,
        parent: tk.Widget,
        existing: dict | None = None,
        analyses: list[str] | None = None,
    ) -> None:
        self._ex = existing or {}
        self._analyses = analyses or []
        super().__init__(parent, "Add / Edit Reference Event")

    def _configure_window(self) -> None:
        self.geometry("420x500")
        self.resizable(False, True)

    def _build(self) -> None:
        ex = self._ex

        frm = ttk.LabelFrame(self._body, text="Reference Event")
        frm.pack(fill="x", pady=(0, 4))
        self._re_id = self._entry(frm, "RE ID *", 0, ex.get("re_id", ""))
        self._svc = self._combo(
            frm, "Service Level *", 1, SERVICE_LEVELS, ex.get("service_lvl", "A")
        )
        self._lcat = self._combo(
            frm, "Load Category *", 2, LOAD_CATEGORIES, ex.get("load_category", "I")
        )
        self._oc = self._entry(frm, "Operating Conditions", 3, ex.get("oc", "N/A"))
        self._ie = self._entry(frm, "Initiating Event", 4, ex.get("ie", "N/A"))
        self._ce = self._entry(frm, "Concatenated Event", 5, ex.get("ce", "N/A"))

        pri_frm = ttk.LabelFrame(self._body, text="Primary Action")
        pri_frm.pack(fill="x", pady=(4, 0))
        self._pri_analysis = self._analysis_field(
            pri_frm, "Analysis *", 0, self._analyses, ex.get("primary_analysis", "")
        )
        self._pri_loadstep = self._entry(
            pri_frm, "Loadstep *", 1, ex.get("primary_loadstep", "")
        )

        all_frm = ttk.LabelFrame(self._body, text="All Loads Action")
        all_frm.pack(fill="x", pady=(4, 0))
        self._all_analysis = self._analysis_field(
            all_frm, "Analysis *", 0, self._analyses, ex.get("all_analysis", "")
        )
        self._all_loadstep = self._entry(
            all_frm, "Loadstep *", 1, ex.get("all_loadstep", "")
        )

    def _collect(self) -> dict | None:
        re_id = self._re_id.get().strip()
        if not re_id:
            messagebox.showerror("Validation", "RE ID is required.", parent=self)
            return None
        pri_ana = self._pri_analysis.get().strip()
        pri_ls = self._pri_loadstep.get().strip()
        all_ana = self._all_analysis.get().strip()
        all_ls = self._all_loadstep.get().strip()
        if not (pri_ana and pri_ls and all_ana and all_ls):
            messagebox.showerror(
                "Validation", "All action fields are required.", parent=self
            )
            return None
        return {
            "re_id": re_id,
            "service_lvl": self._svc.get(),
            "load_category": self._lcat.get(),
            "oc": self._oc.get().strip(),
            "ie": self._ie.get().strip(),
            "ce": self._ce.get().strip(),
            "primary_analysis": pri_ana,
            "primary_loadstep": pri_ls,
            "all_analysis": all_ana,
            "all_loadstep": all_ls,
        }


# ── Bolt Fatigue RE dialog ────────────────────────────────────────────────────


class BoltFatigueREDialog(_Dialog):
    """Dialog for adding/editing a bolt fatigue reference event."""

    def __init__(
        self,
        parent: tk.Widget,
        existing: dict | None = None,
        analyses: list[str] | None = None,
    ) -> None:
        self._ex = existing or {}
        self._analyses = analyses or []
        super().__init__(parent, "Add / Edit Fatigue Reference Event")

    def _configure_window(self) -> None:
        self.geometry("420x580")
        self.resizable(False, True)

    def _build(self) -> None:
        ex = self._ex

        frm = ttk.LabelFrame(self._body, text="Fatigue Reference Event")
        frm.pack(fill="x", pady=(0, 4))
        self._re_id = self._entry(frm, "RE ID *", 0, ex.get("re_id", ""))
        self._svc = self._combo(
            frm, "Service Level *", 1, SERVICE_LEVELS, ex.get("service_lvl", "A")
        )
        self._lcat = self._combo(
            frm, "Load Category *", 2, LOAD_CATEGORIES, ex.get("load_category", "I")
        )
        self._oc = self._entry(frm, "Operating Conditions", 3, ex.get("oc", "N/A"))
        self._ie = self._entry(frm, "Initiating Event", 4, ex.get("ie", "N/A"))
        self._ce = self._entry(frm, "Concatenated Event", 5, ex.get("ce", "N/A"))
        self._ncycles = self._entry(frm, "N cycles *", 6, str(ex.get("n_cycles", "")))

        ds_plus_frm = ttk.LabelFrame(
            self._body, text="Delta Sigma + (analysis, loadstep)"
        )
        ds_plus_frm.pack(fill="x", pady=(4, 0))
        self._ds_plus_ana = self._analysis_field(
            ds_plus_frm, "Analysis *", 0, self._analyses, ex.get("ds_plus_analysis", "")
        )
        self._ds_plus_ls = self._entry(
            ds_plus_frm, "Loadstep *", 1, ex.get("ds_plus_loadstep", "")
        )

        ds_minus_frm = ttk.LabelFrame(
            self._body, text="Delta Sigma − (analysis, loadstep)"
        )
        ds_minus_frm.pack(fill="x", pady=(4, 0))
        self._ds_minus_ana = self._analysis_field(
            ds_minus_frm,
            "Analysis *",
            0,
            self._analyses,
            ex.get("ds_minus_analysis", ""),
        )
        self._ds_minus_ls = self._entry(
            ds_minus_frm, "Loadstep *", 1, ex.get("ds_minus_loadstep", "")
        )

        sus_frm = ttk.LabelFrame(self._body, text="Sigma Sustained (optional)")
        sus_frm.pack(fill="x", pady=(4, 0))
        self._sus_ana = self._analysis_field(
            sus_frm,
            "Analysis",
            0,
            self._analyses,
            ex.get("sigma_sus_analysis", ""),
            optional=True,
        )
        self._sus_ls = self._entry(
            sus_frm, "Loadstep", 1, ex.get("sigma_sus_loadstep", "")
        )

    def _collect(self) -> dict | None:
        re_id = self._re_id.get().strip()
        if not re_id:
            messagebox.showerror("Validation", "RE ID is required.", parent=self)
            return None
        ncycles_raw = self._ncycles.get().strip()
        if not ncycles_raw.isdigit():
            messagebox.showerror(
                "Validation", "N cycles must be a positive integer.", parent=self
            )
            return None
        ds_plus_ana = self._ds_plus_ana.get().strip()
        ds_plus_ls = self._ds_plus_ls.get().strip()
        ds_minus_ana = self._ds_minus_ana.get().strip()
        ds_minus_ls = self._ds_minus_ls.get().strip()
        if not (ds_plus_ana and ds_plus_ls and ds_minus_ana and ds_minus_ls):
            messagebox.showerror(
                "Validation", "All delta sigma fields are required.", parent=self
            )
            return None
        sus_ana = self._sus_ana.get().strip()
        sus_ls = self._sus_ls.get().strip()
        return {
            "re_id": re_id,
            "service_lvl": self._svc.get(),
            "load_category": self._lcat.get(),
            "oc": self._oc.get().strip(),
            "ie": self._ie.get().strip(),
            "ce": self._ce.get().strip(),
            "n_cycles": int(ncycles_raw),
            "ds_plus_analysis": ds_plus_ana,
            "ds_plus_loadstep": ds_plus_ls,
            "ds_minus_analysis": ds_minus_ana,
            "ds_minus_loadstep": ds_minus_ls,
            "sigma_sus_analysis": sus_ana,
            "sigma_sus_loadstep": sus_ls,
        }


# ── General tab ───────────────────────────────────────────────────────────────


class GeneralTab(RunTab):
    _RUN_LABEL = "Run Bolts Assessment"
    _REQUIRED = ("flanges", "No flanges", "Define at least one flange first.")

    def _prepare(self) -> Callable[[], None]:
        configs, geoms = _build_bolts_from_project(self._project)
        root_dir = self._project["run_options"]["root_dir"]
        fatigue = self._project["run_options"].get("fatigue", False)

        def work() -> None:
            from cassy.runners.run_bolts import run_bolts

            run_bolts(root_dir, fatigue=fatigue, geoms=geoms, config_dict=configs)

        return work


# ── Geometries tab ────────────────────────────────────────────────────────────


class GeometriesTab(_TableTab):
    """Geometry library tab with import/export support for cross-project reuse."""

    _ITEM_NAME = "geometry"
    _COLUMNS = ("base_name", "type", "material", "p", "d", "Le", "d_vh", "f", "KF")
    _HEADINGS = {
        "base_name": "Base Name",
        "type": "Type",
        "material": "Material",
        "p": "p [mm]",
        "d": "d [mm]",
        "Le": "Le [mm]",
        "d_vh": "d_vh [mm]",
        "f": "f",
        "KF": "KF",
    }
    _LIST_KEY = "geometries"

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        self._mat_names: list[str] = []
        super().__init__(parent, project)
        self.after(200, self._load_materials)

    def _load_materials(self) -> None:
        self._mat_names = _get_material_names(
            self._project["run_options"].get("matlib_path", "")
        )

    def _extra_toolbar(self, toolbar: ttk.Frame) -> None:
        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", padx=6, fill="y", pady=4
        )
        ttk.Button(toolbar, text="Import library…", command=self._import_lib).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Export library…", command=self._export_lib).pack(
            side="left", padx=2
        )

    def _row_values(self, item: dict) -> tuple:
        return (
            item.get("base_name", ""),
            item.get("type", ""),
            item.get("material", ""),
            item.get("p", ""),
            item.get("d", ""),
            item.get("Le", ""),
            item.get("d_vh", ""),
            item.get("f", ""),
            item.get("KF", "N/A") if item.get("type") == "bolt" else "N/A",
        )

    def _add(self) -> None:
        mat_names = self._mat_names or _get_material_names()
        dlg = GeomDialog(self, mat_names)
        if dlg.result is None:
            return
        new_entries = [dlg.result["bolt"]]
        if dlg.result["insert"] is not None:
            new_entries.append(dlg.result["insert"])
        for entry in new_entries:
            key = (entry["base_name"], entry["type"])
            if any(
                (g["base_name"], g["type"]) == key for g in self._project["geometries"]
            ):
                messagebox.showerror(
                    "Duplicate",
                    f"Geometry '{entry['base_name']}' ({entry['type']}) already exists.",
                )
                return
        for entry in new_entries:
            self._project["geometries"].append(entry)
        self.refresh()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a geometry to edit.")
            return
        mat_names = self._mat_names or _get_material_names()
        base_name = self._project["geometries"][idx]["base_name"]
        bolt_entry = next(
            (
                g
                for g in self._project["geometries"]
                if g["base_name"] == base_name and g["type"] == "bolt"
            ),
            None,
        )
        insert_entry = next(
            (
                g
                for g in self._project["geometries"]
                if g["base_name"] == base_name and g["type"] == "insert"
            ),
            None,
        )
        dlg = GeomDialog(
            self, mat_names, existing_bolt=bolt_entry, existing_insert=insert_entry
        )
        if dlg.result is None:
            return
        bolt_idx = next(
            (
                i
                for i, g in enumerate(self._project["geometries"])
                if g["base_name"] == base_name and g["type"] == "bolt"
            ),
            None,
        )
        if bolt_idx is not None:
            self._project["geometries"][bolt_idx] = dlg.result["bolt"]
        else:
            self._project["geometries"].append(dlg.result["bolt"])
        ins_idx = next(
            (
                i
                for i, g in enumerate(self._project["geometries"])
                if g["base_name"] == base_name and g["type"] == "insert"
            ),
            None,
        )
        if dlg.result["insert"] is not None:
            if ins_idx is not None:
                self._project["geometries"][ins_idx] = dlg.result["insert"]
            else:
                self._project["geometries"].append(dlg.result["insert"])
        else:
            if ins_idx is not None:
                del self._project["geometries"][ins_idx]
        self.refresh()

    def _import_lib(self) -> None:
        """Merge geometries from a standalone library JSON file."""
        path = filedialog.askopenfilename(
            title="Import geometry library",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                raise ValueError("Expected a JSON array of geometry objects.")
        except Exception as exc:
            messagebox.showerror("Import Error", str(exc))
            return
        merged = 0
        for geom in data:
            key = (geom.get("base_name"), geom.get("type"))
            existing_keys = [
                (g["base_name"], g["type"]) for g in self._project["geometries"]
            ]
            if key not in existing_keys:
                self._project["geometries"].append(geom)
                merged += 1
        self.refresh()
        messagebox.showinfo("Import", f"Imported {merged} new geometry entries.")

    def _export_lib(self) -> None:
        """Export the current geometry list to a standalone JSON file."""
        path = filedialog.asksaveasfilename(
            title="Export geometry library",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._project["geometries"], fh, indent=2)
            messagebox.showinfo("Export", f"Geometry library saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))


# ── Flanges tab ───────────────────────────────────────────────────────────────


class FlangesTab(_TableTab):
    _ITEM_NAME = "flange"
    _COLUMNS = ("name", "design_code", "actions_file")
    _HEADINGS = {
        "name": "Name",
        "design_code": "Design Code",
        "actions_file": "Actions CSV",
    }
    _LIST_KEY = "flanges"

    def _row_values(self, item: dict) -> tuple:
        return (item["name"], item["design_code"], item.get("actions_file", ""))

    def _add(self) -> None:
        dlg = FlangeDialog(self)
        if dlg.result is None:
            return
        name = dlg.result["name"]
        if any(f["name"] == name for f in self._project["flanges"]):
            messagebox.showerror("Duplicate", f"Flange '{name}' already exists.")
            return
        self._project["flanges"].append(dlg.result)
        self.refresh()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a flange to edit.")
            return
        old_name = self._project["flanges"][idx]["name"]
        dlg = FlangeDialog(self, existing=self._project["flanges"][idx])
        if dlg.result is None:
            return
        new_name = dlg.result["name"]
        if new_name != old_name:
            if any(
                f["name"] == new_name
                for i, f in enumerate(self._project["flanges"])
                if i != idx
            ):
                messagebox.showerror(
                    "Duplicate", f"Flange '{new_name}' already exists."
                )
                return
            for key in ("tdpa", "tdpa_fatigue"):
                for entry in self._project.get(key, []):
                    if entry.get("flange") == old_name:
                        entry["flange"] = new_name
        self._project["flanges"][idx] = dlg.result
        self.refresh()

    def _delete(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a flange to delete.")
            return
        name = self._project["flanges"][idx]["name"]
        if not messagebox.askyesno(
            "Delete", f"Delete flange '{name}' and all its data?"
        ):
            return
        self._project["flanges"].pop(idx)
        for key in ("tdpa", "tdpa_fatigue"):
            self._project[key] = [
                e for e in self._project.get(key, []) if e.get("flange") != name
            ]
        self.refresh()


# ── Bolt Specs tab ────────────────────────────────────────────────────────────


class BoltSpecsTab(GroupedTableTab):
    """Per-flange bolt specification table (Bolt ID, Bolt Geometry, Preload).

    Thread-verification geometry and base-material are part of the geometry
    library definition; they are not shown here.
    """

    _GROUP_LABEL = "Flange"
    _ITEM_NAME = "bolt"
    _COL_WIDTH = 130
    _COLUMNS = ("bolt_id", "geom_data", "preload")
    _HEADINGS = {
        "bolt_id": "Bolt ID",
        "geom_data": "Bolt Geometry",
        "preload": "Preload [N]",
    }

    def _group_names(self) -> list[str]:
        return [f["name"] for f in self._project["flanges"]]

    def _items_of(self, group: str) -> list:
        fl = next((f for f in self._project["flanges"] if f["name"] == group), None)
        return fl["bolts_spec"] if fl else []

    def _current_flange(self) -> dict | None:
        name = self._current_group()
        return next((f for f in self._project["flanges"] if f["name"] == name), None)

    def _row_values(self, item: dict) -> tuple:
        return (item["bolt_id"], item["geom_data"], item["preload"])

    def _extra_toolbar(self, toolbar: ttk.Frame) -> None:
        ttk.Button(toolbar, text="Duplicate", command=self._duplicate).pack(
            side="left", padx=(0, 4)
        )

    def _geom_names_by_type(self, geom_type: str) -> list[str]:
        return [
            g["base_name"]
            for g in self._project["geometries"]
            if g.get("type") == geom_type
        ]

    def _add(self) -> None:
        fl = self._current_flange()
        if fl is None:
            messagebox.showwarning("No Flange", "Select or create a flange first.")
            return
        bolt_names = self._geom_names_by_type("bolt")
        dlg = BoltSpecDialog(self, bolt_names)
        if dlg.result is None:
            return
        bolt_id = dlg.result["bolt_id"]
        if any(b["bolt_id"] == bolt_id for b in fl["bolts_spec"]):
            messagebox.showerror(
                "Duplicate", f"Bolt ID '{bolt_id}' already exists in this flange."
            )
            return
        fl["bolts_spec"].append(dlg.result)
        self._refresh_table()

    def _edit(self) -> None:
        fl = self._current_flange()
        if fl is None:
            return
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a bolt entry to edit.")
            return
        bolt_names = self._geom_names_by_type("bolt")
        dlg = BoltSpecDialog(self, bolt_names, existing=fl["bolts_spec"][idx])
        if dlg.result:
            fl["bolts_spec"][idx] = dlg.result
            self._refresh_table()

    def _duplicate(self) -> None:
        fl = self._current_flange()
        if fl is None:
            return
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a bolt entry to duplicate.")
            return
        new_bolt = copy.deepcopy(fl["bolts_spec"][idx])
        # Determine next consecutive integer ID
        existing_ids: list[int] = []
        for b in fl["bolts_spec"]:
            try:
                existing_ids.append(int(b["bolt_id"]))
            except (ValueError, TypeError):
                pass
        next_id = (max(existing_ids) + 1) if existing_ids else 1
        new_bolt["bolt_id"] = str(next_id)
        fl["bolts_spec"].append(new_bolt)
        self._refresh_table()
        # Select the newly added row
        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children[-1])
            self._tree.see(children[-1])


# ── Bolt RE tab (base) ────────────────────────────────────────────────────────


class BoltREsTab(_TableTab):
    """Reference events table shared across all flanges and bolts.

    Subclassed for fatigue REs.
    """

    _ITEM_NAME = "reference event"
    _RE_KEY = "reference_events"
    _COLUMNS = (
        "re_id",
        "service_lvl",
        "load_category",
        "oc",
        "ie",
        "ce",
        "primary",
        "all_loads",
    )
    _HEADINGS = {
        "re_id": "RE ID",
        "service_lvl": "Svc. Lvl",
        "load_category": "Load Cat.",
        "oc": "Op. Cond.",
        "ie": "Init. Event",
        "ce": "Concat. Event",
        "primary": "Primary",
        "all_loads": "All Loads",
    }

    def _list(self) -> list:
        return self._project[self._RE_KEY]

    def _row_values(self, item: dict) -> tuple:
        primary = (
            f"({item.get('primary_analysis', '')}, {item.get('primary_loadstep', '')})"
        )
        all_ld = f"({item.get('all_analysis', '')}, {item.get('all_loadstep', '')})"
        return (
            item["re_id"],
            item.get("service_lvl", ""),
            item.get("load_category", ""),
            item.get("oc", ""),
            item.get("ie", ""),
            item.get("ce", ""),
            primary,
            all_ld,
        )

    def _make_dialog(self, parent: tk.Widget, existing: dict | None = None) -> _Dialog:
        return BoltREDialog(
            parent, existing=existing, analyses=_get_analysis_names(self._project)
        )

    def _add(self) -> None:
        dlg = self._make_dialog(self)
        if dlg.result is None:
            return
        re_list = self._list()
        if any(r["re_id"] == dlg.result["re_id"] for r in re_list):
            messagebox.showerror(
                "Duplicate",
                f"RE '{dlg.result['re_id']}' already exists.",
            )
            return
        re_list.append(dlg.result)
        self.refresh()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a reference event to edit.")
            return
        re_list = self._list()
        dlg = self._make_dialog(self, existing=re_list[idx])
        if dlg.result:
            re_list[idx] = dlg.result
            self.refresh()


# ── Bolt Fatigue RE tab ───────────────────────────────────────────────────────


class BoltFatigueREsTab(BoltREsTab):
    _RE_KEY = "fatigue_reference_events"
    _COLUMNS = (
        "re_id",
        "service_lvl",
        "load_category",
        "n_cycles",
        "ds_plus",
        "ds_minus",
        "sigma_sus",
    )
    _HEADINGS = {
        "re_id": "RE ID",
        "service_lvl": "Svc. Lvl",
        "load_category": "Load Cat.",
        "n_cycles": "N Cycles",
        "ds_plus": "\u0394\u03a3+",
        "ds_minus": "\u0394\u03a3\u2212",
        "sigma_sus": "\u03a3 Sustained",
    }

    def _make_dialog(self, parent: tk.Widget, existing: dict | None = None) -> _Dialog:
        return BoltFatigueREDialog(
            parent, existing=existing, analyses=_get_analysis_names(self._project)
        )

    def _row_values(self, item: dict) -> tuple:
        ds_plus = (
            f"({item.get('ds_plus_analysis', '')}, {item.get('ds_plus_loadstep', '')})"
        )
        ds_minus = f"({item.get('ds_minus_analysis', '')}, {item.get('ds_minus_loadstep', '')})"
        sus_ana = item.get("sigma_sus_analysis", "")
        sus_ls = item.get("sigma_sus_loadstep", "")
        sigma_sus = f"({sus_ana}, {sus_ls})" if sus_ana else "N/A"
        return (
            item["re_id"],
            item.get("service_lvl", ""),
            item.get("load_category", ""),
            item.get("n_cycles", ""),
            ds_plus,
            ds_minus,
            sigma_sus,
        )


# ── Bolt T & DPA tab ──────────────────────────────────────────────────────────


class BoltTDPATab(TDPAGridTab):
    """Grid of (flange × bolt) × reference events; each cell holds T and DPA entries."""

    _PROJECT_KEY = "tdpa"
    _RE_KEY = "reference_events"
    _GROUP_FIELD = "flange"
    _ITEM_FIELD = "bolt_id"
    _GROUP_LABEL = "Flange"
    _ITEM_LABEL = "Bolt ID"
    _CSV_ITEM_COL = "bolt"
    _EMPTY_MSG = "No data to display (add flanges, bolts and reference events first)."

    def _groups(self) -> list[tuple[str, list]]:
        return [
            (f["name"], [b["bolt_id"] for b in f.get("bolts_spec", [])])
            for f in self._project.get("flanges", [])
        ]


# ── Bolt T & DPA Fatigue tab ──────────────────────────────────────────────────


class BoltFatigueTDPATab(BoltTDPATab):
    _PROJECT_KEY = "tdpa_fatigue"
    _RE_KEY = "fatigue_reference_events"


# ── Main application window ───────────────────────────────────────────────────


class BoltsGUI(ProjectApp):
    _TITLE = "Cassy \u2014 Bolts Assessment Configuration"

    @staticmethod
    def _fresh_project() -> dict:
        return _fresh_project()

    def _build_tabs(self) -> None:
        self._tab_general = GeneralTab(self._nb, self._project)
        self._tab_geoms = GeometriesTab(self._nb, self._project)
        self._tab_flanges = FlangesTab(self._nb, self._project)
        self._tab_bolt_specs = BoltSpecsTab(self._nb, self._project)
        self._tab_res = BoltREsTab(self._nb, self._project)
        self._tab_fat_res = BoltFatigueREsTab(self._nb, self._project)
        self._tab_tdpa = BoltTDPATab(self._nb, self._project)
        self._tab_tdpa_fat = BoltFatigueTDPATab(self._nb, self._project)

        self._nb.add(self._tab_general, text="General")
        self._nb.add(self._tab_geoms, text="Geometries")
        self._nb.add(self._tab_flanges, text="Flanges")
        self._nb.add(self._tab_bolt_specs, text="Bolt Specs")
        self._nb.add(self._tab_res, text="Ref. Events")
        self._nb.add(self._tab_fat_res, text="Fat. Ref. Events")
        self._nb.add(self._tab_tdpa, text="T & DPA")
        self._nb.add(self._tab_tdpa_fat, text="T & DPA Fatigue")

    def _sync_all(self) -> list[str]:
        self._tab_general.sync()
        return self._tab_tdpa.sync() + self._tab_tdpa_fat.sync()

    def _refresh_all_tabs(self) -> None:
        self._tab_general.load_from_project()
        self._tab_geoms.refresh()
        self._tab_flanges.refresh()
        self._tab_bolt_specs.refresh()
        self._tab_res.refresh()
        self._tab_fat_res.refresh()
        self._tab_tdpa.rebuild_grid()
        self._tab_tdpa_fat.rebuild_grid()


def main() -> None:
    app = BoltsGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
