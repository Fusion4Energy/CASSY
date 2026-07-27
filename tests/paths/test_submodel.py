from importlib.resources import as_file, files

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from cassy.additional_data import materials
from cassy.designcodes.codes import Code
from cassy.designcodes.rccmr import RCC_MR
from cassy.designcodes.rccmrx import RCC_MRx
from cassy.designcodes.sdcic import SDC_IC
from cassy.paths.paths_config import Configuration
from cassy.general.material import Material
from cassy.paths.submodel import Submodel
from tests.paths import res

# Add path to material files
RES = files(materials)


class TestSubmodel:
    @pytest.fixture
    def submodel(self) -> Submodel:
        with as_file(files(res).joinpath("submodel.xlsx")) as file:
            with as_file(files(res).joinpath("submodel_tensors.csv")) as tensors_file:
                config = Configuration("Model_A", file, tensors_file)
        with as_file(RES.joinpath("SS316L(N)-IG_SDC-IC.yaml")) as mat_path:
            steel = Material(mat_path)

        submodel = Submodel("Model", config, {"SS316L(N)-IG": steel})
        return submodel

    def test_build_linearized_stress(self, submodel: Submodel):
        # Test the build_linearized_stress method
        linstress = submodel._build_linearized_stress("ThermalNO", 1, "begin")

    @pytest.mark.parametrize("code", [RCC_MRx(), RCC_MR(), SDC_IC()])
    def test_assess(self, submodel: Submodel, code: Code):
        # Test the build_RE method
        submodel.build_REs(fatigue=True)
        submodel.assess(code, fatigue=True)

    def test_assess_stress_fatigue(self):
        with as_file(files(res).joinpath("submodel.xlsx")) as file:
            with as_file(files(res).joinpath("submodel_tensors.csv")) as tensors_file:
                config = Configuration("Model_A", file, tensors_file)
        with as_file(RES.joinpath("XM-19 SS_SDC-IC.yaml")) as mat_path:
            xm = Material(mat_path)

        submodel = Submodel("Model", config, {"SS316L(N)-IG": xm})
        # Test the build_RE method
        submodel.build_REs(fatigue=True)
        submodel.assess(SDC_IC(), fatigue=True)

    def test_get_recap(self, submodel: Submodel):
        # Test the get_recap method
        submodel.build_REs(fatigue=True)
        submodel.assess(RCC_MRx(), fatigue=True)
        recap = submodel.get_recap()
        assert isinstance(recap, dict)
        assert pytest.approx(recap["Immediate"][0]["Safety Margin"]) == 4.46

    def test_get_recap_ratcheting_screening(self, submodel: Submodel):
        """When 3Sm fails but Efficiency Index passes (IC3131_1_2 sequential rule),
        the recap should report OK and use EI as the design driver, not 3Sm.
        Regression test for issue #49.
        """
        from cassy.designcodes.sdcic import SDC_IC

        # Build a mock assessment df that mirrors the scenario in issue #49:
        # - 3Sm rule FAILED (Screening=True, because EI rows exist)
        # - Efficiency Index rows both OK
        mock_ratcheting_df = pd.DataFrame(
            [
                {
                    "ID": "RE1",
                    "Operating Conditions": "Normal",
                    "Initiating Event": None,
                    "Concatenated Event": None,
                    "Loading Category": None,
                    "Service Level": "A",
                    "Rule Extended Description": "Progressive deformation or ratcheting",
                    "Rule ID": "IC 3131.1",
                    "Sub-Rule": "3Sm rule",
                    "T [°C]": 211,
                    "DPA": 1e-3,
                    "Applied [MPa]": 387.0,
                    "Allowable [MPa]": 383.0,
                    "Result": "FAILED",
                    "Safety Margin": 0.99,
                    "Damage Type": "Ratcheting",
                    "Screening": True,
                },
                {
                    "ID": "RE1",
                    "Operating Conditions": "Normal",
                    "Initiating Event": None,
                    "Concatenated Event": None,
                    "Loading Category": None,
                    "Service Level": "A",
                    "Rule Extended Description": "Progressive deformation or ratcheting",
                    "Rule ID": "IC 3131.1",
                    "Sub-Rule": "Efficiency Index",
                    "T [°C]": 211,
                    "DPA": 1e-3,
                    "Applied [MPa]": 164.0,
                    "Allowable [MPa]": 166.0,
                    "Result": "OK",
                    "Safety Margin": 1.01,
                    "Damage Type": "Ratcheting",
                    "Screening": False,
                },
                {
                    "ID": "RE1",
                    "Operating Conditions": "Normal",
                    "Initiating Event": None,
                    "Concatenated Event": None,
                    "Loading Category": None,
                    "Service Level": "A",
                    "Rule Extended Description": "Progressive deformation or ratcheting",
                    "Rule ID": "IC 3131.1",
                    "Sub-Rule": "Efficiency Index",
                    "T [°C]": 211,
                    "DPA": 1e-3,
                    "Applied [MPa]": 170.0,
                    "Allowable [MPa]": 249.0,
                    "Result": "OK",
                    "Safety Margin": 1.46,
                    "Damage Type": "Ratcheting",
                    "Screening": False,
                },
            ]
        )

        # Inject the mock df into the submodel assessments
        submodel.assessments = {
            1: {"begin": mock_ratcheting_df, "end": mock_ratcheting_df}
        }
        submodel.code = SDC_IC()

        recap = submodel.get_recap(fatigue=False)

        # Both begin and end should report OK, not NOK
        ratcheting_recap = recap["Ratcheting"]
        assert len(ratcheting_recap) == 2
        for row in ratcheting_recap:
            assert row["Assessment"] == "OK", (
                "3Sm failure should be treated as screening when EI passes"
            )
            # EI (SM=1.01) is the minimum among EI rows → design driver
            assert row["Rule"] == "Efficiency Index", (
                "Design driver should be the EI sub-rule, not 3Sm"
            )
            assert pytest.approx(row["Safety Margin"]) == 1.01

    def test_F4E_RCCMRx(self, tmp_path: Path):
        """Stage 1 of test defined at https://idm.f4e.europa.eu/?uid=2E22GB"""
        # convert the tensor file to the format expected by the submodel
        with as_file(files(res).joinpath("2E22GB/f4e_tensors.csv")) as file:
            df = pd.read_csv(file)
        converted_df = _convert_tensor_file(df)
        converted_file = tmp_path / "converted_tensors.csv"
        converted_df.to_csv(converted_file, index=False)

        # read the configuration file
        with as_file(files(res).joinpath("2E22GB/config.xlsx")) as config_file:
            config = Configuration("Model_A", config_file, converted_file)

        with as_file(RES.joinpath("SS316L(N)-IG_RCC-MRx.yaml")) as mat_path:
            steel = Material(mat_path)

        # perform the assessment
        submodel = Submodel("Model", config, {"SS316L(N)-IG": steel})
        submodel.build_REs(fatigue=True)
        submodel.assess(RCC_MRx(), fatigue=True)

        # De2 have been all set to 0 as the pressure must not be considered cyclic
        # according to the benchmark
        expected = {
            1: {
                "RB 3261.111": {"applicable": 286, "allowable": 317},
                "RB 3251.112": {
                    "applicable": np.array([12, 14]),
                    "allowable": np.array([106, 159]),
                },
                "fatigue": {
                    "de1": 0.126795197273733,
                    "de2": 0,
                    "de3": 0.011,
                    "de4": 0.008,
                    "de": 0.146 - 0.001,  # remove de2 from total
                    "N": 38044509,
                },
            },
            2: {
                "RB 3261.111": {"applicable": 182.72, "allowable": 315.72},
                "RB 3251.112": {
                    "applicable": np.array([28.73, 28.82]),
                    "allowable": np.array([105.24, 157.86]),
                },
                "fatigue": {
                    "de1": 0.0627394918568547,
                    "de2": 0,
                    "de3": 0.001 + 0.0003,  # not enough digits in benchmark
                    "de4": 0.001 + 0.0001,  # not enough digits in benchmark
                    "de": 0.065 - 0.001,  # remove de2 from total
                    "N": 1e8,  # max number of cycles (i.e., infinite)
                },
            },
            3: {
                # from 647 (original in benchmark) to 640 because it seems the benchmark
                # is summing the PmPb of begin of the path with the dQ of the end
                "RB 3261.111": {"applicable": 640, "allowable": 300.67},
                "RB 3251.112": {
                    "applicable": np.array([6.72, 13.35]),
                    "allowable": np.array([100.22, 150.34]),
                },
                "fatigue": {
                    "de1": 0.413861954517315,
                    "de2": 0,
                    "de3": 0.198,
                    "de4": 0.096,
                    "de": 0.708,
                    "N": 332,
                },
            },
        }

        # path 1
        for path_num in [1, 2, 3]:
            result = submodel.assessments[path_num]
            for rule in ["RB 3251.112", "RB 3261.111"]:
                applicable = 0
                allowable = 0
                # select the max between begin and end
                for key in ["begin", "end"]:
                    new_applicable = (
                        result[key].set_index("Rule ID").loc[rule]["Applied [MPa]"]
                    )
                    try:
                        new_applicable = new_applicable.values
                    except AttributeError:
                        pass

                    allowable = (
                        result[key].set_index("Rule ID").loc[rule]["Allowable [MPa]"]
                    )
                    try:
                        allowable = allowable.values
                    except AttributeError:
                        pass
                    if (new_applicable >= applicable).all():
                        applicable = new_applicable
                        allowable = allowable

                # tolerance of 3 MPa for roundings
                assert (
                    pytest.approx(applicable, abs=3)
                    == expected[path_num][rule]["applicable"]
                )
                assert (
                    pytest.approx(allowable, rel=0.01)
                    == expected[path_num][rule]["allowable"]
                )
            # fatigue
            de_tot = 0
            for key in ["begin", "end"]:
                new_detot = result[f"{key} fatigue"]["de tot"].iloc[0]
                if new_detot > de_tot:
                    de_tot = new_detot
                    row = {
                        "de1": result[f"{key} fatigue"]["de1"].iloc[0] * 100,
                        "de2": result[f"{key} fatigue"]["de2"].iloc[0] * 100,
                        "de3": result[f"{key} fatigue"]["de3"].iloc[0] * 100,
                        "de4": result[f"{key} fatigue"]["de4"].iloc[0] * 100,
                        "de": result[f"{key} fatigue"]["de tot"].iloc[0] * 100,
                        "N": result[f"{key} fatigue"]["N"].iloc[0],
                    }
            for key, value in row.items():
                if key == "N":
                    # it is non-linear, let's just check same order of magnitude
                    assert (
                        pytest.approx(value, rel=0.5)
                        == expected[path_num]["fatigue"][key]
                    )
                else:
                    assert (
                        pytest.approx(value, rel=0.05)
                        == expected[path_num]["fatigue"][key]
                    )


def _convert_tensor_file(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a tensor that has PmPb and total instead of Pb and F"""
    to_concat = []
    for comp in ["Sx", "Sy", "Sz", "Sxy", "Sxz", "Syz"]:
        component = df.pivot_table(
            index=["path", "analysis", "loadstep", "pathpoint"],
            columns="stress_type",
            values=comp,
        )
        component["Pb"] = component["PmPb"] - component["Pm"]
        component["F"] = component["total"] - component["PmPb"]
        del component["PmPb"]
        del component["total"]
        component = component.stack()
        component.name = comp
        to_concat.append(component)

    result = pd.concat(to_concat, axis=1)
    return result.reset_index()
