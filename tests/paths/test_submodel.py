from importlib.resources import as_file, files

import pytest

from cassy.additional_data import materials, templates
from cassy.auxiliary.constants import EXCEL_AVAILABLE
from cassy.designcodes.rccmrx import RCC_MRx
from cassy.general.configuration import Configuration
from cassy.general.material import Material
from cassy.paths.submodel import Submodel
from tests.paths import res

if EXCEL_AVAILABLE:
    import xlwings as xw

# Add path to material files
RES = files(materials)


class TestSubmodel:
    @pytest.fixture
    def submodel(self) -> Submodel:
        with as_file(files(res).joinpath("submodel.xlsx")) as file:
            with as_file(files(res).joinpath("submodel_tensors.csv")) as tensors_file:
                config = Configuration("Model_A", file, tensors_file)
        with as_file(RES.joinpath("SS316L(N)-IG.xlsx")) as mat_path:
            steel = Material(mat_path)

        submodel = Submodel("Model", config, {"SS316L(N)-IG": steel})
        return submodel

    def test_build_linearized_stress(self, submodel: Submodel):
        # Test the build_linearized_stress method
        linstress = submodel._build_linearized_stress("ThermalNO", 1, "begin")

    def test_assess(self, submodel: Submodel):
        # Test the build_RE method
        submodel.build_REs(fatigue=True)
        code = RCC_MRx()
        submodel.assess(code, fatigue=True)

    @pytest.mark.skipif(
        not EXCEL_AVAILABLE,
        reason="Excel is not installed, skipping test.",
    )
    def test_print_assessment(self, submodel: Submodel, tmpdir):
        # Test the print_assessment method
        submodel.build_REs(fatigue=True)
        code = RCC_MRx()
        submodel.assess(code, fatigue=True)
        images_folder = tmpdir.join("Images")
        with xw.App(visible=False) as app:
            with as_file(files(templates).joinpath("template.xlsx")) as template_path:
                submodel.print_assessment(
                    tmpdir,
                    app,
                    template_path,
                    img_folder=images_folder,
                    fatigue=True,
                )
