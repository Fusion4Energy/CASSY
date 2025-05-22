# -*- coding: utf-8 -*-
"""
Created on Tue Dec 22 14:05:28 2020

@author: davide laghi
"""

from math import pi

import numpy as np
import pandas as pd


class SectionActions:
    def __init__(
        self,
        primary,
        all_loads,
        service_lvl,
        poa,
        T,
        dpa,
        oc=None,
        ie=None,
        ce=None,
        load_ctg=None,
        name=None,
        code=None,
        loads_type=None,
    ):
        """
        Object handling the internal actions extracted on a surface

        Parameters
        ----------
        primary : dic or similar
            contains the primary actions acting on the bolt.
        all_loads : dic or similar
            contains the actions deriving from all loads on the bolt.
        service_lvl : str
            either A, C or D
        poa : bolt.Poa
            generic point of application
        T : float
            Temperature related to the action °C
        dpa : float
            Displacement per atom for the action.
        oc : str
            operating conditions. The default is None.
        ie : str
            initiating event. The default is None.
        ce : str
            concateneted event. The default is None.
        load_ctg : str
            loading category. The default is None
        name : str
            identifier of the reference event causing the actions.
        code : code.Code
            design code to use for assessment

        Returns
        -------
        None.

        """
        self.name = name
        self.poa = poa
        self.actions = {"primary": primary, "all": all_loads}
        self.primary = primary
        self.all_loads = all_loads
        if service_lvl in ["A", "C", "D"]:
            self.service_lvl = service_lvl
        else:
            raise ValueError(str(service_lvl) + " is not an admissible service level")
        self.oc = oc
        self.ie = ie
        self.ce = ce
        self.load_ctg = load_ctg
        self.T = T
        self.dpa = dpa
        self.code = code
        self.loads_type = ["Preload", "primary", "all"]


