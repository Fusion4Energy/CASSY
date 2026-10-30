import math
import logging

from cassy.auxiliary import trace
from cassy.designcodes.codes import Code, Rule
from cassy.general.material import Material
from cassy.paths.linstress import ReferenceEvent
from cassy.auxiliary.custom_errors import OutOfBoundsError


class SDC_IC(Code):
    def __init__(self):
        super().__init__(name="SDC-IC")
        # --- Initiate all elastic rules, negligible creep ---
        # M-Type
        rules = {
            "Immediate plastic collapse and plastic instability": IC3121_1_1_2a(),
            "Immediate plastic flow localization": IC3121_2_1(),
            "Immediate local fracture due to exhaustion of ductility": IC3121_3_1(),
            "Progressive deformation or ratcheting": IC3131_1_2(),
        }
        self.rules = rules
        self.damage_types = ("Immediate", "Ratcheting")
        self.fatigue = True

    def computeVj(self, refEvent: ReferenceEvent, material: Material) -> dict:
        """
        Asses the Rule
        Parameters
        ----------
        refEvent : LinStress.ReferenceEvent
            reference event to assess.
        material : material.Material
            Material data.

        Returns
        -------
        dictionary containing de1, de2, de3, de4, , N allowable,
        ID rule and sigma tot
        """
        T = refEvent.config.T
        dpa = refEvent.config.dpa
        # ds is the total stress of the considered reference event
        name = "IC 3132.3.1"
        # Fatigue Strength Reduction Factor defined in RB 3292.112:
        # ds is multiplied by f which depends on the type of joint
        f = refEvent.config.welding_f
        ds = f * refEvent.PQF
        trace.record("ds", ds, kind="stress", unit="Pa", note="f * PQF")
        T_ds = (T, ds)

        # --- split in case of stress or strain based fatigue curve ---
        if material.N.ftype == "strain":
            # de calculation
            de1 = 2 / 3 * (1 + material.nu()) * (ds / material.E(T, dpa))
            # tresca for shells Pm+0.67*(Pb+Pl-Pm), it is 0 if there is no primary stress
            tresca = refEvent.tresca
            # de2 represents the "plastic" increase in strain due to the primary
            # stress range at the point examined, equal to tresca for shells
            # cyclic_stress_strain looks like it returns strain in [-], not %, so not change it
            try:
                de2 = material.cyclic_stress_strain(T, tresca) - 2 / 3 * (
                    1 + material.nu()
                ) * (tresca / material.E(T, dpa))
            except NotImplementedError as e:
                de2 = 0
                logging.warning(f"Cyclic stress-strain curves not implemented, de2=0")
                trace.record(
                    "de2",
                    "cyclic stress-strain curve not available: de2 = 0",
                    kind="warning",
                )

            # de3 is derived as the intersection point of the cyclic curve and the
            # hyperbola ds*de = costant
            de3 = (de1 + de2) * (material.Keps(T_ds) - 1)
            de4 = de1 * (material.Kmu(T_ds) - 1)
            detot = de1 + de2 + de3 + de4
            # f is already applied once through ds (IC 3132.3.1 welded joints),
            # the base metal fatigue curve is used
            trace.record(
                "de tot", detot, kind="value", note="de1 + de2 + de3 + de4"
            )
            N_all = material.N((T, detot))

        elif material.N.ftype == "stress":
            SA = ds / 2
            trace.record("SA", SA, kind="stress", unit="Pa", note="ds / 2")
            N_all = material.N(
                T, SA * 1e-6
            )  # convention is MPa for stress based curves
            de1 = None
            de2 = None
            de3 = None
            de4 = None
            detot = None
        else:
            raise ValueError("Unknown fatigue curve type: " + material.N.ftype)

        assessment = {
            "de1": de1,
            "de2": de2,
            "de3": de3,
            "de4": de4,
            "de tot": detot,
            "N": N_all,
            "Rule ID": name,
            "sigma tot": ds * 1e-6,
        }  # MPa
        return assessment


