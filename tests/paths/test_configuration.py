from importlib.resources import as_file, files

import pandas as pd
import pytest

from cassy.paths.paths_config import Configuration
from tests.paths import res


class TestConfiguration:
    @pytest.fixture
    def config_fixture(self) -> Configuration:
        with as_file(files(res).joinpath("submodel.xlsx")) as config_file:
            with as_file(files(res).joinpath("submodel_tensors.csv")) as tensors_file:
                config = Configuration("Model_A", config_file, tensors_file)
        return config

    def test_get_stress_tensor(self, config_fixture: Configuration):
        # Test the get_stress_tensor method
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

    def test_get_REloads(self, config_fixture: Configuration):
        # Test the get_REloads method
        re_loads = config_fixture.get_REloads(1, "NOS-II.1")
        assert len(re_loads) == 5
