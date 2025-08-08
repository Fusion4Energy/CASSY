from importlib.resources import as_file, files

import pytest

from cassy.additional_data import materials
from cassy.designcodes.codes import Code
from cassy.designcodes.rccmr import RCC_MR
from cassy.designcodes.rccmrx import RCC_MRx
from cassy.designcodes.sdcic import SDC_IC
from cassy.general.configuration import Configuration
from cassy.general.material import Material
from cassy.paths.submodel import Submodel
from tests.paths import res

# Add path to material files
RES = files(materials)


class TestSubmodel:
    @pytest.fixture
    def submodel(self) -> Submodel:
        with as_file(files(res).joinpath("submodel.xlsx")) as file:
            with as_file(files(res).joinpath("submodel_tensors.csv")) as tensors_file:
                config = Configuration("Model_A", file, tensors_file)
        with as_file(RES.joinpath("SS316L(N)-IG_SDC-IC.yaml")) as mat_path:
            steel = Material(mat_path)

        submodel = Submodel("Model", config, {"SS316L(N)-IG": steel})
        return submodel

    def test_build_linearized_stress(self, submodel: Submodel):
        # Test the build_linearized_stress method
        linstress = submodel._build_linearized_stress("ThermalNO", 1, "begin")

    @pytest.mark.parametrize("code", [RCC_MRx(), RCC_MR(), SDC_IC()])
    def test_assess(self, submodel: Submodel, code: Code):
        # Test the build_RE method
        submodel.build_REs(fatigue=True)
        submodel.assess(code, fatigue=True)

    def test_get_recap(self, submodel: Submodel):
        # Test the get_recap method
        submodel.build_REs(fatigue=True)
        submodel.assess(RCC_MRx(), fatigue=True)
        recap = submodel.get_recap()
        assert isinstance(recap, dict)
        assert pytest.approx(recap["Immediate"][0]["Safety Margin"]) == 4.49
