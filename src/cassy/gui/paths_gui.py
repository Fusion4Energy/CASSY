"""GUI for configuring paths assessments in cassy.

Workflow (tabs in order):
  1. General   — run options (fatigue, material library)
  2. Submodels — submodel definitions
  3. Loads     — single load definitions (stress properties + FEA mapping)
  4. Ref. Events — reference events built from selected loads
  5. Fatigue Ref. Events — fatigue-specific reference events
  6. Paths     — path metadata and RE assignment per submodel
  7. T & DPA   — temperature and irradiation table (submodel × path × RE)
  8. T & DPA Fatigue — same table for fatigue reference events

The project state is saved and loaded as JSON.
"""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import copy
import csv
import logging
import threading

# ── Icon helper ───────────────────────────────────────────────────────────────

_ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.png")


def _set_icon(window: tk.Wm) -> None:
    """Apply the application icon to *window* if the file exists.

    Replace ``icon.png`` in the same folder as this module with the real
    application icon at any time; the change takes effect on the next launch.
    Silently ignored when the file is missing or the image cannot be loaded.
    """
    try:
        from PIL import Image, ImageTk  # type: ignore

        img = Image.open(_ICON_PATH)
        _set_icon._photo = ImageTk.PhotoImage(img)  # keep reference alive
        window.iconphoto(True, _set_icon._photo)
    except Exception:
        pass


# ── Constants ─────────────────────────────────────────────────────────────────


from cassy.designcodes.map import PATH_CODES as _PATH_CODES
from cassy.paths.paths_config import (
    LoadType,
    PathType,
    SpatialRecMethod,
    StressClassification,
)

DESIGN_CODES: list[str] = list(_PATH_CODES.keys())
STRESS_TYPES: list[str] = [e.value for e in StressClassification]
LOAD_TYPES: list[str] = [e.value for e in LoadType]
SPATIAL_REC_METHODS: list[str] = [e.value for e in SpatialRecMethod]
PATH_TYPES: list[str] = [e.value for e in PathType]


UNITS = ["Pa", "MPa", "kPa"]
SERVICE_LEVELS = ["A", "C", "D"]

EMPTY_PROJECT: dict[str, Any] = {
    "run_options": {
        "fatigue": False,
        "matlib_path": "",
        "root_dir": "",
    },
    "loads": [],
    "reference_events": [],
    "fatigue_reference_events": [],
    "submodels": [],  # [{name, design_code, tensors_file}]
    "paths": {},  # {submodel_name: [path_dict, ...]}
    "tdpa": [],  # [{submodel, path_num, re_id, T, dpa}]
    "tdpa_fatigue": [],
}


def _bool_label(v: bool) -> str:
    return "Yes" if v else "No"


def _get_material_names() -> list[str]:
    """Return available material names from the built-in library."""

    from cassy.runners.run_common import build_material_library

    return sorted(build_material_library().keys())


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
        self._body = ttk.Frame(self)
        self._body.pack(padx=12, pady=(12, 4), fill="both")
        self._build()
        self._add_buttons()
        self.wait_visibility()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()

    # -- subclasses override these ------------------------------------------

    def _build(self) -> None:
        raise NotImplementedError

    def _collect(self) -> dict | None:
        """Validate and return result dict, or None to cancel OK."""
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
        self, frame, label: str, row: int, values: list[str], default: str = ""
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

    @staticmethod
    def _multiselect(
        frame, label: str, row: int, items: list[str], selected: list[str]
    ) -> tk.Listbox:
        ttk.Label(frame, text=label).grid(
            row=row, column=0, sticky="nw", padx=6, pady=3
        )
        wrapper = ttk.Frame(frame)
        wrapper.grid(row=row, column=1, padx=6, pady=3)
        sb = ttk.Scrollbar(wrapper, orient="vertical")
        lb = tk.Listbox(
            wrapper,
            selectmode="multiple",
            yscrollcommand=sb.set,
            height=5,
            width=30,
            exportselection=False,
        )
        sb.config(command=lb.yview)
        lb.pack(side="left")
        sb.pack(side="left", fill="y")
        for i, name in enumerate(items):
            lb.insert("end", name)
            if name in selected:
                lb.selection_set(i)
        return lb

    def _file_entry(
        self,
        frame,
        label: str,
        row: int,
        default: str = "",
        filetypes: list | None = None,
    ) -> tk.StringVar:
        """Entry + Browse … button for a file path."""
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


# ── Submodel dialog ───────────────────────────────────────────────────────────


class SubmodelDialog(_Dialog):
    def __init__(self, parent: tk.Widget, existing: dict | None = None) -> None:
        self._ex = existing or {}
        super().__init__(parent, "Add / Edit Submodel")

    def _build(self) -> None:
        ex = self._ex
        frm = ttk.LabelFrame(self._body, text="Submodel definition")
        frm.pack(fill="both")
        self._name = self._entry(frm, "Name *", 0, ex.get("name", ""))
        default_code = ex.get("design_code", DESIGN_CODES[0] if DESIGN_CODES else "")
        self._code = self._combo(frm, "Design Code", 1, DESIGN_CODES, default_code)
        self._tensors = self._file_entry(
            frm,
            "Stress tensors CSV",
            2,
            ex.get("tensors_file", ""),
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
            "tensors_file": self._tensors.get().strip(),
        }


