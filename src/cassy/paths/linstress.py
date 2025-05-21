# -*- coding: utf-8 -*-
"""
Created on Tue Nov 17 09:20:26 2020

@author: Davide Laghi
"""

from copy import deepcopy

import numpy as np
import pandas as pd


class LinStress:
    def __init__(
        self,
        stress_matrice: pd.DataFrame,
        name: str | None = None,
        unit: str = "Pa",
        stress_type: str = "P",
        load_type: str = "Volumetric",
        isPD: bool = False,
        isCyclic: bool = True,
        scale: float = 1,
        spatial_rec_method: str = "srss",
        ptype: str = "normal",
        isPressure: bool = False,
        correctPb: bool = False,
        Welding_n: float = 1,
        Welding_f: float = 1,
        isOccasional: float = False,
    ):
        """
        represent a linearized stress

        Parameters
        ----------
        stress_matrice : pd.DataFrame
            columns = [Sx, Sy, Sz, Sxy, Sxz, Syz]
            index = [Pm, Pb, F].
        name : str
            identifier of the stress. The default is None
        unit : str, optional
            Either 'MPa', 'KPa' or 'Pa'. The default is 'Pa'.
        stress_type : str
            Either 'P' or 'Q' (i. e. primary or secondary). The default is 'P'
        load_type : str
            Either 'Volumetric' or 'Inertial'. The default is 'Volumetric'
        isPD : bool
            if True the stress is a PLadma disruption induced stress.
            The default is False.
        isCyclic : bool
            if True the stress should be considered cyclic
        scale : float
            scale factor for the stresses
        spatial_rec : str
            method to use for spatial recombination. The default is 'srss'
        ptype : str
            type of the path where the linstress is computed
        isPressure : bool
            if True is a sustained loads. This causes different handling if
            the stress is evaluated in a "fillet" path. The deafult is False
        correctPb : bool
            if True Sz, Sxy, Sxz and Syz components of the Pm (bending) are
            set equal to zero. The default is False
        Welding_n : float
            Welded Joint coefficient of the path where the linstress is
            computed, the default value is 1.
        Welding_f : float
            Fatigue Strength Reduction Factor f where the linstress is
            computed, the default value is 1
        isOccasional : bool
            if True is an Occasional laod according to ASME B31.3


        Raises
        ------
        KeyError
            exception is raised for incorrect stress_type or load_tyoe.

        Returns
        -------
        None.

        """
        self.isPD = isPD
        self.isCyclic = isCyclic
        self.name = name
        self.spatial_rec_method = spatial_rec_method
        self.ptype = ptype
        self.isPressure = isPressure
        self.isOccasional = isOccasional
        self.correctPb = correctPb
        self.Welding_n = Welding_n
        self.Welding_f = Welding_f

        # Convert Unit to Pa and compute additional stresses
        stress_matrice = _safePascal(stress_matrice, unit) * scale
        self.original_mtrx = stress_matrice
        transp = stress_matrice.T  # Transpose to operate on columns
        # If Pb correction is activated
        if correctPb:
            for idx in ["Sz", "Sxy", "Sxz", "Syz"]:
                transp.loc[idx, "Pb"] = 0

        transp["PmPb"] = transp["Pm"] + transp["Pb"]
        transp["PmPbF"] = transp["PmPb"] + transp["F"]
        self.stress_matrice = transp.T  # transpose back

        if stress_type not in ["P", "Q"]:
            raise KeyError(str(stress_type) + " is not a valid stress type")
        self.stress_type = stress_type

        if load_type not in ["Volumetric", "Inertial"]:
            raise KeyError(str(load_type) + " is not a valid load type")
        self.load_type = load_type

    @classmethod
    def from_config(
        cls,
        name: str,
        df: pd.DataFrame,
        config: dict | pd.Series,
        ptype: str,
        Welding_n: float,
        Welding_f: float,
    ):
        """
        Generate a LinStress with the help of an Excel config file

        Parameters
        ----------
        cls : TYPE
            DESCRIPTION.
        name : str
            name of the load.
        df : pd.DataFrame
            linearized stress matrix (see __init__).
        config_df : dict | pd.Series
            information on the load type
        ptype : str
            type of the path where the linstress is computed
        Welding_n: float
            welded joint factor of the path where the linstress is computed
        Welding_f: float
            Fatigue Strength Reduction factor of the path where the linstress
            is computed


        Returns
        -------
        LinStress
            Linear stress created.

        """
        row = config
        return cls(
            df,
            name=name,
            unit=row["Unit"],
            stress_type=row["Stress Type"],
            load_type=row["Load Type"],
            isPD=row["Derives from Plasma Disruption"],
            isCyclic=row["Is Cyclic"],
            isOccasional=row["Is Occasional"],
            scale=row["Scale"],
            spatial_rec_method=row["Spatial Recombination"],
            ptype=ptype,
            isPressure=row["Is Pressure"],
            Welding_n=Welding_n,
            Welding_f=Welding_f,
        )

    @staticmethod
    def combine_matrices(linstresses, combination_type="algebraic"):
        """
        Given a list of linear stresses (or matrices) it returns the combined
        matrice of stress according to the selected combination option

        Parameters
        ----------
        linstresses : list of Linstress (or df)
            List of linestress or matrices to combine.
        combination_type : str, optional
            Either 'algebraic', 'abs' or 'srss'. The default is 'algebraic'.

        Raises
        ------
        KeyError
            for a not admitted combination_type.

        Returns
        -------
        new_matrice : pd.DataFrame
            new combined matrice of stresses.

        """
        matrices = []
        for linstress in linstresses:
            try:
                mtrx = linstress.stress_matrice
                if mtrx is not None:
                    matrices.append(mtrx)
            except AttributeError:
                # If not stress we suppose it is a matrix (or maybe None)
                if linstress is not None:
                    matrices.append(linstress)
        # Override
        linstresses = matrices

        if len(linstresses) == 0:
            new_matrice = None
        # If it is only one return himself
        elif len(linstresses) == 1:
            new_matrice = linstresses[0]

        elif combination_type == "algebraic":  # Algebraic sum
            new_matrice = linstresses[0]
            for linstress in linstresses[1:]:
                new_matrice = new_matrice + linstress

        elif combination_type == "srss":  # Square Root of Sum of Squares
            new_matrice = linstresses[0] ** 2
            for linstress in linstresses[1:]:
                new_matrice = new_matrice + linstress**2
            new_matrice = new_matrice**0.5

        elif combination_type == "abs":  # Sum in absolute value
            new_matrice = linstresses[0].abs()
            for linstress in linstresses[1:]:
                new_matrice = new_matrice + linstress.abs()
        else:
            raise KeyError(combination_type + " is not a valid combination type")

        return new_matrice


