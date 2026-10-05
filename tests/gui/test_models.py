"""Tests for the Tk-free GUI project models (run without a display)."""

from cassy.gui.bolts_model import EMPTY_BOLT_PROJECT, get_analysis_names
from cassy.gui.bolts_model import fresh_project as fresh_bolt_project
from cassy.gui.paths_model import EMPTY_PROJECT
from cassy.gui.paths_model import fresh_project as fresh_paths_project


def test_fresh_projects_are_independent_copies():
    bolts = fresh_bolt_project()
    bolts["flanges"].append({"name": "F1"})
    assert EMPTY_BOLT_PROJECT["flanges"] == []

    paths = fresh_paths_project()
    paths["paths"]["SM1"] = []
    assert EMPTY_PROJECT["paths"] == {}


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
    assert get_analysis_names(proj) == ["Dead", "Seismic", "Thermal"]
