# -*- coding: utf-8 -*-
"""
Created on Mon Dec 28 17:07:10 2020

@author: davide laghi
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cassy.bolts.code_assessor import BoltActionAssessor
from cassy.designcodes.codes import Code, Rule
from cassy.general.material import Material


class RCCMR_Bolts(Code):
    def __init__(self, failure_modes=None):
        super().__init__(failure_modes=failure_modes, name="RCC-MR (Bolts)")
        # Minimum bolt cross-sectional area for bolted flanged joints which do
        # not have to satisfy leaktightness
        base = {"Limitation of shear stress": S1_RB3284_121()}
        rules = {"Stress limits for base material": base}
        self.rules = rules


# --- Assessment of the base material ---
class S1_RB3284_121(Rule):
    def __init__(self):
        self.damage_type = "M"
        self.ref = "S1 RB 3284.121"
        d1 = "Limitation of the shear stress due only to mechanical loads"
        d2 = "Limitation of the shear stress"
        self.description = [d1, d2]

    def assess(self, boltaction: "BoltActionAssessor", material: Material) -> list:
        """
        Assess the rule

        Parameters
        ----------
        boltaction : BoltActionAssessor
            internal actions acting on the bolt.
        material : Material
            Material data.

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).
        """

        service_lvl = boltaction.ref_event.service_lvl
        T = boltaction.ref_event.temp
        dpa = boltaction.ref_event.dpa
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = 0.3 * material.Sm_irr(T_dpa)
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
