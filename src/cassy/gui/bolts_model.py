"""Tk-free project model for the bolts GUI.

Holds the JSON project schema and converts a project dict into the objects
consumed by :func:`cassy.runners.run_bolts.run_bolts`.
"""

from __future__ import annotations

import copy
import csv
import os
from typing import Any

from cassy.designcodes.map import BOLT_CODES as _BOLT_CODES

BOLT_DESIGN_CODES: list[str] = list(_BOLT_CODES.keys())
GEOM_TYPES: list[str] = ["bolt", "insert"]
SERVICE_LEVELS: list[str] = ["A", "C", "D"]
LOAD_CATEGORIES: list[str] = ["I", "II", "III", "IV"]

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
    "tdpa": [],  # [{flange, bolt_id, re_id, T, dpa}]
    "tdpa_fatigue": [],  # [{flange, bolt_id, re_id, T, dpa}]
}


def fresh_project() -> dict:
    return copy.deepcopy(EMPTY_BOLT_PROJECT)


def get_material_names(matlib_path: str = "") -> list[str]:
    from cassy.runners.run_common import build_material_library

    return sorted(build_material_library(matlib_path or None).keys())


def get_analysis_names(project: dict) -> list[str]:
    """Unique analysis names found in the actions CSVs of all flanges."""
    names: set[str] = set()
    for flange in project.get("flanges", []):
        path = flange.get("actions_file", "")
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    value = (row.get("analysis") or "").strip()
                    if value:
                        names.add(value)
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
    return sorted(names)


def build_bolts_from_project(project: dict) -> tuple[dict, dict]:
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
