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

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from cassy.gui.common import GroupedTableTab, ProjectApp, RunTab, TDPAGridTab
from cassy.gui.common import Dialog as _Dialog
from cassy.gui.common import TableTab as _TableTab
from cassy.gui.paths_model import (  # noqa: F401  (re-exported)
    DESIGN_CODES,
    EMPTY_PROJECT,
    LOAD_TYPES,
    PATH_TYPES,
    SERVICE_LEVELS,
    SPATIAL_REC_METHODS,
    STRESS_TYPES,
    UNITS,
)
from cassy.gui.paths_model import bool_label as _bool_label
from cassy.gui.paths_model import (
    build_configs_from_project as _build_configs_from_project,
)
from cassy.gui.paths_model import fresh_project as _fresh_project
from cassy.gui.paths_model import get_available_analyses as _get_available_analyses
from cassy.gui.paths_model import get_material_names as _get_material_names


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


class GeneralTab(RunTab):
    _RUN_LABEL = "Run Cassy Assessment"
    _REQUIRED = ("submodels", "No submodels", "Define at least one submodel first.")

    def _prepare(self) -> Callable[[], None]:
        configs = _build_configs_from_project(self._project)
        opts = self._project["run_options"]
        root_dir = opts["root_dir"]
        fatigue = opts.get("fatigue", False)
        matlib = opts.get("matlib_path") or None

        def work() -> None:
            from cassy.runners.run_paths import run_paths

            run_paths(root_dir, fatigue=fatigue, matlib=matlib, configs=configs)

        return work


# ── Submodels tab ─────────────────────────────────────────────────────────────


class SubmodelsTab(_TableTab):
    _ITEM_NAME = "submodel"
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
    _ITEM_NAME = "load"
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
    _ITEM_NAME = "reference event"
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


class PathsTab(GroupedTableTab):
    """Tab showing paths for the currently selected submodel."""

    _GROUP_LABEL = "Submodel"
    _ITEM_NAME = "path"
    _COL_WIDTH = 100
    _COLUMNS = ("path_num", "material", "ptype", "welding_n", "welding_f")
    _HEADINGS = {
        "path_num": "Path #",
        "material": "Material",
        "ptype": "Type",
        "welding_n": "Weld. n",
        "welding_f": "Weld. f",
    }

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        self._mat_names: list[str] = []
        super().__init__(parent, project)
        self.after(200, self._load_materials)

    def _load_materials(self) -> None:
        self._mat_names = _get_material_names()

    def _group_names(self) -> list[str]:
        return [s["name"] for s in self._project["submodels"]]

    def _items_of(self, group: str) -> list:
        return self._project["paths"].setdefault(group, [])

    def _row_values(self, item: dict) -> tuple:
        return (
            item["path_num"],
            item["material"],
            item["ptype"],
            item["welding_n"],
            item["welding_f"],
        )

    def _add(self) -> None:
        sm = self._current_group()
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
        sm = self._current_group()
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


# ── T & DPA tab ───────────────────────────────────────────────────────────────


class TDPATab(TDPAGridTab):
    """Scrollable multiindex grid: rows = submodel x path, columns = REs, cells have T and DPA."""

    _PROJECT_KEY = "tdpa"
    _RE_KEY = "reference_events"
    _GROUP_FIELD = "submodel"
    _ITEM_FIELD = "path_num"
    _GROUP_LABEL = "Submodel"
    _ITEM_LABEL = "Path"
    _CSV_ITEM_COL = "path"
    _EMPTY_MSG = "No data to display (add submodels, paths and reference events first)."

    def _groups(self) -> list[tuple[str, list]]:
        return [
            (
                sm["name"],
                [p["path_num"] for p in self._project["paths"].get(sm["name"], [])],
            )
            for sm in self._project.get("submodels", [])
        ]

    def _parse_item(self, raw: str) -> int:
        return int(raw)


class FatigueTDPATab(TDPATab):
    _PROJECT_KEY = "tdpa_fatigue"
    _RE_KEY = "fatigue_reference_events"


# ── Main application window ───────────────────────────────────────────────────


class PathsGUI(ProjectApp):
    _TITLE = "Cassy \u2014 Paths Assessment Configuration"
    _GEOMETRY = "1100x660"

    @staticmethod
    def _fresh_project() -> dict:
        return _fresh_project()

    def _build_tabs(self) -> None:
        self._tab_general = GeneralTab(self._nb, self._project)
        self._tab_submodels = SubmodelsTab(self._nb, self._project)
        self._tab_loads = LoadsTab(self._nb, self._project)
        self._tab_res = REsTab(self._nb, self._project)
        self._tab_fat_res = FatigueREsTab(self._nb, self._project)
        self._tab_paths = PathsTab(self._nb, self._project)
        self._tab_tdpa = TDPATab(self._nb, self._project)
        self._tab_tdpa_fat = FatigueTDPATab(self._nb, self._project)

        self._nb.add(self._tab_general, text="General")
        self._nb.add(self._tab_submodels, text="Submodels")
        self._nb.add(self._tab_loads, text="Loads")
        self._nb.add(self._tab_res, text="Ref. Events")
        self._nb.add(self._tab_fat_res, text="Fatigue Ref. Events")
        self._nb.add(self._tab_paths, text="Paths")
        self._nb.add(self._tab_tdpa, text="T & DPA")
        self._nb.add(self._tab_tdpa_fat, text="T & DPA Fatigue")

    def _sync_all(self) -> list[str]:
        self._tab_general.sync()
        return self._tab_tdpa.sync() + self._tab_tdpa_fat.sync()

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


def main() -> None:
    app = PathsGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
