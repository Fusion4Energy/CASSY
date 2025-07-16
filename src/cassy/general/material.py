"""
Created on Thu Mar  5 13:01:17 2020

@author: Davide Laghi
"""

from __future__ import annotations

import logging
import os
import warnings
from functools import partial

import numpy as np
import pandas as pd
from scipy import interpolate
from scipy.spatial import Delaunay
from xlrd import XLRDError

from cassy.auxiliary.types import PathLike
from cassy.general.Nueber_rule import compute_Nueber


class Material:
    def __init__(self, excel_data: os.PathLike, name: str = None):
        """Object containing and processing material data

        Parameters
        ----------
        excel_data : os.PathLike
            path to the excel file containing the data
        name : str, optional
            name of the material, by default None
        """
        # --- Read Material properties---
        if name is None:
            filename = os.path.basename(excel_data)
            self.name = filename.split(".")[0]
        else:
            self.name = name

        # Poisson ratio
        nu = pd.read_excel(excel_data, sheet_name="Nu")
        nu = _cleanNA(nu)
        self.nu = float(nu.values[0][0])

        # Young modulus
        E_table = pd.read_excel(excel_data, sheet_name="Young Modulus")
        E_table = _cleanNA(E_table)
        self.E_table = E_table
        self.E = interpolate.interp1d(
            E_table["T"].values, E_table["E [GPa]"].values * 1e9
        )

        try:
            # This is needed for RCCMRx piping assessment
            alpha_table = pd.read_excel(excel_data, sheet_name="alpha")
            alpha_table = _cleanNA(alpha_table)
            self.alpha_table = alpha_table
            self.alpha = interpolate.interp1d(
                alpha_table["T"].values, alpha_table["alpha [1/K]"].values
            )
        except ValueError:
            # If it is not implemented it is ok, an error will be raised while
            # trying to access the alpha attribute only during RCC-MRx
            # assessment
            pass

        # Read n0 for monotonic epsilon calculation
        try:
            # This is needed for RCCMRx piping assessment
            n0_table = pd.read_excel(excel_data, sheet_name="n0")
            n0_table = _cleanNA(n0_table)
            self.n0_table = n0_table
            self.n0 = interpolate.interp1d(n0_table["T"].values, n0_table["n0"].values)
        except ValueError:
            # If it is not implemented it is ok, since only EUROFER has this
            # parameter as a table
            pass

        # Read C0 for monotonic epsilon calculation
        try:
            # This is needed for RCCMRx piping assessment
            C0_table = pd.read_excel(excel_data, sheet_name="C0")
            C0_table = _cleanNA(C0_table)
            self.C0_table = C0_table
            self.C0 = interpolate.interp1d(n0_table["T"].values, C0_table["C0"].values)
        except ValueError:
            # If it is not implemented it is ok, since only EUROFER has this
            # parameter as a table
            pass

        # --- Fatigue data ---
        # K, m
        K_table = pd.read_excel(excel_data, sheet_name="K-m")
        K_table = _cleanNA(K_table)
        self.K = interpolate.interp1d(K_table["T"].values, K_table["K"].values)
        self.m = interpolate.interp1d(K_table["T"].values, K_table["m"].values)

        # Keps/Kmu
        K = {}
        for k in ["Keps", "Kmu"]:
            k_table = pd.read_excel(excel_data, sheet_name=k, skiprows=1)
            k_table = _cleanNA(k_table)
            k_table.set_index("T", inplace=True)
            K[k] = _interpolate_df(k_table)  # (T, ds)

        self.Keps = K["Keps"]
        self.Kmu = K["Kmu"]

        # Keff,rec
        Keff_rec_table = pd.read_excel(excel_data, sheet_name="Keff_rec", skiprows=2)
        Keff_rec_table = _cleanNA(Keff_rec_table)
        self.Keff_rec_table = Keff_rec_table.set_index("T [°C]")
        self.Keff_rec = _interpolate_df(self.Keff_rec_table)  # (T,dpa)

        # Get number of Cycles
        values = pd.read_excel(excel_data, sheet_name="Fatigue Curves", skiprows=2)
        values = list(values.columns)[0]
        if values == "stress":
            self.fatigue_curve = "stress"
        elif values == "strain":
            self.fatigue_curve = "strain"
        else:
            raise ValueError(
                name + " fatigue curve values must be either" + ' "stress" or "strain"'
            )
        self.fatigue_values = values
        fatigue_table = pd.read_excel(
            excel_data, sheet_name="Fatigue Curves", skiprows=3
        )
        fatigue_table = _cleanNA(fatigue_table)
        fatigue_table = fatigue_table.set_index("Ncycles")
        self.fatigue_table = fatigue_table

        points = []
        values = []
        newcols = map(str, list(fatigue_table.columns))
        fatigue_table.columns = newcols
        for column in fatigue_table.columns:
            for idx, row in fatigue_table.iterrows():
                values.append(int(idx))
                point = [int(column), float(row[column])]
                points.append(point)

        self.N = self._build_grid_interpolator(points, values)  # (T,e/s)

        #  --- Allowables ---
        # Sm irr
        Sm_table = pd.read_excel(excel_data, sheet_name="Sm", skiprows=2)
        Sm_table = _cleanNA(Sm_table)
        self.Sm_table = Sm_table.set_index("T [°C]") * 1e6
        self.Sm_irr = _interpolate_df(self.Sm_table)  # (T, dpa)

        # Sy min
        Sy_min_table = pd.read_excel(excel_data, sheet_name="Sy_min", skiprows=2)
        Sy_min_table = _cleanNA(Sy_min_table)
        self.Sy_min_table = Sy_min_table.set_index("T [°C]") * 1e6
        self.Sy_min = _interpolate_df(self.Sy_min_table)  # (T, dpa)

        # Sy mean
        try:
            Sy_moy_table = pd.read_excel(excel_data, sheet_name="Sy_moy", skiprows=2)
            Sy_moy_table = _cleanNA(Sy_moy_table)
            self.Sy_moy_table = Sy_moy_table.set_index("T [°C]") * 1e6
            self.Sy_moy = _interpolate_df(self.Sy_moy_table)  # (T, dpa)
        except ValueError:
            # If it is not implemented it is ok, an error will be raised while
            # trying to access the Sy_moy attribute only during RCC-MRx
            # assessment
            pass

        # Su min
        Su_min_table = pd.read_excel(excel_data, sheet_name="Su_min", skiprows=2)
        Su_min_table = _cleanNA(Su_min_table)
        self.Su_min_table = Su_min_table.set_index("T [°C]") * 1e6
        self.Su_min = _interpolate_df(self.Su_min_table)  # (T, dpa)

        # Se
        Se_table = pd.read_excel(excel_data, sheet_name="Se", skiprows=2)
        Se_table = _cleanNA(Se_table)
        Se_table.set_index("T [°C]", inplace=True)
        with pd.option_context("future.no_silent_downcasting", True):
            Se_table = Se_table.replace(
                to_replace="No limit", value=np.nan
            ).infer_objects()
        self.Se_table = Se_table * 1e6
        self.Se = _interpolate_df(self.Se_table)  # (T, dpa)

        # Sd (inluding peak stress and supposing TF =2)
        Sd_table = pd.read_excel(excel_data, sheet_name="Sd", skiprows=2)
        Sd_table = _cleanNA(Sd_table)
        Sd_table.set_index("T [°C]", inplace=True)
        with pd.option_context("future.no_silent_downcasting", True):
            Sd_table = Sd_table.replace(
                to_replace="No limit", value=np.nan
            ).infer_objects()
        self.Sd_table = Sd_table * 1e6
        self.Sd = _interpolate_df(self.Sd_table)  # (T, dpa)

        # Sd (excluding peak stress and supposing TF =2)
        Sd_nopeak_table = pd.read_excel(excel_data, sheet_name="Sd_nopeak", skiprows=2)
        Sd_nopeak_table = _cleanNA(Sd_nopeak_table)
        Sd_nopeak_table.set_index("T [°C]", inplace=True)
        with pd.option_context("future.no_silent_downcasting", True):
            Sd_nopeak_table = Sd_nopeak_table.replace(
                to_replace="No limit", value=np.nan
            ).infer_objects()
        self.Sd_nopeak_table = Sd_nopeak_table * 1e6
        self.Sd_nopeak = _interpolate_df(self.Sd_nopeak_table)  # (T, dpa)

        # Monotonic stress-strain
        if name == "316L (non leak-tight)":
            # Up to 5%
            df = pd.read_excel(
                excel_data,
                sheet_name="Monotonic stress-strain",
                usecols="A:M",
                skiprows=1,
            )
            df = _cleanNA(df)
            df = df.set_index("T [°C]")
            df.columns = df.columns * 1e6  # Mpa -> Pa
            self.mon_stress_strain_5 = _interpolate_df(df)  # (T, sigma)

            # > 5%
            # there is a need to go around a weird bug in pandas that adds
            # some .1 after header values
            df = pd.read_excel(
                excel_data,
                sheet_name="Monotonic stress-strain",
                usecols="O:AC",
                skiprows=0,
            )
            cols = df.iloc[0].values
            df = pd.read_excel(
                excel_data,
                sheet_name="Monotonic stress-strain",
                usecols="O:AC",
                skiprows=1,
            )
            df.columns = cols
            df = _cleanNA(df)
            df = df.set_index("T [°C]")
            df.columns = df.columns * 1e6  # Mpa -> Pa
            self.mon_stress_strain_up = _interpolate_df(df)  # (T, sigma)

        # True stress-strain curve
        try:
            self.monotonic_stress_strain_table = pd.read_excel(
                excel_data, sheet_name="TrueStressStrain"
            )
        except (ValueError, XLRDError):
            self.monotonic_stress_strain_table = None
        try:
            self.monotonic_stress_strain_table2 = pd.read_excel(
                excel_data, sheet_name="TrueStressStrain2"
            )
        except (ValueError, XLRDError):
            self.monotonic_stress_strain_table2 = None

    def Nueber(self, T, s):
        E = self.E(T)
        df1 = self.monotonic_stress_strain_table  # up to 1.5% of strain

        df2 = self.monotonic_stress_strain_table2  # up to 30% of strain

        if df1 is None and df2 is None:
            warnings.warn(
                "Monotonic Stress-Strain Curves not implemented for "
                + self.name
                + ", Nueber rule returns nominal values"
            )
            return {"stress": s, "Young": E}

        else:
            return compute_Nueber(df1, df2, T, s, E)

    def cyclic_stress_strain(self, T, ds):
        E = self.E(T)
        K = self.K(T)
        m = self.m(T)

        if K == 0 and m == 0:
            raise ValueError("No cyclic stress-strain curve is defined")

        de_tot = 100 * ds * (2 * (1 + self.nu) / (3 * E)) + (ds / K) ** (1 / m)

        return de_tot

    def cyclic_stress_strain_1(self, T, ds):
        E = self.E(T)
        K = self.K(T)
        m = self.m(T)

        if K == 0 and m == 0:
            raise ValueError("No cyclic stress-strain curve is defined")

        de_CP = (ds / K) ** (1 / m)

        return de_CP

    def get_Keff(self, T_dpa, K):
        # To check if it is the same for all materials
        k_rect = self.Keff_rec(T_dpa)
        return 1 + 2 * (K - 1) * (k_rect - 1)

    def _inconel_N(self, max_stress, SA):
        df = self.fatigue_table
        try:
            newcols = map(str, list(df.columns))
        except ValueError:
            # There are NaNs most probably
            # print the problematic df for additional debug
            print(df)
            raise ValueError("Problem in the excel table cell values")
        df.columns = newcols
        for column in df.columns:
            if max_stress < float(column):
                # the right column will be the last in memory
                break
        N = interpolate.interp1d(df[column].values, df.index)
        return N(SA)

    @staticmethod
    def _build_grid_interpolator(
        points: np.ndarray, values: np.ndarray
    ) -> interpolate.LinearNDInterpolator:
        # let's be sure that inputs are indeed arrays
        points = np.array(points)
        values = np.array(values)
        # Compute the triangulation
        tri = Delaunay(points)
        # Perform the interpolation with the given values:
        interpolator = interpolate.LinearNDInterpolator(tri, values)

        return interpolator

    def get_monotonic_eps(self, sigma: float, T: float, dpa: float) -> float:
        """Function that contains all average stress-strain curves for the
        different materials

        Parameters
        ----------
        sigma : float
            _description_

        T: float
            temperature for the evaluation of epsilon

        dpa: float
            DPA for the evaluation of epsilon

        Returns
        -------
        eps: float
            total true strain

        Raises
        ------
        NotImplementedError
            if the formula has not been implemented for the selecte material
        ValueError
            in some cases if the valid ranges for the formulas are exceeded
        """
        msg_limit = "The limit of epsilon  has been reached for {} due to sigma {}"
        if self.name == "SS316L(N)-IG":
            C0 = 1.198
            alpha = 1 / 0.1125
            eps = (
                100 * sigma / self.E(T)
                + (sigma / (C0 * 1.28 * self.Sy_moy([T, dpa])[0])) ** alpha
            ) / 100
            eps_MP = ((sigma / (C0 * 1.28 * self.Sy_moy([T, dpa])[0])) ** alpha) / 100
            # For SS316L(N)-IG the formula is valid only up to 1%
            if eps > 0.015:
                raise ValueError(msg_limit.format(eps, self.name))
        elif self.name == "316L (non leak-tight)":
            C0 = 1.198
            alpha = 1 / 0.1125
            eps = (
                100 * sigma / self.E(T)
                + (sigma / (C0 * self.Sy_moy([T, dpa])[0])) ** alpha
            ) / 100
            eps_MP = ((sigma / (C0 * self.Sy_moy([T, dpa])[0])) ** alpha) / 100
            # For SS316L(N)-IG the formula is valid only up to 1.2%
            if eps > 0.01:
                # try with the up to 0.05 interpolation
                eps = self.mon_stress_strain_5((T, sigma))[0]
                if np.isnan(eps):
                    # 5% was exceeded then, try with second table
                    eps = self.mon_stress_strain_up((T, sigma))[0]
                    if np.isnan(eps):
                        # all limits have been exceeded
                        print(T)
                        raise ValueError(msg_limit.format(self.name, sigma))
                    else:
                        eps_MP = eps - sigma / self.E(T)
                else:
                    eps_MP = eps - sigma / self.E(T)
            if eps_MP < 0:
                eps_MP = 0
        elif self.name == "EUROFER":
            n0 = self.n0(T)
            alpha = 1 / n0
            C0 = self.C0(T)
            eps = (
                100 * sigma / self.E(T)
                + (sigma / (C0 * self.Sy_moy([T, dpa])[0])) ** alpha
            ) / 100
            eps_MP = ((sigma / (C0 * self.Sy_moy([T, dpa])[0])) ** alpha) / 100
        else:
            msg = "True stress-strain cycle is not implemented for: {}"
            raise NotImplementedError(msg.format(self.name))

        return eps, eps_MP


