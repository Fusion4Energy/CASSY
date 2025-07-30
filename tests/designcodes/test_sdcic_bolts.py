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
        primary = {"N": 3.39e1, "T": 2.36e1, "M": 3.09e-3}
        secondary = {"N": 1.15e4, "T": 2.60e2, "M": 1.2}
        for key in ["N", "M", "T"]:
            assert pytest.approx(assessor.primary[key], rel=1e-2) == primary[key]
            assert pytest.approx(assessor.all_loads[key], rel=1e-2) == secondary[key]

    def test_6113(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6113()
        assessed = rule.assess(assessor, material)

    def test_6121_1_3_1(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_1()
        assessed = rule.assess(assessor, material)
        for i, expected in enumerate([(0.7, 425e6), (413, 797e6)]):
            assert pytest.approx(assessed[i], rel=1e-2) == expected

    def test_6121_1_3_2(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_2()
        assessed = rule.assess(assessor, material)
        for i, expected in enumerate([(0.71, 637e6), (516, 1071e6)]):
            assert pytest.approx(assessed[i], rel=1e-2) == expected

    def test_6121_1_3_3(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_3()
        assessed = rule.assess(assessor, material)
        for i, expected in enumerate(
            [(0.208, 255e6), (0.128, 255e6), (192, 568e6), (96, 568e6)]
        ):
            assert pytest.approx(assessed[i], rel=1e-2) == expected

    def test_6121_1_3_4(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6121_1_3_4()
        assessed = rule.assess(assessor, material)
        for i, expected in enumerate([(41, 2560e6), (129, 2560e6)]):
            assert pytest.approx(assessed[i], rel=1e-2) == expected

    def test_6122_1_1(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6122_1_1()
        assessed = rule.assess(assessor, material)
        assert pytest.approx(assessed[0][0], rel=1e-2) == 413
        assert np.isnan(assessed[0][1])

    def test_6122_1_2(self, assessor: BoltActionAssessor, material: Material):
        rule = IC6122_1_2()
        assessed = rule.assess(assessor, material)
        assert pytest.approx(assessed[0][0], rel=1e-2) == 516
        assert np.isnan(assessed[0][1])
        assert pytest.approx(assessed[1][0], rel=1e-2) == 2065
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
            == 94.33
        )
        assert (
            pytest.approx(
                assessor_fatigue.applicable_stresses["all"]["Primary stress"], rel=1e-2
            )
            == 452
        )
        assert pytest.approx(result["N"], rel=1e-2) == 120710
