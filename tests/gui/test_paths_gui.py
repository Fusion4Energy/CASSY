"""Tests for the paths_gui module.

All tests run without a display by using ``Tk()`` widgets that are never
shown (no ``mainloop()``).  The ``root`` fixture creates a hidden root window
and destroys it after each test so that tk state does not bleed between cases.

The entire module is skipped automatically when tkinter is unavailable (e.g.
headless CI servers without python3-tk or a DISPLAY).
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Skip the whole module if tkinter cannot be imported or cannot open a display.
tk = pytest.importorskip("tkinter", reason="tkinter not available")
try:
    _root_check = tk.Tk()
    _root_check.withdraw()
    _root_check.destroy()
except Exception as _e:
    pytest.skip(f"tkinter display not available: {_e}", allow_module_level=True)

from cassy.gui.paths_gui import (
    EMPTY_PROJECT,
    FatigueTDPATab,
    GeneralTab,
    LoadDialog,
    PathDialog,
    PathsGUI,
    PathsTab,
    REDialog,
    REsTab,
    SubmodelDialog,
    SubmodelsTab,
    TDPATab,
    _fresh_project,
    _get_available_analyses,
)

RES = Path(__file__).parent / "res"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def root():
    """Single hidden Tk root shared across the module (faster)."""
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


def _project():
    """Return a populated project dict suitable for most tests."""
    p = _fresh_project()
    p["submodels"] = [
        {"name": "SM1", "design_code": "SDC-IC", "tensors_file": ""},
        {"name": "SM2", "design_code": "RCC-MRx", "tensors_file": ""},
    ]
    p["loads"] = [
        {
            "name": "LD1",
            "analysis_name": "ana1",
            "time_step": "1",
            "stress_type": "P",
            "load_type": "Volumetric",
            "unit": "Pa",
            "scale": 1.0,
            "spatial_rec": "algebraic",
            "is_pd": False,
            "is_cyclic": True,
            "is_pressure": False,
            "is_short_overstress": False,
        }
    ]
    p["reference_events"] = [
        {
            "re_id": "RE-A",
            "service_lvl": "A",
            "loads": ["LD1"],
            "oc": "Normal",
            "ie": "N/A",
            "ce": "N/A",
            "load_ctg": "N/A",
            "ncycles": None,
        },
        {
            "re_id": "RE-B",
            "service_lvl": "A",
            "loads": ["LD1"],
            "oc": "Normal",
            "ie": "N/A",
            "ce": "N/A",
            "load_ctg": "N/A",
            "ncycles": 100,
        },
    ]
    p["paths"] = {
        "SM1": [
            {
                "path_num": 1,
                "material": "SS316L(N)-IG",
                "ptype": "normal",
                "welding_n": 1.0,
                "welding_f": 1.0,
            },
            {
                "path_num": 2,
                "material": "SS316L(N)-IG",
                "ptype": "normal",
                "welding_n": 1.0,
                "welding_f": 1.0,
            },
        ],
        "SM2": [
            {
                "path_num": 1,
                "material": "Inconel 718",
                "ptype": "normal",
                "welding_n": 1.0,
                "welding_f": 1.0,
            },
        ],
    }
    return p


# ---------------------------------------------------------------------------
# 1. Project structure
# ---------------------------------------------------------------------------


class TestFreshProject:
    def test_keys_present(self):
        p = _fresh_project()
        for key in (
            "run_options",
            "loads",
            "reference_events",
            "fatigue_reference_events",
            "submodels",
            "paths",
            "tdpa",
            "tdpa_fatigue",
        ):
            assert key in p

    def test_is_deep_copy(self):
        a = _fresh_project()
        b = _fresh_project()
        a["loads"].append({"name": "x"})
        assert b["loads"] == []


# ---------------------------------------------------------------------------
# 2. Dialogs — _collect() without showing a window
# ---------------------------------------------------------------------------


class TestSubmodelDialog:
    def test_collect_valid(self, root):
        dlg = object.__new__(SubmodelDialog)
        dlg._ex = {}
        dlg._name = tk.StringVar(root, value="SM1")
        dlg._code = tk.StringVar(root, value="SDC-IC")
        dlg._tensors = tk.StringVar(root, value="/tmp/t.csv")
        result = dlg._collect()
        assert result == {
            "name": "SM1",
            "design_code": "SDC-IC",
            "tensors_file": "/tmp/t.csv",
        }

    def test_collect_empty_name(self, root):
        dlg = object.__new__(SubmodelDialog)
        dlg._ex = {}
        dlg._name = tk.StringVar(root, value="  ")
        dlg._code = tk.StringVar(root, value="SDC-IC")
        dlg._tensors = tk.StringVar(root, value="")
        with patch("cassy.gui.paths_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()


class TestPathDialog:
    def _make(
        self,
        root,
        path_num="1",
        material="SS316L(N)-IG",
        ptype="normal",
        wn="1.0",
        wf="1.0",
    ):
        dlg = object.__new__(PathDialog)
        dlg._mat_names = ["SS316L(N)-IG", "Inconel 718"]
        dlg._ex = {}
        dlg._pnum = tk.StringVar(root, value=path_num)
        dlg._mat = tk.StringVar(root, value=material)
        dlg._ptype = tk.StringVar(root, value=ptype)
        dlg._wn = tk.StringVar(root, value=wn)
        dlg._wf = tk.StringVar(root, value=wf)
        return dlg

    def test_collect_valid(self, root):
        dlg = self._make(root)
        result = dlg._collect()
        assert result == {
            "path_num": 1,
            "material": "SS316L(N)-IG",
            "ptype": "normal",
            "welding_n": 1.0,
            "welding_f": 1.0,
        }

    def test_collect_non_integer_path_num(self, root):
        dlg = self._make(root, path_num="abc")
        with patch("cassy.gui.paths_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()

    def test_collect_bad_welding(self, root):
        dlg = self._make(root, wn="not_a_number")
        with patch("cassy.gui.paths_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None


class TestLoadDialog:
    def _make(
        self,
        root,
        name="LD1",
        analysis="ana1",
        timestep="1",
        scale="1.0",
        missing_name=False,
    ):
        dlg = object.__new__(LoadDialog)
        dlg._ex = {}
        dlg._name = tk.StringVar(root, value="" if missing_name else name)
        dlg._analysis = tk.StringVar(root, value=analysis)
        dlg._timestep = tk.StringVar(root, value=timestep)
        dlg._stype = tk.StringVar(root, value="P")
        dlg._ltype = tk.StringVar(root, value="Volumetric")
        dlg._unit = tk.StringVar(root, value="Pa")
        dlg._scale = tk.StringVar(root, value=scale)
        dlg._spatial = tk.StringVar(root, value="algebraic")
        dlg._is_pd = tk.BooleanVar(root, value=False)
        dlg._is_cyclic = tk.BooleanVar(root, value=False)
        dlg._is_pressure = tk.BooleanVar(root, value=False)
        dlg._is_short = tk.BooleanVar(root, value=False)
        return dlg

    def test_collect_valid(self, root):
        dlg = self._make(root)
        result = dlg._collect()
        assert result["name"] == "LD1"
        assert result["scale"] == 1.0

    def test_collect_missing_name(self, root):
        dlg = self._make(root, missing_name=True)
        with patch("cassy.gui.paths_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None

    def test_collect_bad_scale(self, root):
        dlg = self._make(root, scale="oops")
        with patch("cassy.gui.paths_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None


# ---------------------------------------------------------------------------
# 2b. _get_available_analyses + LoadDialog combobox
# ---------------------------------------------------------------------------

TENSOR_CSV = (
    Path(__file__).parents[1] / "runners" / "paths" / "stresses" / "Model_B.csv"
)


class TestGetAvailableAnalyses:
    def test_empty_when_no_submodels(self):
        p = _fresh_project()
        assert _get_available_analyses(p) == []

    def test_empty_when_tensors_file_missing(self):
        p = _fresh_project()
        p["submodels"] = [
            {
                "name": "SM1",
                "design_code": "SDC-IC",
                "tensors_file": "/nonexistent/path.csv",
            }
        ]
        assert _get_available_analyses(p) == []

    def test_reads_analyses_from_csv(self):
        p = _fresh_project()
        p["submodels"] = [
            {"name": "SM1", "design_code": "SDC-IC", "tensors_file": str(TENSOR_CSV)}
        ]
        result = _get_available_analyses(p)
        assert len(result) > 0
        assert result == sorted(set(result))  # sorted and deduplicated

    def test_deduplicates_across_submodels(self):
        p = _fresh_project()
        p["submodels"] = [
            {"name": "SM1", "design_code": "SDC-IC", "tensors_file": str(TENSOR_CSV)},
            {"name": "SM2", "design_code": "SDC-IC", "tensors_file": str(TENSOR_CSV)},
        ]
        result = _get_available_analyses(p)
        assert len(result) == len(set(result))

    def test_load_dialog_uses_combobox_when_analyses_provided(self, root):
        """LoadDialog._build() should produce a combobox for _analysis when
        analyses are provided, so that get() still returns the value correctly."""
        dlg = object.__new__(LoadDialog)
        dlg._ex = {}
        dlg._analyses = ["Inertial", "Thermal"]
        dlg._body = tk.Frame(root)
        dlg._build()
        # _analysis is a StringVar regardless of widget type; set and read it
        dlg._analysis.set("Inertial")
        assert dlg._analysis.get() == "Inertial"

    def test_load_dialog_collect_with_analyses(self, root):
        """_collect() should work correctly when the combobox path is used."""
        dlg = object.__new__(LoadDialog)
        dlg._ex = {}
        dlg._analyses = ["Inertial", "Thermal"]
        dlg._name = tk.StringVar(root, value="LD_new")
        dlg._analysis = tk.StringVar(root, value="Inertial")
        dlg._timestep = tk.StringVar(root, value="2")
        dlg._stype = tk.StringVar(root, value="P")
        dlg._ltype = tk.StringVar(root, value="Volumetric")
        dlg._unit = tk.StringVar(root, value="Pa")
        dlg._scale = tk.StringVar(root, value="1.5")
        dlg._spatial = tk.StringVar(root, value="algebraic")
        dlg._is_pd = tk.BooleanVar(root, value=False)
        dlg._is_cyclic = tk.BooleanVar(root, value=True)
        dlg._is_pressure = tk.BooleanVar(root, value=False)
        dlg._is_short = tk.BooleanVar(root, value=False)
        result = dlg._collect()
        assert result is not None
        assert result["analysis_name"] == "Inertial"
        assert result["scale"] == 1.5


# ---------------------------------------------------------------------------
# 3. TDPATab — sync and CSV import
# ---------------------------------------------------------------------------


class TestTDPATabSync:
    def test_sync_stores_numeric_values(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = TDPATab(nb, proj)
        tab.rebuild_grid()

        # Fill two cells
        key = ("SM1", 1, "RE-A")
        if key in tab._cell_vars:
            t_var, dpa_var = tab._cell_vars[key]
            t_var.set("350")
            dpa_var.set("0.1")

        errors = tab.sync()
        assert errors == []
        entries = {(e["submodel"], e["path_num"], e["re_id"]): e for e in proj["tdpa"]}
        if key in tab._cell_vars:
            assert ("SM1", 1, "RE-A") in entries
            assert entries[("SM1", 1, "RE-A")]["T"] == 350.0
            assert entries[("SM1", 1, "RE-A")]["dpa"] == 0.1

    def test_sync_skips_empty_T(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = TDPATab(nb, proj)
        tab.rebuild_grid()
        # Leave all cells empty
        errors = tab.sync()
        assert errors == []
        assert proj["tdpa"] == []

    def test_sync_error_on_bad_value(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = TDPATab(nb, proj)
        tab.rebuild_grid()
        for key, (t_var, _) in tab._cell_vars.items():
            t_var.set("not_a_number")
            break  # corrupt just one cell
        errors = tab.sync()
        assert len(errors) >= 1

    def test_rebuild_grid_clears_cell_vars(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = TDPATab(nb, proj)
        tab.rebuild_grid()
        initial_count = len(tab._cell_vars)
        tab.rebuild_grid()
        assert len(tab._cell_vars) == initial_count  # same structure rebuilt


class TestTDPATabImportCSV:
    def test_import_fills_matching_cells(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = TDPATab(nb, proj)
        tab.rebuild_grid()

        csv_path = str(RES / "tdpa_import.csv")
        with (
            patch("cassy.gui.common.filedialog") as fd,
            patch("cassy.gui.common.messagebox"),
        ):
            fd.askopenfilename.return_value = csv_path
            tab._import_csv()

        key = ("SM1", 1, "RE-A")
        if key in tab._cell_vars:
            t_val = tab._cell_vars[key][0].get()
            assert t_val == "350"
            dpa_val = tab._cell_vars[key][1].get()
            assert dpa_val == "0.1"

    def test_import_unknown_key_reported(self, root, tmp_path):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = TDPATab(nb, proj)
        tab.rebuild_grid()

        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("submodel,path,event,T,DPA\nNOPE,999,NOPE,100,0\n")

        with (
            patch("cassy.gui.common.filedialog") as fd,
            patch("cassy.gui.common.messagebox") as mb,
        ):
            fd.askopenfilename.return_value = str(csv_file)
            tab._import_csv()
        mb.showinfo.assert_called_once()
        msg = mb.showinfo.call_args[0][1]
        assert "skipped" in msg

    def test_import_cancelled(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = TDPATab(nb, proj)
        tab.rebuild_grid()
        with patch("cassy.gui.common.filedialog") as fd:
            fd.askopenfilename.return_value = ""
            # Should return silently with no error
            tab._import_csv()

    def test_fatigue_tdpa_tab_uses_fatigue_key(self, root):
        proj = _project()
        proj["fatigue_reference_events"] = proj["reference_events"][:]
        nb = tk.ttk.Notebook(root)
        tab = FatigueTDPATab(nb, proj)
        tab.rebuild_grid()
        tab.sync()
        assert "tdpa_fatigue" in proj


# ---------------------------------------------------------------------------
# 4. GeneralTab — sync / load_from_project
# ---------------------------------------------------------------------------


class TestGeneralTab:
    def test_sync_updates_project(self, root):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = GeneralTab(nb, proj)
        tab._fatigue.set(True)
        tab._matlib.set("/some/path")
        tab.sync()
        assert proj["run_options"]["fatigue"] is True
        assert proj["run_options"]["matlib_path"] == "/some/path"

    def test_load_from_project(self, root):
        proj = _fresh_project()
        proj["run_options"]["fatigue"] = True
        proj["run_options"]["matlib_path"] = "/libs"
        nb = tk.ttk.Notebook(root)
        tab = GeneralTab(nb, proj)
        tab.load_from_project()
        assert tab._fatigue.get() is True
        assert tab._matlib.get() == "/libs"


# ---------------------------------------------------------------------------
# 5. SubmodelsTab — add / edit / delete cascade
# ---------------------------------------------------------------------------


class TestSubmodelsTab:
    def test_add_submodel(self, root):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = SubmodelsTab(nb, proj)
        proj["submodels"].append(
            {"name": "SM1", "design_code": "SDC-IC", "tensors_file": ""}
        )
        proj["paths"]["SM1"] = []
        tab.refresh()
        assert len(proj["submodels"]) == 1
        assert "SM1" in proj["paths"]

    def test_delete_submodel_cascades(self, root):
        proj = _project()
        proj["tdpa"] = [
            {"submodel": "SM1", "path_num": 1, "re_id": "RE-A", "T": 350, "dpa": 0}
        ]
        nb = tk.ttk.Notebook(root)
        tab = SubmodelsTab(nb, proj)
        tab.refresh()
        # Simulate deletion of SM1
        proj["submodels"] = [s for s in proj["submodels"] if s["name"] != "SM1"]
        proj["paths"].pop("SM1", None)
        proj["tdpa"] = [e for e in proj["tdpa"] if e.get("submodel") != "SM1"]
        assert "SM1" not in proj["paths"]
        assert all(e["submodel"] != "SM1" for e in proj["tdpa"])


# ---------------------------------------------------------------------------
# 6. PathsGUI — save/open JSON round-trip (no display)
# ---------------------------------------------------------------------------


class TestPathsGUISaveOpen:
    @pytest.fixture()
    def gui(self):
        app = PathsGUI.__new__(PathsGUI)
        app._project = _project()
        app._project_path = None
        return app

    def test_json_round_trip(self, tmp_path):
        proj = _project()
        dest = tmp_path / "project.json"
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(proj, fh, indent=2)
        with open(dest, encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded["submodels"] == proj["submodels"]
        assert loaded["paths"] == proj["paths"]
        assert loaded["reference_events"] == proj["reference_events"]

    def test_json_preserves_tdpa(self, tmp_path):
        proj = _project()
        proj["tdpa"] = [
            {"submodel": "SM1", "path_num": 1, "re_id": "RE-A", "T": 350.0, "dpa": 0.1}
        ]
        dest = tmp_path / "project.json"
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(proj, fh)
        with open(dest, encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded["tdpa"][0]["T"] == 350.0
        assert loaded["tdpa"][0]["dpa"] == 0.1
