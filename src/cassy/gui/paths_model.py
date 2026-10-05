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

    This lets the runner be called without writing any Excel files to disk.
    Stress tensors are read from the CSV paths stored in each submodel entry.
    """
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
