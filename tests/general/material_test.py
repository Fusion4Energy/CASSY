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

    def test_edge_with_null(self, material: Material):
        assert material.Se(50, 5) == 846e6
        assert np.isclose(material.Se(50.001, 4.5), 936e6)

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

    def test_compute_delta_sigma_Neuber(self, material: Material):
        # if the stress is low enough, the result should be the same as the elastic one
        T = 50
        dpa = 0
        sigma = 10e6

        sigma_plastic = material.compute_delta_sigma_Neuber(T, sigma, 1, 0)
        eps_plastic = material.cyclic_stress_strain(T, sigma_plastic)
        assert pytest.approx(eps_plastic, rel=1e-1) == sigma / material.E(T, dpa)

        sigma_plastic = material.compute_delta_sigma_Neuber(
            T, sigma, 1, 0, monotonic=True
        )
        eps_plastic = material.monotonic_min_stress_strain(sigma_plastic, T, dpa)
        assert pytest.approx(eps_plastic, rel=1e-1) == sigma / material.E(T, dpa)


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
    assert material.N(300, 220, 500) > 5e5
    assert material.N(300, 103, 1000) == 2e6
    assert material.Su_min(300, 1) == 994e6


def test_CuCrZr_Tr_B_SDC_IC():
    """
    Test that the CuCrZr-IG Tr B material file is read correctly.
    """
    with as_file(MAT_FOLDER.joinpath("CuCrZr-IG Tr B SDC-IC.yaml")) as mat_path:
        material = Material(mat_path)
    assert pytest.approx(material.E(250, 1), rel=5e-3) == 118.481e9
    assert pytest.approx(material.Sy_min(90, 4), rel=1e-3) == 395.5e6
    assert pytest.approx(material.Sy_min(90, 0.1), rel=1e-3) == 230.5e6
    assert pytest.approx(material.Su_min(90, 4), rel=1e-3) == 401e6
    assert pytest.approx(material.Su_min(90, 0.1), rel=1e-3) == 342e6
    assert pytest.approx(material.Sm(125, 0), rel=1e-3) == 120e6
    assert pytest.approx(material.Sm(125, 0.1), rel=1e-3) == 120e6
    assert (
        pytest.approx(
            material.monotonic_min_stress_strain(243.5547e6, 20, 0.1), rel=1e-3
        )
        == 0.4333075e-2
    )
    assert np.isnan(material.Se(350, 1))
    assert material.Se(275, 1) == 99.5e6
    assert np.isnan(material.Sd(450, 1))

    # assert pytest.approx(material.E(125, 0.1), rel=1e-3) == 120e6
    # assert material.N(300, 220, 500) > 5e5
    # assert material.N(300, 103, 1000) == 2e6
    # assert material.Su_min(300, 1) == 994e6


def test_SS316LNIG_RCCMRx():
    with as_file(MAT_FOLDER.joinpath("SS316L(N)-IG_RCC-MRx.yaml")) as mat_path:
        material = Material(mat_path)

    assert pytest.approx(material.E(550, 1), rel=5e-3) == 155e9


def test_S660_SDC_IC():
    with as_file(MAT_FOLDER.joinpath("SS660 (non leak-tight)_SDC-IC.yaml")) as mat_path:
        material = Material(mat_path)

    assert pytest.approx(material.E(200, 1), rel=2e-3) == 189e9
    assert pytest.approx(material.Sy_min(200, 10), rel=1e-3) == 558e6
    assert pytest.approx(material.Sy_moy(200, 10), rel=1e-3) == 652e6
    assert pytest.approx(material.Su_min(200, 0.1), rel=1e-3) == 817e6
    assert pytest.approx(material.Sm(200, 0.1), rel=1e-3) == 299e6
    assert pytest.approx(material.Smb(200, 0.1), rel=1e-3) == 299e6
    assert pytest.approx(material.N(100, 338e6), rel=1e-3) == 5e3
    assert (
        pytest.approx(material.monotonic_min_stress_strain(351e6, 250, 50), rel=1e-3)
        == 0.189e-2
    )


def test_S660_RCCMRx():
    with as_file(MAT_FOLDER.joinpath("SS660_RCC-MRx.yaml")) as mat_path:
        material = Material(mat_path)

    assert (
        pytest.approx(material.cyclic_stress_strain(600, 3000e6), rel=2e-3) == 2.86e-2
    )


def test_XM19_SDC_IC():
    with as_file(MAT_FOLDER.joinpath("XM-19 SS_SDC-IC.yaml")) as mat_path:
        material = Material(mat_path)

    assert pytest.approx(material.E(200, 1), rel=1e-2) == 183e9
    assert (
        pytest.approx(material.monotonic_min_stress_strain(400e6, 200, 1), rel=1e-3)
        == 5.118e-4
    )


def test_read_materials():
    read_materials(MAT_FOLDER)
