import os
import shutil
from importlib.resources import files
from pathlib import Path

import pandas as pd
import numpy as np

from cassy.runners.run_paths import run_paths
from cassy.paths.paths_config import Configuration
from tests import runners


def test_run_paths(tmpdir):
    to_copy = files(runners).joinpath("paths")
    dest = tmpdir.join("paths")
    shutil.copytree(to_copy, dest)
    run_paths(dest, fatigue=True, matlib=Path(dest, "additional_materials"))


def test_run_paths_no_recap(tmpdir):
    to_copy = files(runners).joinpath("paths")
    dest = tmpdir.join("paths")
    shutil.copytree(to_copy, dest)
    print(to_copy)
    print(dest)
    print(os.listdir(dest))  # for debug
    print(os.listdir(os.path.join(dest, "stresses")))  # for debug
    run_paths(dest, fatigue=True, print_recap=False)


def test_run_paths_with_programmatic_config(tmpdir):
    """Test run_paths with programmatically created configurations."""

    # Create a minimal Configuration object programmatically
    config = Configuration.__new__(Configuration)  # Bypass __init__
    config.submodel = "TestModel"
    config.code = "SDC-IC"

    # Create the required sheets as dataframes
    # 1. General sheet
    general_df = pd.DataFrame({"Parameter": ["Design Code"], "Value": ["SDC-IC"]})
    general_df.set_index("Parameter", inplace=True)

    # 2. Paths sheet
    paths_df = pd.DataFrame(
        {
            "Path N": [1],
            "Material": ["SS316L(N)-IG_SDC-IC"],
            "Type": ["normal"],
            "Welding-n": [1.0],
            "Welding-f": [1.0],
        }
    )
    paths_df.set_index("Path N", inplace=True)

    # 3. Load Steps sheet
    load_steps_df = pd.DataFrame(
        {
            "Load Name": ["Load1", "Load2"],
            "Analysis Name": ["static", "static"],
            "Time Step": [1, 2],
            "Load Type": ["pressure", "pressure"],
        }
    )
    load_steps_df.set_index("Load Name", inplace=True)

    # 4. Stresses sheet
    stresses_df = pd.DataFrame(
        {
            "Load Name": ["Load1", "Load2"],
            "Stress Type": ["P", "P"],  # P for PRIMARY, Q for SECONDARY
            "Load Type": ["Volumetric", "Volumetric"],  # Volumetric or Inertial
            "Scale": [1.0, 1.0],
            "Unit": ["MPa", "MPa"],
            "Spatial Recombination": [
                np.nan,
                np.nan,
            ],  # Use np.nan for default behavior
            "Is Cyclic": [False, False],
            "Is Pressure": [True, True],
            "Is Short Overstress": [False, False],
        }
    )
    stresses_df.set_index("Load Name", inplace=True)

    # 5. Reference Event sheet
    ref_event_df = pd.DataFrame(
        {
            "Path N": [1],
            "ID": ["RE1"],
            "Operating Conditions": ["Normal"],
            "Initiating Event": ["None"],
            "Concatenated Event": ["None"],
            "T [°C]": [20.0],
            "DPA": [0.0],
            "Loading ctg.": ["A"],
            "Service Level": ["A"],
            "Loads": ["Load1, Load2"],  # Comma-separated load names
        }
    )
    ref_event_df.set_index(["Path N", "ID"], inplace=True)

    # 6. Reference Event Fatigue sheet (empty for now)
    ref_event_fat_df = pd.DataFrame(
        {
            "Path N": pd.Series([], dtype=int),
            "ID": pd.Series([], dtype=str),
            "Operating Conditions": pd.Series([], dtype=str),
            "Initiating Event": pd.Series([], dtype=str),
            "Concatenated Event": pd.Series([], dtype=str),
            "T [°C]": pd.Series([], dtype=float),
            "DPA": pd.Series([], dtype=float),
            "Loading ctg.": pd.Series([], dtype=str),
            "Service Level": pd.Series([], dtype=str),
            "N of cycles": pd.Series([], dtype=int),
            "Delta Sigma +": pd.Series([], dtype=str),
            "Delta Sigma -": pd.Series([], dtype=str),
        }
    )
    if len(ref_event_fat_df) > 0:
        ref_event_fat_df.set_index(["Path N", "ID"], inplace=True)

    # Assemble sheets dictionary
    config.sheets = {
        "General": general_df,
        "Paths": paths_df,
        "Load Steps": load_steps_df,
        "Stresses": stresses_df,
        "Reference Event": ref_event_df,
        "Reference Event Fatigue": ref_event_fat_df,
    }

    config.paths = paths_df.index
    config.loads = load_steps_df.index

    # Create stress tensors dataframe
    stress_tensors_data = []
    for path in [1]:
        for analysis in ["static"]:
            for loadstep in [1, 2]:
                for pathpoint in ["begin", "end"]:
                    for stress_type in ["Pm", "Pb", "F"]:
                        stress_tensors_data.append(
                            {
                                "path": path,
                                "analysis": analysis,
                                "loadstep": loadstep,
                                "pathpoint": pathpoint,
                                "stress_type": stress_type,
                                "Sx": 100.0 if stress_type == "Pm" else 10.0,
                                "Sy": 50.0 if stress_type == "Pm" else 5.0,
                                "Sz": 75.0 if stress_type == "Pm" else 7.5,
                                "Sxy": 0.0,
                                "Sxz": 0.0,
                                "Syz": 0.0,
                            }
                        )

    stress_tensors_df = pd.DataFrame(stress_tensors_data)
    stress_tensors_df.set_index(
        ["path", "analysis", "loadstep", "pathpoint", "stress_type"], inplace=True
    )
    config.stress_tensors = stress_tensors_df

    # Create config dictionary
    configs_dict = {"TestModel": config}

    # Setup temporary directory
    dest = Path(tmpdir, "paths_test")
    dest.mkdir()

    # Run the assessment with programmatic configurations
    run_paths(
        dest,
        fatigue=False,  # Disable fatigue since we don't have fatigue REs
        print_recap=False,
        configs=configs_dict,
    )
