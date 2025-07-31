from importlib.resources import as_file, files

import pytest

from cassy.additional_data import materials
from cassy.bolts.bolt_assess import FlangeAssessment
from cassy.bolts.bolt_config import FlangeAssessmentConfig
from cassy.bolts.geometry import BoltGeom, BoltLikeGeom, InsertGeom
from cassy.designcodes.rccmrx_bolts_nl import RCCMRx_Bolts
from cassy.designcodes.sdcic_bolts import SDC_IC_Bolts
from cassy.general.material import Material
from tests.bolts import res


class TestFlangeAssessment:
    @pytest.fixture
    def geometries(self):
        with as_file(
            files(materials).joinpath("Inconel 718 (non leak tight) SDC-IC.yaml")
        ) as mat_path:
            material = Material(mat_path)
        mat_lib = {"SS660 (non leak-tight)": material}

        with as_file(files(res).joinpath("M12_bolt.xlsx")) as path:
            bolt_geom = BoltGeom.from_excel(path, mat_lib)

        with as_file(files(res).joinpath("M12_insert.xlsx")) as path:
            insert_geom = InsertGeom.from_excel(path, mat_lib)

        return {"M12_bolt": bolt_geom, "M12_insert": insert_geom}

    @pytest.fixture
    def flange_assessment(
        self, geometries: dict[str, BoltLikeGeom]
    ) -> FlangeAssessment:
        # Test the from_excel method
        with as_file(files(res).joinpath("Flange1.xlsx")) as config_file:
            with as_file(files(res).joinpath("Flange1.csv")) as actions_file:
                config = FlangeAssessmentConfig.from_excel(
                    config_file, actions_file, fatigue=True
                )
        return FlangeAssessment(geometries, config, fatigue=True)

    def test_init(self, flange_assessment: FlangeAssessment):
        assert isinstance(flange_assessment, FlangeAssessment)
        assert (
            len(flange_assessment.bolts_assessments)
            == len(flange_assessment.insert_assessments)
            == 1
        )
        assert (
            flange_assessment.bolts_assessments[1]["Lift"].applicable_stresses[
                "primary"
            ]["Max stress"]
            > 0
        )
        actions = flange_assessment.bolts_assessments[1]["Lift"].primary
        assert actions["N"] == 4

    @pytest.mark.parametrize("code", [SDC_IC_Bolts(), RCCMRx_Bolts()])
    def test_assess(self, flange_assessment: FlangeAssessment, code):
        # Check that the assessments can run without errors
        flange_assessment.config.code = code
        assessments = flange_assessment.assess()
        assessments = flange_assessment.assess(insert=True)
