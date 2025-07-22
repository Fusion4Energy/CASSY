from importlib.resources import as_file, files

import pytest

from cassy.auxiliary.custom_errors import OutOfBoundsError
from cassy.general.new_material import Material
from tests.general import res


class TestMaterial:
    def test_init(self):
        with as_file(files(res).joinpath("material_example.yaml")) as config_file:
            material = Material(config_file)

        assert material.nu() == 0.3
        assert material.E(500, 100) == 159260000000.0
        assert material.K(500) == 722
        with pytest.raises(OutOfBoundsError):
            material.m(0)
        assert material.Keps(575, 950e6) == 1.6
        with pytest.raises(OutOfBoundsError):
            material.Kmu(0, 120e6)
        assert material.Keff_rec(250, 2.75) == 1.48
        assert pytest.approx(material.N(450, (0.488 + 0.412) / 2 / 100)) == 3e3
        assert material.Sm(500, 5) == 97e6
        assert pytest.approx(material.Sy_min(100, 0.05), rel=1e-2) == 172e6
        assert material.Sy_min(20, 2) > 500e6
        assert material.Sy_min(300, 2) > 500e6
        with pytest.raises(OutOfBoundsError):
            material.Sy_min(700, 16)
