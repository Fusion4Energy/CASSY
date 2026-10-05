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
import csv
import json
import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any
from cassy.designcodes.map import BOLT_CODES as _BOLT_CODES

# ── Icon helper ───────────────────────────────────────────────────────────────

_ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.png")


def _set_icon(window: tk.Wm) -> None:
    try:
        from PIL import Image, ImageTk  # type: ignore

        img = Image.open(_ICON_PATH)
        _set_icon._photo = ImageTk.PhotoImage(img)
        window.iconphoto(True, _set_icon._photo)
    except Exception:
        pass


# ── Constants ─────────────────────────────────────────────────────────────────


BOLT_DESIGN_CODES: list[str] = list(_BOLT_CODES.keys())
GEOM_TYPES: list[str] = ["bolt", "insert"]
SERVICE_LEVELS: list[str] = ["A", "C", "D"]
LOAD_CATEGORIES: list[str] = ["I", "II", "III", "IV"]

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

EMPTY_BOLT_PROJECT: dict[str, Any] = {
    "run_options": {
        "fatigue": False,
        "matlib_path": "",
        "root_dir": "",
    },
    "geometries": [],
    "flanges": [],
    "reference_events": [],  # [re_dict, ...] — shared by all flanges
    "fatigue_reference_events": [],  # [fat_re_dict, ...] — shared by all flanges
    "tdpa": [],  # [{flange, re_id, T, dpa}]
    "tdpa_fatigue": [],  # [{flange, re_id, T, dpa}]
}


def _bool_label(v: bool) -> str:
    return "Yes" if v else "No"


def _get_material_names(matlib_path: str = "") -> list[str]:
    from cassy.runners.run_common import build_material_library

    return sorted(build_material_library(matlib_path or None).keys())


# ── Base dialog ───────────────────────────────────────────────────────────────