class BoltSectionActions(SectionActions):
    def __init__(
        self,
        primary,
        all_loads,
        service_lvl,
        poa,
        T,
        dpa,
        preload,
        oc=None,
        ie=None,
        ce=None,
        load_ctg=None,
        name=None,
        code=None,
        ncycles=None,
        loads_type=None,
    ):
        """
        Sub-class for internal actions on the bolts

        Parameters
        ----------
        primary : dic or similar
            contains the primary actions acting on the bolt.
        all_loads : dic or similar
            contains the actions deriving from all loads on the bolt.
        service_lvl : str
            either A, C or D
        poa : bolt.Bolt
            bolt object onto wich the actions are applied.
        T : float
            Temperature related to the action °C
        dpa : float
            Displacement per atom for the action.
        preload : float
            Preload force in Newton.
        oc : str
            operating conditions. The default is None.
        ie : str
            initiating event. The default is None.
        ce : str
            concateneted event. The default is None.
        load_ctg : str
            loading category. The default is None
        name : str
            identifier of the reference event causing the actions
        code : code.Code
            design code to use for assessment
        ncycles : float, optional
            number of cycles if available. The default is None

        Returns
        -------
        None.

        """
        super().__init__(
            primary,
            all_loads,
            service_lvl,
            poa,
            T,
            dpa,
            oc=oc,
            ie=ie,
            ce=ce,
            load_ctg=load_ctg,
            name=name,
            code=code,
        )
        self.preload = abs(preload)
        self.stresses = self._compute_applied_stresses()
        self.assessment = None
        # ncycles may be in a wrong format (e.g. '7 258')
        if type(ncycles) is str:
            # remove spaces if there are any
            ncycles = int(ncycles.replace(" ", ""))
        self.ncycles = ncycles
        self.loads_type = ["Preload", "primary", "all"]

    @classmethod
    def from_series(
        cls,
        preload,
        primary,
        all_loads,
        event_data,
        bolt,
        name,
        code=None,
        axs=["z", "x", "y"],
    ):
        """
        Generate a bolt action object starting from dfs

        Parameters
        ----------
        cls : TYPE
            DESCRIPTION.
        preload : float
            preload value in N
        primary : pd.Series
            primary actions.
        all_loads : pd.Series
            all loads actions
        event_data : dic/pd.Series
            data of the reference event associated to the actions.
        bolt : bolt.Bolt
            bolt object.
        code : code.Code
            design code to use for assessment
        normal : list, optional
            directions of the section. the first one is the normal

        Returns
        -------
        BoltSectionActions
            alternative initializator for the class.

        """
        # --- Build the proper actions ---
        # Primary
        if primary is None:
            primary_dic = None
        else:
            N = primary["F" + axs[0]]
            M = (primary["M" + axs[1]] ** 2 + primary["M" + axs[2]] ** 2) ** 0.5
            T = (primary["F" + axs[1]] ** 2 + primary["F" + axs[2]] ** 2) ** 0.5
            primary_dic = {"N": N, "M": M, "T": T}
        # All Loads
        N = all_loads["F" + axs[0]]
        M = (all_loads["M" + axs[1]] ** 2 + all_loads["M" + axs[2]] ** 2) ** 0.5
        T = (all_loads["F" + axs[1]] ** 2 + all_loads["F" + axs[2]] ** 2) ** 0.5
        all_loads_dic = {"N": N, "M": M, "T": T}
        preload = preload

        service_lvl = event_data["Service Level"]
        oc = event_data["Operating Conditions"]
        ie = event_data["Initiating Event"]
        ce = event_data["Concatenated Event"]
        load_ctg = event_data["Load Category"]
        T = event_data["T [°C]"]
        dpa = event_data["DPA"]
        try:
            # Add it if available
            ncycles = event_data["Total number of cycles"]
        except KeyError:
            ncycles = None

        # --- Read Event data ---
        return cls(
            primary_dic,
            all_loads_dic,
            service_lvl,
            bolt,
            T,
            dpa,
            preload,
            oc=oc,
            ie=ie,
            ce=ce,
            load_ctg=load_ctg,
            name=name,
            code=code,
            ncycles=ncycles,
        )

    def change_bolt(self, bolt):
        """
        Change the bolt geometry under study

        Parameters
        ----------
        bolt : bolt.Bolt
            new bolt to associate with the actions.

        Returns
        -------
        None.

        """
        self.poa = bolt
        self.stresses = self._compute_applied_stresses()

    def assess(self, insert=False):
        """
        Assess a Reference Event with a specific code and material

        Parameters
        ----------
        insert : bool, optional
            this is the assessment of the base material of the insert.
            The default is False

        Returns
        -------
        df
          dataframe containing the result of the assessement

        """
        if insert:
            assessment = self.code.assess(
                self, self.poa.material, self.T, self.dpa, selection="Insert"
            )
        else:
            assessment = self.code.assess(self, self.poa.material, self.T, self.dpa)
        rows = []
        for mainrulename, rules in assessment.items():
            for rulename, vals in rules.items():
                assessed = vals[0]
                rule = vals[1]
                for i, subrulename in enumerate(rule.description):
                    try:
                        # Rounded at the MPa (compute on mm so already MPa)
                        applied = int(assessed[i][0])
                        try:
                            allowable = int(assessed[i][1][0] * 1e-6)
                        except ValueError:
                            # it means is NaN
                            allowable = assessed[i][1][0] * 1e-6
                    except TypeError:
                        # The assessment is None, hence the assessment was not
                        # valid. Go the next one
                        continue
                    except ValueError:
                        # The assessment is None, hence the assessment was not
                        # valid. Go the next one
                        continue

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
                        "T [°C]": self.T,
                        "DPA": self.dpa,
                        "Rule Extended Description": rulename,
                        "Rule Set": mainrulename,
                        "Rule ID": rule.ref,
                        "Sub-Rule": subrulename,
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

    def computeVj(self):
        """
        Compute the fatigue usage fraction and returns a df containing all
        useful infos of the assessment

        Parameters
        ----------
        material : material.Material
            Material to use.
        Kf : float
            fatigue stress reduction factor (IC 2753) for the application
            of the Neuber's rule.

        Returns
        -------
        assessment : dic
            contains all infos of the performed assessment, Vj included.

        """
        assessment = self.code.computeVj(
            self, self.poa.material, self.T, self.dpa, self.poa.Kf
        )
        assessment["n"] = self.ncycles
        assessment["ID"] = self.name
        assessment["Range"] = self.ce  # TODO this needs to be changed
        assessment["ctg"] = self.load_ctg
        assessment["lvl"] = self.service_lvl
        assessment["T"] = self.T
        assessment["dpa"] = self.dpa
        assessment["Operating conditions"] = self.oc
        assessment["Vj"] = self.ncycles / assessment["N"]
        assessment["Kf"] = self.poa.Kf

        self.fatigue_assessment = assessment

        return assessment

    def _compute_applied_stresses(self):
        """
        Starting from the internal actions compute the applied stresses on the
        bolt.

        Parameters
        ----------

        Returns
        -------
        stresses : dic
            contains all the applicable stresses divided by 'primary' and
            'all'.

        """
        bolt = self.poa
        stresses = {}
        if self.actions["primary"] is None:
            groups = ["all"]
        else:
            groups = ["primary", "all"]

        for group in groups:
            current = stresses[group] = {}

            # --- Stress Induced by axial loads (SDC-IC B 3812.2.6.1) ---
            N = abs(self.actions[group]["N"])
            # mean tensile stress
            sigma_N = N / bolt.An
            if group == "all":
                self.sigma_tensile = self.preload / bolt.An + sigma_N
                sigma_N = self.sigma_tensile
            # shear stress in the threads
            if group == "all":
                tth_N = 2 * (N + self.preload) / (pi * bolt.df * bolt.Le_shear)
            else:
                tth_N = 2 * (N) / (pi * bolt.df * bolt.Le_shear)
            # shear stress in the head
            if bolt.H == 0:  # There is no washer
                th_N = 0
            else:  # There is washer
                th_N = N / (pi * bolt.d1 * bolt.H)

            # Contact pressure between threads
            pth_N = 4 * N * bolt.p / (pi * (bolt.d**2 - bolt.D**2) * bolt.Le)
            # Contact pressure between head and assembly
            if bolt.B == 0:  # There is no washer
                ph_N = 4 * (N + self.preload) / (pi * (bolt.a**2 - bolt.Dp**2))
            else:  # there is washer
                a_prime = bolt.a + 2 * bolt.C
                Dp_prime = max(bolt.Dp, bolt.B)
                ph_N = 4 * (N + self.preload) / (pi * (a_prime**2 - Dp_prime**2))

            # --- Stress Induced by bending moment M (SDC-IC B 3812.2.6.2) ---
            M = self.actions[group]["M"]
            # bending stress
            sigma_M = M / bolt.Z  # used the one on the thread root section
            # shear stress in the threads
            tth_M = 2 * M / (pi * bolt.df**2 * bolt.Le_shear)
            # shear stress in the head
            if bolt.H == 0:  # There is no washer
                th_M = 0
            else:  # There is washer
                th_M = M / (pi * bolt.d1**2 * bolt.H)
            # contact pressure between the threads
            pth_M = (
                96
                * M
                * bolt.p
                / (
                    pi
                    * (bolt.d - bolt.D)
                    * ((bolt.d + bolt.D) ** 2 + 2 * bolt.d**2)
                    * bolt.Le
                )
            )
            # contact pressure between joint parts
            if bolt.B == 0:  # There is no washer
                ph_M = (
                    96
                    * M
                    / (
                        pi
                        * (bolt.a - bolt.Dp)
                        * ((bolt.a + bolt.Dp) ** 2 + 2 * bolt.a**2)
                    )
                )
            else:  # there is washer
                a_prime = bolt.a + 2 * bolt.C
                Dp_prime = max(bolt.Dp, bolt.B)
                ph_M = (
                    96
                    * M
                    / (
                        pi
                        * (a_prime - Dp_prime)
                        * ((a_prime + Dp_prime) ** 2 + 2 * a_prime**2)
                    )
                )

            # --- Stress induced by residual twisting
            #     torques Cr and Ct (B 3812.2.6.3) ---
            Cr = self.preload * (0.16 * bolt.p + 0.583 * bolt.f * bolt.df)
            Ct = self.preload * 0.5 * bolt.f_prime * bolt.Dm
            # Shear stress in threads
            tau_Cr = 16 * Cr / (pi * bolt.dn**3)
            try:
                tau_Ct = 16 * Ct / (pi * bolt.d1**3)
            except ZeroDivisionError:
                tau_Ct = 0  # in case of insert

            # --- Stress induced by transverse load T ---
            # Shear stress in the threaded root section
            T = self.actions[group]["T"]
            tau_T = 4 * T / (pi * bolt.dn**2)

            # --- Allowable stresses ---
            current["Primary stress"] = sigma_N
            current["Mean stress"] = (sigma_N**2 + 3 * tau_T**2) ** 0.5
            current["Avg shear stress in threads"] = tth_N + tth_M

            if group == "primary":
                current["Max stress"] = ((sigma_N + sigma_M) ** 2 + 3 * tau_T**2) ** 0.5
                current["Avg shear stress in head"] = th_N + th_M
            else:  # All
                current["Max stress"] = (
                    (sigma_N + sigma_M) ** 2 + 3 * (tau_T + tau_Cr) ** 2
                ) ** 0.5
                current["Avg shear stress in head"] = (
                    (th_N + th_M) ** 2 + tau_Ct**2
                ) ** 0.5
                current["Stress intensity range"] = (
                    (sigma_N + sigma_M) ** 2 + 3 * (tau_T) ** 2
                ) ** 0.5

            current["Avg contact pressure betweeen threads"] = pth_M + pth_N
            current["Avg contact pressure between head and assembly"] = ph_N + ph_M
        return stresses

    def get_df_actions(self):
        """
        Return a DF containing the actions used for the assessment

        Returns
        -------
        df : pd.DataFrame
            contains the actions used for the assessment of the RE.

        """
        rows = []
        for load in self.loads_type:
            row = {
                "RE ID": self.name,
                "Operating Conditions": self.oc,
                "Initiating Event": self.ie,
                "Concatenated Event": self.ce,
                "Type of Load": load,
            }
            if load == "Preload":
                row["N"] = self.preload
                row["T"] = "-"
                row["M"] = "-"
            else:
                row["N"] = abs(self.actions[load]["N"])
                row["T"] = abs(self.actions[load]["T"])
                row["M"] = abs(self.actions[load]["M"])

            rows.append(row)

        df = pd.DataFrame(rows)

        return df
