from importlib.resources import as_file, files

import numpy as np
import pytest

from cassy.additional_data import materials as mat_folder
from cassy.designcodes.sdcic import (
    SDC_IC,
    IC3121_1_1_2a,
    IC3121_2_1,
    IC3121_3_1,
    IC3131_1_2,
)
from cassy.general.material import Material
from tests.designcodes import res
from cassy.paths.linstress import ReferenceEvent

RES = files(res)


# Fixtures for real materials
@pytest.fixture
def material_cucrzr():
    with as_file(files(mat_folder).joinpath("CuCrZr-IG Tr B SDC-IC.yaml")) as path:
        return Material(path)


@pytest.fixture
def material_ss316():
    with as_file(files(mat_folder).joinpath("SS316L(N)-IG_SDC-IC.yaml")) as path:
        return Material(path)


# Fixture for a real ReferenceEvent from path_stresses.csv and path_config_recomb.xlsx
# Fixture for a real ReferenceEvent from path_stresses.csv and path_config_recomb.xlsx using from_recombination
@pytest.fixture
def ref_event() -> ReferenceEvent:
    from cassy.paths.paths_config import parse_cfg_files
    from cassy.paths.submodel import Submodel

    # Prepare file paths
    stress_path = str(RES.joinpath("stress"))
    config_folder = str(RES.joinpath("conf"))

    # Parse the configuration as in production
    configs = parse_cfg_files(config_folder, stress_path)
    # Use the first submodel in the config
    submodel_name, conf = next(iter(configs.items()))
    # Use a dummy material library (not used for ReferenceEvent creation)
    mat_dict = {
        "CuCrZr-IG Tr B SDC-IC": Material(
            files(mat_folder).joinpath("CuCrZr-IG Tr B SDC-IC.yaml")
        ),
        "SS316L(N)-IG_SDC-IC": Material(
            files(mat_folder).joinpath("SS316L(N)-IG_SDC-IC.yaml")
        ),
    }
    submodel = Submodel(submodel_name, conf, mat_dict)

    # Build all ReferenceEvents (non-fatigue)
    submodel.build_REs(fatigue=False)

    # Pick the only ReferenceEvent built (first path, 'begin')
    first_pathnum = next(iter(submodel.paths))
    path = submodel.paths[first_pathnum]
    ref_event = path.REs_beg[0]
    return ref_event


