from importlib.resources import as_file, files

import numpy as np
import pandas as pd
import pytest

from cassy.additional_data import materials as mat_folder
from cassy.bolts.bolt_config import BoltReferenceEvent, BoltReferenceEventFatigue
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
            "Fx": -213,
            "Fy": 56,
            "Fz": 274,
            "Mx": -0.562,
            "My": -2.312,
            "Mz": 0.187,
        }
    )
    secondary = pd.Series(
        {
            "Fx": -394.31,
            "Fy": 225.18,
            "Fz": 17703,
            "Mx": -2.637,
            "My": -2.44,
            "Mz": 0.913,
        }
    )
    ref_event = BoltReferenceEvent(
        "test", "op", "init", "concat", 133, 2.5, "II", "A", ("1", "1"), ("2", "2")
    )
    return BoltActionAssessor("test", primary, secondary, ref_event, bolt_geom, 1.5e4)


@pytest.fixture
def assessor_fatigue(material):
    materials = {"Inconel 718 (non leak-tight)": material}
    with as_file(files(res).joinpath("M12_bolt.xlsx")) as path:
        bolt_geom = BoltGeom.from_excel(path, materials)

    primary = pd.Series(
        {
            "Fx": 1402.2,
            "Fy": 421.82,
            "Fz": 25762,
            "Mx": -1014.4,
            "My": 2280.3,
            "Mz": -8829,
        }
    )
    secondary = pd.Series(
        {
            "Fx": -73.6,
            "Fy": -1376.93,
            "Fz": -1384 * 4,
            "Mx": 1.42659,
            "My": -0.572,
            "Mz": 0.9629,
        }
    )
    ref_event = BoltReferenceEventFatigue(
        "test",
        "op",
        "init",
        "concat",
        240,
        0,
        "II",
        "A",
        30000,
        [("1", "1"), ("1", "1")],
        ("2", "2"),
    )
    return BoltActionAssessor("test", primary, secondary, ref_event, bolt_geom, 2.0e4)


class TestSDC_IC_Bolts:
    def test_starting_actions(self, assessor: BoltActionAssessor):
        primary = {"N": 274, "T": 220, "M": 2.379}
        secondary = {"N": 17703, "T": 454, "M": 3.593}
        for key in ["N", "M", "T"]:
            assert pytest.approx(assessor.primary[key], rel=1e-2) == primary[key]
            assert pytest.approx(assessor.all_loads[key], rel=1e-2) == secondary[key]

    def test_6113(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6113()
        assessed = rule.assess(assessor, material)

    def test_6121_1_3_1(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_1()
        assessed = rule.assess(assessor, material)
        for i, expected in enumerate([(6.36, 387e6), (240.43, 701e6)]):
            assert pytest.approx(assessed[i], rel=1e-2) == expected

    def test_6121_1_3_2(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_2()
        assessed = rule.assess(assessor, material)
        for i, expected in enumerate([(29.5, 581e6), (357.9, 941e6)]):
            assert pytest.approx(assessed[i], rel=1e-2) == expected

    def test_6121_1_3_3(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_3()
        assessed = rule.assess(assessor, material)
        for i, expected in enumerate(
            [(3, 232e6), (1.79, 232e6), (110, 499e6), (92.3, 499e6)]
        ):
            assert pytest.approx(assessed[i], rel=1e-2) == expected

    def test_6121_1_3_4(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_4()
        assessed = rule.assess(assessor, material)
        for i, expected in enumerate([(81.2, 2245e6), (77.1, 2245e6)]):
            assert pytest.approx(assessed[i], rel=1e-2) == expected

    def test_6122_1_1(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6122_1_1()
        assessed = rule.assess(assessor, material)
        assert pytest.approx(assessed[0][0], rel=1e-2) == 240
        assert np.isnan(assessed[0][1])

    def test_6122_1_2(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6122_1_2()
        assessed = rule.assess(assessor, material)
        assert pytest.approx(assessed[0][0], rel=1e-2) == 357
        assert np.isnan(assessed[0][1])
        assert pytest.approx(assessed[1][0], rel=1e-2) == 1431
        assert np.isnan(assessed[1][1])

    def test_computeVj(
        self,
        code: SDC_IC_Bolts,
        assessor_fatigue: BoltActionAssessor,
        material: Material,
    ):
        result = code.computeVj(assessor_fatigue, material)
        assert (
            pytest.approx(
                assessor_fatigue.applicable_stresses["all"]["Stress intensity range"],
                rel=1e-2,
            )
            == 97.33
        )
        assert (
            pytest.approx(
                assessor_fatigue.applicable_stresses["all"]["Primary stress"], rel=1e-2
            )
            == 75
        )
        assert pytest.approx(result["N"], rel=1e-2) == 3123333
