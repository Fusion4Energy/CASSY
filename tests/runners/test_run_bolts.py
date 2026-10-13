import os
from importlib.resources import as_file, files
from pathlib import Path

from cassy.additional_data import materials as mat_folder
from cassy.auxiliary.types import LoadTerm
from cassy.gui.bolts_model import build_bolts_from_project
from cassy.runners.run_bolts import run_bolts
from cassy.bolts.bolt_config import FlangeAssessmentConfig
from cassy.bolts.geometry import BoltGeom, InsertGeom
from cassy.general.material import Material
from tests.helpers import load_project

RES = Path(__file__).parent / "bolts"


def _project_configs() -> tuple[dict, dict]:
    configs, geoms = {}, {}
    for name in ("Flange1", "Flange2"):
        project = load_project(RES / f"{name}.json")
        project["run_options"]["matlib_path"] = str(RES / "additional_materials")
        c, g = build_bolts_from_project(project)
        configs.update(c)
        geoms.update(g)
    return configs, geoms


def test_run_bolts(tmp_path):
    configs, geoms = _project_configs()
    run_bolts(tmp_path, configs, geoms, fatigue=True)
    # check that the recap has been produced
    assert os.path.exists(Path(tmp_path, "Recap.docx"))


def test_run_bolts_no_recap_no_merge_only_bolts(tmp_path):
    configs, geoms = _project_configs()
    run_bolts(
        tmp_path,
        configs,
        geoms,
        fatigue=True,
        print_recap=False,
        merge=False,
        only_bolts=True,
    )
    assert not os.path.exists(Path(tmp_path, "Recap.docx"))


def test_run_bolts_with_geoms_and_configs(tmpdir):
    """Test run_bolts with programmatically created geometries and configurations."""
    import pandas as pd
    from cassy.bolts.bolt_config import BoltReferenceEvent, BoltReferenceEventFatigue
    from cassy.designcodes.map import BOLT_CODES

    # Load a real material from the defaults
    with as_file(
        files(mat_folder).joinpath("Inconel 718 (non leak tight) SDC-IC.yaml")
    ) as path:
        test_material = Material(path)

    # Create a bolt geometry
    bolt_geom = BoltGeom(
        name="M12_bolt",
        material=test_material,
        p=1.75,  # thread pitch
        d=12,  # nominal diameter
        Le=20,  # insertion length
        d_vh=0,  # venting hole diameter
    )

    # Create an insert geometry
    insert_geom = InsertGeom(
        name="M12_insert",
        material=test_material,
        p=1.75,
        d=12,
        Le=25,
        d_vh=0,
    )

    # Create geometries dictionary with proper naming convention
    geoms = {
        "M12_bolt": bolt_geom,
        "M12_insert": insert_geom,
    }

    # Create actions DataFrame
    actions_data = {
        "boltID": ["1", "1", "1", "2", "2", "2"],
        "analysis": ["loads", "loads", "loads", "loads", "loads", "loads"],
        "loadstep": [1, 2, 3, 1, 2, 3],  # Use integers, not strings
        "Fx": [10, 11, 12, 10, 11, 12],
        "Fy": [10, 11, 12, 10, 11, 12],
        "Fz": [1e5, 1.2e5, 1.3e5, 1e5, 1.2e5, 1.3e5],
        "Mz": [10, 20, 30, 10, 20, 30],
        "Mx": [-10, -20, 30, -10, -20, 30],
        "My": [1, 2, 3, 1, 2, 3],
    }
    actions_df = pd.DataFrame(actions_data)
    actions_df.set_index(["boltID", "analysis", "loadstep"], inplace=True)

    # Create bolts specification DataFrame
    bolts_spec_data = {
        "Bolt ID": ["1", "2"],
        "Geom data": ["M12", "M12"],
        "Geom type": ["bolt", "insert"],
        "Preload [N]": [50000, 45000],
    }
    bolts_spec_df = pd.DataFrame(bolts_spec_data)
    bolts_spec_df.set_index("Bolt ID", inplace=True)

    # Create Reference Events
    REs = {
        bolt_id: [
            BoltReferenceEvent(
                name="RE1",
                oper_cond="Normal",
                init_event="None",
                concat_event="None",
                temp=20.0,
                dpa=0.0,
                load_category="I",
                service_lvl="A",
                primary=[LoadTerm("+", "loads", 1)],
                all_loads=[LoadTerm("+", "loads", 2)],
            )
        ]
        for bolt_id in ("1", "2")
    }

    # Create Fatigue Reference Events
    REs_fatigue = {
        bolt_id: [
            BoltReferenceEventFatigue(
                name="FRE1",
                oper_cond="Normal",
                init_event="None",
                concat_event="None",
                temp=20.0,
                dpa=0.0,
                load_category="I",
                service_lvl="A",
                n_cycles=1000,
                delta_sigma=(
                    [LoadTerm("+", "loads", 2)],
                    [LoadTerm("+", "loads", 1)],
                ),
                sigma_sustained=[LoadTerm("+", "loads", 1)],
            )
        ]
        for bolt_id in ("1", "2")
    }

    # Get the design code
    code = BOLT_CODES["SDC-IC"]

    # Create FlangeAssessmentConfig
    config = FlangeAssessmentConfig(
        actions=actions_df,
        code=code,
        bolts_spec=bolts_spec_df,
        REs=REs,
        REs_fatigue=REs_fatigue,
        name="TestFlange",
    )

    # Setup temporary directory
    dest = Path(tmpdir, "bolts_test")
    dest.mkdir()

    # Run the assessment with programmatic geometries and configurations
    run_bolts(
        dest,
        {"TestFlange": config},
        geoms,
        fatigue=True,
        print_recap=False,
    )
