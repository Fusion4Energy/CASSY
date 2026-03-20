import pandas as pd
import numpy as np
from copy import deepcopy
from cassy.designcodes.codes import Code
from cassy.general.material import Material
from cassy.paths.paths_config import (
    LinStressConfig,
    STRESS_ORDER,
    StressClassification,
    PathType,
    LoadType,
    ReferenceEventConfig,
    SpatialRecMethod,
)


class LinStress:
    def __init__(self, stress_tensor: pd.DataFrame, config: LinStressConfig):
        """Object representing a linearized stress on a path

        Parameters
        ----------
        stress_tensor : pd.DataFrame
            tensor of the linearized stress. The index should be the type of stress
            (i.e., M, B, F) and the columns should be the stress components
        config : LinStressConfig
            configuration of the linearized stress
        """
        # change index for clarity
        stress_tensor = (
            self._safePascal(stress_tensor[STRESS_ORDER], config.unit) * config.scale
        )
        stress_tensor = stress_tensor.loc[["Pm", "Pb", "F"]]
        stress_tensor.index = ["M", "B", "F"]
        stress_tensor.index.name = "stress_type"
        self.original_mtrx = stress_tensor.copy()
        self.config = config

        if self.config.stress_classification == StressClassification.PRIMARY:
            primary = stress_tensor.T
            secondary = stress_tensor.T
            secondary.loc[:, :] = 0
        else:
            primary = stress_tensor.T
            primary.loc[:, :] = 0
            secondary = stress_tensor.T

        # --- Now perform changes in primary/secondary classifications ---

        # SDC-IC: fillet and pressure
        if (
            self.config.stress_classification == StressClassification.PRIMARY
            and self.config.ptype == PathType.FILLET
            and self.config.isPressure
        ):
            vals = primary["B"].values
            primary.loc[:, "B"] = 0
            secondary.loc[:, "B"] = vals

        # --- compute the rest of the tensor ---
        for matrix in [primary, secondary]:
            matrix["MB"] = matrix["M"] + matrix["B"]
            matrix["MBF"] = matrix["MB"] + matrix["F"]
            matrix["tresca"] = matrix["M"] + 0.67 * matrix["B"]

        self.primary: pd.DataFrame = primary.T
        self.secondary: pd.DataFrame = secondary.T

    @staticmethod
    def _safePascal(df: pd.DataFrame, unit: str) -> pd.DataFrame:
        # Convert Unit to Pa
        if unit == "MPa":
            df = df * 1e6
        elif unit == "KPa":
            df = df * 1e3
        elif unit == "Pa":
            pass
        else:
            raise KeyError(unit + " is not an admissible unit")

        return df


