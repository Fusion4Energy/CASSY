# -*- coding: utf-8 -*-
"""
Created on Fri Nov 18 10:35 2022

@authors: davide falco, davide laghi
"""

from cassy.designcodes.codes import Code, Rule

ASSESSMENTS = {
    "core": "Rules for the screw core",
    "threads heads": "Rules for screw threads and head",
    "threads base": "Rules for threads in base material",
}


class RCCMRx_Bolts(Code):
    def __init__(self, failure_modes=None):
        super().__init__(failure_modes=failure_modes, name="RCC-MRx (Bolts)")

        core = {"Mean stress": RB3284_1112(), "Max stress": RB3284_1113()}
        threads_heads = {"Shear stress": RB3284_1211(), "Bearing stress": RB3284_1213()}
        rules = {ASSESSMENTS["core"]: core, ASSESSMENTS["threads heads"]: threads_heads}
        self.rules = rules

        # --- Customized rule sets ---
        # Base material threads assessment
        pc = {"Shear Stress Limits": RB3284_1211_insert()}
        base_material = {ASSESSMENTS["threads base"]: pc}

        self.custom_rules = {"Insert": base_material}

    def computeVj(self, boltAction, material, T, dpa, Kf):
        """
        Asses the Rule
        Parameters
        ----------
        boltAction : section_action.ReferenceEvent
            reference event to assess.
        material : material.Material
            Material data.
        T : float
            Temperature of the path.
        dpa : float
            Displacement per atom value in the path.
        Kf : float
            fatigue stress coefficient (RB 3285.11) for the application
            of the Neuber's rule.

        Returns
        -------
        dictionary containing: sigma bar, epsilon bar, N, Rule ID,
        epsilon plasticity, signa_pre, epsilon N, sigma N.
        """
        ruleID = "RB 3261.112"

        # Nominal stress intensity range, needs to be brought in Pa from MPa
        ds_n = boltAction.stresses["all"]["Stress intensity range"] * 1e6

        # Range of total stress multiplied by the stress coefficient
        ds_tot = Kf * ds_n
        T_ds = (T, ds_tot)

        # delta epsilon calculation
        de1 = 100 * 2 / 3 * (1 + material.nu) * (ds_tot / material.E(T))
        de2 = 0
        de3 = (de1 + de2) * (material.Keps(T_ds) - 1)
        de4 = de1 * (material.Kmu(T_ds) - 1)
        detot = de1 + de2 + de3 + de4

        N = material.N((T, detot))

        return {
            "de1": de1,
            "de2": de2,
            "de3": de3,
            "de4": de4,
            "de4": de4,
            "N": N,
            "Rule ID": ruleID,
            "sigma tot": ds_tot * 1e-6,
        }


class RB3284_1112:
    def __init__(self):
        self.damage_type = "P"
        self.ref = "RB3284_1112"
        self.description = ["Mean stress, primary loads", "Mean stress, all loads"]

    def assess(self, boltaction, material, T, dpa):
        """
        Assess the rule. For level C allowable taken from RB 3284.112,
        for level D taken from RB 3284.113. Primary for level A taken from
        RB3284_1111.

        Parameters
        ----------
        boltaction : section_action.BoltSectionActions
            internal actions acting on the bolt.
        material : material.Material
            Material data.
        T : float
            Temperature of the bolt.
        dpa : float
            Displacement per atom value in the bolt section.

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.service_lvl
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A":
            allowable = allowable = material.Sm_irr(T_dpa)
            allowable2 = min(
                0.9 * material.Sy_min(T_dpa), 0.67 * material.Su_min(T_dpa)
            )

        elif service_lvl == "C":
            if material.Su_min(T_dpa) >= 700e6:
                allowable = material.Sm_irr(T_dpa)
                allowable2 = min(
                    0.9 * material.Sy_min(T_dpa), 0.67 * material.Su_min(T_dpa)
                )
            else:
                allowable = 1.5 * material.Sm_irr(T_dpa)
                allowable2 = "No limit"

        elif service_lvl == "D":
            if material.Su_min(T_dpa) <= 700e6:
                allowable = min(
                    2.4 * material.Sm_irr(T_dpa), 0.7 * material.Su_min(T_dpa)
                )
            else:
                allowable = 2 * material.Sm_irr(T_dpa)

            allowable2 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress = boltaction.stresses["primary"]["Mean stress"]
        stress2 = boltaction.stresses["all"]["Mean stress"]

        return [(stress, allowable), (stress2, allowable2)]


class RB3284_1113:
    def __init__(self):
        self.damage_type = "P"
        self.ref = "RB 3284.1113"
        self.description = ["Max stress, primary loads", "Max stress, all loads"]

    def assess(self, boltaction, material, T, dpa):
        """
        Assess the rule. For level C allowable taken from RB 3284.112,
        for level D taken from RB 3284.113

        Parameters
        ----------
        boltaction : section_action.BoltSectionActions
            internal actions acting on the bolt.
        material : material.Material
            Material data.
        T : float
            Temperature of the bolt.
        dpa : float
            Displacement per atom value in the bolt section.

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.service_lvl
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A":
            allowable1 = "No limit"
            allowable2 = 1.33 * min(
                0.9 * material.Sy_min(T_dpa), 0.67 * material.Su_min(T_dpa)
            )
        elif service_lvl == "C":
            allowable1 = 2.25 * material.Sm_irr(T_dpa)
            if material.Su_min(T_dpa) >= 700e6:
                allowable2 = 1.33 * min(
                    0.9 * material.Sy_min(T_dpa), 0.67 * material.Su_min(T_dpa)
                )
            else:
                allowable2 = "No limit"

        elif service_lvl == "D":
            if material.Su_min(T_dpa) <= 700e6:
                allowable1 = "No limit"
                allowable2 = 1.5 * allowable1
            else:
                allowable1 = "No limit"
                allowable2 = 3 * material.Sm_irr(T_dpa)
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = boltaction.stresses["primary"]["Max stress"]
        stress2 = boltaction.stresses["all"]["Max stress"]

        return [(stress1, allowable1), (stress2, allowable2)]