# ── Load dialog ───────────────────────────────────────────────────────────────


def _get_available_analyses(project: dict) -> list[str]:
    """Return sorted unique analysis names found in all submodels' tensor CSVs."""
    names: set[str] = set()
    for sm in project.get("submodels", []):
        path = sm.get("tensors_file", "")
        if path and os.path.exists(path):
            try:
                import pandas as pd

                col = pd.read_csv(path, usecols=["analysis"])["analysis"]
                names.update(col.dropna().astype(str).unique())
            except Exception:
                pass
    return sorted(names)


class LoadDialog(_Dialog):
    def __init__(
        self,
        parent: tk.Widget,
        existing: dict | None = None,
        analyses: list[str] | None = None,
    ) -> None:
        self._ex = existing or {}
        self._analyses = analyses or []
        super().__init__(parent, "Add / Edit Load")

    def _build(self) -> None:
        ex = self._ex
        frm = ttk.LabelFrame(self._body, text="Load definition")
        frm.pack(fill="both")
        self._name = self._entry(frm, "Name *", 0, ex.get("name", ""))
        if self._analyses:
            self._analysis = self._combo(
                frm, "Analysis name *", 1, self._analyses, ex.get("analysis_name", "")
            )
        else:
            self._analysis = self._entry(
                frm, "Analysis name *", 1, ex.get("analysis_name", "")
            )
        self._timestep = self._entry(frm, "Time step *", 2, ex.get("time_step", "1"))
        self._stype = self._combo(
            frm, "Stress type", 3, STRESS_TYPES, ex.get("stress_type", "P")
        )
        self._ltype = self._combo(
            frm, "Load type", 4, LOAD_TYPES, ex.get("load_type", "Volumetric")
        )
        self._unit = self._combo(frm, "Unit", 5, UNITS, ex.get("unit", "Pa"))
        self._scale = self._entry(frm, "Scale", 6, str(ex.get("scale", 1.0)))
        self._spatial = self._combo(
            frm,
            "Spatial recombination",
            7,
            SPATIAL_REC_METHODS,
            ex.get("spatial_rec", "algebraic"),
        )
        self._is_pd = self._check(frm, "Plasma Disruption?", 8, ex.get("is_pd", False))
        self._is_cyclic = self._check(frm, "Is Cyclic?", 9, ex.get("is_cyclic", False))
        self._is_pressure = self._check(
            frm, "Is Pressure?", 10, ex.get("is_pressure", False)
        )
        self._is_short = self._check(
            frm, "Is Short Overstress?", 11, ex.get("is_short_overstress", False)
        )

    def _collect(self) -> dict | None:
        name = self._name.get().strip()
        if not name:
            messagebox.showerror("Validation", "Name is required.", parent=self)
            return None
        analysis = self._analysis.get().strip()
        if not analysis:
            messagebox.showerror(
                "Validation", "Analysis name is required.", parent=self
            )
            return None
        timestep = self._timestep.get().strip()
        if not timestep:
            messagebox.showerror("Validation", "Time step is required.", parent=self)
            return None
        try:
            scale = float(self._scale.get())
        except ValueError:
            messagebox.showerror("Validation", "Scale must be a number.", parent=self)
            return None
        return {
            "name": name,
            "analysis_name": analysis,
            "time_step": timestep,
            "stress_type": self._stype.get(),
            "load_type": self._ltype.get(),
            "unit": self._unit.get(),
            "scale": scale,
            "spatial_rec": self._spatial.get(),
            "is_pd": self._is_pd.get(),
            "is_cyclic": self._is_cyclic.get(),
            "is_pressure": self._is_pressure.get(),
            "is_short_overstress": self._is_short.get(),
        }


# ── Reference Event dialog ────────────────────────────────────────────────────