class ReferenceEvent:
    def __init__(
        self,
        lin_stress_list,
        n_welding,
        f_welding,
        matriceP_V,
        matriceP_I,
        matriceQ,
        service_lvl,
        T,
        dpa,
        name=None,
        cyclicP_V=None,
        SL=None,
        cyclicP_I=None,
        cyclicQ=None,
        maxP_V=None,
        maxP_I=None,
        PD_V=None,
        Ps_V=None,
        PD_I=None,
        Ps_I=None,
        Pns_I=None,
        Pns_V=None,
        oc=None,
        ie=None,
        ce=None,
        load_ctg=None,
        ncycles=None,
        isOccasional=False,
    ):
        """
        Recombination of linear stresses to assess a reference event.
        Units of the matrices must be already in Pa.

        Parameters
        ----------
        lin_stress_list : list
            list of the LinStress that are combined in the reference
        n_welding: float
            Welded Joint Coefficient
        f_welding: float
            Fatigue Strength Reduction Factor
        matriceP_V : pd.DataFrame
            volumetric primary stresses.
        matriceP_I : pd.DataFrame
            inertial primary stresses.
        matriceQ : pd.DataFrame
            secondary stresses.
        service_lvl : str
            Either 'A', 'C' or 'D'
        T : float
            Temperature of the path.
        dpa : float
            Displacement per atom value in the path.
        name : TYPE, optional
            Path name. The default is None.
        cyclicP_V : pd.DataFrame, optional
            Primary volumetric stresses to be considered cyclic
            (i.e. no plasma disruption). The default is None.
        SL : Stress due to Sustained Loads
        cyclicP_I : pd.DataFrame, optional
            Primary inertial stresses to be considered cyclic
            (i.e. no plasma disruption). The default is None.
        cyclicQ : pd.DataFrame, optional
            Primary inertial stresses to be considered cyclic
            (i.e. no plasma disruption). The default is None.
        maxP_V : pd.DataFrame, optional
            volumetric primary stresses to be considered for SDC-IC maxPmPb.
            They exclude plasma disruption derived loads
            The default is None.
        maxP_I : pd.DataFrame, optional
            inertial primary stresses to be considered for SDC-IC maxPmPb.
            They exclude plasma disruption derived loads
            The default is None.
        PD_V : pd.DataFrame, optional
            plasma distruption derived volumetric stresses.
            The default is None.
        PD_I : pd.DataFrame, optional
            plasma distruption derived volumetric stresses.
            The default is None.
        oc : str
            operating conditions. The default is None.
        ie : str
            initiating event. The default is None.
        ce : str
            concateneted event. The default is None.
        load_ctg : str
            loading category. The default is None
        ncycles : int
            number of total cycles for the reference event

        Returns
        -------
        None.

        """
        for lin_stress in lin_stress_list:
            if lin_stress.isOccasional:
                self.isOccasional = True
                break
            else:
                self.isOccasional = False
        self.lin_stress_list = lin_stress_list
        load_names = []
        for linstress in lin_stress_list:
            load_names.append(linstress.name)
        self.load_names = load_names
        self.name = name
        self.oc = oc
        self.ie = ie
        self.ce = ce
        self.assessment = None
        self.fatigue_assessment = None
        self.load_ctg = load_ctg
        self.matriceP_V = matriceP_V
        self.matriceP_I = matriceP_I
        self.matriceQ = matriceQ
        self.cyclicP_V = cyclicP_V
        self.cyclicP_I = cyclicP_I
        self.cyclicQ = (cyclicQ,)
        self.maxP_V = maxP_V
        self.maxP_I = maxP_I
        self.PD_V = PD_V
        self.SL = SL
        self.PD_I = PD_I
        self.T = T
        self.dpa = dpa
        self.n_welding = n_welding
        self.f_welding = f_welding
        loads = ""
        for i, load in enumerate(load_names):
            if i == len(load_names) - 1:  # it is the last load
                loads = loads + load
            else:
                loads = loads + load + "+ "
        self.loads_list = loads

        try:
            self.ncycles = int(ncycles)
        except TypeError:
            # It means that the number of cycles is None
            self.ncyles = None

        if service_lvl in ["A", "C", "D"]:
            self.service_lvl = service_lvl
        else:
            raise ValueError(str(service_lvl) + " is not an admitted service level")

        K = 1.5

        # --- Collect Elementary Stresses ---
        # Primary volumetric elementary stresses
        try:
            Pm_v = matriceP_V.loc["Pm"]
            Pb_v = matriceP_V.loc["Pb"]
            # PF_v = matriceP_V.loc['F']
            PmPb_v = matriceP_V.loc["PmPb"]
            PmPbPF_v = matriceP_V.loc["PmPbF"]
        except AttributeError:
            # There is no primary stress
            Pm_v = None
            Pb_v = None
            # PF_v = matriceP_V.loc['F']
            PmPb_v = None
            PmPbPF_v = None

        try:
            SL = SL.loc["PmPbF"]
        except AttributeError:  # there are not Sustained Loads
            SL = None

        self.Sl = self.von_mises(SL)  # Sustained Loads for ASME B31.3

        # Primary inertial elementary stresses
        try:
            Pm_i = matriceP_I.loc["Pm"]
            Pb_i = matriceP_I.loc["Pb"]
            # PF_i = matriceP_I.loc['F']
            PmPb_i = matriceP_I.loc["PmPb"]
            PmPbPF_i = matriceP_I.loc["PmPbF"]
        except AttributeError:
            # There is no inertial stress
            Pm_i = None
            Pb_i = None
            # PF_i = None
            PmPb_i = None
            PmPbPF_i = None

        # Secondary elementary stresses (considered all volumetric)
        # There may not be no seondary stresses
        try:
            Qm = matriceQ.loc["Pm"]
            # Qb = matriceQ.loc['Pb']
            # QF = matriceQ.loc['F']
            QmQb = matriceQ.loc["PmPb"]
            QmQbQF = matriceQ.loc["PmPbF"]
        except AttributeError:
            Qm = None
            QmQb = None
            QmQbQF = None

        # Get the max stress except plasma disruption induced ones
        try:
            maxPmPb_v = maxP_V.loc["PmPb"]
        except AttributeError:
            maxPmPb_v = None
        try:
            maxPmPb_i = maxP_I.loc["PmPb"]
        except AttributeError:
            maxPmPb_i = None

        # --- Collect Cyclic Stresses ---
        # All cyclic stresses
        # try:
        #     P_v_cyc = cyclicP_V.loc['PmPb']
        # except AttributeError:
        #     P_v_cyc = None
        # try:
        #     P_i_cyc = cyclicP_I.loc['PmPb']
        # except AttributeError:
        #     P_i_cyc = None
        try:
            Q_cyc = cyclicQ.loc["PmPb"]
        except AttributeError:
            Q_cyc = None

        # Get the plasma disruption ones
        try:
            deltaPD_V = PD_V.loc["PmPb"]
        except AttributeError:
            deltaPD_V = None
        try:
            deltaPD_I = PD_I.loc["PmPb"]
        except AttributeError:
            deltaPD_I = None

        # Get the overstress of short Duration both Inertial and Volumetric
        # ones
        try:
            Psm_V = Ps_V.loc["Pm"]
            PsmPsb_V = Ps_V.loc["PmPb"]
        except AttributeError:
            Psm_V = None
            PsmPsb_V = None

        try:
            Pm_ns_V = Pns_V.loc["Pm"]
            PmPb_ns_V = Pns_V.loc["PmPb"]
        except AttributeError:
            Pm_ns_V = None
            PmPb_ns_V = None

        try:
            Pm_ns_I = Pns_I.loc["Pm"]
            PmPb_ns_I = Pns_I.loc["PmPb"]
        except AttributeError:
            Pm_ns_I = None
            PmPb_ns_I = None

        try:
            Psm_I = Ps_I.loc["Pm"]
            PsmPsb_I = Ps_I.loc["PmPb"]

        except AttributeError:
            Psm_I = None
            PsmPsb_I = None

        # tresca for fatigue assessment
        if Pm_v is None and Pm_i is None:
            # there are not primary stresses
            self.tresca = None
        else:
            if Pm_i is None:
                # there are only volumetric stresses
                tresca_i = None
                tresca_v = matriceP_V.loc["Pm"] + 0.67 * matriceP_V.loc["Pb"]
            if Pm_v is None:
                # there are only inertial stresses
                tresca_i = matriceP_I.loc["Pm"] + 0.67 * matriceP_I.loc["Pb"]
                # print(self.name)
                # print(tresca_i)
                tresca_v = None
            if Pm_v is not None and Pm_i is not None:
                # there are both inertial and volumetric stresses
                tresca_i = matriceP_I.loc["Pm"] + 0.67 * matriceP_I.loc["Pb"]
                tresca_v = matriceP_V.loc["Pm"] + 0.67 * matriceP_V.loc["Pb"]
            self.tresca = self.von_mises(tresca_v, ine=tresca_i)

        # --- Equivalent stresses for P-Type assessment ---
        # Primary Membrane Stress
        self.Pm = self.von_mises(Pm_v, ine=Pm_i)
        # Primary Bending Stress
        self.Pb = self.von_mises(Pb_v, ine=Pb_i)
        # Primary Linear Stress
        self.PmPb = self.von_mises(PmPb_v, ine=PmPb_i)
        # Primary plus Secondary Membrane
        self.PmQm = self.von_mises([Pm_v, Qm], ine=Pm_i)
        # Total Stress Excluding Peak
        self.PQ = self.von_mises([PmPb_v, QmQb], ine=PmPb_i)
        # Total Stress
        self.PQF = self.von_mises([PmPbPF_v, QmQbQF], ine=PmPbPF_i)
        # Total Primary Stress
        self.PF = self.von_mises(PmPbPF_v, ine=PmPbPF_i)

        self.PmPbQm = self.von_mises([PmPb_v, Qm], ine=PmPb_i)

        self.dq = self.von_mises(Q_cyc)

        # --- Equivalent stresses for M-Type assessment ---
        # --- Ratcheting ---
        # maximum local primary membrane plus bending stress intensity
        # (excluding plasma disruption loadings)
        self.maxPmPb = self.von_mises(maxPmPb_v, maxPmPb_i)
        # maximum in the thickness stress intensity range
        # Here it is assumed that plasma induced load is always cyclic
        if Q_cyc is None:
            self.cyc_dPQ = self.von_mises(deltaPD_V, ine=deltaPD_I)

        elif self.von_mises(deltaPD_V, ine=deltaPD_I) is None:
            self.cyc_dPQ = self.von_mises(Q_cyc)

        else:
            self.cyc_dPQ = self.von_mises(deltaPD_V, ine=deltaPD_I) + self.von_mises(
                Q_cyc
            )
        # 3Sm stress
        if self.maxPmPb is None:
            self.Sm3_stress = self.cyc_dPQ
        elif self.cyc_dPQ is None:
            # If there are no cyclic loads, no ratcheting should be assessed
            self.Sm3_stress = None
        else:
            self.Sm3_stress = self.maxPmPb + self.cyc_dPQ

        # 3Sm stress RCCMR
        if self.PmPb is None:
            self.Sm3_stress_RCCMR = self.von_mises(Q_cyc)
        elif Q_cyc is None:
            self.Sm3_stress_RCCMR = None
        else:
            self.Sm3_stress_RCCMR = self.PmPb + self.von_mises(Q_cyc)

        # stress of short duration for Efficiency Index
        self.Pms = self.von_mises(Psm_V, Psm_I)
        self.PmPbs = self.von_mises(PsmPsb_V, ine=PsmPsb_I)

        # stress excluding stress of short duration
        self.Pm_ns = self.von_mises(Pm_ns_V, ine=Pm_ns_I)
        self.PmPb_ns = self.von_mises(PmPb_ns_V, ine=PmPb_ns_I)
        self.PmQm_ns = self.von_mises([Pm_ns_V, Qm], ine=Pm_ns_I)
        self.PmPbQm_ns = self.von_mises([PmPb_ns_V, Qm], ine=PmPb_ns_I)

        # Bree Stress for Ratcheting assessment
        if Pm_v is None and Pm_i is None:
            self.PmPb_bree = 0
        else:
            if Pm_i is None:
                # there are only volumetric stresses
                PmPb_bree_v = matriceP_V.loc["Pm"] + 1 / K * matriceP_V.loc["Pb"]
                PmPb_bree_i = None

            if Pm_v is None:
                # there are only inertial stress
                PmPb_bree_v = None
                PmPb_bree_i = matriceP_I.loc["Pm"] + 1 / K * matriceP_I.loc["Pb"]

            if Pm_v is not None and Pm_i is not None:
                PmPb_bree_v = matriceP_V.loc["Pm"] + 1 / K * matriceP_V.loc["Pb"]
                PmPb_bree_i = matriceP_I.loc["Pm"] + 1 / K * matriceP_I.loc["Pb"]

            self.PmPb_bree = self.von_mises(PmPb_bree_v, PmPb_bree_i)

    @classmethod
    def from_recombination(
        cls,
        lin_stress_list,
        service_lvl,
        name,
        T,
        dpa,
        oc=None,
        ie=None,
        ce=None,
        load_ctg=None,
        ncycles=None,
        isOccasional=False,
    ):
        """
        Create a RecombinedLinStress from a list of single loads
        (linear stresses)

        Parameters
        ----------
        cls : TYPE
            DESCRIPTION.
        lin_stress_list : list of LinStress
            list of linear stresses of the single loads in the event.
        service_lvl : str
            Either 'A', 'C' or 'D'.
        name : str
            name of the event.
        T : float
            Temperature of the path.
        dpa : float
            Displacement per atom value in the path.
        oc : str
            operating conditions. The default is None.
        ie : str
            initiating event. The default is None.
        ce : str
            concateneted event. The default is None.
        ncycles : int
            number of total cycles for fatigue assessment

        Returns
        -------
        RecombinedLinStress
            the equivalent event stress.

        """
        # Initialize matrix
        stress_dic = {}
        in_dic = {}
        vol_types = [
            "PV",
            "Q",
            "cyc_PV",
            "cyc_Q",
            "maxPV",
            "PD_V",
            "SL",
            "shortPV",
            "noshortPV",
        ]
        in_types = ["PI", "cyc_PI", "maxPI", "PD_I", "shortPI", "noshortPI"]
        # Initialize for each type of stress its  list of
        # stresses to combine in order to obtain it
        for stress in vol_types:
            stress_dic[stress] = []
        for stress in in_types:
            in_dic[stress] = {}

        # ### Organize stresses ###
        for lin_stress in lin_stress_list:
            n_welding = lin_stress.Welding_n
            f_welding = lin_stress.Welding_f
            # --- Collect Volumetric Stresses ---
            if lin_stress.load_type == "Volumetric":
                # PRIMARY
                if lin_stress.stress_type == "P":
                    # Pb has to be considered secondary load in case of fillet
                    # and a "pressure" load
                    if lin_stress.ptype == "fillet" and lin_stress.isPressure:
                        # Create copies of the original stress
                        orig_stress = deepcopy(lin_stress)
                        lin_stress = deepcopy(orig_stress)
                        # Transpose the stress matrice to easily operate on it
                        mtrx = lin_stress.stress_matrice.T
                        # Memorize Pb
                        Pb = deepcopy(mtrx["Pb"])
                        # Adjourn the primary matrix
                        for column in ["Pb", "PmPb", "PmPbF"]:
                            mtrx[column] = mtrx[column] - Pb
                        lin_stress.stress_matrice = mtrx.T
                        # create the new Q matrix to add in secondaries
                        df = pd.DataFrame()
                        for col in ["Pm", "F"]:
                            df[col] = [0, 0, 0, 0, 0, 0]
                        for col in ["Pb", "PmPb", "PmPbF"]:
                            df[col] = Pb.values
                        df.index = ["Sx", "Sy", "Sz", "Sxy", "Syz", "Sxz"]
                        orig_stress.stress_matrice = df.T
                        orig_stress.type = "Q"
                        # Now original stress needs to be added to secondaries
                        stress_dic["Q"].append(orig_stress)
                        if orig_stress.isCyclic:
                            stress_dic["cyc_Q"].append(orig_stress)

                    # --- Regular Operations ---
                    # The volumetric load is always added to the general list
                    # of volumetrics
                    stress_dic["PV"].append(lin_stress)
                    # SDC-IC requires to distinguish plasma derived stresses
                    # for the 3sm rules
                    if not lin_stress.isPD:  # for the maxPmPb
                        stress_dic["maxPV"].append(lin_stress)
                    else:  # for the deltaP computation
                        stress_dic["PD_V"].append(lin_stress)
                    # Register the stress if cyclic
                    if lin_stress.isCyclic:
                        stress_dic["cyc_PV"].append(lin_stress)
                    elif lin_stress.isPressure:
                        stress_dic["SL"].append(lin_stress)
                    elif lin_stress.isOccasional:
                        stress_dic["shortPV"].append(lin_stress)
                    else:
                        stress_dic["noshortPV"].append(lin_stress)

                # SECONDARY
                elif lin_stress.stress_type == "Q":
                    # Always register it among secondaries
                    stress_dic["Q"].append(lin_stress)
                    if lin_stress.isCyclic:  # register if cyclic
                        stress_dic["cyc_Q"].append(lin_stress)

            # --- Collect Inertial Stresses ---
            # No secondary inertial stress is allowed here
            # If they are inertial we should expect them to be linked 3 by 3
            # (X, Y and Z) component -> must be explicitly in the stress name
            elif lin_stress.load_type == "Inertial":
                if lin_stress.stress_type == "Q":
                    raise ValueError("Inertial loads as Q are not implemented")
                main_name = lin_stress.name[:-2]

                # Register in primary inertial
                if main_name not in in_dic["PI"].keys():
                    in_dic["PI"][main_name] = [lin_stress]
                else:
                    in_dic["PI"][main_name].append(lin_stress)

                # Again here is the split needed for 3Sm
                if not lin_stress.isPD:  # No derives from plasma disruption
                    if main_name not in in_dic["maxPI"].keys():
                        in_dic["maxPI"][main_name] = [lin_stress]
                    else:
                        in_dic["maxPI"][main_name].append(lin_stress)

                # Again here is the split needed for Efficiency Index
                if lin_stress.isOccasional:  # overstress of short duration
                    if main_name not in in_dic["shortPI"].keys():
                        in_dic["shortPI"][main_name] = [lin_stress]
                    else:
                        in_dic["shortPI"][main_name].append(lin_stress)
                if not lin_stress.isOccasional:
                    if main_name not in in_dic["noshortPI"].keys():
                        in_dic["noshortPI"][main_name] = [lin_stress]
                    else:
                        in_dic["noshortPI"][main_name].append(lin_stress)
                else:  # derives from plasma disruption
                    if main_name not in in_dic["PD_I"].keys():
                        in_dic["PD_I"][main_name] = [lin_stress]
                    else:
                        in_dic["PD_I"][main_name].append(lin_stress)

                if lin_stress.isCyclic:  # Add it to the cyclic list
                    if main_name not in in_dic["cyc_PI"].keys():
                        in_dic["cyc_PI"][main_name] = [lin_stress]
                    else:
                        in_dic["cyc_PI"][main_name].append(lin_stress)

        # ### Spatial Recombination of Inertial ###
        for stresstype, dic in in_dic.items():
            spatially_recombined = []
            for main_name, stresses in dic.items():
                rec_meth = stresses[0].spatial_rec_method
                mtrx = LinStress.combine_matrices(stresses, combination_type=rec_meth)
                spatially_recombined.append(mtrx)
            # Add it to the main dic
            stress_dic[stresstype] = spatially_recombined

        # ### Compute matrices ###
        matrices = {}
        for stresstype, stresslist in stress_dic.items():
            if len(stresslist) == 0:
                mtrx = None
            elif len(stresslist) == 1:
                try:
                    mtrx = stresslist[0].stress_matrice
                except AttributeError:
                    mtrx = stresslist[0]
            else:
                # All inertial are recombined in SRSS between them
                # Different recombinations are allowed only between spatial
                # comps. The others are recombined algebraically
                if stresstype in in_types:
                    mtrx = LinStress.combine_matrices(
                        stresslist, combination_type="srss"
                    )
                else:
                    mtrx = LinStress.combine_matrices(
                        stresslist, combination_type="algebraic"
                    )
            matrices[stresstype] = mtrx

        return cls(
            lin_stress_list,
            n_welding,
            f_welding,
            matrices["PV"],
            matrices["PI"],
            matrices["Q"],
            service_lvl,
            T,
            dpa,
            name=name,
            cyclicP_V=matrices["cyc_PV"],
            SL=matrices["SL"],
            cyclicP_I=matrices["cyc_PI"],
            cyclicQ=matrices["cyc_Q"],
            maxP_V=matrices["maxPV"],
            maxP_I=matrices["maxPI"],
            PD_V=matrices["PD_V"],
            Ps_I=matrices["shortPI"],
            Ps_V=matrices["shortPV"],
            Pns_I=matrices["noshortPI"],
            Pns_V=matrices["noshortPV"],
            PD_I=matrices["PD_I"],
            oc=oc,
            ie=ie,
            ce=ce,
            load_ctg=load_ctg,
            ncycles=ncycles,
            isOccasional=isOccasional,
        )

    @staticmethod
    def von_mises(vol, ine=None):
        """
        Compute Von Mises or Equivalent Von mises depending on the given
        stress types

        Parameters
        ----------
        vol : pd.Series (or list of series)
            volumetric linearized stress component.
        ine : pd.Series, optional
            volumetric linearized stress component, if not None the ULVM
            formulation is used. The default is None.
        onlyine : bool, optional
            if True the vol is actually an inertial load and a simil ULVM is
            computed instead of normal Von Mises

        Returns
        -------
        vm : float
            resulting equivalent stress.

        """
        # Volumetric loads can be algebrically sum. None values must
        # be avoided though
        idx = ["Sx", "Sy", "Sz", "Sxy", "Sxz", "Syz"]
        new_vol = pd.Series([0, 0, 0, 0, 0, 0], index=idx)
        if type(vol) == list:
            for s in vol:
                if s is not None:
                    new_vol = new_vol + s
        else:
            if vol is None and ine is None:
                return None  # there are no loads!
            else:
                new_vol = vol
        vol = new_vol
        # Standard Von Mises
        if ine is None:
            A = vol.loc["Sx"] ** 2 + vol.loc["Sy"] ** 2 + vol.loc["Sz"] ** 2
            B = (
                3 * vol.loc["Sxy"] ** 2
                + 3 * vol.loc["Sxz"] ** 2
                + 3 * vol.loc["Syz"] ** 2
            )
            C = (
                vol.loc["Sx"] * vol.loc["Sy"]
                + vol.loc["Sx"] * vol.loc["Sz"]
                + vol.loc["Sy"] * vol.loc["Sz"]
            )

            vm = (A + B - C) ** 0.5
        # Upper-Limit Von-Mises
        else:
            if vol is None:
                # there are only inertial stresses
                idx = ["Sx", "Sy", "Sz", "Sxy", "Sxz", "Syz"]
                vol = pd.Series([0, 0, 0, 0, 0, 0], index=idx)
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

    def assess(self, code, material):
        """
        Assess a Reference Event with a specific code and material

        Parameters
        ----------
        code : code.Code
            Design code to use.
        material : material.Material
            Material to use.

        Returns
        -------
        df
          dataframe containing the result of the assessement

        """
        assessment = code.assess(self, material, self.T, self.dpa)
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
                    allowable = allowable.item()
                except TypeError:
                    allowable = allowable.item()

                if applied < allowable:
                    res = "OK"
                    try:
                        sm = round(allowable / applied, 2)
                        if sm > 10:
                            sm = "> 10"
                    except ZeroDivisionError:
                        sm = "> 10"
                elif np.isnan(allowable):
                    # This happens also for interpolations out of range!
                    allowable = "No Limit"
                    res = "Assessment not required"
                    sm = None
                else:
                    res = "FAILED"
                    sm = None

                row = {
                    "ID": self.name,
                    "Operating Conditions": self.oc,
                    "Initiating Event": self.ie,
                    "Concatenated Event": self.ce,
                    "Loading Category": self.load_ctg,
                    "Service Level": self.service_lvl,
                    "Rule Extended Description": rulename,
                    "Rule ID": rule.ref,
                    "Sub-Rule": subrulename,
                    "T [°C]": self.T,
                    "dpa": self.dpa,
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

    def computeVj(self, code, material):
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
        assessment : dic
            contains all infos of the performed assessment, Vj included.

        """
        assessment = code.computeVj(self, material, self.T, self.dpa)
        assessment["n"] = self.ncycles
        assessment["ID"] = self.name
        assessment["Range"] = self.ce
        assessment["ctg"] = self.load_ctg
        assessment["lvl"] = self.service_lvl
        assessment["T"] = self.T
        assessment["dpa"] = self.dpa
        assessment["Operating conditions"] = self.oc
        assessment["Vj"] = self.ncycles / assessment["N"]

        self.fatigue_assessment = assessment

        return assessment


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
