"""Tests for the Tk-free GUI project models (run without a display)."""

import copy
import shutil
from pathlib import Path

import pytest

from cassy.additional_data import materials as mat_folder
from cassy.gui.bolts_model import EMPTY_BOLT_PROJECT, get_analysis_names
from cassy.gui.bolts_model import fresh_project as fresh_bolt_project
from cassy.gui.bolts_model import migrate_project as migrate_bolt_project
from cassy.gui.bolts_model import read_geometries_csv, write_geometries_csv
from cassy.gui.paths_model import EMPTY_PROJECT
from cassy.gui.paths_model import fresh_project as fresh_paths_project
from cassy.gui.paths_model import get_material_names as get_paths_material_names
from cassy.gui.paths_model import migrate_project as migrate_paths_project


def _t(sign: str, analysis: str, step: int) -> dict:
    return {"sign": sign, "analysis": analysis, "step": step}


def test_migrate_bolt_project_from_legacy_fields():
    proj = {
        "reference_events": [
            {
                "re_id": "RE1",
                "primary_analysis": "X",
                "primary_loadstep": "2-1",
                "all_analysis": "Y",
                "all_loadstep": "5",
            }
        ],
        "fatigue_reference_events": [
            {
                "re_id": "F1",
                "ds_plus_analysis": "X",
                "ds_plus_loadstep": "2",
                "ds_minus_analysis": "X",
                "ds_minus_loadstep": "1",
                "sigma_sus_analysis": "",
                "sigma_sus_loadstep": "",
            }
        ],
    }
    migrate_bolt_project(proj)
    assert proj["reference_events"][0] == {
        "re_id": "RE1",
        "primary": [_t("+", "X", 2), _t("-", "X", 1)],
        "all_loads": [_t("+", "Y", 5)],
    }
    assert proj["fatigue_reference_events"][0] == {
        "re_id": "F1",
        "ds_plus": [_t("+", "X", 2)],
        "ds_minus": [_t("+", "X", 1)],
        "sigma_sus": [],
    }

    # idempotent
    before = copy.deepcopy(proj)
    migrate_bolt_project(proj)
    assert proj == before


def test_migrate_paths_project_from_legacy_fields():
    proj = {"loads": [{"name": "L1", "analysis_name": "A", "time_step": 3}]}
    migrate_paths_project(proj)
    assert proj["loads"][0] == {"name": "L1", "steps": [_t("+", "A", 3)]}

    before = copy.deepcopy(proj)
    migrate_paths_project(proj)
    assert proj == before


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


def test_paths_material_names_include_additional_folder(tmp_path):
    builtin = Path(mat_folder.__file__).parent / "Inconel 718 RCC-MRx.yaml"
    shutil.copy(builtin, tmp_path / "My custom steel.yaml")
    assert "My custom steel" not in get_paths_material_names()
    names = get_paths_material_names(str(tmp_path))
    assert "My custom steel" in names
    assert "Inconel 718 RCC-MRx" in names


def test_geometries_csv_roundtrip(tmp_path):
    geoms = [
        {
            "base_name": "M8",
            "type": "bolt",
            "material": "SS660",
            "p": 1.25,
            "d": 8.0,
            "Le": 12.0,
            "d_vh": 0.0,
            "f": 0.15,
            "f_prime": 0.15,
            "B": 8.4,
            "C": 1.6,
            "KF": 4.0,
            "dn": 6.47,
            "df": 7.19,
            "D": 6.65,
            "d1": None,
            "H": None,
            "a": None,
            "Dm": None,
            "Dp": None,
        },
        {
            "base_name": "M8",
            "type": "insert",
            "material": "XM-19",
            "p": 1.25,
            "d": 8.0,
            "Le": 10.0,
            "d_vh": 0.0,
            "f": 0.15,
            "dn": None,
            "df": None,
            "D": None,
        },
    ]
    path = tmp_path / "lib.csv"
    write_geometries_csv(geoms, path)
    assert read_geometries_csv(path) == geoms


def test_geometries_csv_defaults_and_errors(tmp_path):
    path = tmp_path / "lib.csv"
    path.write_text("base_name,type,material,p,d,Le\nM6,Bolt,SS660,1,6,9\n")
    (geom,) = read_geometries_csv(path)
    assert geom["type"] == "bolt" and geom["KF"] == 4.0 and geom["dn"] is None
    path.write_text("base_name,type,material,p,d,Le\nM6,bolt,SS660,1,x,9\n")
    with pytest.raises(ValueError, match="Line 2: 'd' must be a number"):
        read_geometries_csv(path)
    path.write_text("base_name,type,material,p,d\nM6,bolt,SS660,1,6\n")
    with pytest.raises(ValueError, match="Missing columns"):
        read_geometries_csv(path)