class ReferenceEvent:
    def __init__(
        self,
        linstresses: list[LinStress],
        refevent_config: ReferenceEventConfig,
    ):
        self.stresses = linstresses

        # override the welding factor with the path ones
        refevent_config.welding_n = linstresses[0].config.Welding_n
        refevent_config.welding_f = linstresses[0].config.Welding_f
        self.config = refevent_config

        # split the stresses between volumetric and inertial
        self.volumetric: list[LinStress] = []
        inertial: list[LinStress] = []
        for lin_stress in self.stresses:
            if lin_stress.config.load_type == LoadType.VOLUMETRIC:
                self.volumetric.append(lin_stress)
            else:
                inertial.append(lin_stress)

        # Spatially recombine the inertial stresses
        self.inertial = _combine_inertial_stresses(inertial)

        self._cache = {}

    @staticmethod
    def _get_final_VM(
        volumetric: list[np.ndarray],
        inertial: list[np.ndarray],
    ) -> float:
        # For volumetric is easy, they are all sum anyway
        vol = _combine_linstresses(
            volumetric, combination_type=SpatialRecMethod.ALGEBRAIC
        )
        # inertials are summed in SRSS
        ine = _combine_linstresses(inertial, combination_type=SpatialRecMethod.SRSS)

        return von_mises(vol, ine)

    @property
    def Pm(self) -> float:
        """primary membrane stress"""
        if "Pm" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.primary.loc["M"].values)
            for matrix in self.inertial:
                inertial.append(matrix.primary.loc["M"].values)

            self._cache["Pm"] = self._get_final_VM(vol, inertial)

        return self._cache["Pm"]

    @property
    def Pms(self) -> float:
        """primary membrane overstress from short duration loads"""
        if "Pms" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                if matrix.config.isShortOverstress:
                    vol.append(matrix.primary.loc["M"].values)
            for matrix in self.inertial:
                if matrix.config.isShortOverstress:
                    inertial.append(matrix.primary.loc["M"].values)

            self._cache["Pms"] = self._get_final_VM(vol, inertial)

        return self._cache["Pms"]

    @property
    def Pm_ns(self) -> float:
        """primary membrane stress not from short duration loads"""
        if "Pm_ns" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                if not matrix.config.isShortOverstress:
                    vol.append(matrix.primary.loc["M"].values)
            for matrix in self.inertial:
                if not matrix.config.isShortOverstress:
                    inertial.append(matrix.primary.loc["M"].values)

            self._cache["Pm_ns"] = self._get_final_VM(vol, inertial)

        return self._cache["Pm_ns"]

    @property
    def Pb(self) -> float:
        """primary bending stress"""
        if "Pb" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.primary.loc["B"].values)
            for matrix in self.inertial:
                inertial.append(matrix.primary.loc["B"].values)

            self._cache["Pb"] = self._get_final_VM(vol, inertial)

        return self._cache["Pb"]

    @property
    def PmPb(self) -> float:
        """primary membrane + bending stress"""
        if "PmPb" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.primary.loc["MB"].values)
            for matrix in self.inertial:
                inertial.append(matrix.primary.loc["MB"].values)

            self._cache["PmPb"] = self._get_final_VM(vol, inertial)
        return self._cache["PmPb"]

    @property
    def PmPbs(self) -> float:
        """primary membrane + bending overstress from short duration load"""
        if "PmPbs" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                if matrix.config.isShortOverstress:
                    vol.append(matrix.primary.loc["MB"].values)
            for matrix in self.inertial:
                if matrix.config.isShortOverstress:
                    inertial.append(matrix.primary.loc["MB"].values)

            self._cache["PmPbs"] = self._get_final_VM(vol, inertial)

        return self._cache["PmPbs"]

    @property
    def PmPb_ns(self) -> float:
        """primary membrane + bending stress not from short duration loads"""
        if "PmPb_ns" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                if not matrix.config.isShortOverstress:
                    vol.append(matrix.primary.loc["MB"].values)
            for matrix in self.inertial:
                if not matrix.config.isShortOverstress:
                    inertial.append(matrix.primary.loc["MB"].values)

            self._cache["PmPb_ns"] = self._get_final_VM(vol, inertial)

        return self._cache["PmPb_ns"]

    @property
    def PmQm(self) -> float:
        """total membrane stress (primary + secondary)"""
        if "PmQm" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.primary.loc["M"].values)
                vol.append(matrix.secondary.loc["M"].values)
            for matrix in self.inertial:
                inertial.append(matrix.primary.loc["M"].values)
                inertial.append(matrix.secondary.loc["M"].values)

            self._cache["PmQm"] = self._get_final_VM(vol, inertial)
        return self._cache["PmQm"]

    @property
    def PmQm_ns(self) -> float:
        """total membrane stress (primary + secondary) not from short duration loads"""
        if "PmQm_ns" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                if not matrix.config.isShortOverstress:
                    vol.append(matrix.primary.loc["M"].values)
                    vol.append(matrix.secondary.loc["M"].values)
            for matrix in self.inertial:
                if not matrix.config.isShortOverstress:
                    inertial.append(matrix.primary.loc["M"].values)
                    inertial.append(matrix.secondary.loc["M"].values)

            self._cache["PmQm_ns"] = self._get_final_VM(vol, inertial)
        return self._cache["PmQm_ns"]

    @property
    def PQ(self) -> float:
        """total stress, excluding peaks (primary + secondary)"""
        if "PQ" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.primary.loc["MB"].values)
                vol.append(matrix.secondary.loc["MB"].values)
            for matrix in self.inertial:
                inertial.append(matrix.primary.loc["MB"].values)
                inertial.append(matrix.secondary.loc["MB"].values)

            self._cache["PQ"] = self._get_final_VM(vol, inertial)
        return self._cache["PQ"]

    @property
    def PQF(self) -> float:
        """total stress, including peaks (primary + secondary)"""
        if "PQF" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.primary.loc["MBF"].values)
                vol.append(matrix.secondary.loc["MBF"].values)
            for matrix in self.inertial:
                inertial.append(matrix.primary.loc["MBF"].values)
                inertial.append(matrix.secondary.loc["MBF"].values)

            self._cache["PQF"] = self._get_final_VM(vol, inertial)
        return self._cache["PQF"]

    @property
    def PF(self) -> float:
        """total primary stress (Pm+Pb+F)"""
        if "PF" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.primary.loc["MBF"].values)
            for matrix in self.inertial:
                inertial.append(matrix.primary.loc["MBF"].values)

            self._cache["PF"] = self._get_final_VM(vol, inertial)
        return self._cache["PF"]

    @property
    def PmPbQm(self) -> float:
        """Primary membrane + bending and secondary membrane stresses"""
        if "PmPbQm" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.primary.loc["MB"].values)
                vol.append(matrix.secondary.loc["M"].values)
            for matrix in self.inertial:
                inertial.append(matrix.primary.loc["MB"].values)
                inertial.append(matrix.secondary.loc["M"].values)

            self._cache["PmPbQm"] = self._get_final_VM(vol, inertial)
        return self._cache["PmPbQm"]

    @property
    def PmPbQm_ns(self) -> float:
        """Primary membrane + bending and secondary membrane stresses not from short duration loads"""
        if "PmPbQm_ns" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                if not matrix.config.isShortOverstress:
                    vol.append(matrix.primary.loc["MB"].values)
                    vol.append(matrix.secondary.loc["M"].values)
            for matrix in self.inertial:
                if not matrix.config.isShortOverstress:
                    inertial.append(matrix.primary.loc["MB"].values)
                    inertial.append(matrix.secondary.loc["M"].values)

            self._cache["PmPbQm_ns"] = self._get_final_VM(vol, inertial)
        return self._cache["PmPbQm_ns"]

    @property
    def tresca(self) -> float:
        """Pm + 0.67*Pb"""
        # first, isolate primary bending and membrane
        if "tresca" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                if matrix.config.isCyclic:
                    vol.append(matrix.primary.loc["tresca"].values)
            for matrix in self.inertial:
                if matrix.config.isCyclic:
                    inertial.append(matrix.primary.loc["tresca"].values)

            self._cache["tresca"] = self._get_final_VM(vol, inertial)
        return self._cache["tresca"]

    @property
    def dQ(self) -> float:
        """cyclic secondary stress range (no peak)"""
        if "dQ" not in self._cache:
            vol = []
            inertial = []
            for matrix in self.volumetric:
                vol.append(matrix.secondary.loc["MB"].values)
            for matrix in self.inertial:
                inertial.append(matrix.secondary.loc["MB"].values)

            self._cache["dQ"] = self._get_final_VM(vol, inertial)
        return self._cache["dQ"]

    @property
    def ratcheting3Sm_SDCIC(self) -> float:
        """3Sm according to SDC-IC"""
        if "ratcheting3Sm_SDCIC" not in self._cache:
            maxPmPb_vol = []
            maxPmPb_inertial = []

            P_plasma_vol = []
            P_plasma_inertial = []

            for matrix in self.volumetric:
                # do not include plasma disruption
                if not matrix.config.isPD:
                    maxPmPb_vol.append(matrix.primary.loc["MB"].values)
                else:
                    # plasma disruption cyclic
                    if matrix.config.isCyclic:
                        P_plasma_vol.append(matrix.primary.loc["MB"].values)

            for matrix in self.inertial:
                if not matrix.config.isPD:
                    maxPmPb_inertial.append(matrix.primary.loc["MB"].values)
                else:
                    if matrix.config.isCyclic:
                        P_plasma_inertial.append(matrix.primary.loc["MB"].values)

            maxPmPb = self._get_final_VM(maxPmPb_vol, maxPmPb_inertial)
            P_plasma = self._get_final_VM(P_plasma_vol, P_plasma_inertial)

            self._cache["ratcheting3Sm_SDCIC"] = maxPmPb + P_plasma + self.dQ

        return self._cache["ratcheting3Sm_SDCIC"]

    def assess(self, code: Code, material: Material):
        """
        Assess a Reference Event with a specific code and material

        Parameters
        ----------
        code : Code
            Design code to use.
        material : Material
            Material to use.

        Returns
        -------
        df
          dataframe containing the result of the assessement

        """
        assessment = code.assess(self, material)
        rows = []
        for rulename, vals in assessment.items():
            assessed = vals[0]
            rule = vals[1]
            for i, subrulename in enumerate(rule.description):
                try:
                    # Rounded at the MPa
                    applied = round(assessed[i][0] * 1e-6)
                except TypeError:
                    # The assessment is None, hence the assessment was not
                    # valid. Go the next one
                    continue

                allowable = assessed[i][1]
                if isinstance(allowable, np.ndarray) and len(allowable) == 1:
                    allowable = allowable[0]

                try:
                    allowable = round(allowable * 1e-6)
                except ValueError:
                    # it means is NaN
                    allowable = allowable
                except TypeError:
                    allowable = allowable

                if np.isnan(allowable):
                    allowable = "No Limit"
                    res = "Assessment not required"
                    sm = None
                else:
                    if applied < allowable:
                        res = "OK"
                    else:
                        res = "FAILED"
                    try:
                        sm = round(allowable / applied, 2)
                        if sm > 10:
                            sm = "> 10"
                    except ZeroDivisionError:
                        sm = "> 10"

                row = {
                    "ID": self.config.re_ID,
                    "Operating Conditions": self.config.oc,
                    "Initiating Event": self.config.ie,
                    "Concatenated Event": self.config.ce,
                    "Loading Category": self.config.load_ctg,
                    "Service Level": self.config.service_lvl,
                    "Rule Extended Description": rulename,
                    "Rule ID": rule.ref,
                    "Sub-Rule": subrulename,
                    "T [°C]": self.config.T,
                    "DPA": self.config.dpa,
                    "Applied [MPa]": applied,
                    "Allowable [MPa]": allowable,
                    "Result": res,
                    "Safety Margin": sm,
                    "Damage Type": rule.damage_type,
                }
                rows.append(row)

        df = pd.DataFrame(rows)
        self.assessment = df

        return self.assessment

    def computeVj(self, code: Code, material: Material):
        """
        Compute the fatigue usage fraction and returns a df containing all
        useful infos of the assessment

        Parameters
        ----------
        code : code.Code
            Design code to use.
        material : material.Material
            Material to use.

        Returns
        -------
        assessment : dict
            contains all infos of the performed assessment, Vj included.

        """
        assessment = code.computeVj(self, material)
        assessment["n"] = self.config.ncycles
        assessment["ID"] = self.config.re_ID
        assessment["Range"] = self.config.ce
        assessment["ctg"] = self.config.load_ctg
        assessment["lvl"] = self.config.service_lvl
        assessment["T"] = self.config.T
        assessment["dpa"] = self.config.dpa
        assessment["Operating conditions"] = self.config.oc
        assessment["Vj"] = self.config.ncycles / assessment["N"]

        self.fatigue_assessment = assessment

        return assessment


