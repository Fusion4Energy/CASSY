import os
from pathlib import Path

import numpy as np
import pandas as pd

from cassy.auxiliary.trace import load_trace
from cassy.auxiliary.types import LoadTerm
from cassy.gui.paths_model import build_configs_from_project
from cassy.paths.paths_config import (
    Configuration,
    LoadConfig,
    LoadType,
    PathConfig,
    ReferenceEventConfig,
    StressClassification,
)
from cassy.runners.run_paths import run_paths
from tests.helpers import load_project

RES = Path(__file__).parent / "paths"


def test_run_paths(tmp_path):
    configs = build_configs_from_project(load_project(RES / "project.json"))
    run_paths(tmp_path, configs, fatigue=True, matlib=RES / "additional_materials")
    assert os.path.exists(Path(tmp_path, "Recap.docx"))


def test_run_paths_no_recap(tmp_path):
    configs = build_configs_from_project(load_project(RES / "project.json"))
    run_paths(tmp_path, configs, fatigue=True, print_recap=False, merge=False)
    assert not os.path.exists(Path(tmp_path, "Recap.docx"))
    assert not os.path.exists(Path(tmp_path, "assessment", "trace"))


def test_run_paths_trace(tmp_path):
    configs = build_configs_from_project(load_project(RES / "project.json"))
    run_paths(tmp_path, configs, fatigue=True, print_recap=False, trace=True)
    folder = Path(tmp_path, "assessment", "trace")
    assert os.path.exists(folder / "index.html")

    df = load_trace(folder)
    assert set(df["module"].dropna()) == {"paths"}
    assert {"material", "stress", "allowable", "result", "input"} <= set(df["kind"])
    assert set(df["analysis"].dropna()) == {"immediate", "fatigue"}
    assert set(df["position"].dropna()) == {"begin", "end"}
    # each html page per submodel
    for name in configs:
        assert any(f.startswith(name.replace(" ", "_")) for f in os.listdir(folder))

    # the allowable reported for each equation matches the one built in the rule
    keys = ["component", "item", "position", "event", "rule"]
    rule_allowables = df[(df["kind"] == "allowable") & (df["name"] == "allowable 1")]
    first_eq = df[(df["kind"] == "result") & (df["name"] == "allowable")]
    first_eq = first_eq.groupby(keys, sort=False).head(1)
    merged = rule_allowables.merge(first_eq, on=keys, suffixes=("_rule", "_eq"))
    assert not merged.empty
    np.testing.assert_allclose(merged["value_rule"], merged["value_eq"])


def test_run_paths_with_programmatic_config(tmpdir):
    """Test run_paths with programmatically created configurations."""
    loads = {
        name: LoadConfig(
            name=name,
            steps=[LoadTerm("+", "static", step)],
            stress_classification=StressClassification.PRIMARY,
            load_type=LoadType.VOLUMETRIC,
            unit="MPa",
            isPressure=True,
        )
        for name, step in (("Load1", 1), ("Load2", 2))
    }
    paths = {1: PathConfig(pnum=1, material="SS316L(N)-IG_SDC-IC")}
    reference_events = {
        1: [
            ReferenceEventConfig(
                service_lvl="A",
                re_ID="RE1",
                T=20.0,
                oc="Normal",
                ie="None",
                ce="None",
                load_ctg="A",
                loads=["Load1", "Load2"],
            )
        ]
    }

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
    config = Configuration(
        submodel="TestModel",
        code="SDC-IC",
        loads=loads,
        paths=paths,
        stress_tensors=stress_tensors_df.sort_index(),
        reference_events=reference_events,
    )

    # Setup temporary directory
    dest = Path(tmpdir, "paths_test")
    dest.mkdir()

    # Run the assessment with programmatic configurations
    run_paths(dest, {"TestModel": config}, fatigue=False, print_recap=False)