class TestSDCICPaths:
    @pytest.mark.parametrize(
        "material_fixture, T, dpa, expected_Sm, expected_Se, expected_symin, expected_sumin, expected_keff",
        [
            ("material_cucrzr", 300, 0.1, 96e6, 96e6, 185e6, 259e6, 1.5),
            # For SS316, use T=200C, dpa=0.0. Sy_min = Min Yield Strength (225.75 MPa), Su_min = Min Tensile Strength (529.75 MPa)
            ("material_ss316", 200, 0.0, 130e6, None, 145.1e6, 423e6, 1.5),
        ],
    )
    @pytest.mark.parametrize("service_lvl", ["A", "C", "D"])
    def test_ic3121_1_1_2a_assess_levels(
        self,
        ref_event: ReferenceEvent,
        request,
        material_fixture,
        T,
        dpa,
        expected_Sm,
        expected_Se,
        expected_symin,
        expected_sumin,
        expected_keff,
        service_lvl,
    ):
        material = request.getfixturevalue(material_fixture)
        rule = IC3121_1_1_2a()
        ref_event.config.service_lvl = service_lvl
        ref_event.config.T = T
        ref_event.config.dpa = dpa
        n = ref_event.config.welding_n
        if service_lvl == "A":
            allowable1 = n * expected_Sm
        elif service_lvl == "C":
            allowable1 = min(1.2 * n * expected_Sm, expected_symin)
        elif service_lvl == "D":
            allowable1 = min(2.4 * n * expected_Sm, 0.7 * expected_sumin)
        results = rule.assess(ref_event, material)
        assert isinstance(results, list)
        assert len(results) == 2
        stress1, test_allowable1 = results[0]
        stress2, test_allowable2 = results[1]
        assert pytest.approx(stress1, rel=1e-2) == 77.7e6
        assert pytest.approx(stress2, rel=1e-2) == 100.2e6
        assert pytest.approx(test_allowable1, rel=1e-2) == allowable1
        assert pytest.approx(test_allowable2, rel=1e-2) == expected_keff * allowable1

    @pytest.mark.parametrize(
        "material_fixture, expected_Se",
        [
            ("material_cucrzr", 96e6),
            ("material_ss316", None),  # Se not defined for SS316 at (300,0.1)
        ],
    )
    @pytest.mark.parametrize(
        "service_lvl, factor",
        [
            ("A", 1.0),
            ("C", 1.2),
            ("D", 2.0),
        ],
    )
    def test_ic3121_2_1_assess_levels(
        self,
        ref_event: ReferenceEvent,
        request,
        material_fixture,
        expected_Se,
        service_lvl,
        factor,
    ):
        material = request.getfixturevalue(material_fixture)
        rule = IC3121_2_1()
        ref_event.config.service_lvl = service_lvl
        ref_event.config.T = 300
        ref_event.config.dpa = 0.1
        results = rule.assess(ref_event, material)
        assert isinstance(results, list)
        assert len(results) == 1
        stress, allowable = results[0]
        assert pytest.approx(stress, rel=1e-2) == 56.4e6
        if expected_Se is None:
            assert np.isnan(allowable)
        else:
            assert pytest.approx(allowable, rel=1e-6) == factor * expected_Se

    @pytest.mark.parametrize(
        "material_fixture, expected_Sd, expected_Sd_nopeak, temperature",
        [
            ("material_cucrzr", 492e6, 235e6, 150),
            ("material_ss316", 449e6, 449e6, 350),
        ],
    )
    @pytest.mark.parametrize(
        "service_lvl, factor",
        [
            ("A", 1.0),
            ("C", 1.2),
            ("D", 1.35),
        ],
    )
    def test_ic3121_3_1_assess_levels(
        self,
        ref_event: ReferenceEvent,
        request,
        material_fixture,
        expected_Sd,
        expected_Sd_nopeak,
        temperature,
        service_lvl,
        factor,
    ):
        material = request.getfixturevalue(material_fixture)
        rule = IC3121_3_1()
        ref_event.config.service_lvl = service_lvl
        ref_event.config.T = temperature
        ref_event.config.dpa = 5
        results = rule.assess(ref_event, material)
        assert isinstance(results, list)
        assert len(results) == 2
        stress1, allowable1 = results[0]
        stress2, allowable2 = results[1]
        assert pytest.approx(stress1, rel=1e-2) == 114.8e6
        assert pytest.approx(stress2, rel=1e-2) == 87e6
        assert pytest.approx(allowable1, rel=1e-2) == factor * expected_Sd
        assert pytest.approx(allowable2, rel=1e-2) == factor * expected_Sd_nopeak

    @pytest.mark.parametrize(
        "material_fixture, T, dpa, expected_Sm",
        [
            ("material_cucrzr", 300, 0.1, 96e6),
            ("material_ss316", 150, 0.0, 141e6),  # Sm(150,0.0) for SS316 is 141 MPa
        ],
    )
    @pytest.mark.parametrize("service_lvl", ["A", "C", "D"])
    def test_ic3131_1_2_assess_levels(
        self,
        ref_event: ReferenceEvent,
        request,
        material_fixture,
        T,
        dpa,
        expected_Sm,
        service_lvl,
    ):
        material = request.getfixturevalue(material_fixture)
        rule = IC3131_1_2()
        ref_event.config.service_lvl = service_lvl
        ref_event.config.T = T
        ref_event.config.dpa = dpa
        result = rule.assess(ref_event, material)
        if service_lvl == "D":
            assert result is None
        else:
            assert isinstance(result, list)
            assert result[0][0] == ref_event.ratcheting3Sm_SDCIC
            assert pytest.approx(result[0][1], rel=1e-6) == 3 * expected_Sm

    @pytest.mark.parametrize("material_fixture", ["material_cucrzr", "material_ss316"])
    def test_sdc_ic_computeVj(
        self, ref_event: ReferenceEvent, request, material_fixture
    ):
        code = SDC_IC()
        material = request.getfixturevalue(material_fixture)
        ref_event.config.T = 300
        ref_event.config.dpa = 0.1
        result = code.computeVj(ref_event, material)
        assert "de1" in result
        assert "de2" in result
        assert "de3" in result
        assert "de4" in result
        assert "N" in result
        assert "Rule ID" in result
        assert "sigma tot" in result
        assert result["Rule ID"] == "IC 3132.3.1"
        if material_fixture == "material_cucrzr":
            assert result["de2"] == 0