class RB3284_1211(Rule):
    def __init__(self):
        self.damage_type = "P"
        self.ref = "RB 3284.1211"
        self.description = [
            "Avg shear stress in threads, primary loads",
            "Avg shear stress in head, primary loads",
            "Avg shear stress in the threads, all loads",
            "Avg shear stress in head, all loads",
        ]

    def assess(self, boltaction, material, T, dpa):
        """
        Assess the rule. For level C allowable taken from RB 3284.1212

        Parameters
        ----------
        boltaction : section_action.BoltSectionActions
            internal actions acting on the bolt.
        material : material.Material
            Material data.
        T : float
            Temperature of the bolt.
        dpa : float
            Displacement per atom value in the bolt section.

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.service_lvl
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A":
            allowable1 = allowable2 = 0.6 * material.Sm_irr(T_dpa)
            allowable3 = allowable4 = 0.6 * material.Sy_min(T_dpa)

        elif service_lvl == "C":
            if material.Su_min(T_dpa) >= 700e6:
                allowable1 = allowable2 = 0.6 * material.Sm_irr(T_dpa)
                allowable3 = allowable4 = 0.6 * material.Sy_min(T_dpa)

            else:
                allowable1 = "No limit"
                allowable2 = "No limit"
                allowable3 = "No limit"
                allowable4 = "No limit"

        elif service_lvl == "D":
            allowable1 = "No limit"
            allowable2 = "No limit"
            allowable3 = "No limit"
            allowable4 = "No limit"
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        primary = boltaction.stresses["primary"]
        stress1 = primary["Avg shear stress in threads"]
        stress2 = primary["Avg shear stress in head"]

        _all = boltaction.stresses["all"]
        stress3 = _all["Avg shear stress in threads"]
        stress4 = _all["Avg shear stress in head"]

        return [
            (stress1, allowable1),
            (stress2, allowable2),
            (stress3, allowable3),
            (stress4, allowable4),
        ]


class RB3284_1211_insert(Rule):
    def __init__(self):
        self.damage_type = "P"
        self.ref = "RB 3284.1211 (base material)"
        self.description = [
            "Avg shear stress in threads, primary loads",
            "Avg shear stress in the threads, all loads",
        ]

    def assess(self, boltaction, material, T, dpa):
        """
        Assess the rule. For level C allowable taken from RB 3284.1212

        Parameters
        ----------
        boltaction : section_action.BoltSectionActions
            internal actions acting on the bolt.
        material : material.Material
            Material data.
        T : float
            Temperature of the bolt.
        dpa : float
            Displacement per atom value in the bolt section.

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.service_lvl
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = 0.6 * material.Sm_irr(T_dpa)
            allowable2 = 0.6 * material.Sy_min(T_dpa)

        elif service_lvl == "D":
            allowable1 = "No limit"
            allowable2 = "No limit"

        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        primary = boltaction.stresses["primary"]
        stress1 = primary["Avg shear stress in threads"]

        _all = boltaction.stresses["all"]
        stress2 = _all["Avg shear stress in threads"]

        return [(stress1, allowable1), (stress2, allowable2)]


class RB3284_1213(Rule):
    def __init__(self):
        self.damage_type = "P"
        self.ref = "RB 3284.1213"
        self.description = ["Avg contact pressure between head and assembly, all loads"]

    def assess(self, boltaction, material, T, dpa):
        """
        Assess the rule

        Parameters
        ----------
        boltaction : section_action.BoltSectionActions
            internal actions acting on the bolt.
        material : material.Material
            Material data.
        T : float
            Temperature of the bolt.
        dpa : float
            Displacement per atom value in the bolt section.

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.service_lvl
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A":
            allowable = 2.7 * material.Sy_min(T_dpa)
        elif service_lvl == "C":
            if material.Su_min(T_dpa) >= 700e6:
                allowable = 2.7 * material.Sy_min(T_dpa)
            else:
                allowable = "No limit"
        elif service_lvl == "D":
            allowable = "No limit"

        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        sdesc = "Avg contact pressure between head and assembly"
        stress = boltaction.stresses["all"][sdesc]

        return [(stress, allowable)]