class IC3121_1_1_2a(Rule):
    def __init__(self) -> None:
        self.damage_type = "Immediate"
        self.ref = "IC 3121.1.1.2a"
        self.description = ["Primary membrane", "Primary Membrane plus Bending"]
        # self.equation = '$$A_{b}$$ (P_L+ P_b ) ̅≤〖K_eff S〗_m (〖T_m,Φt〗_m)'

    def assess(
        self,
        refEvent: ReferenceEvent,
        material: Material,
        K: float = 1.5,
    ) -> list:
        """
        Assess the rule

        Parameters
        ----------
        refEvent : LinStress.ReferenceEvent
            reference event to assess.
        material : material.Material
            Material data.
        K : float
            Bending Section shape factor. The default is 1.5

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).

        """
        T = refEvent.config.T
        dpa = refEvent.config.dpa
        service_lvl = refEvent.config.service_lvl
        T_dpa = (T, dpa)
        n = refEvent.config.welding_n
        # select allowable
        if service_lvl == "A":
            allowable1 = n * material.Sm(T_dpa)
            formula = "n * Sm"
        elif service_lvl == "C":
            allowable1 = min(1.2 * n * material.Sm(T_dpa), material.Sy_min(T_dpa))
            formula = "min(1.2 * n * Sm, Sy_min)"
        elif service_lvl == "D":
            allowable1 = min(2.4 * n * material.Sm(T_dpa), 0.7 * material.Su_min(T_dpa))
            formula = "min(2.4 * n * Sm, 0.7 * Su_min)"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")
        trace.record("allowable 1", allowable1, kind="allowable", note=formula)

        stress1 = refEvent.Pm
        stress2 = refEvent.PmPb
        trace.equation_terms(("Pm", "allowable 1"), ("PmPb", "allowable 2"))
        allowable2 = material.get_Keff(T, dpa, K) * allowable1
        trace.record("K", K, kind="factor")
        trace.record(
            "allowable 2", allowable2, kind="allowable", note="Keff * allowable 1"
        )

        return [(stress1, allowable1), (stress2, allowable2)]


class IC3121_2_1(Rule):
    def __init__(self) -> None:
        self.damage_type = "Immediate"
        self.ref = "IC 3121.2.1"
        self.description = ["Primary plus secondary membrane stress"]
        # self.equation = '$$A_{b}$$ (P_L+ P_b ) ̅≤〖K_eff S〗_m (〖T_m,Φt〗_m)'

    def assess(self, refEvent: ReferenceEvent, material: Material) -> list:
        """
        Assess the rule

        Parameters
        ----------
        refEvent : LinStress.ReferenceEvent
            Recombined linear stress to assess.
        material : material.Material
            Material data.

        Returns
        -------
        list
            Each item in the list represents an equation result, eache equation
            is of the type (stress, allowable).

        """
        T = refEvent.config.T
        dpa = refEvent.config.dpa
        # n = refEvent.n_welding
        service_lvl = refEvent.config.service_lvl
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A":
            allowable = material.Se(T_dpa)
            formula = "Se"
        elif service_lvl == "C":
            allowable = 1.2 * material.Se(T_dpa)
            formula = "1.2 * Se"
        elif service_lvl == "D":
            allowable = 2 * material.Se(T_dpa)
            formula = "2 * Se"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")
        trace.record("allowable", allowable, kind="allowable", note=formula)

        stress = refEvent.PmQm
        trace.equation_terms(("PmQm", "allowable"))

        return [(stress, allowable)]


