import math
from importlib.resources import as_file, files

import numpy as np
import pandas as pd
import pytest

from cassy.additional_data import materials
from cassy.bolts.bolt_config import BoltReferenceEvent, BoltReferenceEventFatigue
from cassy.bolts.code_assessor import BoltActionAssessor
from cassy.bolts.geometry import BoltGeom
from cassy.designcodes.rccmrx_bolts_nl import RCCMRx_Bolts
from cassy.designcodes.sdcic_bolts import SDC_IC_Bolts
from cassy.general.material import Material
from tests.bolts import res


class TestBoltActionAssessor:
    @pytest.fixture
    def mat_list(self) -> dict[str, Material]:
        with as_file(
            files(materials).joinpath("Inconel 718 (non leak tight) SDC-IC.yaml")
        ) as mat_path:
            inconel = Material(mat_path)
        return {
            "SS660 (non leak-tight)": inconel,
            "Inconel 718 (non leak-tight)": inconel,
        }

    @pytest.fixture
    def bolt_geom(self, mat_list: dict[str, Material]) -> BoltGeom:
        with as_file(files(res).joinpath("M12_bolt.xlsx")) as test_data:
            # Create a BoltGeom instance from the test data
            bolt_geom = BoltGeom.from_excel(test_data, mat_list)
        return bolt_geom

    @pytest.fixture
    def bolt_assessor(self, bolt_geom: BoltGeom) -> BoltActionAssessor:
        event = BoltReferenceEvent(
            "dummy",
            "dummy",
            "dummy",
            "dummy",
            35,
            0,
            "III",
            "C",
            ("dummy", "1"),
            ("dummy", "1"),
        )
        preload = 1.42e4  # N
        actions = pd.Series(
            {
                "Fx": 0,
                "Fy": 0,
                "Fz": 10456.7730139521,
                "Mz": -0.1040330880136899,
                "Mx": -30.869778512423903,
                "My": -36.2913287438325,
            }
        )
        # Test the initialization of BoltActionAssessor
        assessor = BoltActionAssessor(
            "test", actions, actions, event, bolt_geom, preload
        )
        return assessor

    def test_convert_actions(self, bolt_assessor: BoltActionAssessor):
        # Test the convert_actions method
        for key, val in zip(["N", "T", "M"], [1.0456e4, 0, 4.76e1]):
            assert math.isclose(bolt_assessor.primary[key], val, rel_tol=1e-2)
        # TODO: test something where secondary actions are different from primary
        for key, val in zip(["N", "T", "M"], [1.0456e4, 0, 4.76e1]):
            assert math.isclose(bolt_assessor.all_loads[key], val, rel_tol=1e-2)
