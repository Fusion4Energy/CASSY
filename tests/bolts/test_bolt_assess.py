from pathlib import Path

import pytest

from cassy.additional_data import materials
from cassy.bolts.bolt_assess import FlangeAssessment
from cassy.designcodes.rccmrx_bolts_nl import RCCMRx_Bolts
from cassy.designcodes.EN13445_bolts import EN_13445_Bolts
from cassy.designcodes.sdcic_bolts import SDC_IC_Bolts
from cassy.general.material import Material
from cassy.gui.bolts_model import build_bolts_from_project
from tests.helpers import load_project

RES = Path(__file__).parent / "res"


@pytest.fixture
def flange_assessment() -> FlangeAssessment:
    mat_path = (
        Path(materials.__file__).parent / "Inconel 718 (non leak tight) SDC-IC.yaml"
    )
    mat_lib = {"SS660 (non leak-tight)": Material(mat_path)}
    configs, geometries = build_bolts_from_project(
        load_project(RES / "Flange1.json"), materials=mat_lib
    )
    return FlangeAssessment(geometries, configs["Flange1"], fatigue=True)


class TestFlangeAssessment:
    def test_init(self, flange_assessment: FlangeAssessment):
        assert isinstance(flange_assessment, FlangeAssessment)
        assert (
            len(flange_assessment.bolts_assessments)
            == len(flange_assessment.insert_assessments)
            == 1
        )
        assert (
            flange_assessment.bolts_assessments["1"]["Lift"].applicable_stresses[
                "primary"
            ]["Max stress"]
            > 0
        )
        actions = flange_assessment.bolts_assessments["1"]["Lift"].primary
        assert actions["N"] == 4

    @pytest.mark.parametrize(
        "code",
        [
            SDC_IC_Bolts(),
            RCCMRx_Bolts(),
            EN_13445_Bolts(),
        ],
    )
    def test_assess(self, flange_assessment: FlangeAssessment, code, tmp_path):
        # Check that the assessments can run without errors
        flange_assessment.config.code = code
        assessments = flange_assessment.assess()
        assessments = flange_assessment.assess(insert=True)
        flange_assessment.print_global_df(tmp_path)
        flange_assessment.get_recap(fatigue=True)