class IC3121_3_1(Rule):
    def __init__(self) -> None:
        self.damage_type = "Immediate"
        self.ref = "IC 3121.3.1"
        self.description = [
            "Total stress, including peak stress",
            "Total stress, excluding peak stress",
        ]
        # self.equation = '$$A_{b}$$ (P_L+ P_b ) ̅≤〖K_eff S〗_m (〖T_m,Φt〗_m)'

    def assess(self, refEvent: ReferenceEvent, material: Material) -> list:
        """
        Assess the rule

        Parameters
        ----------
        refEvent : LinStress.ReferenceEvent
            Recombined linear stress to assess.
        material : material.Material
            Material data.
        K : float
            Bending Section shape factor. The default is 1.5

        Returns
        -------
        list
            Each item in the list represents an equation result, eache equation
            is of the type (stress, allowable).

        """
        service_lvl = refEvent.config.service_lvl
        T_dpa = (refEvent.config.T, refEvent.config.dpa)
        # select allowable
        if service_lvl == "A":
            factor = 1
            allowable1 = material.Sd(T_dpa)
            allowable2 = material.Sd_nopeak(T_dpa)
        elif service_lvl == "C":
            factor = 1.2
            allowable1 = 1.2 * material.Sd(T_dpa)
            allowable2 = 1.2 * material.Sd_nopeak(T_dpa)
        elif service_lvl == "D":
            factor = 1.35
            allowable1 = 1.35 * material.Sd(T_dpa)
            allowable2 = 1.35 * material.Sd_nopeak(T_dpa)
        else:
            raise KeyError(service_lvl + " is not an admissible service level")
        trace.record("service level factor", factor, kind="factor")
        trace.record("allowable 1", allowable1, kind="allowable", note="factor * Sd")
        trace.record(
            "allowable 2", allowable2, kind="allowable", note="factor * Sd_nopeak"
        )

        stress1 = refEvent.PQF
        stress2 = refEvent.PQ
        trace.equation_terms(("PQF", "allowable 1"), ("PQ", "allowable 2"))

        return [(stress1, allowable1), (stress2, allowable2)]


