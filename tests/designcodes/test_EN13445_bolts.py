from cassy.designcodes.EN13445_bolts import EN_13445_Bolts
import pytest
from importlib.resources import files, as_file

from cassy.general.material import Material
from cassy.additional_data import materials as mat_folder


@pytest.fixture
def material():
    with as_file(
        files(mat_folder).joinpath("Inconel 718 (non leak tight) SDC-IC.yaml")
    ) as path:
        return Material(path)


class TestEN13445Bolts:
    def test_computeVj(self, material: Material):
        # Create a mock BoltActionAssessor and Material
        class MockBoltActionAssessor:
            def __init__(self):
                self.ref_event = type("Event", (), {"temp": 150, "dpa": 0})()
                self.applicable_stresses = {"all": {"Stress intensity range": 543}}
                self.poa = type("POA", (), {"d": 30})()  # diameter in mm

        bolt_action = MockBoltActionAssessor()

        en13445_bolts = EN_13445_Bolts()
        result = en13445_bolts.computeVj(bolt_action, material)
        assert result["fb"] < 1
        assert pytest.approx(result["N"], rel=1e-2) == 823
