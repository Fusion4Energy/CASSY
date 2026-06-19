from typing import TYPE_CHECKING, Any
import numpy as np

if TYPE_CHECKING:
    from cassy.bolts.code_assessor import BoltActionAssessor
from cassy.designcodes.codes import BoltCode, Rule
from cassy.general.material import Material

ASSESSMENTS = {
    "cross section": "Minimum bolt cross-sectional area for bolted flanged joints which do not have to satisfy leaktightness",
    "plastic collapse": "Rules for the prevention of M type damage, Immediate plastic collapse or excessive plastic deformation",
    "flow localization": "Rules for the prevention of M type damage, Immediate flow localization and immediate local fracture due to exhaustion of ductility",
}


class SDC_IC_Bolts(BoltCode):
    def __init__(
        self,
    ):
        super().__init__(name="SDC-IC (Bolts)")
        # Minimum bolt cross-sectional area for bolted flanged joints which do
        # not have to satisfy leaktightness
        primary = {"Primary Stress": IC6113()}
        plastic_collapse = {
            "Mean Stress Limits": IC6121_1_3_1(),
            "Maximum Stress Limits": IC6121_1_3_2(),
            "Shear Stress Limits": IC6121_1_3_3(),
            "Contact pressure limits": IC6121_1_3_4(),
        }
        flow_localization = {
            "Mean Stress Limits": IC6122_1_1(),
            "Maximum Stress Limits:": IC6122_1_2(),
        }
        rules = {
            ASSESSMENTS["cross section"]: primary,
            ASSESSMENTS["plastic collapse"]: plastic_collapse,
            ASSESSMENTS["flow localization"]: flow_localization,
        }
        self.rules = rules

        # --- Customized rule sets ---
        # Base material threads assessment
        pc = {
            "Shear Stress Limits": IC6121_1_3_3_insert(),
            "Contact pressure limits": IC6121_1_3_4_insert(),
        }
        base_material = {ASSESSMENTS["plastic collapse"]: pc}

        self.custom_rules = {"Insert": base_material}

    def computeVj(
        self,
        boltAction: "BoltActionAssessor",
        material: Material,
    ) -> dict:
        """
        Compute the Vj value for the bolt assessment.

        Parameters
        ----------
        boltAction : BoltActionAssessor
            reference event to assess.
        material : Material
            Material data.

        Returns
        -------
        dict
            Dictionary containing: sigma bar, epsilon bar, N, Rule ID,
            epsilon plasticity, sigma_pre, epsilon N, sigma N.
        """
        ruleID = "IC 6131.2.1"
        ref_event = boltAction.ref_event
        T_dpa = (ref_event.temp, ref_event.dpa)
        # In a bolt action for fatigue, the primary stress are to be used for
        # sigma pre and the all loads for the stress intensity range
        s_tens_sust = boltAction.sigma_tensile
        ds_tens = boltAction.applicable_stresses["all"]["Primary stress"]
        s_pre = (s_tens_sust + ds_tens) * 1e6  # Pa

        # Nominal stress intensity range
        ds_n = (
            boltAction.applicable_stresses["all"]["Stress intensity range"] * 1e6
        )  # Pa
        # --- Nominal elastic strain range (IC 6131.2.1.1) ---
        de_n = ds_n / material.E(ref_event.temp, 0)  # No DPA dependent prop

        # --- Correction for stress concentration and plasticity ---
        #                    (IC 6131.2.1.2)
        try:
            ds = material.compute_delta_sigma_Neuber(
                ref_event.temp, ds_n, boltAction.poa.KF
            )
        except NotImplementedError:
            # Correction implemented in case true stress-strain curve is not
            # available
            ds = boltAction.poa.KF * ds_n
            de = "-"

        # --- Correction for mean stress (IC 6131.2.1.3) ---
        #             Goodman's correction
        # minimum ultimate tensile strength
        Su = material.Su_min(T_dpa)
        # minimum yield strength
        Sy = material.Sy_min(T_dpa)
        # maximum average tensile stress in bolt during cycle
        # Sigma m
        s_m = min(Sy, boltAction.poa.KF * s_pre)
        # equivalent stress range at zero mean stress
        ds_bar = ds / (1 - s_m / Su)

        if material.N.ftype == "strain":
            de_bar = material.cyclic_stress_strain(ref_event.temp, ds_bar)
            N = material.N(ref_event.temp, de_bar)
        elif material.N.ftype == "stress":
            de_bar = "-"
            if material.N.mean_stress:
                SA = ds / 2 * 1e-6  # convert to MPa
                # Sigma pre is used as max mean stress
                N = material.N(ref_event.temp, SA, s_pre * 1e-6)  # MPa
                # update ds_bar as it will be the one displayed
                ds_bar = ds
            else:
                T_s = (ref_event.temp, ds_bar / 2 * 1e-6)  # use the amplitude (MPa)
                N = material.N(T_s)

        return {
            "sigma bar": ds_bar * 1e-6,  # convert to MPa
            "epsilon bar": de_bar,
            "N": float(N),
            "Rule ID": ruleID,
            "epsilon plasticity": de,
            "sigma plasticity": ds * 1e-6,  # convert to MPa
            "sigma pre": s_pre * 1e-6,  # convert to MPa
            "epsilon N": de_n,
            "sigma N": ds_n * 1e-6,  # convert to MPa
        }


