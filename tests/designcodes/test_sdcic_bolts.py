from importlib.resources import as_file, files

import pandas as pd
import pytest

from cassy.additional_data import materials as mat_folder
from cassy.bolts.bolt_config import BoltReferenceEvent
from cassy.bolts.code_assessor import BoltActionAssessor
from cassy.bolts.geometry import BoltGeom
from cassy.designcodes.sdcic_bolts import (
    IC6113,
    IC6121_1_3_1,
    IC6121_1_3_2,
    IC6121_1_3_3,
    IC6121_1_3_4,
    IC6122_1_1,
    IC6122_1_2,
    SDC_IC_Bolts,
)
from cassy.general.material import Material
from tests.designcodes import res

RES = files(res)


@pytest.fixture
def code():
    return SDC_IC_Bolts()


@pytest.fixture
def material():
    with as_file(
        files(mat_folder).joinpath("Inconel 718 (non leak tight) SDC-IC.yaml")
    ) as path:
        return Material(path)


@pytest.fixture
def assessor(material):
    materials = {"Inconel 718 (non leak-tight)": material}
    with as_file(files(res).joinpath("M12_bolt.xlsx")) as path:
        bolt_geom = BoltGeom.from_excel(path, materials)

    primary = pd.Series(
        {
            "Fx": -23.5,
            "Fy": 1.31,
            "Fz": 33.85,
            "Mx": 0.00296,
            "My": -0.000884,
            "Mz": 0.00767,
        }
    )
    secondary = pd.Series(
        {"Fx": -254, "Fy": 56, "Fz": -31541, "Mx": -1.08, "My": 0.53, "Mz": -0.165}
    )
    ref_event = BoltReferenceEvent(
        "test", "op", "init", "concat", 240, 0, "II", "A", ("1", "1"), ("2", "2")
    )
    return BoltActionAssessor("test", primary, secondary, ref_event, bolt_geom, 2.0e4)


class TestSDC_IC_Bolts:
    def test_starting_actions(self, assessor: BoltActionAssessor):
        primary = {"N": 3.39e1, "T": 2.36e1, "M": 3.09e-3}
        secondary = {"N": 1.15e4, "T": 2.60e2, "M": 1.2e2}
        for key in ["N", "M", "T"]:
            assert pytest.approx(assessor.primary[key], rel=1e-2) == primary[key]

    def test_6113(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6113()
        assessed = rule.assess(assessor, material)
        assert False

    def test_6121_1_3_1(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_1()
        assessed = rule.assess(assessor, material)
        assert isinstance(assessed, list)
        assert len(assessed) == 2
        for stress, allowable in assessed:
            assert allowable is not None

    def test_6121_1_3_2(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_2()
        assessed = rule.assess(assessor, material)
        assert isinstance(assessed, list)
        assert len(assessed) == 2
        for stress, allowable in assessed:
            assert allowable is not None

    def test_6121_1_3_3(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_3()
        assessed = rule.assess(assessor, material)
        assert isinstance(assessed, list)
        assert len(assessed) == 4
        for stress, allowable in assessed:
            assert allowable is not None

    def test_6121_1_3_4(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_4()
        assessed = rule.assess(assessor, material)
        assert isinstance(assessed, list)
        assert len(assessed) == 2
        for stress, allowable in assessed:
            assert allowable is not None

    def test_6122_1_1(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6122_1_1()
        assessed = rule.assess(assessor, material)
        assert isinstance(assessed, list)
        assert len(assessed) == 1
        for stress, allowable in assessed:
            assert allowable is not None

    def test_6122_1_2(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6122_1_2()
        assessed = rule.assess(assessor, material)
        assert isinstance(assessed, list)
        assert len(assessed) == 2
        for stress, allowable in assessed:
            assert allowable is not None

    def test_computeVj(
        self, code: SDC_IC_Bolts, assessor: BoltActionAssessor, material: Material
    ):
        result = code.computeVj(assessor, material)
        assert isinstance(result, dict)
        keys = [
            "sigma bar",
            "epsilon bar",
            "N",
            "Rule ID",
            "epsilon plasticity",
            "sigma plasticity",
            "sigma pre",
            "epsilon N",
            "sigma N",
        ]
        for key in keys:
            assert key in result
