from pathlib import Path

import pandas as pd
import pytest

from cassy.auxiliary.custom_errors import TensorInputError
from cassy.auxiliary.types import LoadTerm
from cassy.gui.paths_model import build_configs_from_project
from cassy.paths.paths_config import Configuration, LoadConfig, LoadType
from cassy.paths.paths_config import StressClassification
from tests.helpers import load_project

RES = Path(__file__).parent / "res"


def _config(name: str) -> Configuration:
    return build_configs_from_project(load_project(RES / name))["Model_A"]


class TestConfiguration:
    @pytest.fixture
    def config_fixture(self) -> Configuration:
        return _config("submodel.json")

    def test_get_stress_tensor(self, config_fixture: Configuration):
        stress_tensor = config_fixture.get_stress_tensor("SustainedLoads", 1, "begin")
        assert isinstance(stress_tensor, pd.DataFrame)
        assert stress_tensor.shape == (3, 6)

        stress_tensor = config_fixture.get_stress_tensor("combination", 1, "begin")
        assert isinstance(stress_tensor, pd.DataFrame)
        assert stress_tensor.shape == (3, 6)
        # assert all values are zero
        assert (stress_tensor == 0).all().all()

        with pytest.raises(ValueError):
            config_fixture.get_stress_tensor("SustainedLoads", 1, "begi")

    def test_reference_event_loads(self, config_fixture: Configuration):
        re = next(
            r for r in config_fixture.reference_events[1] if r.re_ID == "NOS-II.1"
        )
        assert len(re.loads) == 5

    def test_get_stress_tensor_launcher(self):
        config = _config("launcher_bug/EC_UL.json")
        stress_tensor = config.get_stress_tensor("SustainedLoads", 1, "begin")
        assert isinstance(stress_tensor, pd.DataFrame)
        assert stress_tensor.shape == (3, 6)


class TestCrossAnalysisCombination:
    @pytest.fixture
    def setup(self) -> tuple[Configuration, str]:
        config = _config("submodel.json")
        analysis = config.stress_tensors.index.get_level_values("analysis")[0]
        # duplicate one analysis under a new name with doubled stresses
        other = config.stress_tensors.xs(analysis, level="analysis", drop_level=False)
        other = other.rename(index={analysis: "Other"}, level="analysis") * 2
        config.stress_tensors = pd.concat([config.stress_tensors, other]).sort_index()
        return config, analysis

    @staticmethod
    def _add_load(config: Configuration, name: str, steps: list[LoadTerm]):
        config.loads[name] = LoadConfig(
            name=name,
            steps=steps,
            stress_classification=StressClassification.PRIMARY,
            load_type=LoadType.VOLUMETRIC,
        )

    def test_terms_from_different_analyses(self, setup):
        config, ana = setup
        self._add_load(config, "single", [LoadTerm("+", ana, 1)])
        self._add_load(
            config, "cross", [LoadTerm("+", "Other", 1), LoadTerm("-", ana, 1)]
        )
        single = config.get_stress_tensor("single", 1, "begin")
        cross = config.get_stress_tensor("cross", 1, "begin")
        pd.testing.assert_frame_equal(cross, single)

    def test_leading_minus(self, setup):
        config, ana = setup
        self._add_load(config, "single", [LoadTerm("+", ana, 1)])
        self._add_load(config, "negated", [LoadTerm("-", ana, 1)])
        single = config.get_stress_tensor("single", 1, "begin")
        negated = config.get_stress_tensor("negated", 1, "begin")
        pd.testing.assert_frame_equal(negated, -single)

    def test_missing_step(self, setup):
        config, _ = setup
        self._add_load(config, "missing", [LoadTerm("+", "Other", 999)])
        with pytest.raises(TensorInputError):
            config.get_stress_tensor("missing", 1, "begin")
