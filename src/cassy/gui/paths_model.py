"""Tk-free project model for the paths GUI.

Holds the JSON project schema and converts a project dict into the
``Configuration`` objects consumed by :func:`cassy.runners.run_paths.run_paths`.
"""

from __future__ import annotations

import copy
import os
from typing import Any

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
UNITS: list[str] = ["Pa", "MPa", "kPa"]
SERVICE_LEVELS: list[str] = ["A", "C", "D"]

EMPTY_PROJECT: dict[str, Any] = {
    "run_options": {
        "fatigue": False,
        "print_recap": True,
        "merge": True,
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


def fresh_project() -> dict:
    return copy.deepcopy(EMPTY_PROJECT)


def migrate_project(project: dict) -> dict:
    """Upgrade, in place, loads saved with the old analysis_name/time_step fields."""
    from cassy.auxiliary.functions import parse_legacy_combination

    for ld in project.get("loads", []):
        if "steps" not in ld:
            terms = parse_legacy_combination(
                ld.pop("analysis_name", ""), ld.pop("time_step", "")
            )
            ld["steps"] = [t.to_dict() for t in terms]
    return project


def bool_label(v: bool) -> str:
    return "Yes" if v else "No"


def get_material_names() -> list[str]:
    """Return available material names from the built-in library."""
    from cassy.runners.run_common import build_material_library

    return sorted(build_material_library().keys())


def get_available_analyses(project: dict) -> list[str]:
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


def build_configs_from_project(project: dict) -> dict:
    """Build a dict of ``Configuration`` objects from the in-memory project dict.

    Stress tensors are read from the CSV paths stored in each submodel entry.
    """
    from cassy.auxiliary.types import LoadTerm
    from cassy.paths.paths_config import (
        Configuration,
        LoadConfig,
        PathConfig,
        ReferenceEventConfig,
        read_stress_tensors,
    )

    loads = {
        ld["name"]: LoadConfig(
            name=ld["name"],
            steps=[LoadTerm.from_dict(t) for t in ld["steps"]],
            stress_classification=StressClassification(ld["stress_type"]),
            load_type=LoadType(ld["load_type"]),
            unit=ld["unit"],
            scale=float(ld["scale"]),
            spatial_rec_method=SpatialRecMethod(ld.get("spatial_rec") or "algebraic"),
            isPD=ld.get("is_pd", False),
            isCyclic=ld.get("is_cyclic", False),
            isPressure=ld.get("is_pressure", False),
            isShortOverstress=ld.get("is_short_overstress", False),
        )
        for ld in project.get("loads", [])
    }

    def _tdpa_lut(key: str) -> dict:
        return {
            (e["submodel"], e["path_num"], e["re_id"]): (float(e["T"]), float(e["dpa"]))
            for e in project.get(key, [])
            if "submodel" in e
        }

    def _re_configs(
        re_list: list, lut: dict, sm_name: str, pnum: int, fatigue: bool
    ) -> list[ReferenceEventConfig]:
        out = []
        for re in re_list:
            T, dpa = lut.get((sm_name, pnum, re["re_id"]), (0.0, 0.0))
            out.append(
                ReferenceEventConfig(
                    service_lvl=re.get("service_lvl", "A"),
                    re_ID=re["re_id"],
                    T=T,
                    dpa=dpa,
                    oc=re.get("oc", "N/A"),
                    ie=re.get("ie", "N/A"),
                    ce=re.get("ce", "N/A"),
                    load_ctg=re.get("load_ctg", "N/A"),
                    ncycles=(re.get("ncycles") or 0) if fatigue else None,
                    loads=list(re.get("loads", [])),
                )
            )
        return out

    tdpa_lut = _tdpa_lut("tdpa")
    tdpa_fat_lut = _tdpa_lut("tdpa_fatigue")
    res = project.get("reference_events", [])
    fat_res = project.get("fatigue_reference_events", [])

    configs: dict = {}
    for sm in project.get("submodels", []):
        sm_name = sm["name"]
        tensors_file = sm.get("tensors_file", "")
        if not tensors_file or not os.path.exists(tensors_file):
            raise ValueError(
                f"Stress tensors CSV not found for submodel '{sm_name}': "
                f"'{tensors_file}'"
            )
        paths = {
            int(p["path_num"]): PathConfig(
                pnum=int(p["path_num"]),
                material=p["material"],
                ptype=PathType(p.get("ptype", "normal")),
                welding_n=float(p.get("welding_n", 1.0)),
                welding_f=float(p.get("welding_f", 1.0)),
            )
            for p in project["paths"].get(sm_name, [])
        }
        configs[sm_name] = Configuration(
            submodel=sm_name,
            code=sm["design_code"],
            loads=loads,
            paths=paths,
            stress_tensors=read_stress_tensors(tensors_file),
            reference_events={
                pnum: _re_configs(res, tdpa_lut, sm_name, pnum, False) for pnum in paths
            },
            fatigue_reference_events={
                pnum: _re_configs(fat_res, tdpa_fat_lut, sm_name, pnum, True)
                for pnum in paths
            },
        )

    return configs