# ############# Cross Section ##############
# --- Primary stress limit for bolts ---
class IC6113(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6113"
        self.description = ["Primary stress"]

    def assess(
        self, boltaction: "BoltActionAssessor", material: Material
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = material.Sm(T_dpa)
        elif service_lvl == "D":
            allowable1 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = boltaction.applicable_stresses["primary"]["Primary stress"]

        return [(stress1, allowable1)]


# ############# Plastic collapse ##############
# --- Stress limits for structural joints high strength bolts ---
class IC6121_1_3_1(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6121.1.3.1"
        self.description = ["Mean stress, primary loads", "Mean stress, all loads"]

    def assess(
        self, boltaction: "BoltActionAssessor", material: Material
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = material.Sm(T_dpa)
            allowable2 = min(
                0.9 * material.Sy_min(T_dpa), 0.67 * material.Su_min(T_dpa)
            )
        elif service_lvl == "D":
            allowable1 = 2 * material.Sm(T_dpa)
            allowable2 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = boltaction.applicable_stresses["primary"]["Mean stress"]
        stress2 = boltaction.applicable_stresses["all"]["Mean stress"]

        return [(stress1, allowable1), (stress2, allowable2)]


class IC6121_1_3_2(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6121.1.3.2"
        self.description = ["Max stress, primary loads", "Max stress, all loads"]

    def assess(
        self, boltaction: "BoltActionAssessor", material: Material
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = 1.5 * material.Sm(T_dpa)
            allowable2 = min(1.2 * material.Sy_min(T_dpa), 0.9 * material.Su_min(T_dpa))
        elif service_lvl == "D":
            allowable1 = 3 * material.Sm(T_dpa)
            allowable2 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = boltaction.applicable_stresses["primary"]["Max stress"]
        stress2 = boltaction.applicable_stresses["all"]["Max stress"]

        return [(stress1, allowable1), (stress2, allowable2)]


class IC6121_1_3_3(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6121.1.3.3"
        self.description = [
            "Avg shear stress in threads, primary loads",
            "Avg shear stress in head, primary loads",
            "Avg shear stress in the threads, all loads",
            "Avg shear stress in head, all loads",
        ]

    def assess(
        self, boltaction: "BoltActionAssessor", material: Material
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = allowable2 = 0.6 * material.Sm(T_dpa)
            allowable3 = allowable4 = 0.6 * material.Sy_min(T_dpa)
        elif service_lvl == "D":
            allowable1 = "No limit"
            allowable2 = "No limit"
            allowable3 = "No limit"
            allowable4 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        primary = boltaction.applicable_stresses["primary"]
        _all = boltaction.applicable_stresses["all"]
        stress1 = primary["Avg shear stress in threads"]
        stress2 = primary["Avg shear stress in head"]
        stress3 = _all["Avg shear stress in threads"]
        stress4 = _all["Avg shear stress in head"]

        return [
            (stress1, allowable1),
            (stress2, allowable2),
            (stress3, allowable3),
            (stress4, allowable4),
        ]


class IC6121_1_3_3_insert(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6121.1.3.3 (base material)"
        self.description = [
            "Avg shear stress in threads, primary loads",
            "Avg shear stress in the threads, all loads",
        ]

    def assess(
        self, boltaction: "BoltActionAssessor", material: Material
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = 0.6 * material.Sm(T_dpa)
            allowable2 = 0.6 * material.Sy_min(T_dpa)
        elif service_lvl == "D":
            allowable1 = "No limit"
            allowable2 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        primary = boltaction.applicable_stresses["primary"]
        _all = boltaction.applicable_stresses["all"]
        stress1 = primary["Avg shear stress in threads"]
        stress2 = _all["Avg shear stress in threads"]

        return [(stress1, allowable1), (stress2, allowable2)]


class IC6121_1_3_4(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6121.1.3.4"
        dsc2 = "Avg contact pressure between head and assembly, all loads"
        self.description = ["Avg contact pressure between threads, all loads", dsc2]

    def assess(
        self, boltaction: "BoltActionAssessor", material: Material
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = allowable2 = 2.7 * material.Sy_min(T_dpa)
        elif service_lvl == "D":
            allowable1 = "No limit"
            allowable2 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        sdesc1 = "Avg contact pressure betweeen threads"
        sdesc2 = "Avg contact pressure between head and assembly"
        stress1 = boltaction.applicable_stresses["all"][sdesc1]
        stress2 = boltaction.applicable_stresses["all"][sdesc2]

        return [(stress1, allowable1), (stress2, allowable2)]


class IC6121_1_3_4_insert(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6121.1.3.4 (base material)"
        self.description = ["Avg contact pressure between threads, all loads"]

    def assess(
        self, boltaction: "BoltActionAssessor", material: Material
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = 2.7 * material.Sy_min(T_dpa)
        elif service_lvl == "D":
            allowable1 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        sdesc = "Avg contact pressure betweeen threads"
        stress1 = boltaction.applicable_stresses["all"][sdesc]

        return [(stress1, allowable1)]


# ############# Flow localization ##############
class IC6122_1_1(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6122.1.1"
        self.description = ["Mean stress, all loads"]

    def assess(
        self, boltaction: "BoltActionAssessor", material: Material
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)

        if dpa < 0.1:
            allowable1 = np.nan
        else:
            # select allowable
            if service_lvl == "A":
                allowable1 = material.Se(T_dpa)
            elif service_lvl == "C":
                allowable1 = 1.2 * material.Se(T_dpa)
            elif service_lvl == "D":
                allowable1 = 2 * material.Se(T_dpa)
            else:
                raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = boltaction.applicable_stresses["all"]["Mean stress"]

        return [(stress1, allowable1)]


class IC6122_1_2(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "IC 6122.1.2"
        self.description = [
            "Max stress, neglecting concentrations, all loads",
            "Max stress, including concentrations, all loads",
        ]

    def assess(
        self,
        boltaction: "BoltActionAssessor",
        material: Material,
    ) -> list[tuple]:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            Internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list[tuple]
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        if dpa < 0.1:
            allowable1 = np.nan
            allowable2 = np.nan
        else:
            # select allowable
            if service_lvl == "A":
                allowable1 = allowable2 = material.Sd(T_dpa)
            elif service_lvl == "C":
                allowable1 = allowable2 = 1.2 * material.Sd(T_dpa)
            elif service_lvl == "D":
                allowable1 = allowable2 = 1.35 * material.Sd(T_dpa)
            else:
                raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = boltaction.applicable_stresses["all"]["Max stress"]
        stress2 = stress1 * boltaction.poa.KF  # THIS NEEDS TO BE DOUBLE-CHECKED

        return [(stress1, allowable1), (stress2, allowable2)]
