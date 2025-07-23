from importlib.resources import as_file, files

import numpy as np
import pytest

from cassy.additional_data import materials
from cassy.auxiliary.custom_errors import OutOfBoundsError
from cassy.general.material import Material, read_materials
from tests.general import res

MAT_FOLDER = files(materials)


class TestMaterial:
    @pytest.fixture()
    def material(self):
        with as_file(files(res).joinpath("material_example.yaml")) as config_file:
            material = Material(config_file)
        return material

    def test_properties(self, material: Material):
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
        assert np.isnan(material.Se(50, 4.3))
        assert material.Se(250, 3.25) == 211.5e6
        assert np.isnan(material.Sd(50, 4))
        assert material.Sd(250, 4) == 435e6
        assert material.monotonic_min_stress_strain(80e6, 200, 0) == 0.044314e-2
        assert (
            material.monotonic_min_stress_strain(80e6, 150, 0.01)
            == (0.044314 + 0.041665) / 2 / 100
        )
        assert (
            pytest.approx(material.monotonic_min_stress_strain(868.35e6, 20, 0.01))
            == 50.31966 / 100
        )

    def test_cyclic_stress_strain(self, material: Material):
        assert (
            pytest.approx(material.cyclic_stress_strain(20, 900e6), rel=1e-2)
            == 1.81 / 100
        )

    def test_accept_tuple(self, material: Material):
        """Test that the cyclic_stress_strain method accepts a tuple for T and ds."""
        assert material.Sd((250, 4)) == 435e6


def test_read_materials():
    read_materials(MAT_FOLDER)
