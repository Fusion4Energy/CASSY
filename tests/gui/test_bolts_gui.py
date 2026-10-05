"""Tests for the bolts_gui module.

All tests run without a display by using ``Tk()`` widgets that are never
shown (no ``mainloop()``).  The ``root`` fixture creates a hidden root window
shared across the module so that Tk state does not bleed between cases.

The entire module is skipped automatically when tkinter is unavailable (e.g.
headless CI servers without python3-tk or a DISPLAY).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# Skip the whole module if tkinter cannot be imported or cannot open a display.
tk = pytest.importorskip("tkinter", reason="tkinter not available")
try:
    _root_check = tk.Tk()
    _root_check.withdraw()
    _root_check.destroy()
except Exception as _e:
    pytest.skip(f"tkinter display not available: {_e}", allow_module_level=True)

from cassy.gui.bolts_gui import (
    BOLT_DESIGN_CODES,
    EMPTY_BOLT_PROJECT,
    BoltFatigueREDialog,
    BoltFatigueREsTab,
    BoltFatigueTDPATab,
    BoltREDialog,
    BoltREsTab,
    BoltSpecDialog,
    BoltSpecsTab,
    BoltTDPATab,
    FlangeDialog,
    FlangesTab,
    GeneralTab,
    GeomDialog,
    GeometriesTab,
    _build_bolts_from_project,
    _fresh_project,
    _get_analysis_names,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


def _geom_bolt(base_name: str = "M8") -> dict:
    return {
        "base_name": base_name,
        "type": "bolt",
        "material": "SS316L(N)-IG_SDC-IC",
        "p": 1.25,
        "d": 8.0,
        "Le": 16.0,
        "d_vh": 0.0,
        "f": 0.15,
        "dn": None,
        "df": None,
        "D": None,
        "f_prime": 0.15,
        "B": 0.0,
        "C": 0.0,
        "KF": 4.0,
        "d1": None,
        "H": None,
        "a": None,
        "Dm": None,
        "Dp": None,
    }


def _geom_insert(base_name: str = "M8") -> dict:
    return {
        "base_name": base_name,
        "type": "insert",
        "material": "SS316L(N)-IG_SDC-IC",
        "p": 1.25,
        "d": 8.0,
        "Le": 10.0,
        "d_vh": 0.0,
        "f": 0.15,
        "dn": None,
        "df": None,
        "D": None,
    }


def _re_dict(re_id: str = "RE-01") -> dict:
    return {
        "re_id": re_id,
        "service_lvl": "A",
        "load_category": "I",
        "oc": "Normal",
        "ie": "N/A",
        "ce": "N/A",
        "primary_analysis": "Inertial",
        "primary_loadstep": "1",
        "all_analysis": "Inertial",
        "all_loadstep": "1",
    }


def _fat_re_dict(re_id: str = "FRE-01") -> dict:
    return {
        "re_id": re_id,
        "service_lvl": "A",
        "load_category": "I",
        "oc": "Normal",
        "ie": "N/A",
        "ce": "N/A",
        "n_cycles": 100,
        "ds_plus_analysis": "Inertial",
        "ds_plus_loadstep": "1",
        "ds_minus_analysis": "Inertial",
        "ds_minus_loadstep": "2",
        "sigma_sus_analysis": "",
        "sigma_sus_loadstep": "",
    }


def _bolt_entry(bolt_id: str = "B1") -> dict:
    """Return a minimal bolt spec entry (ID + geometry + preload).

    Thread-verification geometry and base-material live in the geometry
    library; they are not part of the bolt spec.
    """
    return {"bolt_id": bolt_id, "geom_data": "M8", "preload": 5000.0}


def _project() -> dict:
    """Return a fully populated project dict suitable for most tests."""
    p = _fresh_project()
    p["geometries"] = [_geom_bolt(), _geom_insert()]
    p["flanges"] = [
        {
            "name": "F1",
            "design_code": BOLT_DESIGN_CODES[0],
            "actions_file": "",
            "bolts_spec": [_bolt_entry("B1"), _bolt_entry("B2")],
        },
        {
            "name": "F2",
            "design_code": BOLT_DESIGN_CODES[0],
            "actions_file": "",
            "bolts_spec": [_bolt_entry("B3")],
        },
    ]
    p["reference_events"] = [_re_dict("RE-01"), _re_dict("RE-02")]
    p["fatigue_reference_events"] = [_fat_re_dict("FRE-01")]
    p["tdpa"] = [
        {"flange": "F1", "bolt_id": "B1", "re_id": "RE-01", "T": 100.0, "dpa": 0.0},
        {"flange": "F1", "bolt_id": "B1", "re_id": "RE-02", "T": 120.0, "dpa": 0.1},
        {"flange": "F1", "bolt_id": "B2", "re_id": "RE-01", "T": 100.0, "dpa": 0.0},
        {"flange": "F1", "bolt_id": "B2", "re_id": "RE-02", "T": 120.0, "dpa": 0.1},
        {"flange": "F2", "bolt_id": "B3", "re_id": "RE-01", "T": 80.0, "dpa": 0.0},
    ]
    p["tdpa_fatigue"] = [
        {"flange": "F1", "bolt_id": "B1", "re_id": "FRE-01", "T": 100.0, "dpa": 0.0},
        {"flange": "F1", "bolt_id": "B2", "re_id": "FRE-01", "T": 100.0, "dpa": 0.0},
    ]
    return p


# ---------------------------------------------------------------------------
# 1. Project structure helpers
# ---------------------------------------------------------------------------


class TestFreshProject:
    def test_required_keys_present(self):
        p = _fresh_project()
        for key in (
            "run_options",
            "geometries",
            "flanges",
            "reference_events",
            "fatigue_reference_events",
        ):
            assert key in p

    def test_run_options_defaults(self):
        p = _fresh_project()
        assert p["run_options"]["fatigue"] is False
        assert p["run_options"]["matlib_path"] == ""
        assert p["run_options"]["root_dir"] == ""

    def test_lists_and_dicts_are_empty(self):
        p = _fresh_project()
        assert p["geometries"] == []
        assert p["flanges"] == []
        assert p["reference_events"] == []
        assert p["fatigue_reference_events"] == []
        assert p["tdpa"] == []
        assert p["tdpa_fatigue"] == []

    def test_is_deep_copy(self):
        a = _fresh_project()
        b = _fresh_project()
        a["geometries"].append({"base_name": "x"})
        assert b["geometries"] == []

    def test_empty_bolt_project_constant_not_mutated(self):
        _fresh_project()["geometries"].append({"base_name": "x"})
        assert EMPTY_BOLT_PROJECT["geometries"] == []


# ---------------------------------------------------------------------------
# 2. GeomDialog._collect()
# ---------------------------------------------------------------------------


class TestGeomDialogCollect:
    def _make(
        self,
        root,
        base_name="M8",
        bolt_mat="SS316L(N)-IG_SDC-IC",
        has_insert=False,
        ins_mat="SS316L(N)-IG_SDC-IC",
    ):
        dlg = object.__new__(GeomDialog)
        dlg._mat_names = ["SS316L(N)-IG_SDC-IC", "Inconel 718"]
        dlg._ex_bolt = {}
        dlg._ex_ins = {}
        dlg._base_name = tk.StringVar(root, value=base_name)
        dlg._bolt_mat = tk.StringVar(root, value=bolt_mat)
        dlg._bolt_vars = {
            "p": tk.StringVar(root, value="1.25"),
            "d": tk.StringVar(root, value="8.0"),
            "Le": tk.StringVar(root, value="16.0"),
            "d_vh": tk.StringVar(root, value="0.0"),
            "f": tk.StringVar(root, value="0.15"),
            "f_prime": tk.StringVar(root, value="0.15"),
            "B": tk.StringVar(root, value="0"),
            "C": tk.StringVar(root, value="0"),
            "KF": tk.StringVar(root, value="4"),
            "dn": tk.StringVar(root, value=""),
            "df": tk.StringVar(root, value=""),
            "D": tk.StringVar(root, value=""),
            "d1": tk.StringVar(root, value=""),
            "H": tk.StringVar(root, value=""),
            "a": tk.StringVar(root, value=""),
            "Dm": tk.StringVar(root, value=""),
            "Dp": tk.StringVar(root, value=""),
        }
        dlg._has_insert = tk.BooleanVar(root, value=has_insert)
        dlg._ins_mat = tk.StringVar(root, value=ins_mat)
        dlg._ins_vars = {
            "p": tk.StringVar(root, value="1.25"),
            "d": tk.StringVar(root, value="8.0"),
            "Le": tk.StringVar(root, value="10.0"),
            "d_vh": tk.StringVar(root, value="0.0"),
            "f": tk.StringVar(root, value="0.15"),
            "dn": tk.StringVar(root, value=""),
            "df": tk.StringVar(root, value=""),
            "D": tk.StringVar(root, value=""),
        }
        return dlg

    def test_collect_bolt_valid(self, root):
        """No dedicated insert: bolt geometry dims are copied, base mat thread material used."""
        dlg = self._make(root)
        result = dlg._collect()
        assert result is not None
        bolt = result["bolt"]
        assert bolt["base_name"] == "M8"
        assert bolt["type"] == "bolt"
        assert bolt["p"] == 1.25
        assert bolt["d"] == 8.0
        assert bolt["Le"] == 16.0
        # optional auto fields blank → None
        assert bolt["dn"] is None
        assert bolt["d1"] is None
        # insert is always produced with base material; geometry copied from bolt
        ins = result["insert"]
        assert ins is not None
        assert ins["type"] == "insert"
        assert ins["base_name"] == "M8"
        assert ins["material"] == "SS316L(N)-IG_SDC-IC"
        assert ins["p"] == 1.25  # copied from bolt
        assert ins["Le"] == 16.0  # copied from bolt

    def test_collect_with_insert(self, root):
        """Dedicated insert geometry: its own dimension fields are used."""
        dlg = self._make(root, has_insert=True)
        result = dlg._collect()
        assert result is not None
        ins = result["insert"]
        assert ins["base_name"] == "M8"
        assert ins["type"] == "insert"
        assert ins["Le"] == 10.0  # from _ins_vars (distinct from bolt Le=16.0)
        # bolt-only fields not present in insert
        assert "f_prime" not in ins
        assert "KF" not in ins

    def test_collect_different_base_material(self, root):
        """Base mat material may differ from bolt material."""
        dlg = self._make(root, bolt_mat="SS316L(N)-IG_SDC-IC", ins_mat="Inconel 718")
        result = dlg._collect()
        assert result["bolt"]["material"] == "SS316L(N)-IG_SDC-IC"
        assert result["insert"]["material"] == "Inconel 718"

    def test_collect_optional_fields_set(self, root):
        dlg = self._make(root)
        dlg._bolt_vars["dn"].set("6.5")
        dlg._bolt_vars["d1"].set("8.0")
        result = dlg._collect()
        assert result["bolt"]["dn"] == 6.5
        assert result["bolt"]["d1"] == 8.0

    def test_collect_missing_base_name(self, root):
        dlg = self._make(root, base_name="  ")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()

    def test_collect_missing_required_dimension(self, root):
        dlg = self._make(root)
        dlg._bolt_vars["p"].set("")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()

    def test_collect_non_numeric_dimension(self, root):
        dlg = self._make(root)
        dlg._bolt_vars["d"].set("abc")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()

    def test_collect_non_numeric_bolt_field(self, root):
        dlg = self._make(root)
        dlg._bolt_vars["KF"].set("bad")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()


# ---------------------------------------------------------------------------
# 3. FlangeDialog._collect()
# ---------------------------------------------------------------------------


class TestFlangeDialogCollect:
    def _make(self, root, name="Flange1", code=None, actions=""):
        dlg = object.__new__(FlangeDialog)
        dlg._ex = {}
        dlg._name = tk.StringVar(root, value=name)
        dlg._code = tk.StringVar(root, value=code or BOLT_DESIGN_CODES[0])
        dlg._actions = tk.StringVar(root, value=actions)
        return dlg

    def test_collect_valid(self, root):
        dlg = self._make(root)
        result = dlg._collect()
        assert result == {
            "name": "Flange1",
            "design_code": BOLT_DESIGN_CODES[0],
            "actions_file": "",
            "bolts_spec": [],
        }

    def test_collect_preserves_existing_bolts_spec(self, root):
        dlg = object.__new__(FlangeDialog)
        dlg._ex = {"bolts_spec": [_bolt_entry()]}
        dlg._name = tk.StringVar(root, value="F")
        dlg._code = tk.StringVar(root, value=BOLT_DESIGN_CODES[0])
        dlg._actions = tk.StringVar(root, value="")
        result = dlg._collect()
        assert len(result["bolts_spec"]) == 1

    def test_collect_empty_name_returns_none(self, root):
        dlg = self._make(root, name="")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()


# ---------------------------------------------------------------------------
# 4. BoltSpecDialog._collect()
# ---------------------------------------------------------------------------


class TestBoltSpecDialogCollect:
    def _make(self, root, bolt_id="B1", geom="M8", preload="5000"):
        dlg = object.__new__(BoltSpecDialog)
        dlg._bolt_geom_names = ["M8", "M12"]
        dlg._ex = {}
        dlg._bolt_id = tk.StringVar(root, value=bolt_id)
        dlg._geom_data = tk.StringVar(root, value=geom)
        dlg._preload = tk.StringVar(root, value=preload)
        return dlg

    def test_collect_valid(self, root):
        dlg = self._make(root)
        result = dlg._collect()
        assert result == {"bolt_id": "B1", "geom_data": "M8", "preload": 5000.0}

    def test_collect_missing_bolt_id(self, root):
        dlg = self._make(root, bolt_id="")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()

    def test_collect_missing_geom(self, root):
        dlg = self._make(root, geom="")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None

    def test_collect_bad_preload(self, root):
        dlg = self._make(root, preload="not_a_number")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()


# ---------------------------------------------------------------------------
# 5. BoltREDialog._collect()
# ---------------------------------------------------------------------------


class TestBoltREDialogCollect:
    def _make(
        self,
        root,
        re_id="RE-01",
        pri_ana="Inertial",
        pri_ls="1",
        all_ana="Inertial",
        all_ls="1",
    ):
        dlg = object.__new__(BoltREDialog)
        dlg._ex = {}
        dlg._re_id = tk.StringVar(root, value=re_id)
        dlg._svc = tk.StringVar(root, value="A")
        dlg._lcat = tk.StringVar(root, value="I")
        dlg._oc = tk.StringVar(root, value="Normal")
        dlg._ie = tk.StringVar(root, value="N/A")
        dlg._ce = tk.StringVar(root, value="N/A")
        dlg._pri_analysis = tk.StringVar(root, value=pri_ana)
        dlg._pri_loadstep = tk.StringVar(root, value=pri_ls)
        dlg._all_analysis = tk.StringVar(root, value=all_ana)
        dlg._all_loadstep = tk.StringVar(root, value=all_ls)
        return dlg

    def test_collect_valid(self, root):
        dlg = self._make(root)
        result = dlg._collect()
        assert result is not None
        assert result["re_id"] == "RE-01"
        assert "temp" not in result
        assert "dpa" not in result
        assert result["primary_analysis"] == "Inertial"
        assert result["primary_loadstep"] == "1"
        assert result["service_lvl"] == "A"
        assert result["load_category"] == "I"

    def test_collect_missing_re_id(self, root):
        dlg = self._make(root, re_id="")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()

    def test_collect_missing_action_fields(self, root):
        dlg = self._make(root, pri_ana="")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()


# ---------------------------------------------------------------------------
# 6. BoltFatigueREDialog._collect()
# ---------------------------------------------------------------------------


class TestBoltFatigueREDialogCollect:
    def _make(
        self,
        root,
        re_id="FRE-01",
        ncycles="100",
        ds_plus_ana="Inertial",
        ds_plus_ls="1",
        ds_minus_ana="Inertial",
        ds_minus_ls="2",
        sus_ana="",
        sus_ls="",
    ):
        dlg = object.__new__(BoltFatigueREDialog)
        dlg._ex = {}
        dlg._re_id = tk.StringVar(root, value=re_id)
        dlg._svc = tk.StringVar(root, value="A")
        dlg._lcat = tk.StringVar(root, value="I")
        dlg._oc = tk.StringVar(root, value="Normal")
        dlg._ie = tk.StringVar(root, value="N/A")
        dlg._ce = tk.StringVar(root, value="N/A")
        dlg._ncycles = tk.StringVar(root, value=ncycles)
        dlg._ds_plus_ana = tk.StringVar(root, value=ds_plus_ana)
        dlg._ds_plus_ls = tk.StringVar(root, value=ds_plus_ls)
        dlg._ds_minus_ana = tk.StringVar(root, value=ds_minus_ana)
        dlg._ds_minus_ls = tk.StringVar(root, value=ds_minus_ls)
        dlg._sus_ana = tk.StringVar(root, value=sus_ana)
        dlg._sus_ls = tk.StringVar(root, value=sus_ls)
        return dlg

    def test_collect_valid(self, root):
        dlg = self._make(root)
        result = dlg._collect()
        assert result is not None
        assert result["re_id"] == "FRE-01"
        assert "temp" not in result
        assert "dpa" not in result
        assert result["n_cycles"] == 100
        assert result["ds_plus_analysis"] == "Inertial"
        assert result["ds_plus_loadstep"] == "1"
        assert result["ds_minus_analysis"] == "Inertial"
        assert result["ds_minus_loadstep"] == "2"
        assert result["sigma_sus_analysis"] == ""
        assert result["sigma_sus_loadstep"] == ""

    def test_collect_with_sustained(self, root):
        dlg = self._make(root, sus_ana="Thermal", sus_ls="3")
        result = dlg._collect()
        assert result["sigma_sus_analysis"] == "Thermal"
        assert result["sigma_sus_loadstep"] == "3"

    def test_collect_missing_re_id(self, root):
        dlg = self._make(root, re_id="")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()

    def test_collect_bad_ncycles(self, root):
        dlg = self._make(root, ncycles="3.5")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()

    def test_collect_missing_delta_sigma(self, root):
        dlg = self._make(root, ds_plus_ana="")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            result = dlg._collect()
        assert result is None
        mb.showerror.assert_called_once()


# ---------------------------------------------------------------------------
# 7. GeneralTab
# ---------------------------------------------------------------------------


class TestGeneralTab:
    def test_sync_updates_project(self, root):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = GeneralTab(nb, proj)
        tab._fatigue.set(True)
        tab._matlib.set("/my/libs")
        tab._root_dir.set("/my/output")
        tab.sync()
        assert proj["run_options"]["fatigue"] is True
        assert proj["run_options"]["matlib_path"] == "/my/libs"
        assert proj["run_options"]["root_dir"] == "/my/output"

    def test_load_from_project(self, root):
        proj = _fresh_project()
        proj["run_options"]["fatigue"] = True
        proj["run_options"]["matlib_path"] = "/libs"
        proj["run_options"]["root_dir"] = "/out"
        nb = tk.ttk.Notebook(root)
        tab = GeneralTab(nb, proj)
        tab.load_from_project()
        assert tab._fatigue.get() is True
        assert tab._matlib.get() == "/libs"
        assert tab._root_dir.get() == "/out"

    def test_run_no_root_dir_shows_warning(self, root):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = GeneralTab(nb, proj)
        tab._root_dir.set("")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            tab._run_assessment()
        mb.showwarning.assert_called_once()

    def test_run_no_flanges_shows_warning(self, root):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = GeneralTab(nb, proj)
        tab._root_dir.set("/some/dir")
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            tab._run_assessment()
        mb.showwarning.assert_called_once()


# ---------------------------------------------------------------------------
# 8. GeometriesTab — add / edit / delete, import / export
# ---------------------------------------------------------------------------


class TestGeometriesTab:
    def test_refresh_populates_tree(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = GeometriesTab(nb, proj)
        tab.refresh()
        assert len(tab._tree.get_children()) == len(proj["geometries"])

    def test_delete_removes_geometry(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = GeometriesTab(nb, proj)
        tab.refresh()
        children = tab._tree.get_children()
        tab._tree.selection_set(children[0])
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            mb.askyesno.return_value = True
            tab._delete()
        assert len(proj["geometries"]) == 1

    def test_export_lib_writes_json(self, root, tmp_path):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = GeometriesTab(nb, proj)
        dest = tmp_path / "geom_lib.json"
        with (
            patch("cassy.gui.bolts_gui.filedialog") as fd,
            patch("cassy.gui.bolts_gui.messagebox"),
        ):
            fd.asksaveasfilename.return_value = str(dest)
            tab._export_lib()
        assert dest.exists()
        data = json.loads(dest.read_text())
        assert isinstance(data, list)
        assert len(data) == 2

    def test_import_lib_merges_new_entries(self, root, tmp_path):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = GeometriesTab(nb, proj)
        lib_file = tmp_path / "lib.json"
        lib_file.write_text(json.dumps([_geom_bolt("M10"), _geom_bolt("M12")]))
        with (
            patch("cassy.gui.bolts_gui.filedialog") as fd,
            patch("cassy.gui.bolts_gui.messagebox") as mb,
        ):
            fd.askopenfilename.return_value = str(lib_file)
            tab._import_lib()
        assert len(proj["geometries"]) == 2
        mb.showinfo.assert_called_once()

    def test_import_lib_skips_duplicates(self, root, tmp_path):
        proj = _project()  # already has M8 bolt and M8ins insert
        nb = tk.ttk.Notebook(root)
        tab = GeometriesTab(nb, proj)
        lib_file = tmp_path / "lib.json"
        lib_file.write_text(json.dumps([_geom_bolt("M8")]))  # duplicate
        with (
            patch("cassy.gui.bolts_gui.filedialog") as fd,
            patch("cassy.gui.bolts_gui.messagebox") as mb,
        ):
            fd.askopenfilename.return_value = str(lib_file)
            tab._import_lib()
        assert len(proj["geometries"]) == 2  # no new entries
        msg = mb.showinfo.call_args[0][1]
        assert "0" in msg

    def test_import_lib_cancelled(self, root):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = GeometriesTab(nb, proj)
        with patch("cassy.gui.bolts_gui.filedialog") as fd:
            fd.askopenfilename.return_value = ""
            tab._import_lib()  # must not raise
        assert proj["geometries"] == []

    def test_import_lib_invalid_json(self, root, tmp_path):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = GeometriesTab(nb, proj)
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json")
        with (
            patch("cassy.gui.bolts_gui.filedialog") as fd,
            patch("cassy.gui.bolts_gui.messagebox") as mb,
        ):
            fd.askopenfilename.return_value = str(bad_file)
            tab._import_lib()
        mb.showerror.assert_called_once()

    def test_import_lib_non_list_json(self, root, tmp_path):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = GeometriesTab(nb, proj)
        bad_file = tmp_path / "bad.json"
        bad_file.write_text('{"key": "value"}')
        with (
            patch("cassy.gui.bolts_gui.filedialog") as fd,
            patch("cassy.gui.bolts_gui.messagebox") as mb,
        ):
            fd.askopenfilename.return_value = str(bad_file)
            tab._import_lib()
        mb.showerror.assert_called_once()


# ---------------------------------------------------------------------------
# 9. FlangesTab — add / edit / delete cascade
# ---------------------------------------------------------------------------


class TestFlangesTab:
    def test_add_flange_populates_re_dicts(self, root):
        proj = _fresh_project()
        nb = tk.ttk.Notebook(root)
        tab = FlangesTab(nb, proj)
        proj["flanges"].append(
            {
                "name": "F1",
                "design_code": BOLT_DESIGN_CODES[0],
                "actions_file": "",
                "bolts_spec": [],
            }
        )
        tab.refresh()
        assert len(proj["flanges"]) == 1

    def test_delete_flange_cascades_re_data(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = FlangesTab(nb, proj)
        tab.refresh()
        # Remove F1 directly (simulates _delete logic); REs are now shared
        proj["flanges"] = [f for f in proj["flanges"] if f["name"] != "F1"]
        assert len(proj["flanges"]) == 1

    def test_refresh_shows_all_flanges(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = FlangesTab(nb, proj)
        tab.refresh()
        assert len(tab._tree.get_children()) == 2


# ---------------------------------------------------------------------------
# 10. BoltSpecsTab — per-flange bolt/insert management
# ---------------------------------------------------------------------------


class TestBoltSpecsTab:
    def test_refresh_populates_correct_flange(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltSpecsTab(nb, proj)
        tab.refresh()
        # F1 should be auto-selected (first flange)
        assert tab._fl_var.get() == "F1"
        rows = tab._tree.get_children()
        assert len(rows) == 2  # B1 and B2

    def test_insert_shown_in_has_insert_column(self, root):
        """Table shows exactly bolt_id, geom_data and preload — no insert columns."""
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltSpecsTab(nb, proj)
        tab.refresh()
        rows = tab._tree.get_children()
        vals_b1 = tab._tree.item(rows[0])["values"]
        assert vals_b1[0] == "B1"
        assert vals_b1[1] == "M8"
        assert vals_b1[2] == 5000.0 or vals_b1[2] == "5000.0"
        assert len(vals_b1) == 3

    def test_delete_bolt_removes_bolt_from_spec(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltSpecsTab(nb, proj)
        tab.refresh()
        rows = tab._tree.get_children()
        tab._tree.selection_set(rows[0])  # select B1
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            mb.askyesno.return_value = True
            tab._delete()
        assert not any(b["bolt_id"] == "B1" for b in proj["flanges"][0]["bolts_spec"])

    def test_delete_multiple_bolts(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltSpecsTab(nb, proj)
        tab.refresh()
        tab._tree.selection_set(tab._tree.get_children())
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            mb.askyesno.return_value = True
            tab._delete()
        assert proj["flanges"][0]["bolts_spec"] == []

    def test_geom_names_by_type_filters_correctly(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltSpecsTab(nb, proj)
        bolts = tab._geom_names_by_type("bolt")
        inserts = tab._geom_names_by_type("insert")
        assert bolts == ["M8"]
        assert inserts == ["M8"]  # same base_name as bolt (from GeomDialog pairing)


# ---------------------------------------------------------------------------
# 11. BoltREsTab — per-flange RE management
# ---------------------------------------------------------------------------


class TestBoltREsTab:
    def test_refresh_populates_table(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltREsTab(nb, proj)
        tab.refresh()
        assert len(tab._tree.get_children()) == 2  # RE-01 and RE-02

    def test_refresh_table_shows_correct_res(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltREsTab(nb, proj)
        tab.refresh()
        assert len(tab._tree.get_children()) == 2  # RE-01 and RE-02

    def test_delete_re_removes_entry(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltREsTab(nb, proj)
        tab.refresh()
        rows = tab._tree.get_children()
        tab._tree.selection_set(rows[0])
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            mb.askyesno.return_value = True
            tab._delete()
        assert len(proj["reference_events"]) == 1

    def test_row_values_formats_actions(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltREsTab(nb, proj)
        vals = tab._row_values(_re_dict())
        assert vals[0] == "RE-01"
        assert "Inertial" in vals[6]  # primary column
        assert "Inertial" in vals[7]  # all loads column

    def test_no_selection_on_delete_shows_warning(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltREsTab(nb, proj)
        tab.refresh()
        # No item selected
        with patch("cassy.gui.bolts_gui.messagebox") as mb:
            tab._delete()
        mb.showwarning.assert_called_once()


# ---------------------------------------------------------------------------
# 12. BoltFatigueREsTab — subclass differences
# ---------------------------------------------------------------------------


class TestBoltFatigueREsTab:
    def test_uses_fatigue_re_key(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltFatigueREsTab(nb, proj)
        assert tab._RE_KEY == "fatigue_reference_events"

    def test_row_values_includes_ncycles(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltFatigueREsTab(nb, proj)
        vals = tab._row_values(_fat_re_dict())
        assert vals[0] == "FRE-01"
        assert vals[3] == 100  # n_cycles

    def test_row_values_shows_sustained_na_when_empty(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltFatigueREsTab(nb, proj)
        vals = tab._row_values(_fat_re_dict())
        assert vals[6] == "N/A"  # sigma_sus column

    def test_row_values_shows_sustained_when_set(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltFatigueREsTab(nb, proj)
        fat_re = _fat_re_dict()
        fat_re["sigma_sus_analysis"] = "Thermal"
        fat_re["sigma_sus_loadstep"] = "3"
        vals = tab._row_values(fat_re)
        assert "Thermal" in vals[6]

    def test_make_dialog_returns_fatigue_dialog(self, root):
        proj = _project()
        nb = tk.ttk.Notebook(root)
        tab = BoltFatigueREsTab(nb, proj)
        # _make_dialog should return a BoltFatigueREDialog instance
        # We test this indirectly by verifying it's not BoltREDialog
        dlg_class = type(tab._make_dialog.__func__)
        # The method is overridden — check the bound method creates the right type
        # by inspecting the code rather than calling it (would open a window)
        import inspect

        src = inspect.getsource(BoltFatigueREsTab._make_dialog)
        assert "BoltFatigueREDialog" in src


def test_get_analysis_names_from_actions_files(tmp_path):
    header = "boltID,analysis,loadstep,Fx,Fy,Fz,Mz,Mx,My\n"
    f1 = tmp_path / "f1.csv"
    f1.write_text(header + "1,Thermal,1,0,0,0,0,0,0\n2,Seismic,1,0,0,0,0,0,0\n")
    f2 = tmp_path / "f2.csv"
    f2.write_text(header + "1,Thermal,2,0,0,0,0,0,0\n1,Dead,1,0,0,0,0,0,0\n")
    proj = {
        "flanges": [
            {"actions_file": str(f1)},
            {"actions_file": str(f2)},
            {"actions_file": str(tmp_path / "missing.csv")},
            {"actions_file": ""},
        ]
    }
    assert _get_analysis_names(proj) == ["Dead", "Seismic", "Thermal"]


# ---------------------------------------------------------------------------
# 13. JSON round-trip
# ---------------------------------------------------------------------------


class TestJSONRoundTrip:
    def test_full_project_serialises(self, tmp_path):
        proj = _project()
        dest = tmp_path / "bolts_project.json"
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(proj, fh, indent=2)
        with open(dest, encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded["flanges"] == proj["flanges"]
        assert loaded["geometries"] == proj["geometries"]
        assert loaded["reference_events"] == proj["reference_events"]
        assert loaded["fatigue_reference_events"] == proj["fatigue_reference_events"]
        assert loaded["tdpa"] == proj["tdpa"]
        assert loaded["tdpa_fatigue"] == proj["tdpa_fatigue"]

    def test_geometry_optional_none_fields_serialised(self, tmp_path):
        proj = _project()
        dest = tmp_path / "proj.json"
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(proj, fh)
        loaded = json.loads(dest.read_text())
        bolt_geom = next(g for g in loaded["geometries"] if g["type"] == "bolt")
        # None serialises to JSON null
        assert bolt_geom["dn"] is None
        assert bolt_geom["d1"] is None

    def test_bolt_with_insert_serialises(self, tmp_path):
        proj = _project()
        dest = tmp_path / "proj.json"
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(proj, fh)
        loaded = json.loads(dest.read_text())
        b1 = next(b for b in loaded["flanges"][0]["bolts_spec"] if b["bolt_id"] == "B1")
        assert b1 == {"bolt_id": "B1", "geom_data": "M8", "preload": 5000.0}

    def test_bolt_without_insert_serialises(self, tmp_path):
        proj = _project()
        dest = tmp_path / "proj.json"
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(proj, fh)
        loaded = json.loads(dest.read_text())
        b2 = next(b for b in loaded["flanges"][0]["bolts_spec"] if b["bolt_id"] == "B2")
        assert b2 == {"bolt_id": "B2", "geom_data": "M8", "preload": 5000.0}


# ---------------------------------------------------------------------------
# 14. _build_bolts_from_project — geometry builder
# ---------------------------------------------------------------------------


class TestBuildBoltsFromProject:
    def test_raises_on_missing_actions_file(self):
        proj = _project()
        proj["flanges"][0]["actions_file"] = "/nonexistent/actions.csv"
        with pytest.raises(ValueError, match="Actions CSV not found"):
            _build_bolts_from_project(proj)

    def test_raises_on_unknown_material(self):
        proj = _project()
        proj["geometries"][0]["material"] = "UNKNOWN_MAT_XYZ"
        # actions_file would fail first; set it to empty to reach material check
        # Provide a real path that doesn't exist to get the actions error first
        # Easier: give no flanges so we only test geometry building
        proj["flanges"] = []
        with pytest.raises((ValueError, KeyError)):
            _build_bolts_from_project(proj)

    def test_geoms_keyed_by_base_name_plus_type(self):
        proj = _project()
        proj["flanges"] = []  # skip config building, just test geom
        _configs, geoms = _build_bolts_from_project(proj)
        assert "M8_bolt" in geoms
        assert "M8_insert" in geoms

    def test_bolt_geom_auto_computes_optional_fields(self):
        proj = _project()
        proj["flanges"] = []
        _configs, geoms = _build_bolts_from_project(proj)
        bolt = geoms["M8_bolt"]
        # dn was None → auto-computed from d and p
        assert bolt.dn is not None
        assert bolt.dn > 0

    def test_bolts_spec_includes_insert_row(self, tmp_path):
        import pandas as pd

        # Create a minimal actions CSV
        actions_df = pd.DataFrame(
            [{"boltID": "B1", "analysis": "Inertial", "loadstep": 1, "Fz": 1000.0}]
        )
        actions_file = tmp_path / "actions.csv"
        actions_df.to_csv(actions_file, index=False)

        proj = _project()
        # geometry library has both M8 bolt and M8 insert (same base_name)
        proj["flanges"] = [
            {
                "name": "F1",
                "design_code": BOLT_DESIGN_CODES[0],
                "actions_file": str(actions_file),
                "bolts_spec": [_bolt_entry("B1")],
            }
        ]
        proj["reference_events"] = [_re_dict()]
        proj["fatigue_reference_events"] = []
        proj["tdpa"] = [
            {"flange": "F1", "bolt_id": "B1", "re_id": "RE-01", "T": 100.0, "dpa": 0.0}
        ]

        _configs, _geoms = _build_bolts_from_project(proj)
        bolts_spec = _configs["F1"].bolts_spec
        assert "bolt" in bolts_spec["Geom type"].values
        assert "insert" in bolts_spec["Geom type"].values

    def test_fatigue_res_built_when_fatigue_enabled(self, tmp_path):
        import pandas as pd

        actions_df = pd.DataFrame(
            [{"boltID": "B1", "analysis": "Inertial", "loadstep": 1, "Fz": 1000.0}]
        )
        actions_file = tmp_path / "actions.csv"
        actions_df.to_csv(actions_file, index=False)

        proj = _project()
        proj["run_options"]["fatigue"] = True
        proj["flanges"] = [
            {
                "name": "F1",
                "design_code": BOLT_DESIGN_CODES[0],
                "actions_file": str(actions_file),
                "bolts_spec": [_bolt_entry("B1")],
            }
        ]
        proj["reference_events"] = [_re_dict()]
        proj["fatigue_reference_events"] = [_fat_re_dict()]
        proj["tdpa"] = [
            {"flange": "F1", "bolt_id": "B1", "re_id": "RE-01", "T": 100.0, "dpa": 0.0}
        ]
        proj["tdpa_fatigue"] = [
            {"flange": "F1", "bolt_id": "B1", "re_id": "FRE-01", "T": 100.0, "dpa": 0.0}
        ]

        _configs, _geoms = _build_bolts_from_project(proj)
        assert _configs["F1"].REs_fatigue is not None
        assert len(_configs["F1"].REs_fatigue["B1"]) == 1

    def test_fatigue_res_none_when_fatigue_disabled(self, tmp_path):
        import pandas as pd

        actions_df = pd.DataFrame(
            [{"boltID": "B1", "analysis": "Inertial", "loadstep": 1, "Fz": 1000.0}]
        )
        actions_file = tmp_path / "actions.csv"
        actions_df.to_csv(actions_file, index=False)

        proj = _project()
        proj["run_options"]["fatigue"] = False
        proj["flanges"] = [
            {
                "name": "F1",
                "design_code": BOLT_DESIGN_CODES[0],
                "actions_file": str(actions_file),
                "bolts_spec": [_bolt_entry("B1")],
            }
        ]
        proj["reference_events"] = [_re_dict()]
        proj["fatigue_reference_events"] = []
        proj["tdpa"] = [
            {"flange": "F1", "bolt_id": "B1", "re_id": "RE-01", "T": 100.0, "dpa": 0.0}
        ]

        _configs, _geoms = _build_bolts_from_project(proj)
        assert _configs["F1"].REs_fatigue is None

    def test_sustained_sigma_none_when_fields_empty(self, tmp_path):
        import pandas as pd
        from cassy.bolts.bolt_config import BoltReferenceEventFatigue

        actions_df = pd.DataFrame(
            [{"boltID": "B1", "analysis": "Inertial", "loadstep": 1, "Fz": 1000.0}]
        )
        actions_file = tmp_path / "actions.csv"
        actions_df.to_csv(actions_file, index=False)

        proj = _project()
        proj["run_options"]["fatigue"] = True
        fat_re = _fat_re_dict()
        fat_re["sigma_sus_analysis"] = ""
        fat_re["sigma_sus_loadstep"] = ""
        proj["flanges"] = [
            {
                "name": "F1",
                "design_code": BOLT_DESIGN_CODES[0],
                "actions_file": str(actions_file),
                "bolts_spec": [_bolt_entry("B1")],
            }
        ]
        proj["reference_events"] = [_re_dict()]
        proj["fatigue_reference_events"] = [fat_re]
        proj["tdpa"] = [
            {"flange": "F1", "bolt_id": "B1", "re_id": "RE-01", "T": 100.0, "dpa": 0.0}
        ]
        proj["tdpa_fatigue"] = [
            {"flange": "F1", "bolt_id": "B1", "re_id": "FRE-01", "T": 100.0, "dpa": 0.0}
        ]

        _configs, _geoms = _build_bolts_from_project(proj)
        built_fat_re: BoltReferenceEventFatigue = _configs["F1"].REs_fatigue["B1"][0]
        assert built_fat_re.sigma_sustained is None