class REDialog(_Dialog):
    def __init__(
        self,
        parent: tk.Widget,
        load_names: list[str],
        existing: dict | None = None,
    ) -> None:
        self._load_names = load_names
        self._ex = existing or {}
        super().__init__(parent, "Add / Edit Reference Event")

    def _build(self) -> None:
        ex = self._ex
        frm = ttk.LabelFrame(self._body, text="Reference Event definition")
        frm.pack(fill="both")
        self._re_id = self._entry(frm, "RE ID *", 0, ex.get("re_id", ""))
        self._svc = self._combo(
            frm, "Service level", 1, SERVICE_LEVELS, ex.get("service_lvl", "A")
        )
        self._oc = self._entry(frm, "Operating Conditions", 2, ex.get("oc", "N/A"))
        self._ie = self._entry(frm, "Initiating Event", 3, ex.get("ie", "N/A"))
        self._ce = self._entry(frm, "Concatenated Event", 4, ex.get("ce", "N/A"))
        self._lctg = self._entry(frm, "Load category", 5, ex.get("load_ctg", "N/A"))
        self._ncycles = self._entry(
            frm,
            "N cycles (blank = N/A)",
            6,
            "" if ex.get("ncycles") is None else str(ex["ncycles"]),
        )
        self._loads_lb = self._multiselect(
            frm, "Loads *", 7, self._load_names, ex.get("loads", [])
        )

    def _collect(self) -> dict | None:
        re_id = self._re_id.get().strip()
        if not re_id:
            messagebox.showerror("Validation", "RE ID is required.", parent=self)
            return None
        sel = self._loads_lb.curselection()
        if not sel:
            messagebox.showerror("Validation", "Select at least one load.", parent=self)
            return None
        ncycles_raw = self._ncycles.get().strip()
        if ncycles_raw:
            if not ncycles_raw.isdigit():
                messagebox.showerror(
                    "Validation", "N cycles must be a positive integer.", parent=self
                )
                return None
            ncycles = int(ncycles_raw)
        else:
            ncycles = None
        return {
            "re_id": re_id,
            "service_lvl": self._svc.get(),
            "loads": [self._load_names[i] for i in sel],
            "oc": self._oc.get().strip(),
            "ie": self._ie.get().strip(),
            "ce": self._ce.get().strip(),
            "load_ctg": self._lctg.get().strip(),
            "ncycles": ncycles,
        }


# ── Path dialog ───────────────────────────────────────────────────────────────


