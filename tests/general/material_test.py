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
        with pytest.raises(NotImplementedError):
            material.Smb(20, 0)

    def test_cyclic_stress_strain(self, material: Material):
        assert (
            pytest.approx(material.cyclic_stress_strain(20, 900e6), rel=1e-2)
            == 1.81 / 100
        )

    def test_accept_tuple(self, material: Material):
        """Test that the cyclic_stress_strain method accepts a tuple for T and ds."""
        assert material.Sd((250, 4)) == 435e6


def test_Inconel_SDC_IC():
    """
    Test that the Inconel 718 material file is read correctly.
    """
    with as_file(
        MAT_FOLDER.joinpath("Inconel 718 (non leak tight) SDC-IC.yaml")
    ) as mat_path:
        material = Material(mat_path)
    assert pytest.approx(material.E(350, 1), rel=5e-3) == 183e9
    assert pytest.approx(material.Sy_min(20, 0), rel=1e-3) == 1035e6
    assert material.Sy_min(350, 1) == 791e6
    assert material.Smb(300, 0) == 425e6
    assert material.Smb(300, 1) == 368e6
    assert material.N(300, 220e6, 500e6) > 5e5
    assert material.N(300, 103e6, 1000e6) == 2e6
    assert material.Su_min(300, 1) == 994e6


def test_read_materials():
    read_materials(MAT_FOLDER)
