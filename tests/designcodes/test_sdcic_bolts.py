import json
from importlib.resources import as_file, files
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cassy.additional_data import materials as mat_folder
from cassy.auxiliary.custom_errors import MissingPropertyError
from cassy.auxiliary.types import LoadTerm
from cassy.bolts.bolt_config import BoltReferenceEvent, BoltReferenceEventFatigue
from cassy.bolts.code_assessor import BoltActionAssessor
from cassy.bolts.geometry import BoltGeom
from cassy.designcodes.codes import INVALID_VJ
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
from cassy.gui.bolts_model import build_geometries
from tests.designcodes import res

RES = files(res)


def _bolt_geom(material: Material) -> BoltGeom:
    entries = json.loads(
        (Path(res.__file__).parent / "M12_bolt.json").read_text(encoding="utf-8")
    )
    return build_geometries(entries, {"Inconel 718 (non leak-tight)": material})[
        "M12_bolt"
    ]


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
    bolt_geom = _bolt_geom(material)

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
        "test",
        "op",
        "init",
        "concat",
        133,
        2.5,
        "II",
        "A",
        [LoadTerm("+", "1", 1)],
        [LoadTerm("+", "2", 2)],
    )
    return BoltActionAssessor("test", primary, secondary, ref_event, bolt_geom, 1.5e4)


@pytest.fixture
def assessor_fatigue(material):
    return _fatigue_assessor(material)


def _fatigue_assessor(material: Material, scale: float = 1) -> BoltActionAssessor:
    """Fatigue assessor; scale multiplies the delta (secondary) actions."""
    bolt_geom = _bolt_geom(material)

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
    secondary = secondary * scale
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
        ([LoadTerm("+", "1", 1)], [LoadTerm("+", "1", 1)]),
        [LoadTerm("+", "2", 2)],
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
        # Sd_nopeak is not available for the material
        rule = IC6122_1_2()
        with pytest.raises(MissingPropertyError):
            rule.assess(assessor, material)

    def test_missing_property_invalidates_rule(
        self, code: SDC_IC_Bolts, assessor: BoltActionAssessor
    ):
        # a missing material property invalidates the rule, which fails, while
        # the others are still assessed
        df = assessor.assess(code)
        invalid = df[df["Rule ID"] == "IC 6122.1.2"]
        assert len(invalid) == 2
        assert (invalid["Result"] == "FAILED").all()
        assert invalid["Note"].str.contains("Sd_nopeak").all()
        assert df["Note"].isna().any()

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

    def test_computeVj_sigma_pre(
        self,
        code: SDC_IC_Bolts,
        assessor_fatigue: BoltActionAssessor,
        material: Material,
    ):
        # sigma pre is the axial stress of the sustained tensor only: it must
        # not depend on the delta actions nor sum the range stress to itself
        sustained = assessor_fatigue.applicable_stresses["primary"]["Primary stress"]
        delta = assessor_fatigue.applicable_stresses["all"]["Primary stress"]
        assert sustained != pytest.approx(delta, rel=1e-2)
        result = code.computeVj(assessor_fatigue, material)
        assert result["sigma pre"] == pytest.approx(sustained)

    def test_computeVj_neuber(self, code: SDC_IC_Bolts, assessor_fatigue):
        # a material with a cyclic stress-strain curve goes through the Neuber branch
        with as_file(
            files(mat_folder).joinpath("SS316L(N)-IG_SDC-IC.yaml")
        ) as path:
            ss316 = Material(path)
        result = code.computeVj(assessor_fatigue, ss316)
        assert result["N"] > 0
        assert "epsilon plasticity" not in result
        assert result["sigma plasticity"] > 0

    def test_out_of_bounds_invalidates_rule(
        self, code: SDC_IC_Bolts, assessor: BoltActionAssessor
    ):
        # above the material bounds: the rules needing the material are invalidated
        # and fail, the others are still assessed
        assessor.ref_event.temp = 2000
        df = assessor.assess(code)
        invalid = df[df["Note"].notna()]
        assert len(invalid) > 0
        assert (invalid["Result"] == "FAILED").all()
        assert (invalid["Safety Margin"] == 0).all()
        assert (invalid["Applied [MPa]"] == "-").all()
        assert invalid["Note"].str.startswith("invalidated:").all()
        assert df["Note"].isna().any()

    def test_out_of_bounds_invalidates_fatigue(
        self, code: SDC_IC_Bolts, assessor_fatigue: BoltActionAssessor
    ):
        assessor_fatigue.ref_event.temp = 2000
        result = assessor_fatigue.computeVj(code)
        assert result["Vj"] == INVALID_VJ
        assert np.isnan(result["N"])
        assert result["Note"].startswith("invalidated:")

    def test_above_fatigue_curve_invalidates_fatigue(
        self, code: SDC_IC_Bolts, material: Material
    ):
        # a stress amplitude above the fatigue curve must fail the event, not
        # return a NaN usage fraction that would be skipped in the total
        result = _fatigue_assessor(material, scale=200).computeVj(code)
        assert result["Vj"] == INVALID_VJ
        assert "above the fatigue curve" in result["Note"]

    def test_nan_N_invalidates_fatigue(
        self, code: SDC_IC_Bolts, assessor_fatigue: BoltActionAssessor, monkeypatch
    ):
        monkeypatch.setattr(code, "computeVj", lambda *args: {"N": np.nan})
        result = assessor_fatigue.computeVj(code)
        assert result["Vj"] == INVALID_VJ