class IC3131_1_2(Rule):
    def __init__(self) -> None:
        self.damage_type = "Ratcheting"
        self.ref = "IC 3131.1"
        self.description = ["3Sm rule", "Efficiency Index", "Efficiency Index"]
        self.sequential = (
            True  # 3Sm is a screening check; EI is evaluated only if 3Sm fails
        )
        # self.equation = '$$A_{b}$$ (P_L+ P_b ) ̅≤〖K_eff S〗_m (〖T_m,Φt〗_m)'

    def assess(
        self,
        refEvent: ReferenceEvent,
        material: Material,
        K: float = 1.5,
    ) -> list:
        """
        Assess the rule

        Parameters
        ----------
        refEvent: LinStress.ReferenceEvent
            Recombined linear stress to assess.
        material : material.Material
            Material data.

        Returns
        -------
        list
            Each item in the list represents an equation result, eache equation
            is of the type (stress, allowable).

        """
        T = refEvent.config.T
        dpa = refEvent.config.dpa
        # n = refEvent.n_welding ( base metal properties for ratcheting)
        service_lvl = refEvent.config.service_lvl
        T_dpa = (T, dpa)
        # ------IC 3131.1.2 '3Sm Rule'-------#
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = 3 * material.Sm(T_dpa)
            trace.record("allowable 1", allowable1, kind="allowable", note="3 * Sm")
        elif service_lvl == "D":
            # warnings.warn(service_lvl +
            #               ' is not an admissible service level')
            trace.record("rule", "not applicable for level D", kind="branch")
            return None
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = refEvent.ratcheting3Sm_SDCIC
        trace.equation_terms(("ratcheting3Sm_SDCIC", "allowable 1"))

        # Perform efficiency index only if 3Sm is not passed
        if stress1 <= allowable1:
            trace.record("efficiency index", "skipped: 3Sm satisfied", kind="branch")
            return [(stress1, allowable1), (None, None), (None, None)]
        trace.record("efficiency index", "evaluated: 3Sm not satisfied", kind="branch")

        # -----IC 3131.1.1 'Efficiency Index Diagram'------#
        # Operating period with secondary membrane stress
        # thermal loads are considered mandatory for ratcheting
        try:
            sigma_nm = material.compute_delta_sigma_Neuber(
                T, refEvent.PmQm_ns, 1, dpa=dpa, monotonic=True
            )
            sigma_nmb = material.compute_delta_sigma_Neuber(
                T, refEvent.PmPbQm_ns, 1, dpa=dpa, monotonic=True
            )
        except (NotImplementedError, OutOfBoundsError) as e:
            logging.warning(e)
            logging.warning("Efficiency index cannot be computed")
            trace.record("efficiency index", f"not computed: {e}", kind="warning")
            return [(stress1, allowable1), (None, None), (None, None)]

        Em = material.compute_tangent_young(sigma_nm, T, dpa=dpa)
        Emb = material.compute_tangent_young(sigma_nmb, T, dpa=dpa)

        # short duration overstress
        if refEvent.Pms > 1e-6 or refEvent.PmPbs > 1e-6:
            trace.record("short duration overstress", "yes", kind="branch")
            sigma_mb = (
                0.5 * (refEvent.PmPb_ns + sigma_nmb)
                + (3 * material.E(T, dpa) / Emb) * refEvent.PmPbs
            )
            sigma_m = (
                0.5 * (refEvent.Pm_ns + sigma_nm)
                + (3 * material.E(T, dpa) / Em) * refEvent.Pms
            )

        else:  # no overstress of short duration
            trace.record("short duration overstress", "no", kind="branch")
            sigma_nm = material.compute_delta_sigma_Neuber(
                T, refEvent.PmQm, 1, dpa=dpa, monotonic=True
            )
            sigma_nmb = material.compute_delta_sigma_Neuber(
                T, refEvent.PmPbQm, 1, dpa=dpa, monotonic=True
            )
            sigma_mb = 0.5 * (refEvent.PmPb + sigma_nmb)
            sigma_m = 0.5 * (refEvent.Pm + sigma_nm)

        dq = refEvent.dQ + refEvent.PmPbs  # secondary stress range

        # seconday ratio ( relative variation in secondary stress in relation)
        # to the primary stress considered IC 3131.1.1.3)
        SR1 = dq / sigma_m
        SR2 = dq / sigma_mb
        # efficiency index ( IC 3131.1.1.4)
        eff_idx = []
        for SR in [SR1, SR2]:
            if SR <= 0.46:
                v = 1
            elif SR >= 4:
                v = 1 / math.sqrt(SR)
            else:
                v = 1.093 - (0.926 * SR**2) / (1 + SR) ** 2

            eff_idx.append(v)

        trace.record("sigma_m", sigma_m, kind="stress", unit="Pa")
        trace.record("sigma_mb", sigma_mb, kind="stress", unit="Pa")
        trace.record("dq", dq, kind="stress", unit="Pa", note="dQ + PmPbs")
        trace.record("SR1", SR1, kind="value", note="dq / sigma_m")
        trace.record("SR2", SR2, kind="value", note="dq / sigma_mb")
        trace.record("v1", eff_idx[0], kind="factor", note="efficiency index (SR1)")
        trace.record("v2", eff_idx[1], kind="factor", note="efficiency index (SR2)")

        # effective primary stress intensity (IC 3131.1.1.5)
        p1 = sigma_m / eff_idx[0]
        p2 = sigma_mb / eff_idx[1]
        trace.record("p1", p1, kind="stress", unit="Pa", note="sigma_m / v1")
        trace.record("p2", p2, kind="stress", unit="Pa", note="sigma_mb / v2")
        T_dpa = (T, dpa)

        stress2 = p1
        stress3 = p2
        allowable2 = 1.3 * material.Sm(T_dpa)
        allowable3 = 1.5 * allowable2
        trace.record("allowable 2", allowable2, kind="allowable", note="1.3 * Sm")
        trace.record("allowable 3", allowable3, kind="allowable", note="1.5 * 1.3 * Sm")

        # # -------Bree diagram Rule (IC 3131.1.2)--------- #
        # # coordinates calculation
        # X = refEvent.PmPb_bree/material.Sy_min(T_dpa)
        # # the rule has been implemented according to ITER template.
        # # Y = (refEvent.PmPb+dq)/material.Sy_min(T_dpa)

        # if X > 0 and X <= 0.5:
        #     stress4 = math.sqrt((refEvent.PmPb+dq)*(refEvent.PmPb_bree))
        # else:
        #     stress4 = math.sqrt((refEvent.PmPb+dq)/4*(refEvent.PmPb_bree))

        # allowable4 = material.Sy_min(T_dpa)

        trace.equation_terms(
            ("ratcheting3Sm_SDCIC", "allowable 1"),
            ("p1", "allowable 2"),
            ("p2", "allowable 3"),
        )
        return [(stress1, allowable1), (stress2, allowable2), (stress3, allowable3)]