class _Dialog(tk.Toplevel):
    """Modal dialog base class."""

    def __init__(self, parent: tk.Widget, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: dict | None = None
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_window()
        self._body = ttk.Frame(self)
        self._body.pack(padx=12, pady=(12, 4), fill="both", expand=True)
        self._build()
        self._add_buttons()
        self.wait_visibility()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()

    # -- subclasses override these -------------------------------------------

    def _configure_window(self) -> None:
        """Called before _build. Override to adjust window size / resizability."""
        pass

    def _build(self) -> None:
        raise NotImplementedError

    def _collect(self) -> dict | None:
        raise NotImplementedError

    # -- private ---------------------------------------------------------------

    def _add_buttons(self) -> None:
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(frm, text="OK", width=8, command=self._on_ok).pack(
            side="right", padx=4
        )
        ttk.Button(frm, text="Cancel", width=8, command=self._on_close).pack(
            side="right"
        )

    def _on_close(self) -> None:
        self.destroy()

    def _on_ok(self) -> None:
        result = self._collect()
        if result is not None:
            self.result = result
            self.destroy()

    def destroy(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    # -- field helpers ---------------------------------------------------------

    @staticmethod
    def _row(frame, label: str, row: int) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)

    def _entry(self, frame, label: str, row: int, default: str = "") -> tk.StringVar:
        self._row(frame, label, row)
        var = tk.StringVar(value=default)
        ttk.Entry(frame, textvariable=var, width=30).grid(
            row=row, column=1, padx=6, pady=3
        )
        return var

    def _combo(
        self,
        frame,
        label: str,
        row: int,
        values: list[str],
        default: str = "",
    ) -> tk.StringVar:
        self._row(frame, label, row)
        var = tk.StringVar(value=default or (values[0] if values else ""))
        ttk.Combobox(
            frame, textvariable=var, values=values, state="readonly", width=28
        ).grid(row=row, column=1, padx=6, pady=3)
        return var

    def _check(
        self, frame, label: str, row: int, default: bool = False
    ) -> tk.BooleanVar:
        self._row(frame, label, row)
        var = tk.BooleanVar(value=default)
        ttk.Checkbutton(frame, variable=var).grid(
            row=row, column=1, sticky="w", padx=6, pady=3
        )
        return var

    def _file_entry(
        self,
        frame,
        label: str,
        row: int,
        default: str = "",
        filetypes: list | None = None,
    ) -> tk.StringVar:
        self._row(frame, label, row)
        var = tk.StringVar(value=default)
        wrap = ttk.Frame(frame)
        wrap.grid(row=row, column=1, padx=6, pady=3)
        ttk.Entry(wrap, textvariable=var, width=26).pack(side="left")
        ft = filetypes or [("All files", "*.*")]
        ttk.Button(
            wrap,
            text="…",
            width=3,
            command=lambda: var.set(
                filedialog.askopenfilename(filetypes=ft) or var.get()
            ),
        ).pack(side="left", padx=2)
        return var


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
        canvas = tk.Canvas(self._body, borderwidth=0, highlightthickness=0)
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
            foreground="gray",
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

    def __init__(self, parent: tk.Widget, existing: dict | None = None) -> None:
        self._ex = existing or {}
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
        self._pri_analysis = self._entry(
            pri_frm, "Analysis *", 0, ex.get("primary_analysis", "")
        )
        self._pri_loadstep = self._entry(
            pri_frm, "Loadstep *", 1, ex.get("primary_loadstep", "")
        )

        all_frm = ttk.LabelFrame(self._body, text="All Loads Action")
        all_frm.pack(fill="x", pady=(4, 0))
        self._all_analysis = self._entry(
            all_frm, "Analysis *", 0, ex.get("all_analysis", "")
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

    def __init__(self, parent: tk.Widget, existing: dict | None = None) -> None:
        self._ex = existing or {}
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
        self._ds_plus_ana = self._entry(
            ds_plus_frm, "Analysis *", 0, ex.get("ds_plus_analysis", "")
        )
        self._ds_plus_ls = self._entry(
            ds_plus_frm, "Loadstep *", 1, ex.get("ds_plus_loadstep", "")
        )

        ds_minus_frm = ttk.LabelFrame(
            self._body, text="Delta Sigma − (analysis, loadstep)"
        )
        ds_minus_frm.pack(fill="x", pady=(4, 0))
        self._ds_minus_ana = self._entry(
            ds_minus_frm, "Analysis *", 0, ex.get("ds_minus_analysis", "")
        )
        self._ds_minus_ls = self._entry(
            ds_minus_frm, "Loadstep *", 1, ex.get("ds_minus_loadstep", "")
        )

        sus_frm = ttk.LabelFrame(self._body, text="Sigma Sustained (optional)")
        sus_frm.pack(fill="x", pady=(4, 0))
        self._sus_ana = self._entry(
            sus_frm, "Analysis", 0, ex.get("sigma_sus_analysis", "")
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


class GeneralTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        self._build()

    def _build(self) -> None:
        frm = ttk.LabelFrame(self, text="Run Options")
        frm.pack(padx=20, pady=20, fill="x")

        ttk.Label(frm, text="Fatigue assessment").grid(
            row=0, column=0, sticky="w", padx=10, pady=6
        )
        self._fatigue = tk.BooleanVar(
            value=self._project["run_options"].get("fatigue", False)
        )
        ttk.Checkbutton(frm, variable=self._fatigue).grid(
            row=0, column=1, sticky="w", padx=10, pady=6
        )

        ttk.Label(frm, text="Additional materials folder").grid(
            row=1, column=0, sticky="w", padx=10, pady=6
        )
        self._matlib = tk.StringVar(
            value=self._project["run_options"].get("matlib_path", "")
        )
        ttk.Entry(frm, textvariable=self._matlib, width=40).grid(
            row=1, column=1, padx=10, pady=6, sticky="w"
        )
        ttk.Button(frm, text="Browse...", command=self._browse_matlib).grid(
            row=1, column=2, padx=4, pady=6
        )

        ttk.Label(frm, text="Output root folder").grid(
            row=2, column=0, sticky="w", padx=10, pady=6
        )
        self._root_dir = tk.StringVar(
            value=self._project["run_options"].get("root_dir", "")
        )
        ttk.Entry(frm, textvariable=self._root_dir, width=40).grid(
            row=2, column=1, padx=10, pady=6, sticky="w"
        )
        ttk.Button(frm, text="Browse...", command=self._browse_root).grid(
            row=2, column=2, padx=4, pady=6
        )

        run_frm = ttk.LabelFrame(self, text="Run")
        run_frm.pack(padx=20, pady=(0, 20), fill="x")
        ttk.Button(
            run_frm, text="Run Bolts Assessment", command=self._run_assessment
        ).pack(padx=10, pady=10)
        self._status_var = tk.StringVar(value="")
        ttk.Label(run_frm, textvariable=self._status_var, foreground="gray").pack(
            padx=10, pady=(0, 6)
        )

    def _browse_matlib(self) -> None:
        d = filedialog.askdirectory(title="Select additional materials folder")
        if d:
            self._matlib.set(d)

    def _browse_root(self) -> None:
        d = filedialog.askdirectory(title="Select output root folder")
        if d:
            self._root_dir.set(d)

    def _run_assessment(self) -> None:
        self.sync()
        root_dir = self._root_dir.get().strip()
        if not root_dir:
            messagebox.showwarning(
                "No root folder", "Please set the output root folder first."
            )
            return
        if not self._project.get("flanges"):
            messagebox.showwarning("No flanges", "Define at least one flange first.")
            return

        self._status_var.set("Building configuration…")
        try:
            configs, geoms = _build_bolts_from_project(self._project)
        except Exception as exc:
            messagebox.showerror("Configuration Error", str(exc))
            self._status_var.set("Configuration error.")
            return

        fatigue = self._project["run_options"].get("fatigue", False)

        log_win = _LogWindow(self.winfo_toplevel())
        handler = _TextHandler(log_win)
        root_logger = logging.getLogger()
        old_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        self._status_var.set("Running…")

        def _work() -> None:
            try:
                from cassy.runners.run_bolts import run_bolts
                from tqdm.contrib.logging import logging_redirect_tqdm

                with logging_redirect_tqdm():
                    run_bolts(
                        root_dir,
                        fatigue=fatigue,
                        geoms=geoms,
                        config_dict=configs,
                    )
                self.after(0, lambda: self._status_var.set("Completed successfully."))
                self.after(
                    0,
                    lambda: log_win.set_done(
                        True, "Assessment completed successfully."
                    ),
                )
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._status_var.set(f"Error: {msg}"))
                self.after(0, lambda: log_win.set_done(False, f"Error: {msg}"))
            finally:
                root_logger.removeHandler(handler)
                root_logger.setLevel(old_level)

        threading.Thread(target=_work, daemon=True).start()

    def sync(self) -> None:
        self._project["run_options"]["fatigue"] = self._fatigue.get()
        self._project["run_options"]["matlib_path"] = self._matlib.get().strip()
        self._project["run_options"]["root_dir"] = self._root_dir.get().strip()

    def load_from_project(self) -> None:
        self._fatigue.set(self._project["run_options"].get("fatigue", False))
        self._matlib.set(self._project["run_options"].get("matlib_path", ""))
        self._root_dir.set(self._project["run_options"].get("root_dir", ""))


# ── Base table tab ────────────────────────────────────────────────────────────


class _TableTab(ttk.Frame):
    """Tab with a Treeview table and Add / Edit / Delete toolbar."""

    _COLUMNS: tuple[str, ...]
    _HEADINGS: dict[str, str]
    _LIST_KEY: str

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        self._build()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=4)
        ttk.Button(toolbar, text="Add", width=7, command=self._add).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Edit", width=7, command=self._edit).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Delete", width=7, command=self._delete).pack(
            side="left", padx=2
        )
        self._extra_toolbar(toolbar)

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        vsb = ttk.Scrollbar(frm, orient="vertical")
        hsb = ttk.Scrollbar(frm, orient="horizontal")
        self._tree = ttk.Treeview(
            frm,
            columns=self._COLUMNS,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
        )
        vsb.config(command=self._tree.yview)
        hsb.config(command=self._tree.xview)
        for col in self._COLUMNS:
            self._tree.heading(col, text=self._HEADINGS.get(col, col), anchor="center")
            self._tree.column(col, width=110, minwidth=60, anchor="center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        self._tree.bind("<Double-1>", lambda _e: self._edit())
        self.refresh()

    def _extra_toolbar(self, toolbar: ttk.Frame) -> None:
        """Override to add extra toolbar buttons."""
        pass

    def _row_values(self, item: dict) -> tuple:
        raise NotImplementedError

    def _list(self) -> list:
        return self._project[self._LIST_KEY]

    def refresh(self) -> None:
        for child in self._tree.get_children():
            self._tree.delete(child)
        for item in self._list():
            self._tree.insert("", "end", values=self._row_values(item))

    def _selected_index(self) -> int | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return list(self._tree.get_children()).index(sel[0])

    def _add(self) -> None:
        raise NotImplementedError

    def _edit(self) -> None:
        raise NotImplementedError

    def _delete(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select an item to delete.")
            return
        if messagebox.askyesno("Delete", "Delete the selected item?"):
            self._list().pop(idx)
            self.refresh()


# ── Geometries tab ────────────────────────────────────────────────────────────


class GeometriesTab(_TableTab):
    """Geometry library tab with import/export support for cross-project reuse."""

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


class BoltSpecsTab(ttk.Frame):
    """Per-flange bolt specification table (Bolt ID, Bolt Geometry, Preload).

    Thread-verification geometry and base-material are part of the geometry
    library definition; they are not shown here.
    """

    _COLUMNS = ("bolt_id", "geom_data", "preload")
    _HEADINGS = {
        "bolt_id": "Bolt ID",
        "geom_data": "Bolt Geometry",
        "preload": "Preload [N]",
    }

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        self._build()

    def _current_flange(self) -> dict | None:
        name = self._fl_var.get()
        if not name:
            return None
        for f in self._project["flanges"]:
            if f["name"] == name:
                return f
        return None

    def _current_bolts(self) -> list:
        fl = self._current_flange()
        return fl["bolts_spec"] if fl else []

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Flange:").pack(side="left", padx=(0, 4))
        self._fl_var = tk.StringVar()
        self._fl_combo = ttk.Combobox(
            top, textvariable=self._fl_var, state="readonly", width=24
        )
        self._fl_combo.pack(side="left")
        self._fl_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_table())
        self.bind("<Map>", lambda _e: self.refresh())

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=2)
        ttk.Button(toolbar, text="Add", width=7, command=self._add).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Edit", width=7, command=self._edit).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Duplicate", width=9, command=self._duplicate).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Delete", width=7, command=self._delete).pack(
            side="left", padx=2
        )

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        vsb = ttk.Scrollbar(frm, orient="vertical")
        hsb = ttk.Scrollbar(frm, orient="horizontal")
        self._tree = ttk.Treeview(
            frm,
            columns=self._COLUMNS,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
        )
        vsb.config(command=self._tree.yview)
        hsb.config(command=self._tree.xview)
        for col in self._COLUMNS:
            self._tree.heading(col, text=self._HEADINGS[col], anchor="center")
            self._tree.column(col, width=130, minwidth=70, anchor="center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        self._tree.bind("<Double-1>", lambda _e: self._edit())

    def refresh(self) -> None:
        fl_names = [f["name"] for f in self._project["flanges"]]
        self._fl_combo["values"] = fl_names
        if self._fl_var.get() not in fl_names:
            self._fl_var.set(fl_names[0] if fl_names else "")
        self._refresh_table()

    def _refresh_table(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for bolt in self._current_bolts():
            self._tree.insert(
                "",
                "end",
                values=(bolt["bolt_id"], bolt["geom_data"], bolt["preload"]),
            )

    def _selected_index(self) -> int | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.index(sel[0])

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

    def _delete(self) -> None:
        fl = self._current_flange()
        if fl is None:
            return
        indices = sorted(self._tree.index(item) for item in self._tree.selection())
        if not indices:
            messagebox.showwarning("Selection", "Select a bolt entry to delete.")
            return
        if len(indices) == 1:
            bolt_id = fl["bolts_spec"][indices[0]]["bolt_id"]
            prompt = f"Delete bolt '{bolt_id}' and its reference events?"
        else:
            prompt = f"Delete {len(indices)} selected bolts and their reference events?"
        if not messagebox.askyesno("Delete", prompt):
            return
        for idx in reversed(indices):
            fl["bolts_spec"].pop(idx)
        self._refresh_table()


# ── Bolt RE tab (base) ────────────────────────────────────────────────────────


class BoltREsTab(ttk.Frame):
    """Reference events table shared across all flanges and bolts.

    Subclassed for fatigue REs.
    """

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

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        self._build()

    def _current_res(self) -> list:
        return self._project[self._RE_KEY]

    def _build(self) -> None:
        self.bind("<Map>", lambda _e: self.refresh())

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=4)
        ttk.Button(toolbar, text="Add", width=7, command=self._add).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Edit", width=7, command=self._edit).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Delete", width=7, command=self._delete).pack(
            side="left", padx=2
        )

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        vsb = ttk.Scrollbar(frm, orient="vertical")
        hsb = ttk.Scrollbar(frm, orient="horizontal")
        self._tree = ttk.Treeview(
            frm,
            columns=self._COLUMNS,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
        )
        vsb.config(command=self._tree.yview)
        hsb.config(command=self._tree.xview)
        for col in self._COLUMNS:
            self._tree.heading(col, text=self._HEADINGS[col], anchor="center")
            self._tree.column(col, width=110, minwidth=60, anchor="center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        self._tree.bind("<Double-1>", lambda _e: self._edit())

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

    def refresh(self) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for re in self._current_res():
            self._tree.insert("", "end", values=self._row_values(re))

    def _selected_index(self) -> int | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.index(sel[0])

    def _make_dialog(self, parent: tk.Widget, existing: dict | None = None):
        return BoltREDialog(parent, existing=existing)

    def _add(self) -> None:
        dlg = self._make_dialog(self)
        if dlg.result is None:
            return
        re_list = self._project[self._RE_KEY]
        if any(r["re_id"] == dlg.result["re_id"] for r in re_list):
            messagebox.showerror(
                "Duplicate",
                f"RE '{dlg.result['re_id']}' already exists.",
            )
            return
        re_list.append(dlg.result)
        self._refresh_table()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a reference event to edit.")
            return
        re_list = self._project[self._RE_KEY]
        dlg = self._make_dialog(self, existing=re_list[idx])
        if dlg.result:
            re_list[idx] = dlg.result
            self._refresh_table()

    def _delete(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a reference event to delete.")
            return
        if messagebox.askyesno("Delete", "Delete the selected reference event?"):
            self._project[self._RE_KEY].pop(idx)
            self._refresh_table()


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

    def _make_dialog(self, parent: tk.Widget, existing: dict | None = None):
        return BoltFatigueREDialog(parent, existing=existing)

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


class BoltTDPATab(ttk.Frame):
    """Grid of (flange × bolt) × reference events; each cell holds T and DPA entries."""

    _PROJECT_KEY = "tdpa"
    _RE_KEY = "reference_events"

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        # key: (flange_name, bolt_id, re_id) -> (t_var, dpa_var)
        self._cell_vars: dict[
            tuple[str, str, str], tuple[tk.StringVar, tk.StringVar]
        ] = {}
        self._build_shell()
        self.after(0, self.rebuild_grid)

    def _build_shell(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=4)
        ttk.Button(toolbar, text="Refresh grid", command=self.rebuild_grid).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Import CSV...", command=self._import_csv).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Export CSV...", command=self._export_csv).pack(
            side="left", padx=2
        )
        ttk.Label(
            toolbar,
            text="CSV columns: flange, bolt, event, T, DPA",
            foreground="gray",
        ).pack(side="left", padx=8)

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._canvas = tk.Canvas(outer, borderwidth=0, background="#f0f0f0")
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        self._inner = ttk.Frame(self._canvas)
        self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )

    def rebuild_grid(self) -> None:
        for widget in self._inner.winfo_children():
            widget.destroy()
        self._cell_vars.clear()

        flanges = self._project.get("flanges", [])
        flange_bolt_pairs: list[tuple[str, str]] = [
            (f["name"], b["bolt_id"]) for f in flanges for b in f.get("bolts_spec", [])
        ]
        re_ids = [r["re_id"] for r in self._project.get(self._RE_KEY, [])]
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_re_ids: list[str] = []
        for rid in re_ids:
            if rid not in seen:
                seen.add(rid)
                unique_re_ids.append(rid)

        if not flange_bolt_pairs or not unique_re_ids:
            ttk.Label(
                self._inner,
                text="No data to display (add flanges, bolts and reference events first).",
                foreground="gray",
            ).grid(padx=20, pady=20)
            return

        existing: dict[tuple[str, str, str], tuple[str, str]] = {
            (e["flange"], e["bolt_id"], e["re_id"]): (str(e["T"]), str(e["dpa"]))
            for e in self._project.get(self._PROJECT_KEY, [])
            if "bolt_id" in e
        }

        CELL_W = 9

        # Header row 0: Flange | Bolt ID | [RE1 colspan=2] [RE2 colspan=2] ...
        ttk.Label(
            self._inner,
            text="Flange",
            relief="groove",
            width=16,
            anchor="center",
            padding=3,
        ).grid(row=0, column=0, rowspan=2, sticky="nsew", padx=1, pady=1)
        ttk.Label(
            self._inner,
            text="Bolt ID",
            relief="groove",
            width=10,
            anchor="center",
            padding=3,
        ).grid(row=0, column=1, rowspan=2, sticky="nsew", padx=1, pady=1)

        for c, re_id in enumerate(unique_re_ids):
            ttk.Label(
                self._inner,
                text=re_id,
                relief="groove",
                width=CELL_W * 2 + 1,
                anchor="center",
                padding=3,
            ).grid(row=0, column=2 + c * 2, columnspan=2, sticky="nsew", padx=1, pady=1)
            ttk.Label(
                self._inner,
                text="T [°C]",
                relief="groove",
                width=CELL_W,
                anchor="center",
            ).grid(row=1, column=2 + c * 2, sticky="nsew", padx=1, pady=1)
            ttk.Label(
                self._inner, text="DPA", relief="groove", width=CELL_W, anchor="center"
            ).grid(row=1, column=3 + c * 2, sticky="nsew", padx=1, pady=1)

        for row_idx, (flange_name, bolt_id) in enumerate(flange_bolt_pairs):
            ttk.Label(
                self._inner,
                text=flange_name,
                relief="groove",
                width=16,
                anchor="center",
            ).grid(row=2 + row_idx, column=0, sticky="nsew", padx=1, pady=1)
            ttk.Label(
                self._inner,
                text=bolt_id,
                relief="groove",
                width=10,
                anchor="center",
            ).grid(row=2 + row_idx, column=1, sticky="nsew", padx=1, pady=1)
            for c, re_id in enumerate(unique_re_ids):
                t_def, dpa_def = existing.get((flange_name, bolt_id, re_id), ("", "0"))
                t_var = tk.StringVar(value=t_def)
                dpa_var = tk.StringVar(value=dpa_def)
                self._cell_vars[(flange_name, bolt_id, re_id)] = (t_var, dpa_var)
                ttk.Entry(self._inner, textvariable=t_var, width=CELL_W).grid(
                    row=2 + row_idx, column=2 + c * 2, padx=1, pady=1
                )
                ttk.Entry(self._inner, textvariable=dpa_var, width=CELL_W).grid(
                    row=2 + row_idx, column=3 + c * 2, padx=1, pady=1
                )

    def _import_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Import T & DPA from CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        errors: list[str] = []
        loaded = 0
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for lineno, row in enumerate(reader, start=2):
                    row = {k.strip().lower(): v.strip() for k, v in row.items()}
                    flange = row.get("flange", "")
                    bolt = row.get("bolt", "")
                    event = row.get("event", "")
                    t_raw = row.get("t", "")
                    dpa_raw = row.get("dpa", "")
                    if not (flange and bolt and event):
                        errors.append(
                            f"Line {lineno}: missing flange/bolt/event — skipped"
                        )
                        continue
                    key = (flange, bolt, event)
                    if key not in self._cell_vars:
                        errors.append(
                            f"Line {lineno}: ({flange!r}, {bolt!r}, {event!r}) not in grid — skipped"
                        )
                        continue
                    t_var, dpa_var = self._cell_vars[key]
                    t_var.set(t_raw)
                    dpa_var.set(dpa_raw)
                    loaded += 1
        except Exception as exc:
            messagebox.showerror("Import Error", str(exc))
            return
        summary = f"Imported {loaded} value(s)."
        if errors:
            summary += f"\n\nWarnings ({len(errors)}):\n" + "\n".join(errors[:20])
            if len(errors) > 20:
                summary += f"\n… and {len(errors) - 20} more"
        messagebox.showinfo("Import complete", summary)

    def _export_csv(self) -> None:
        if not self._cell_vars:
            messagebox.showwarning(
                "Empty grid", "No data to export (build the grid first)."
            )
            return
        path = filedialog.asksaveasfilename(
            title="Export T & DPA to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["flange", "bolt", "event", "T", "DPA"])
                for (flange_name, bolt_id, re_id), (
                    t_var,
                    dpa_var,
                ) in self._cell_vars.items():
                    writer.writerow(
                        [flange_name, bolt_id, re_id, t_var.get(), dpa_var.get()]
                    )
            messagebox.showinfo("Export complete", f"T & DPA data saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def sync(self) -> list[str]:
        """Read cells into project[_PROJECT_KEY]; return validation errors."""
        entries = []
        errors = []
        for (flange_name, bolt_id, re_id), (t_var, dpa_var) in self._cell_vars.items():
            t_str = t_var.get().strip()
            dpa_str = dpa_var.get().strip()
            if not t_str:
                continue
            try:
                T = float(t_str)
                dpa = float(dpa_str) if dpa_str else 0.0
            except ValueError:
                errors.append(
                    f"Flange '{flange_name}' / Bolt '{bolt_id}' / RE '{re_id}': T and DPA must be numbers"
                )
                continue
            entries.append(
                {
                    "flange": flange_name,
                    "bolt_id": bolt_id,
                    "re_id": re_id,
                    "T": T,
                    "dpa": dpa,
                }
            )
        self._project[self._PROJECT_KEY] = entries
        return errors


# ── Bolt T & DPA Fatigue tab ──────────────────────────────────────────────────


class BoltFatigueTDPATab(BoltTDPATab):
    _PROJECT_KEY = "tdpa_fatigue"
    _RE_KEY = "fatigue_reference_events"


# ── Log window ────────────────────────────────────────────────────────────────


class _LogWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Cassy \u2014 Assessment Log")
        self.geometry("860x540")
        self.resizable(True, True)
        _set_icon(self)

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=6, pady=6)
        self._text = tk.Text(
            frm,
            state="disabled",
            wrap="none",
            font=("Courier New", 9),
            bg="#1e1e1e",
            fg="#d4d4d4",
        )
        vsb = ttk.Scrollbar(frm, orient="vertical", command=self._text.yview)
        hsb = ttk.Scrollbar(frm, orient="horizontal", command=self._text.xview)
        self._text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._text.pack(side="left", fill="both", expand=True)

        bot = ttk.Frame(self)
        bot.pack(fill="x", padx=6, pady=(2, 6))
        self._status = tk.Label(bot, text="Running\u2026", anchor="w")
        self._status.pack(side="left", fill="x", expand=True)
        ttk.Button(bot, text="Close", command=self.destroy).pack(side="right")

    def append(self, text: str) -> None:
        self._text.configure(state="normal")
        self._text.insert("end", text + "\n")
        self._text.see("end")
        self._text.configure(state="disabled")

    def set_done(self, success: bool, msg: str) -> None:
        color = "#4caf50" if success else "#f44336"
        self._status.configure(text=msg, foreground=color)


class _TextHandler(logging.Handler):
    def __init__(self, win: _LogWindow) -> None:
        super().__init__()
        self._win = win
        self.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._win.after(0, self._win.append, msg)
        except Exception:
            pass


# ── Builder helpers ───────────────────────────────────────────────────────────


def _build_bolts_from_project(
    project: dict,
) -> tuple[dict, dict]:
    """Build ``(configs, geoms)`` from the in-memory project dict.

    Returns
    -------
    configs : dict[str, FlangeAssessmentConfig]
        One entry per flange, keyed by flange name.
    geoms : dict[str, BoltLikeGeom]
        Geometry objects keyed by ``"{base_name}_{type}"``
        (e.g. ``"M8_bolt"``, ``"M8_ins_insert"``).
    """
    import pandas as pd

    from cassy.bolts.bolt_config import (
        BoltReferenceEvent,
        BoltReferenceEventFatigue,
        FlangeAssessmentConfig,
    )
    from cassy.bolts.geometry import BoltGeom, InsertGeom
    from cassy.designcodes.map import BOLT_CODES
    from cassy.runners.run_common import build_material_library

    matlib = project["run_options"].get("matlib_path") or None
    materials = build_material_library(matlib)
    fatigue = project["run_options"].get("fatigue", False)

    # ---- Build geometry objects ----
    geoms: dict = {}
    for geom_entry in project.get("geometries", []):
        base_name = geom_entry["base_name"]
        geom_type = geom_entry["type"]
        mat_name = geom_entry["material"]
        if mat_name not in materials:
            raise ValueError(
                f"Material '{mat_name}' not found in the library "
                f"(geometry '{base_name}')."
            )

        kwargs: dict = {
            "name": f"{base_name}_{geom_type}",
            "material": materials[mat_name],
            "p": geom_entry.get("p", 0),
            "d": geom_entry.get("d", 0),
            "Le": geom_entry.get("Le", 0),
            "d_vh": geom_entry.get("d_vh", 0),
            "f": geom_entry.get("f", 0.15),
            "dn": geom_entry.get("dn"),
            "df": geom_entry.get("df"),
            "D": geom_entry.get("D"),
        }

        if geom_type == "bolt":
            kwargs.update(
                {
                    "f_prime": geom_entry.get("f_prime", 0.15),
                    "B": geom_entry.get("B", 0),
                    "C": geom_entry.get("C", 0),
                    "KF": geom_entry.get("KF", 4),
                    "d1": geom_entry.get("d1"),
                    "H": geom_entry.get("H"),
                    "a": geom_entry.get("a"),
                    "Dm": geom_entry.get("Dm"),
                    "Dp": geom_entry.get("Dp"),
                }
            )
            geoms[f"{base_name}_bolt"] = BoltGeom(**kwargs)
        elif geom_type == "insert":
            geoms[f"{base_name}_insert"] = InsertGeom(**kwargs)

    # ---- Build FlangeAssessmentConfig objects ----
    configs: dict = {}
    for flange in project.get("flanges", []):
        flange_name = flange["name"]
        actions_file = flange.get("actions_file", "")
        if not actions_file or not os.path.exists(actions_file):
            raise ValueError(
                f"Actions CSV not found for flange '{flange_name}': '{actions_file}'"
            )
        actions = pd.read_csv(actions_file)
        actions["boltID"] = actions["boltID"].astype(str)
        actions.set_index(["boltID", "analysis", "loadstep"], inplace=True)

        code = BOLT_CODES[flange["design_code"]]

        # bolts_spec DataFrame — insert row added automatically when a matching
        # insert geometry (same base_name) exists in the geometry library
        rows = []
        for bolt_entry in flange.get("bolts_spec", []):
            bolt_id = str(bolt_entry["bolt_id"])
            bolt_geom_name = bolt_entry["geom_data"]
            rows.append(
                {
                    "Bolt ID": bolt_id,
                    "Geom type": "bolt",
                    "Geom data": bolt_geom_name,
                    "Preload [N]": float(bolt_entry["preload"]),
                }
            )
            if f"{bolt_geom_name}_insert" in geoms:
                rows.append(
                    {
                        "Bolt ID": bolt_id,
                        "Geom type": "insert",
                        "Geom data": bolt_geom_name,
                        "Preload [N]": 0.0,
                    }
                )
        bolts_spec = (
            pd.DataFrame(rows).set_index("Bolt ID")
            if rows
            else pd.DataFrame(columns=["Geom type", "Geom data", "Preload [N]"])
        )

        # Reference events — per bolt; T/DPA from tdpa table keyed by (flange, bolt_id, re_id)
        tdpa_lut: dict[tuple[str, str, str], tuple[float, float]] = {
            (e["flange"], e["bolt_id"], e["re_id"]): (float(e["T"]), float(e["dpa"]))
            for e in project.get("tdpa", [])
            if "bolt_id" in e
        }
        shared_res = project.get("reference_events", [])
        REs: dict = {}
        for bolt_entry in flange.get("bolts_spec", []):
            bid = str(bolt_entry["bolt_id"])
            REs[bid] = [
                BoltReferenceEvent(
                    name=re["re_id"],
                    oper_cond=re.get("oc", "N/A"),
                    init_event=re.get("ie", "N/A"),
                    concat_event=re.get("ce", "N/A"),
                    temp=tdpa_lut.get((flange_name, bid, re["re_id"]), (0.0, 0.0))[0],
                    dpa=tdpa_lut.get((flange_name, bid, re["re_id"]), (0.0, 0.0))[1],
                    load_category=re.get("load_category", "I"),
                    service_lvl=re.get("service_lvl", "A"),
                    primary=(re["primary_analysis"], re["primary_loadstep"]),
                    all_loads=(re["all_analysis"], re["all_loadstep"]),
                )
                for re in shared_res
            ]

        # Fatigue reference events — per bolt; T/DPA from tdpa_fatigue table keyed by (flange, bolt_id, re_id)
        REs_fatigue = None
        if fatigue:
            tdpa_fat_lut: dict[tuple[str, str, str], tuple[float, float]] = {
                (e["flange"], e["bolt_id"], e["re_id"]): (
                    float(e["T"]),
                    float(e["dpa"]),
                )
                for e in project.get("tdpa_fatigue", [])
                if "bolt_id" in e
            }
            shared_fat_res = project.get("fatigue_reference_events", [])
            REs_fatigue = {}
            for bolt_entry in flange.get("bolts_spec", []):
                bid = str(bolt_entry["bolt_id"])
                bolt_fat_re_list = []
                for re in shared_fat_res:
                    sus_ana = re.get("sigma_sus_analysis", "")
                    sus_ls = re.get("sigma_sus_loadstep", "")
                    sigma_sus = (sus_ana, sus_ls) if (sus_ana and sus_ls) else None
                    T_fat, dpa_fat = tdpa_fat_lut.get(
                        (flange_name, bid, re["re_id"]), (0.0, 0.0)
                    )
                    bolt_fat_re_list.append(
                        BoltReferenceEventFatigue(
                            name=re["re_id"],
                            oper_cond=re.get("oc", "N/A"),
                            init_event=re.get("ie", "N/A"),
                            concat_event=re.get("ce", "N/A"),
                            temp=T_fat,
                            dpa=dpa_fat,
                            load_category=re.get("load_category", "I"),
                            service_lvl=re.get("service_lvl", "A"),
                            n_cycles=int(re["n_cycles"]),
                            delta_sigma=(
                                (re["ds_plus_analysis"], re["ds_plus_loadstep"]),
                                (re["ds_minus_analysis"], re["ds_minus_loadstep"]),
                            ),
                            sigma_sustained=sigma_sus,
                        )
                    )
                REs_fatigue[bid] = bolt_fat_re_list

        configs[flange_name] = FlangeAssessmentConfig(
            actions=actions,
            code=code,
            bolts_spec=bolts_spec,
            REs=REs,
            REs_fatigue=REs_fatigue,
            name=flange_name,
        )

    return configs, geoms


# ── Main application window ───────────────────────────────────────────────────


class BoltsGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Cassy \u2014 Bolts Assessment Configuration")
        self.geometry("1100x680")
        self.minsize(800, 520)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        _set_icon(self)

        self._project_path: str | None = None
        self._project: dict = _fresh_project()

        self._build_menu()
        self._build_tabs()

    # ── Menu ──────────────────────────────────────────────────

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", accelerator="Ctrl+N", command=self._new)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self._open)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self._save)
        file_menu.add_command(label="Save As...", command=self._save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)

        self.bind_all("<Control-n>", lambda _e: self._new())
        self.bind_all("<Control-o>", lambda _e: self._open())
        self.bind_all("<Control-s>", lambda _e: self._save())

    # ── Tabs ──────────────────────────────────────────────────

    def _build_tabs(self) -> None:
        if hasattr(self, "_nb"):
            self._nb.destroy()
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=5, pady=5)

        self._tab_general = GeneralTab(self._nb, self._project)
        self._tab_geoms = GeometriesTab(self._nb, self._project)
        self._tab_flanges = FlangesTab(self._nb, self._project)
        self._tab_bolt_specs = BoltSpecsTab(self._nb, self._project)
        self._tab_res = BoltREsTab(self._nb, self._project)
        self._tab_fat_res = BoltFatigueREsTab(self._nb, self._project)
        self._tab_tdpa = BoltTDPATab(self._nb, self._project)
        self._tab_tdpa_fat = BoltFatigueTDPATab(self._nb, self._project)

        self._nb.add(self._tab_general, text="  General  ")
        self._nb.add(self._tab_geoms, text="  Geometries  ")
        self._nb.add(self._tab_flanges, text="  Flanges  ")
        self._nb.add(self._tab_bolt_specs, text="  Bolt Specs  ")
        self._nb.add(self._tab_res, text="  Ref. Events  ")
        self._nb.add(self._tab_fat_res, text="  Fat. Ref. Events  ")
        self._nb.add(self._tab_tdpa, text="  T & DPA  ")
        self._nb.add(self._tab_tdpa_fat, text="  T & DPA Fatigue  ")

    # ── Sync / refresh helpers ────────────────────────────────

    def _sync_all(self) -> None:
        self._tab_general.sync()
        self._tab_tdpa.sync()
        self._tab_tdpa_fat.sync()

    def _refresh_all_tabs(self) -> None:
        self._tab_general.load_from_project()
        self._tab_geoms.refresh()
        self._tab_flanges.refresh()
        self._tab_bolt_specs.refresh()
        self._tab_res.refresh()
        self._tab_fat_res.refresh()
        self._tab_tdpa.rebuild_grid()
        self._tab_tdpa_fat.rebuild_grid()

    # ── File operations ───────────────────────────────────────

    def _new(self) -> None:
        if not messagebox.askyesno("New Project", "Discard current project?"):
            return
        self._project.clear()
        self._project.update(_fresh_project())
        self._project_path = None
        self.title("Cassy \u2014 Bolts Assessment Configuration")
        self._refresh_all_tabs()
        self.focus_force()

    def _open(self) -> None:
        path = filedialog.askopenfilename(
            title="Open bolts project",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            messagebox.showerror("Open Error", str(exc))
            return
        self._project.clear()
        self._project.update(data)
        self._project_path = path
        self.title(f"Cassy \u2014 {os.path.basename(path)}")
        self._refresh_all_tabs()

    def _save(self) -> None:
        if self._project_path is None:
            self._save_as()
        else:
            self._write(self._project_path)

    def _save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save bolts project as",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self._project_path = path
        self._write(path)

    def _write(self, path: str) -> None:
        self._sync_all()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._project, fh, indent=2)
            self.title(f"Cassy \u2014 {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))


# ── Module helpers ────────────────────────────────────────────────────────────


def _fresh_project() -> dict:
    return copy.deepcopy(EMPTY_BOLT_PROJECT)


def main() -> None:
    app = BoltsGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
