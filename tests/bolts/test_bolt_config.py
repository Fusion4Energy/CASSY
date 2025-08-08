from importlib.resources import as_file, files

import pytest

from cassy.auxiliary.custom_errors import ConfigError
from cassy.bolts.bolt_config import FlangeAssessmentConfig
from tests.bolts import res


class TestFlangeAssessmentConfig:
    @pytest.fixture()
    def config(self) -> FlangeAssessmentConfig:
        # Test the from_excel method
        with as_file(files(res).joinpath("Flange1.xlsx")) as config_file:
            with as_file(files(res).joinpath("Flange1.csv")) as actions_file:
                config = FlangeAssessmentConfig.from_excel(
                    config_file, actions_file, fatigue=True
                )
        return config

    def test_from_excel(self, config: FlangeAssessmentConfig):
        assert config.REs_fatigue is not None and len(config.REs_fatigue) == 1
        assert len(config.bolts_spec) == 2
        assert config.REs["1"][0].primary == ("loads", "1")
        assert config.REs["1"][-1].all_loads == ("loads", "5-2")
        assert config.REs_fatigue["1"][0].delta_sigma == (
            ("loads", "2"),
            ("loads", "1"),
        )

    def test_get_actions(self, config: FlangeAssessmentConfig):
        actions = config.get_actions("1", "loads", "2")
        assert actions["My"] == 2

        actions = config.get_actions("1", "loads", "2- 1+5 ")
        assert actions["Fx"] == 15

        with pytest.raises(ConfigError):
            actions = config.get_actions("1", "loads", "6")
