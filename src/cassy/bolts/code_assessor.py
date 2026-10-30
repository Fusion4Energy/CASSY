import logging
import re
from math import pi

import numpy as np
import pandas as pd

from cassy.auxiliary import trace
from cassy.bolts.bolt_config import BoltReferenceEventFatigue, Event
from cassy.bolts.geometry import BoltGeom, BoltLikeGeom
from cassy.designcodes.codes import (
    INVALID_VJ,
    INVALIDATING_ERRORS,
    BoltCode,
    InvalidAssessment,
    bolt_stress_name,
    invalidate_nan_vj,
)


class TracedStresses(dict):
    def __init__(
        self,
        group: str,
        components: dict[str, float],
        formulas: dict[str, str],
        values: dict[str, float],
    ):
        """Applicable stresses of a load group. Each time a stress is accessed it is
        recorded in the trace, together with the formula used to compute it and the
        stress components it depends on.

        Parameters
        ----------
        group : str
            load group of the stresses ('primary' or 'all').
        components : dict[str, float]
            stress components the applicable stresses are computed from [MPa].
        formulas : dict[str, str]
            formula of each applicable stress, written with the component names.
        values : dict[str, float]
            value of each applicable stress [MPa].
        """
        super().__init__(values)
        self.group = group
        self.components = components
        self.formulas = formulas

    def __getitem__(self, key: str) -> float:
        value = super().__getitem__(key)
        if trace.is_active():
            formula = self.formulas.get(key)
            for name in re.findall(r"\w+", formula or ""):
                if name in self.components:
                    trace.record(
                        bolt_stress_name(self.group, name),
                        self.components[name],
                        kind="stress",
                        unit="MPa",
                    )
            trace.record(
                bolt_stress_name(self.group, key),
                value,
                kind="stress",
                unit="MPa",
                note=formula,
            )
        return value


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
        N = abs(all_loads["F" + axs[0]])
        M = (all_loads["M" + axs[1]] ** 2 + all_loads["M" + axs[2]] ** 2) ** 0.5
        T = (all_loads["F" + axs[1]] ** 2 + all_loads["F" + axs[2]] ** 2) ** 0.5
        all_loads_dic = {"N": N, "M": M, "T": T}

        return primary_dic, all_loads_dic

    def _record_inputs(self) -> None:
        if not trace.is_active():
            return
        ev = self.ref_event
        trace.record("T", ev.temp, kind="input", unit="°C")
        trace.record("dpa", ev.dpa, kind="input")
        trace.record("service level", ev.service_lvl, kind="input")
        trace.record("loading category", ev.load_category, kind="input")
        trace.record("preload", self.preload, kind="input", unit="N")
        trace.record("material", self.poa.material.name, kind="input")
        units = {"N": "N", "T": "N", "M": "N m"}
        for group, actions in (("primary", self.primary), ("all", self.all_loads)):
            for key, val in actions.items():
                trace.record(f"{key} ({group})", val, kind="input", unit=units.get(key))

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
        with trace.scope(event=self.ref_event.name, analysis="immediate"):
            self._record_inputs()
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
                    applied = assessed[i][0]
                    allowable = assessed[i][1]
                    note = None
                    if isinstance(assessed, InvalidAssessment):
                        # the rule could not be assessed, it counts as failed
                        applied, allowable = "-", "-"
                        res, sm, note = "FAILED", 0, assessed.message
                    elif allowable == "No limit" or np.isnan(allowable):
                        # If allowable is nan, it means that there are no limits
                        allowable = "No Limit"
                        res = "Assessment not required"
                        sm = None
                    else:
                        allowable = allowable * 1e-6  # make sure is rounded
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
                    if note is not None:
                        row["Note"] = note
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
        with trace.scope(event=self.ref_event.name, analysis="fatigue"):
            self._record_inputs()
            with trace.scope(rule_set="Fatigue"):
                try:
                    assessment = code.computeVj(
                        self,
                        self.poa.material,
                    )
                except INVALIDATING_ERRORS as e:
                    # the event counts as failed, the assessment goes on
                    logging.warning(
                        f"Fatigue of {self.ref_event.name} invalidated: {e}"
                    )
                    trace.record("fatigue", f"invalidated: {e}", kind="warning")
                    assessment = {"N": np.nan, "Note": f"invalidated: {e}"}
                    vj = INVALID_VJ
                else:
                    try:
                        vj = invalidate_nan_vj(
                            self.ref_event.n_cycles / assessment["N"],
                            self.ref_event.name,
                        )
                    except ZeroDivisionError:
                        vj = INVALID_VJ  # infinity
                for key, val in assessment.items():
                    trace.record(key, val, kind="result")
            trace.record("n cycles", self.ref_event.n_cycles, kind="input")
            trace.record("Vj", vj, kind="result", note="n/N")
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
    ) -> TracedStresses:
        bolt = self.poa

        applicables = {}
        formulas = {}

        # --- Stress Induced by axial loads (SDC-IC B 3812.2.6.1) ---
        N = actions["N"]
        # mean tensile stress [N/mm^2 = MPa]
        sigma_N = N / bolt.An
        if group == "primary":
            # In fatigue events the "primary" group holds the sustained tensor
            # (preload included), which is what sigma pre is computed on
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
        # formulas are written with the names of the components below
        applicables["Primary stress"] = sigma_N
        formulas["Primary stress"] = "sigma_N"
        applicables["Mean stress"] = (sigma_N**2 + 3 * tau_T**2) ** 0.5
        formulas["Mean stress"] = "sqrt(sigma_N^2 + 3 * tau_T^2)"
        applicables["Avg shear stress in threads"] = tth_N + tth_M
        formulas["Avg shear stress in threads"] = "tau_th_N + tau_th_M"

        if group == "primary":
            applicables["Max stress"] = ((sigma_N + sigma_M) ** 2 + 3 * tau_T**2) ** 0.5
            formulas["Max stress"] = "sqrt((sigma_N + sigma_M)^2 + 3 * tau_T^2)"
            if isinstance(bolt, BoltGeom):
                applicables["Avg shear stress in head"] = th_N + th_M
                formulas["Avg shear stress in head"] = "tau_h_N + tau_h_M"
        else:  # All
            applicables["Max stress"] = (
                (sigma_N + sigma_M) ** 2 + 3 * (tau_T + tau_Cr) ** 2
            ) ** 0.5
            formulas["Max stress"] = (
                "sqrt((sigma_N + sigma_M)^2 + 3 * (tau_T + tau_Cr)^2)"
            )
            if isinstance(bolt, BoltGeom):
                applicables["Avg shear stress in head"] = (
                    (th_N + th_M) ** 2 + tau_Ct**2
                ) ** 0.5
                formulas["Avg shear stress in head"] = (
                    "sqrt((tau_h_N + tau_h_M)^2 + tau_Ct^2)"
                )
            applicables["Stress intensity range"] = (
                (sigma_N + sigma_M) ** 2 + 3 * (tau_T) ** 2
            ) ** 0.5
            formulas["Stress intensity range"] = (
                "sqrt((sigma_N + sigma_M)^2 + 3 * tau_T^2)"
            )

        applicables["Avg contact pressure betweeen threads"] = pth_M + pth_N
        formulas["Avg contact pressure betweeen threads"] = "p_th_N + p_th_M"
        if isinstance(bolt, BoltGeom):
            # can be computed only for bolts
            applicables["Avg contact pressure between head and assembly"] = ph_N + ph_M
            formulas["Avg contact pressure between head and assembly"] = (
                "p_h_N + p_h_M"
            )

        components = {
            "sigma_N": sigma_N,
            "sigma_M": sigma_M,
            "tau_th_N": tth_N,
            "tau_th_M": tth_M,
            "tau_h_N": th_N,
            "tau_h_M": th_M,
            "p_th_N": pth_N,
            "p_th_M": pth_M,
            "tau_T": tau_T,
            "tau_Cr": tau_Cr,
            "tau_Ct": tau_Ct,
        }
        if isinstance(bolt, BoltGeom):
            components["p_h_N"] = ph_N
            components["p_h_M"] = ph_M
        return TracedStresses(group, components, formulas, applicables)

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
