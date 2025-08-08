from math import pi

import numpy as np
import pandas as pd

from cassy.bolts.bolt_config import BoltReferenceEventFatigue, Event
from cassy.bolts.geometry import BoltGeom, BoltLikeGeom
from cassy.designcodes.codes import BoltCode


class BoltActionAssessor:
    def __init__(
        self,
        name: str,
        primary_actions: pd.Series,
        all_loads_actions: pd.Series,
        ref_event: Event,
        poa: BoltLikeGeom,
        preload: float,
    ):
        """
        Compute the applicable forces and moments acting on the bolt section and
        perform the assessment of a specific reference event.

        Parameters
        ----------
        name : str
            identifier of the poa.
        primary_actions : pd.Series
            index is Fx,Fy,Fz,Mz,Mx,My
        all_loads_actions : pd.Series
            index is Fx,Fy,Fz,Mz,Mx,My
        ref_event : Event
            Event to assess.
        poa : BoltLikeGeom
            geometry of the bolt/insert under assessment.
        preload : float
            preload applied to the bolt.
        """
        self.name = name
        self.poa = poa
        self.preload = abs(preload)
        self.primary, self.all_loads = self._convert_actions(
            primary_actions, all_loads_actions
        )
        self.ref_event = ref_event

        self.loads_type = ["Preload", "primary", "all"]

        # Compute applicable stresses
        primary_stresses = self._compute_applicable_stresses(
            self.primary, group="primary"
        )
        all_stresses = self._compute_applicable_stresses(self.all_loads, group="all")
        self.applicable_stresses = {"primary": primary_stresses, "all": all_stresses}

        self.assessment = None
        # # ncycles may be in a wrong format (e.g. '7 258')
        # if type(ncycles) is str:
        #     # remove spaces if there are any
        #     ncycles = int(ncycles.replace(" ", ""))
        # self.ncycles = ncycles

    def _convert_actions(
        self,
        primary: pd.Series,
        all_loads: pd.Series,
        axs=["z", "x", "y"],
    ) -> tuple[dict[str, float], dict[str, float]]:
        """
        Generate a bolt action object starting from dfs
        """

        N = abs(primary["F" + axs[0]])
        M = (primary["M" + axs[1]] ** 2 + primary["M" + axs[2]] ** 2) ** 0.5
        T = (primary["F" + axs[1]] ** 2 + primary["F" + axs[2]] ** 2) ** 0.5
        primary_dic = {"N": N, "M": M, "T": T}

        # All Loads
        N_nopreload = abs(
            all_loads["F" + axs[0]] - self.preload
        )  # subtract preload from all loads actions
        N = abs(all_loads["F" + axs[0]])
        M = (all_loads["M" + axs[1]] ** 2 + all_loads["M" + axs[2]] ** 2) ** 0.5
        T = (all_loads["F" + axs[1]] ** 2 + all_loads["F" + axs[2]] ** 2) ** 0.5
        all_loads_dic = {"N": N, "M": M, "T": T, "N_nopreload": N_nopreload}

        return primary_dic, all_loads_dic

    def assess(self, code: BoltCode, insert=False):
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
            assessment = code.assess(
                self,
                self.poa.material,
                selection="Insert",
            )
        else:
            assessment = code.assess(
                self,
                self.poa.material,
            )
        rows = []
        for mainrulename, rules in assessment.items():
            for rulename, vals in rules.items():
                assessed = vals[0]
                rule = vals[1]
                for i, subrulename in enumerate(rule.description):
                    # Rounded at the MPa (compute on mm so already MPa)
                    applied = int(assessed[i][0])
                    allowable = assessed[i][1]
                    # If allowable is nan, it means that there are no limits
                    if allowable != "No limit" and not np.isnan(allowable):
                        allowable = int(allowable * 1e-6)  # make sure is rounded

                    if allowable == "No limit" or np.isnan(allowable):
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
                        "ID": self.ref_event.name,
                        "Operating Conditions": self.ref_event.oper_cond,
                        "Initiating Event": self.ref_event.init_event,
                        "Concatenated Event": self.ref_event.concat_event,
                        "Loading Category": self.ref_event.load_category,
                        "Service Level": self.ref_event.service_lvl,
                        "T [°C]": self.ref_event.temp,
                        "DPA": self.ref_event.dpa,
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

    def computeVj(self, code: BoltCode) -> dict:
        """
        Compute the fatigue usage fraction and returns a df containing all
        useful infos of the assessment

        Parameters
        ----------
        code : BoltCode
            Design code to use for the assessment.

        Returns
        -------
        assessment : dic
            contains all infos of the performed assessment, Vj included.

        """
        assert isinstance(self.ref_event, BoltReferenceEventFatigue), (
            "The reference event must be a BoltReferenceEventFatigue"
        )
        assert isinstance(self.poa, BoltLikeGeom), (
            "Only Bolts can be assessed for fatigue usage fraction"
        )
        assessment = code.computeVj(
            self,
            self.poa.material,
        )
        try:
            vj = self.ref_event.n_cycles / assessment["N"]
        except ZeroDivisionError:
            vj = 1e5  # infinity
        assessment["n"] = self.ref_event.n_cycles
        assessment["ID"] = self.ref_event.name
        assessment["Range"] = (
            self.ref_event.concat_event
        )  # TODO this needs to be changed
        assessment["ctg"] = self.ref_event.load_category
        assessment["lvl"] = self.ref_event.service_lvl
        assessment["T"] = self.ref_event.temp
        assessment["dpa"] = self.ref_event.dpa
        assessment["Operating conditions"] = self.ref_event.oper_cond
        assessment["Vj"] = vj
        assessment["Kf"] = self.poa.KF

        self.fatigue_assessment = assessment

        return assessment

    def _compute_applicable_stresses(
        self, actions: dict, group: str
    ) -> dict[str, float]:
        bolt = self.poa

        applicables = {}

        # --- Stress Induced by axial loads (SDC-IC B 3812.2.6.1) ---
        N = actions["N"]
        # mean tensile stress [N/mm^2 = MPa]
        sigma_N = N / bolt.An
        if group == "all":
            self.sigma_tensile = sigma_N
        # shear stress in the threads [N/mm^2 = MPa]
        tth_N = 2 * (N) / (pi * bolt.df * bolt.Le_shear)

        # shear stress in the head [N/mm^2 = MPa]
        if not isinstance(bolt, BoltGeom) or bolt.H == 0:
            th_N = 0
        else:  # There is washer
            th_N = N / (pi * bolt.d1 * bolt.H)

        # Contact pressure between threads [N*mm/mm^3 = MPa]
        pth_N = 4 * N * bolt.p / (pi * (bolt.d**2 - bolt.D**2) * bolt.Le)

        # Contact pressure between head and assembly, do not compute for insert
        if isinstance(bolt, BoltGeom):  # [N/mm^2 = MPa]
            if bolt.B == 0:  # There is no washer
                ph_N = 4 * N / (pi * (bolt.a**2 - bolt.Dp**2))
            else:  # there is washer
                a_prime = bolt.a + 2 * bolt.C
                Dp_prime = max(bolt.Dp, bolt.B)
                ph_N = 4 * N / (pi * (a_prime**2 - Dp_prime**2))

        # --- Stress Induced by bending moment M (SDC-IC B 3812.2.6.2) ---
        M = actions["M"] * 1000
        # Easier to bring the Moment N/m -> N/mm to avoid errors with units
        sigma_M = M / bolt.Z  # used the one on the thread root section
        # shear stress in the threads
        tth_M = 2 * M / (pi * bolt.df**2 * bolt.Le_shear)
        # shear stress in the head
        if not isinstance(bolt, BoltGeom) or bolt.H == 0:  # There is no washer
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
        if isinstance(bolt, BoltGeom):
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
        # Shear stress in threads
        tau_Cr = 16 * Cr * bolt.dn / (pi * (bolt.dn**4 - bolt.d_vh**4))

        if isinstance(bolt, BoltGeom):
            Ct = self.preload * 0.5 * bolt.f_prime * bolt.Dm
            tau_Ct = 16 * Ct / (pi * bolt.d1**3)
        else:
            tau_Ct = 0  # in case of insert

        # --- Stress induced by transverse load T ---
        # Shear stress in the threaded root section
        T = actions["T"]
        tau_T = 4 * T / (pi * (bolt.dn**2 - bolt.d_vh**2))

        # --- Allowable stresses ---
        applicables["Primary stress"] = sigma_N
        applicables["Mean stress"] = (sigma_N**2 + 3 * tau_T**2) ** 0.5
        applicables["Avg shear stress in threads"] = tth_N + tth_M

        if group == "primary":
            applicables["Max stress"] = ((sigma_N + sigma_M) ** 2 + 3 * tau_T**2) ** 0.5
            if isinstance(bolt, BoltGeom):
                applicables["Avg shear stress in head"] = th_N + th_M
        else:  # All
            applicables["Max stress"] = (
                (sigma_N + sigma_M) ** 2 + 3 * (tau_T + tau_Cr) ** 2
            ) ** 0.5
            if isinstance(bolt, BoltGeom):
                applicables["Avg shear stress in head"] = (
                    (th_N + th_M) ** 2 + tau_Ct**2
                ) ** 0.5
            applicables["Stress intensity range"] = (
                (sigma_N + sigma_M) ** 2 + 3 * (tau_T) ** 2
            ) ** 0.5

        applicables["Avg contact pressure betweeen threads"] = pth_M + pth_N
        if isinstance(bolt, BoltGeom):
            # can be computed only for bolts
            applicables["Avg contact pressure between head and assembly"] = ph_N + ph_M
        return applicables

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
                "RE ID": self.ref_event.name,
                "Operating Conditions": self.ref_event.oper_cond,
                "Initiating Event": self.ref_event.init_event,
                "Concatenated Event": self.ref_event.concat_event,
                "Type of Load": load,
            }
            if load == "Preload":
                row["N"] = self.preload
                row["T"] = "-"
                row["M"] = "-"
            else:
                if load == "primary":
                    actions = self.primary
                elif load == "all":
                    actions = self.all_loads
                row["N"] = abs(actions["N"])
                row["T"] = abs(actions["T"])
                row["M"] = abs(actions["M"])

            rows.append(row)

        df = pd.DataFrame(rows)

        return df