def linear_interp(points, values, point):
    return interpolate.interpn(points, values, point, bounds_error=False)


def _interpolate_df(df):
    """
    Given a df return an interpolator for i, j values

    Parameters
    ----------
    df : pd.DataFrame
        data for interpolation.

    Returns
    -------
    function
        interpolator that takes (i, j) as argument.

    """
    points = []
    values = []
    xs = []
    ys = []
    try:
        newcols = map(str, list(df.columns))
    except ValueError:
        # There are NaNs most probably
        # print the problematic df for additional debug
        print(df)
        raise ValueError("Problem in the excel table cell values")
    df.columns = newcols

    for column in df.columns:
        y = float(column)
        ys.append(y)

    for idx, row in df.iterrows():
        value = []
        x = float(idx)
        xs.append(x)
        value = row.values
        values.append(value)

    points = (xs, ys)
    interpolator = partial(linear_interp, points, values)

    # return Material._build_grid_interpolator(points, values)
    return interpolator


def _cleanNA(df):
    # Drop all rows containing only NaN
    df.dropna(axis=0, how="all", inplace=True)
    # Drop all columns containing only NaN
    df.dropna(axis=1, how="all", inplace=True)

    return df


def read_materials(mat_folder: PathLike) -> dict[str, Material]:
    """Parse all materials listed in a folder as excel files.

    Parameters
    ----------
    mat_folder : os.PathLike
        folder containing the excel files describing the materials data

    Returns
    -------
    dict[str, Material]
        parsed material objects
    """
    materials = {}
    for file in os.listdir(mat_folder):
        if file.endswith(".xlsx"):
            logging.info("Reading {}".format(file))
            filepath = os.path.join(mat_folder, file)
            matname = file.split(".")[0]
            material = Material(filepath, name=matname)
            materials[matname] = material

    return materials