class PathDialog(_Dialog):
    def __init__(
        self,
        parent: tk.Widget,
        mat_names: list[str],
        existing: dict | None = None,
    ) -> None:
        self._mat_names = mat_names
        self._ex = existing or {}
        super().__init__(parent, "Add / Edit Path")

    def _build(self) -> None:
        ex = self._ex
        frm = ttk.LabelFrame(self._body, text="Path definition")
        frm.pack(fill="both")
        self._pnum = self._entry(frm, "Path number *", 0, str(ex.get("path_num", "")))
        default_mat = ex.get("material", self._mat_names[0] if self._mat_names else "")
        self._mat = self._combo(frm, "Material", 1, self._mat_names, default_mat)
        self._ptype = self._combo(
            frm, "Path type", 2, PATH_TYPES, ex.get("ptype", "normal")
        )
        self._wn = self._entry(frm, "Welding n", 3, str(ex.get("welding_n", 1.0)))
        self._wf = self._entry(frm, "Welding f", 4, str(ex.get("welding_f", 1.0)))

    def _collect(self) -> dict | None:
        pnum_str = self._pnum.get().strip()
        if not pnum_str.isdigit():
            messagebox.showerror(
                "Validation", "Path number must be a positive integer.", parent=self
            )
            return None
        try:
            wn = float(self._wn.get())
            wf = float(self._wf.get())
        except ValueError:
            messagebox.showerror(
                "Validation", "Welding factors must be numbers.", parent=self
            )
            return None
        return {
            "path_num": int(pnum_str),
            "material": self._mat.get(),
            "ptype": self._ptype.get(),
            "welding_n": wn,
            "welding_f": wf,
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
            run_frm, text="Run Cassy Assessment", command=self._run_assessment
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
        if not self._project.get("submodels"):
            messagebox.showwarning(
                "No submodels", "Define at least one submodel first."
            )
            return

        self._status_var.set("Running…")
        fatigue = self._project["run_options"].get("fatigue", False)
        matlib = self._project["run_options"].get("matlib_path") or None
        configs = _build_configs_from_project(self._project)

        log_win = _LogWindow(self.winfo_toplevel())
        handler = _TextHandler(log_win)
        root_logger = logging.getLogger()
        old_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)

        def _work() -> None:
            try:
                from cassy.runners.run_paths import run_paths
                from tqdm.contrib.logging import logging_redirect_tqdm

                with logging_redirect_tqdm():
                    run_paths(root_dir, fatigue=fatigue, matlib=matlib, configs=configs)
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

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        vsb = ttk.Scrollbar(frm, orient="vertical")
        hsb = ttk.Scrollbar(frm, orient="horizontal")
        style = ttk.Style()
        style.configure(
            "BoldHeading.Treeview.Heading", font=("TkDefaultFont", 10, "bold")
        )
        self._tree = ttk.Treeview(
            frm,
            columns=self._COLUMNS,
            show="headings",
            style="BoldHeading.Treeview",
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

    def _row_values(self, item: dict) -> tuple:
        raise NotImplementedError

    def refresh(self) -> None:
        for child in self._tree.get_children():
            self._tree.delete(child)
        for item in self._project[self._LIST_KEY]:
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
            self._project[self._LIST_KEY].pop(idx)
            self.refresh()


# ── Submodels tab ─────────────────────────────────────────────────────────────


class SubmodelsTab(_TableTab):
    _COLUMNS = ("name", "design_code", "tensors_file")
    _HEADINGS = {
        "name": "Name",
        "design_code": "Design Code",
        "tensors_file": "Stress Tensors CSV",
    }
    _LIST_KEY = "submodels"

    def _row_values(self, item: dict) -> tuple:
        return (item["name"], item["design_code"], item.get("tensors_file", ""))

    def _add(self) -> None:
        dlg = SubmodelDialog(self)
        if dlg.result is None:
            return
        name = dlg.result["name"]
        if any(s["name"] == name for s in self._project["submodels"]):
            messagebox.showerror("Duplicate", f"Submodel '{name}' already exists.")
            return
        self._project["submodels"].append(dlg.result)
        self._project["paths"].setdefault(name, [])
        self.refresh()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a submodel to edit.")
            return
        old_name = self._project["submodels"][idx]["name"]
        dlg = SubmodelDialog(self, existing=self._project["submodels"][idx])
        if dlg.result is None:
            return
        new_name = dlg.result["name"]
        if new_name != old_name:
            if any(
                s["name"] == new_name
                for i, s in enumerate(self._project["submodels"])
                if i != idx
            ):
                messagebox.showerror(
                    "Duplicate", f"Submodel '{new_name}' already exists."
                )
                return
            paths = self._project["paths"].pop(old_name, [])
            self._project["paths"][new_name] = paths
            for entry in self._project["tdpa"]:
                if entry.get("submodel") == old_name:
                    entry["submodel"] = new_name
            for entry in self._project["tdpa_fatigue"]:
                if entry.get("submodel") == old_name:
                    entry["submodel"] = new_name
        self._project["submodels"][idx] = dlg.result
        self.refresh()

    def _delete(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a submodel to delete.")
            return
        name = self._project["submodels"][idx]["name"]
        if not messagebox.askyesno(
            "Delete", f"Delete submodel '{name}' and all its paths?"
        ):
            return
        self._project["submodels"].pop(idx)
        self._project["paths"].pop(name, None)
        self._project["tdpa"] = [
            e for e in self._project["tdpa"] if e.get("submodel") != name
        ]
        self._project["tdpa_fatigue"] = [
            e for e in self._project["tdpa_fatigue"] if e.get("submodel") != name
        ]
        self.refresh()


# ── Loads tab ─────────────────────────────────────────────────────────────────


class LoadsTab(_TableTab):
    _COLUMNS = (
        "name",
        "analysis",
        "timestep",
        "stress_type",
        "load_type",
        "unit",
        "scale",
        "spatial_rec",
        "is_pd",
        "is_cyclic",
        "is_pressure",
        "is_short",
    )
    _HEADINGS = {
        "name": "Name",
        "analysis": "Analysis",
        "timestep": "Time Step",
        "stress_type": "Stress Type",
        "load_type": "Load Type",
        "unit": "Unit",
        "scale": "Scale",
        "spatial_rec": "Spatial Rec.",
        "is_pd": "Plasma Dis.",
        "is_cyclic": "Cyclic",
        "is_pressure": "Pressure",
        "is_short": "Short OS",
    }
    _LIST_KEY = "loads"

    def _row_values(self, item: dict) -> tuple:
        return (
            item["name"],
            item["analysis_name"],
            item["time_step"],
            item["stress_type"],
            item["load_type"],
            item["unit"],
            item["scale"],
            item["spatial_rec"],
            _bool_label(item["is_pd"]),
            _bool_label(item["is_cyclic"]),
            _bool_label(item["is_pressure"]),
            _bool_label(item["is_short_overstress"]),
        )

    def _add(self) -> None:
        dlg = LoadDialog(self, analyses=_get_available_analyses(self._project))
        if dlg.result is None:
            return
        if any(ld["name"] == dlg.result["name"] for ld in self._project["loads"]):
            messagebox.showerror(
                "Duplicate", f"Load '{dlg.result['name']}' already exists."
            )
            return
        self._project["loads"].append(dlg.result)
        self.refresh()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a load to edit.")
            return
        dlg = LoadDialog(
            self,
            existing=self._project["loads"][idx],
            analyses=_get_available_analyses(self._project),
        )
        if dlg.result:
            self._project["loads"][idx] = dlg.result
            self.refresh()


# ── Reference Events tab ──────────────────────────────────────────────────────


class REsTab(_TableTab):
    _COLUMNS = (
        "re_id",
        "service_lvl",
        "loads",
        "oc",
        "ie",
        "ce",
        "load_ctg",
        "ncycles",
    )
    _HEADINGS = {
        "re_id": "RE ID",
        "service_lvl": "Svc. Lvl",
        "loads": "Loads",
        "oc": "Op. Conditions",
        "ie": "Init. Event",
        "ce": "Concat. Event",
        "load_ctg": "Load Ctg.",
        "ncycles": "N Cycles",
    }
    _LIST_KEY = "reference_events"

    def _row_values(self, item: dict) -> tuple:
        return (
            item["re_id"],
            item["service_lvl"],
            ", ".join(item["loads"]),
            item["oc"],
            item["ie"],
            item["ce"],
            item["load_ctg"],
            item.get("ncycles") or "N/A",
        )

    def _add(self) -> None:
        load_names = [ld["name"] for ld in self._project["loads"]]
        if not load_names:
            messagebox.showwarning("No Loads", "Define at least one load first.")
            return
        dlg = REDialog(self, load_names)
        if dlg.result is None:
            return
        if any(
            r["re_id"] == dlg.result["re_id"] for r in self._project[self._LIST_KEY]
        ):
            messagebox.showerror(
                "Duplicate", f"RE '{dlg.result['re_id']}' already exists."
            )
            return
        self._project[self._LIST_KEY].append(dlg.result)
        self.refresh()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a Reference Event to edit.")
            return
        load_names = [ld["name"] for ld in self._project["loads"]]
        dlg = REDialog(self, load_names, existing=self._project[self._LIST_KEY][idx])
        if dlg.result:
            self._project[self._LIST_KEY][idx] = dlg.result
            self.refresh()


# ── Fatigue Reference Events tab ──────────────────────────────────────────────


class FatigueREsTab(REsTab):
    _LIST_KEY = "fatigue_reference_events"


# ── Paths tab ─────────────────────────────────────────────────────────────────


class PathsTab(ttk.Frame):
    """Tab showing paths for the currently selected submodel."""

    _COLUMNS = ("path_num", "material", "ptype", "welding_n", "welding_f")
    _HEADINGS = {
        "path_num": "Path #",
        "material": "Material",
        "ptype": "Type",
        "welding_n": "Weld. n",
        "welding_f": "Weld. f",
    }

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        self._mat_names: list[str] = []
        self._build()
        self.after(200, self._load_materials)

    def _load_materials(self) -> None:
        self._mat_names = _get_material_names()

    def _current_submodel(self) -> str | None:
        return self._sm_var.get() or None

    def _current_paths(self) -> list:
        sm = self._current_submodel()
        if sm is None:
            return []
        return self._project["paths"].get(sm, [])

    def _build(self) -> None:
        # Submodel selector row
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Submodel:").pack(side="left", padx=(0, 4))
        self._sm_var = tk.StringVar()
        self._sm_combo = ttk.Combobox(
            top, textvariable=self._sm_var, state="readonly", width=24
        )
        self._sm_combo.pack(side="left")
        self._sm_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_table())
        # Refresh combobox whenever this tab is shown
        self.bind("<Map>", lambda _e: self.refresh())

        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=2)
        ttk.Button(toolbar, text="Add", width=7, command=self._add).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Edit", width=7, command=self._edit).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Delete", width=7, command=self._delete).pack(
            side="left", padx=2
        )

        # Treeview
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
            self._tree.column(col, width=100, anchor="center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

    def refresh(self) -> None:
        """Refresh submodel combobox and table."""
        sm_names = [s["name"] for s in self._project["submodels"]]
        self._sm_combo["values"] = sm_names
        current = self._sm_var.get()
        if current not in sm_names:
            self._sm_var.set(sm_names[0] if sm_names else "")
        self._refresh_table()

    def _refresh_table(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for path in self._current_paths():
            self._tree.insert(
                "",
                "end",
                values=(
                    path["path_num"],
                    path["material"],
                    path["ptype"],
                    path["welding_n"],
                    path["welding_f"],
                ),
            )

    def _selected_index(self) -> int | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.index(sel[0])

    def _add(self) -> None:
        sm = self._current_submodel()
        if not sm:
            messagebox.showwarning("No Submodel", "Select or create a submodel first.")
            return
        mat_names = self._mat_names or _get_material_names()
        dlg = PathDialog(self, mat_names)
        if dlg.result is None:
            return
        paths = self._project["paths"].setdefault(sm, [])
        if any(p["path_num"] == dlg.result["path_num"] for p in paths):
            messagebox.showerror(
                "Duplicate", f"Path {dlg.result['path_num']} already exists."
            )
            return
        paths.append(dlg.result)
        self._refresh_table()

    def _edit(self) -> None:
        sm = self._current_submodel()
        if not sm:
            return
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a path to edit.")
            return
        paths = self._project["paths"].get(sm, [])
        mat_names = self._mat_names or _get_material_names()
        dlg = PathDialog(self, mat_names, existing=paths[idx])
        if dlg.result:
            paths[idx] = dlg.result
            self._refresh_table()

    def _delete(self) -> None:
        sm = self._current_submodel()
        if not sm:
            return
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Selection", "Select a path to delete.")
            return
        if messagebox.askyesno("Delete", "Delete the selected path?"):
            self._project["paths"][sm].pop(idx)
            self._refresh_table()


# ── T & DPA tab ───────────────────────────────────────────────────────────────


class TDPATab(ttk.Frame):
    """Scrollable multiindex grid: rows = submodel x path, columns = REs, cells have T and DPA."""

    _PROJECT_KEY = "tdpa"
    _RE_KEY = "reference_events"

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        # key: (submodel_name, path_num, re_id) -> (t_var, dpa_var)
        self._cell_vars: dict[
            tuple[str, int, str], tuple[tk.StringVar, tk.StringVar]
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
        ttk.Label(
            toolbar,
            text="CSV columns: submodel, path, event, T, DPA",
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

        submodels = self._project.get("submodels", [])
        re_ids = [r["re_id"] for r in self._project.get(self._RE_KEY, [])]

        # Build all (submodel, path) pairs
        rows: list[tuple[str, int]] = []
        for sm in submodels:
            for path in self._project["paths"].get(sm["name"], []):
                rows.append((sm["name"], path["path_num"]))

        if not rows or not re_ids:
            ttk.Label(
                self._inner,
                text="No data to display (add submodels, paths and reference events first).",
                foreground="gray",
            ).grid(padx=20, pady=20)
            return

        # Build lookup of existing values
        existing: dict[tuple[str, int, str], tuple[str, str]] = {
            (e["submodel"], e["path_num"], e["re_id"]): (str(e["T"]), str(e["dpa"]))
            for e in self._project.get(self._PROJECT_KEY, [])
            if "submodel" in e
        }

        CELL_W = 9

        # Header row 0: Submodel | Path | [RE1 colspan=2] [RE2 colspan=2] ...
        ttk.Label(
            self._inner,
            text="Submodel",
            relief="groove",
            width=14,
            anchor="center",
            padding=3,
        ).grid(row=0, column=0, rowspan=2, sticky="nsew", padx=1, pady=1)
        ttk.Label(
            self._inner,
            text="Path",
            relief="groove",
            width=6,
            anchor="center",
            padding=3,
        ).grid(row=0, column=1, rowspan=2, sticky="nsew", padx=1, pady=1)

        for c, re_id in enumerate(re_ids):
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

        # Data rows — group by submodel for rowspan labels
        data_row = 2
        sm_idx = 0
        while sm_idx < len(submodels):
            sm_name = submodels[sm_idx]["name"]
            sm_paths = self._project["paths"].get(sm_name, [])
            n_paths = len(sm_paths)
            if n_paths == 0:
                sm_idx += 1
                continue
            ttk.Label(
                self._inner, text=sm_name, relief="groove", width=14, anchor="center"
            ).grid(
                row=data_row, column=0, rowspan=n_paths, sticky="nsew", padx=1, pady=1
            )
            for path in sm_paths:
                pnum = path["path_num"]
                ttk.Label(
                    self._inner,
                    text=str(pnum),
                    relief="groove",
                    width=6,
                    anchor="center",
                ).grid(row=data_row, column=1, sticky="nsew", padx=1, pady=1)
                for c, re_id in enumerate(re_ids):
                    t_def, dpa_def = existing.get((sm_name, pnum, re_id), ("", "0"))
                    t_var = tk.StringVar(value=t_def)
                    dpa_var = tk.StringVar(value=dpa_def)
                    self._cell_vars[(sm_name, pnum, re_id)] = (t_var, dpa_var)
                    ttk.Entry(self._inner, textvariable=t_var, width=CELL_W).grid(
                        row=data_row, column=2 + c * 2, padx=1, pady=1
                    )
                    ttk.Entry(self._inner, textvariable=dpa_var, width=CELL_W).grid(
                        row=data_row, column=3 + c * 2, padx=1, pady=1
                    )
                data_row += 1
            sm_idx += 1

    def _import_csv(self) -> None:
        """Load T/DPA values from a CSV file (submodel, path, event, T, DPA)."""
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
                # Accept both capitalised and lowercase header variants
                for lineno, row in enumerate(reader, start=2):
                    # normalise keys
                    row = {k.strip().lower(): v.strip() for k, v in row.items()}
                    sm = row.get("submodel", "")
                    path_raw = row.get("path", "")
                    event = row.get("event", "")
                    t_raw = row.get("t", "")
                    dpa_raw = row.get("dpa", "")
                    if not (sm and path_raw and event):
                        errors.append(
                            f"Line {lineno}: missing submodel/path/event — skipped"
                        )
                        continue
                    try:
                        pnum = int(path_raw)
                    except ValueError:
                        errors.append(
                            f"Line {lineno}: path must be an integer — skipped"
                        )
                        continue
                    key = (sm, pnum, event)
                    if key not in self._cell_vars:
                        errors.append(
                            f"Line {lineno}: ({sm}, path {pnum}, {event!r}) not in grid — skipped"
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

    def sync(self) -> list[str]:
        """Read cells into project[_PROJECT_KEY]; return validation errors. Empty T cells are skipped."""
        entries = []
        errors = []
        for (sm_name, pnum, re_id), (t_var, dpa_var) in self._cell_vars.items():
            t_str = t_var.get().strip()
            dpa_str = dpa_var.get().strip()
            if not t_str:
                continue  # skip empty cells
            try:
                T = float(t_str)
                dpa = float(dpa_str) if dpa_str else 0.0
            except ValueError:
                errors.append(
                    f"Submodel '{sm_name}' / Path {pnum} / RE '{re_id}': T and DPA must be numbers"
                )
                continue
            entries.append(
                {
                    "submodel": sm_name,
                    "path_num": pnum,
                    "re_id": re_id,
                    "T": T,
                    "dpa": dpa,
                }
            )
        self._project[self._PROJECT_KEY] = entries
        return errors


# ── T & DPA Fatigue tab ───────────────────────────────────────────────────────


class FatigueTDPATab(TDPATab):
    _PROJECT_KEY = "tdpa_fatigue"
    _RE_KEY = "fatigue_reference_events"


# ── Log window ───────────────────────────────────────────────────────────────


class _LogWindow(tk.Toplevel):
    """Scrollable pop-up that captures log output from a cassy assessment run."""

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

    # Called from the main thread only (route via after() from other threads).
    def append(self, text: str) -> None:
        self._text.configure(state="normal")
        self._text.insert("end", text + "\n")
        self._text.see("end")
        self._text.configure(state="disabled")

    def set_done(self, success: bool, msg: str) -> None:
        color = "#4caf50" if success else "#f44336"
        self._status.configure(text=msg, foreground=color)


class _TextHandler(logging.Handler):
    """Routes log records to a _LogWindow (thread-safe via after())."""

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


# ── Runner helper ─────────────────────────────────────────────────────────────


def _build_configs_from_project(project: dict) -> dict:
    """Build a dict of ``Configuration`` objects from the in-memory project dict.

    This lets the runner be called without writing any Excel files to disk.
    Stress tensors are read from the CSV paths stored in each submodel entry.
    """
    import numpy as np
    import pandas as pd
    from cassy.paths.paths_config import Configuration

    tdpa_lut = {
        (e["submodel"], e["path_num"], e["re_id"]): (e["T"], e["dpa"])
        for e in project.get("tdpa", [])
        if "submodel" in e
    }
    tdpa_fat_lut = {
        (e["submodel"], e["path_num"], e["re_id"]): (e["T"], e["dpa"])
        for e in project.get("tdpa_fatigue", [])
        if "submodel" in e
    }

    loads = project.get("loads", [])

    def _re_df(
        re_list: list, lut: dict, sm_name: str, paths: list, with_ncycles: bool
    ) -> pd.DataFrame:
        rows = []
        for p in paths:
            pnum = p["path_num"]
            for re in re_list:
                re_id = re["re_id"]
                T, dpa = lut.get((sm_name, pnum, re_id), (0.0, 0.0))
                row = {
                    "Path N": pnum,
                    "ID": re_id,
                    "Operating Conditions": re.get("oc", "N/A"),
                    "Initiating Event": re.get("ie", "N/A"),
                    "Concatenated Event": re.get("ce", "N/A"),
                    "T [\u00b0C]": T,
                    "DPA": dpa,
                    "Loading ctg.": re.get("load_ctg", "N/A"),
                    "Service Level": re.get("service_lvl", "A"),
                    "Loads": ", ".join(re.get("loads", [])),
                }
                if with_ncycles:
                    row["N of cycles"] = re.get("ncycles") or 0
                rows.append(row)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index(["Path N", "ID"]).sort_index()

    configs: dict = {}
    for sm in project.get("submodels", []):
        sm_name = sm["name"]
        sm_paths = project["paths"].get(sm_name, [])

        # Stresses sheet
        df_stresses = (
            pd.DataFrame(
                [
                    {
                        "Load Name": ld["name"],
                        "Stress Type": ld["stress_type"],
                        "Load Type": ld["load_type"],
                        "Unit": ld["unit"],
                        "Scale": ld["scale"],
                        "Spatial Recombination": ld["spatial_rec"],
                        "Is Cyclic": ld["is_cyclic"],
                        "Is Pressure": ld["is_pressure"],
                        "Is Short Overstress": ld["is_short_overstress"],
                        "Derives from Plasma Disruption": ld["is_pd"],
                    }
                    for ld in loads
                ]
            ).set_index("Load Name")
            if loads
            else pd.DataFrame()
        )

        # Load Steps sheet
        df_load_steps = (
            pd.DataFrame(
                [
                    {
                        "Load Name": ld["name"],
                        "Analysis Name": ld["analysis_name"],
                        "Time Step": ld["time_step"],
                    }
                    for ld in loads
                ]
            ).set_index("Load Name")
            if loads
            else pd.DataFrame()
        )

        # Paths sheet
        df_paths = (
            pd.DataFrame(
                [
                    {
                        "Path N": p["path_num"],
                        "Material": p["material"],
                        "Type": p["ptype"],
                        "Welding-n": p["welding_n"],
                        "Welding-f": p["welding_f"],
                    }
                    for p in sm_paths
                ]
            ).set_index("Path N")
            if sm_paths
            else pd.DataFrame()
        )

        # Reference Event sheets
        df_re = _re_df(
            project.get("reference_events", []),
            tdpa_lut,
            sm_name,
            sm_paths,
            with_ncycles=False,
        )
        df_re_fat = _re_df(
            project.get("fatigue_reference_events", []),
            tdpa_fat_lut,
            sm_name,
            sm_paths,
            with_ncycles=True,
        )

        # General sheet
        df_general = pd.DataFrame({"Value": [sm["design_code"]]}, index=["Design Code"])
        df_general.index.name = df_general.columns[0]

        # Build Configuration bypassing file-based __init__
        conf = object.__new__(Configuration)
        conf.submodel = sm_name
        conf.code = sm["design_code"]
        conf.sheets = {
            "Stresses": df_stresses,
            "Load Steps": df_load_steps,
            "Paths": df_paths,
            "Reference Event": df_re,
            "Reference Event Fatigue": df_re_fat,
            "General": df_general,
        }
        conf.paths = df_paths.index if not df_paths.empty else pd.Index([], dtype=int)
        conf.loads = df_load_steps.index if not df_load_steps.empty else pd.Index([])

        # Stress tensors
        tensors_file = sm.get("tensors_file", "")
        if tensors_file and os.path.exists(tensors_file):
            st = pd.read_csv(tensors_file)
            st["loadstep"] = st["loadstep"].astype(int)
            st["path"] = st["path"].astype(int)
            conf.stress_tensors = st.set_index(
                ["path", "analysis", "loadstep", "pathpoint", "stress_type"]
            ).sort_index()
        else:
            conf.stress_tensors = pd.DataFrame()

        configs[sm_name] = conf

    return configs


# ── Main application window ───────────────────────────────────────────────────


class PathsGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Cassy — Paths Assessment Configuration")
        self.geometry("1100x660")
        self.minsize(800, 500)
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
        self._tab_submodels = SubmodelsTab(self._nb, self._project)
        self._tab_loads = LoadsTab(self._nb, self._project)
        self._tab_res = REsTab(self._nb, self._project)
        self._tab_fat_res = FatigueREsTab(self._nb, self._project)
        self._tab_paths = PathsTab(self._nb, self._project)
        self._tab_tdpa = TDPATab(self._nb, self._project)
        self._tab_tdpa_fat = FatigueTDPATab(self._nb, self._project)

        self._nb.add(self._tab_general, text="  General  ")
        self._nb.add(self._tab_submodels, text="  Submodels  ")
        self._nb.add(self._tab_loads, text="  Loads  ")
        self._nb.add(self._tab_res, text="  Ref. Events  ")
        self._nb.add(self._tab_fat_res, text="  Fatigue Ref. Events  ")
        self._nb.add(self._tab_paths, text="  Paths  ")
        self._nb.add(self._tab_tdpa, text="  T & DPA  ")
        self._nb.add(self._tab_tdpa_fat, text="  T & DPA Fatigue  ")

    # ── Sync / refresh helpers ────────────────────────────────

    def _sync_all(self) -> list[str]:
        self._tab_general.sync()
        errors = self._tab_tdpa.sync()
        errors += self._tab_tdpa_fat.sync()
        return errors

    def _refresh_all_tabs(self) -> None:
        """Reload every tab's UI from the current project dict."""
        self._tab_general.load_from_project()
        self._tab_submodels.refresh()
        self._tab_loads.refresh()
        self._tab_res.refresh()
        self._tab_fat_res.refresh()
        self._tab_paths.refresh()
        self._tab_tdpa.rebuild_grid()
        self._tab_tdpa_fat.rebuild_grid()

    # ── File operations ───────────────────────────────────────

    def _new(self) -> None:
        if not messagebox.askyesno("New Project", "Discard current project?"):
            return
        # Update the shared dict in-place so all tab references stay valid
        self._project.clear()
        self._project.update(_fresh_project())
        self._project_path = None
        self.title("Cassy \u2014 Paths Assessment Configuration")
        self._refresh_all_tabs()
        self.focus_force()

    def _open(self) -> None:
        path = filedialog.askopenfilename(
            title="Open project",
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
        # Update the shared dict in-place so all tab references stay valid
        self._project.clear()
        self._project.update(data)
        self._project_path = path
        self.title(f"Cassy — {os.path.basename(path)}")
        self._refresh_all_tabs()

    def _save(self) -> None:
        if self._project_path is None:
            self._save_as()
        else:
            self._write(self._project_path)

    def _save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save project as",
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
            self.title(f"Cassy — {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))


# ── Module helpers ────────────────────────────────────────────────────────────


def _fresh_project() -> dict:
    return copy.deepcopy(EMPTY_PROJECT)


def main() -> None:
    app = PathsGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