def _combine_linstresses(
    matrices: list[np.ndarray],
    combination_type: SpatialRecMethod = SpatialRecMethod.ALGEBRAIC,
) -> np.ndarray | None:
    if len(matrices) == 0:
        return None

    if len(matrices) == 1:
        return matrices[0]

    if combination_type == SpatialRecMethod.ALGEBRAIC:  # Algebraic sum
        new_value = matrices[0]
        for matrix in matrices[1:]:
            new_value = new_value + matrix

    elif combination_type == SpatialRecMethod.SRSS:  # Square Root of Sum of Squares
        new_value = matrices[0] ** 2
        for matrix in matrices[1:]:
            new_value = new_value + matrix**2
        new_value = new_value**0.5

    elif combination_type == SpatialRecMethod.ABS:  # Sum in absolute value
        new_value = np.abs(matrices[0])
        for matrix in matrices[1:]:
            new_value = new_value + np.abs(matrix)
    else:
        raise KeyError(combination_type + " is not a valid combination type")

    return new_value


def _combine_inertial_stresses(
    lin_stress_list: list[LinStress],
) -> list[LinStress]:
    groups: dict[str, list[LinStress]] = {}
    # group same inertial by name
    for lin_stress in lin_stress_list:
        main_name = lin_stress.config.name[:-2]
        if main_name not in groups.keys():
            groups[main_name] = [lin_stress]
        else:
            groups[main_name].append(lin_stress)

    # Perform spatial recombination for each group
    recombined = []
    for main_name, lin_stresses in groups.items():
        newstress = deepcopy(lin_stresses[0])
        newstress.config.name = main_name
        rec_meth = newstress.config.spatial_rec_method

        primary_list = [lin_stress.primary.values for lin_stress in lin_stresses]
        secondary_list = [lin_stress.secondary.values for lin_stress in lin_stresses]

        for matrix_list in [primary_list, secondary_list]:
            assert (
                len(matrix_list) == 3
            ), f"Issue in {main_name}. There should be 3 components for each inertial load (X, Y and Z)"

        new_primary = _combine_linstresses(primary_list, combination_type=rec_meth)
        new_secondary = _combine_linstresses(secondary_list, combination_type=rec_meth)
        newstress.primary = pd.DataFrame(
            new_primary,
            index=newstress.primary.index,
            columns=newstress.primary.columns,
        )
        newstress.secondary = pd.DataFrame(
            new_secondary,
            index=newstress.secondary.index,
            columns=newstress.secondary.columns,
        )
        recombined.append(newstress)

    return recombined


