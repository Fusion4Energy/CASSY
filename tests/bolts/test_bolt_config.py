from pathlib import Path

import pandas as pd
import pytest

from cassy.additional_data import materials as mat_folder
from cassy.auxiliary.custom_errors import ConfigError
from cassy.auxiliary.types import LoadTerm
from cassy.bolts.bolt_config import FlangeAssessmentConfig
from cassy.designcodes.map import BOLT_CODES
from cassy.general.material import Material
from cassy.gui.bolts_model import build_bolts_from_project
from tests.helpers import load_project

RES = Path(__file__).parent / "res"


def _t(sign: str, analysis: str, step: int) -> LoadTerm:
    return LoadTerm(sign, analysis, step)


@pytest.fixture
def mat_lib() -> dict[str, Material]:
    path = Path(mat_folder.__file__).parent / "Inconel 718 (non leak tight) SDC-IC.yaml"
    return {"SS660 (non leak-tight)": Material(path)}


class TestFlangeAssessmentConfig:
    @pytest.fixture()
    def config(self, mat_lib) -> FlangeAssessmentConfig:
        configs, _ = build_bolts_from_project(
            load_project(RES / "Flange1.json"), materials=mat_lib
        )
        return configs["Flange1"]

    def test_from_project(self, config: FlangeAssessmentConfig):
        assert config.REs_fatigue is not None and len(config.REs_fatigue) == 1
        assert len(config.bolts_spec) == 2
        assert config.REs["1"][0].primary == [_t("+", "loads", 1)]
        assert config.REs["1"][-1].all_loads == [
            _t("+", "loads", 5),
            _t("-", "loads", 2),
        ]
        assert config.REs_fatigue["1"][0].delta_sigma == (
            [_t("+", "loads", 2)],
            [_t("+", "loads", 1)],
        )

    def test_get_actions(self, config: FlangeAssessmentConfig):
        actions = config.get_actions("1", [_t("+", "loads", 2)])
        assert actions["My"] == 2

        terms = [_t("+", "loads", 2), _t("-", "loads", 1), _t("+", "loads", 5)]
        actions = config.get_actions("1", terms)
        assert actions["Fx"] == 15

        with pytest.raises(ConfigError):
            config.get_actions("1", [_t("+", "loads", 6)])
        with pytest.raises(ConfigError):
            config.get_actions("1", [])


def test_get_actions_across_analyses():
    actions = pd.DataFrame(
        {
            "boltID": ["1", "1", "1"],
            "analysis": ["X", "X", "Y"],
            "loadstep": [1, 2, 5],
            "Fx": [10.0, 20.0, 3.0],
            "Fy": [0.0, 0.0, 0.0],
            "Fz": [100.0, 200.0, 7.0],
            "Mx": [0.0, 0.0, 0.0],
            "My": [0.0, 0.0, 0.0],
            "Mz": [0.0, 0.0, 0.0],
        }
    ).set_index(["boltID", "analysis", "loadstep"])
    bolts_spec = pd.DataFrame(
        {"Geom type": ["bolt"], "Geom data": ["M12"], "Preload [N]": [0.0]},
        index=pd.Index(["1"], name="Bolt ID"),
    )
    config = FlangeAssessmentConfig(actions, BOLT_CODES["SDC-IC"], bolts_spec, REs={})

    combined = config.get_actions("1", [_t("+", "X", 1), _t("-", "Y", 5)])
    assert combined["Fx"] == 7.0
    assert combined["Fz"] == 93.0

    combined = config.get_actions("1", [_t("-", "Y", 5), _t("+", "X", 2)])
    assert combined["Fx"] == 17.0

    with pytest.raises(ConfigError):
        config.get_actions("1", [_t("+", "Y", 1)])


def test_non_numeric_actions_raise():
    actions = pd.DataFrame(
        {
            "boltID": ["1", "1"],
            "analysis": ["X", "X"],
            "loadstep": [1, 2],
            "Fx": ["10.0", "1,5"],
            "Fz": [100.0, 200.0],
        }
    ).set_index(["boltID", "analysis", "loadstep"])
    bolts_spec = pd.DataFrame(
        {"Geom type": ["bolt"], "Geom data": ["M12"], "Preload [N]": [0.0]},
        index=pd.Index(["1"], name="Bolt ID"),
    )
    with pytest.raises(ConfigError, match="'1,5' at bolt 1, analysis 'X'"):
        FlangeAssessmentConfig(actions, BOLT_CODES["SDC-IC"], bolts_spec, REs={})


def test_extra_actions_columns_are_ignored(tmp_path, mat_lib):
    df = pd.read_csv(RES / "Flange1.csv")
    df["comment"] = "some text"
    csv_file = tmp_path / "Flange1.csv"
    df.to_csv(csv_file, index=False)
    project = load_project(RES / "Flange1.json")
    project["flanges"][0]["actions_file"] = str(csv_file)

    configs, _ = build_bolts_from_project(project, materials=mat_lib)
    assert "comment" not in configs["Flange1"].actions.columns

    df.drop(columns="Mz").to_csv(csv_file, index=False)
    project["flanges"][0]["actions_file"] = str(csv_file)
    with pytest.raises(ValueError, match="missing columns"):
        build_bolts_from_project(project, materials=mat_lib)