def von_mises(
    volumetric: np.ndarray | None, inertial: np.ndarray | None = None
) -> float:
    """
    Compute Von Mises or Equivalent Von mises depending on the given
    stress types

    Parameters
    ----------
    volumetric : np.ndarray | None
        volumetric linearized stress component.
    inertial : np.ndarray | None, optional
        inertial linearized stress component, if not None the ULVM
        formulation is used. The default is None.

    Returns
    -------
    vm : float
        resulting equivalent stress.

    """
    # None values must be avoided
    if volumetric is None and inertial is None:
        return 0  # there are no loads!
    else:
        vol = pd.Series(volumetric, index=STRESS_ORDER)

    # Standard Von Mises
    if inertial is None:
        A = vol.loc["Sx"] ** 2 + vol.loc["Sy"] ** 2 + vol.loc["Sz"] ** 2
        B = 3 * vol.loc["Sxy"] ** 2 + 3 * vol.loc["Sxz"] ** 2 + 3 * vol.loc["Syz"] ** 2
        C = (
            vol.loc["Sx"] * vol.loc["Sy"]
            + vol.loc["Sx"] * vol.loc["Sz"]
            + vol.loc["Sy"] * vol.loc["Sz"]
        )

        vm = (A + B - C) ** 0.5
    # Upper-Limit Von-Mises
    else:
        ine = pd.Series(inertial, index=STRESS_ORDER)
        if volumetric is None:
            # there are only inertial stresses
            vol = pd.Series([0, 0, 0, 0, 0, 0], index=STRESS_ORDER)
        vm = 0
        for comp in ["Sx", "Sy", "Sz"]:
            vm = vm + (ine.loc[comp] + abs(vol.loc[comp])) ** 2

        for comp in ["Sxy", "Sxz", "Syz"]:
            vm = vm + 3 * (ine.loc[comp] + abs(vol.loc[comp])) ** 2

        for i, j in [("Sx", "Sy"), ("Sy", "Sz"), ("Sx", "Sz")]:
            vm = vm + (
                np.abs(ine.loc[i] * ine.loc[j])
                + np.abs(ine.loc[i] * vol.loc[j])
                + np.abs(vol.loc[i] * ine.loc[j])
                - vol.loc[i] * vol.loc[j]
            )

        vm = vm**0.5

    return vm
