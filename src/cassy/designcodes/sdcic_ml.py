# -*- coding: utf-8 -*-
"""
Created on Mon Apr 19 12:13:22 2021

@author: s.guidozzi
"""

import math

from cassy.designcodes.codes import Code, Rule
from cassy.general.material import Material
from cassy.paths.linstress import ReferenceEvent


class SDC_IC_ML(Code):
    def __init__(self, failure_modes=None):
        super().__init__(failure_modes=failure_modes, name="SDC-IC multilayer")
        # --- Initiate all elastic rules, negligible creep ---
        # M-Type
        rules = {
            "Immediate local fracture due to exhaustion of ductility": IC7121_3_1(),
            "Progressive deformation or ratcheting": IC7131_1_1(),
        }
        self.rules = rules
        self.damage_types = ("Immediate", "Ratcheting")
        self.fatigue = True

    def computeVj(
        self, refEvent: ReferenceEvent, material: Material, T: float, dpa: float
    ):
        """
        Asses the Rule
        Parameters
        ----------
        refEvent : LinStress.ReferenceEvent
            reference event to assess.
        material : material.Material
            Material data.
        T : float
            Temperature of the path.
        dpa : float
            Displacement per atom value in the path.

        Returns
        -------
        dictionary containing de1, de2, de3, de4, , N allowable,
        ID rule and sigma tot
        """
        # ds is the total stress of the considered reference event
        name = "IC 3132.3.1"
        # Fatigue Strength Reduction Factor defined in RB 3292.112:
        # ds is multiplied by f which depends on the type of joint
        f = refEvent.f_welding
        ds = f * refEvent.PQF
        T_ds = (T, ds)
        # de calculation
        de1 = 2 / 3 * (1 + material.nu()) * (ds / material.E(T))
        if refEvent.tresca is not None:
            # tresca for shells Pm+0.67*(Pb+Pl-Pm)
            tresca = refEvent.tresca
            # de2 represents the "plastic" increase in strain due to the primary
            # stress range at the point examined, equal to tresca for shells
            # cyclic_stress_strain looks like it returns strain in [-], not %, so not change it
            de2 = material.cyclic_stress_strain(T, tresca) - 2 / 3 * (
                1 + material.nu()
            ) * (tresca / material.E(T, dpa))
        else:
            # there is no primary stress
            de2 = 0

        # de3 is derived as the intersection point of the cyclic curve and the
        # hyperbola ds*de = costant
        de3 = (de1 + de2) * (material.Keps(T_ds) - 1)
        de4 = de1 * (material.Kmu(T_ds) - 1)
        detot = de1 + de2 + de3 + de4
        # the fatigue curve of the welded joint is obatined dividing the
        # ordinates (epsilon) by f factor
        detot = detot / f
        # total allowable cycles calculation
        if material.N.ftype == "strain":
            N_all = material.N((T, detot))
        elif material.N.ftype == "stress":
            # TODO not implemented yet!
            raise ValueError("stress based curves need to be implemented")

        assessment = {
            "de1": de1,
            "de2": de2,
            "de3": de3,
            "de4": de4,
            "N": N_all,
            "Rule ID": name,
            "sigma tot": ds * 1e-6,
        }  # MPa
        return assessment


class IC7121_3_1(Rule):
    def __init__(self):
        self.damage_type = "Immediate"
        self.ref = "IC 7121.3.1"
        self.description = [
            "Elastic analysis (Local fracture)-including peak",
            "Elastic analysis (Local fracture)-excluding peak",
        ]

    def assess(self, refEvent, material, T, dpa, K=1.5):
        """
        Assess the rule

        Parameters
        ----------
        refEvent : LinStress.ReferenceEvent
            reference event to assess.
        material : material.Material
            Material data.
        T : float
            Temperature of the path.
        dpa : float
            Displacement per atom value in the path.
        K : float
            Bending Section shape factor. The default is 1.5

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).

        """
        # n = refEvent.n_welding
        service_lvl = refEvent.service_lvl
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A":
            allowable1 = material.Sd(T_dpa)
            allowable2 = material.Sd_nopeak(T_dpa)
        elif service_lvl == "C":
            allowable1 = 1.2 * material.Sd(T_dpa)
            allowable2 = 1.2 * material.Sd_nopeak(T_dpa)
        elif service_lvl == "D":
            allowable1 = 1.35 * material.Sd(T_dpa)
            allowable2 = 1.35 * material.Sd_nopeak(T_dpa)
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = refEvent.PQF
        stress2 = refEvent.PQ
        allowable2 = allowable1

        return [(stress1, allowable1), (stress2, allowable2)]


class IC7131_1_1(Rule):
    def __init__(self):
        self.damage_type = "Ratcheting"
        self.ref = "IC 7131.1.1"
        self.description = ["3Sm rule", "Efficiency Index", "Efficiency Index"]
        # self.equation = '$$A_{b}$$ (P_L+ P_b ) ̅≤〖K_eff S〗_m (〖T_m,Φt〗_m)'

    def assess(self, refEvent, material, T, dpa):
        """
        Assess the rule

        Parameters
        ----------
        refEvent: LinStress.ReferenceEvent
            Recombined linear stress to assess.
        material : material.Material
            Material data.
        T : float
            Temperature of the path.
        dpa : float
            Displacement per atom value in the path.

        Returns
        -------
        list
            Each item in the list represents an equation result, eache equation
            is of the type (stress, allowable).

        """
        # n = refEvent.n_welding ( base metal properties for ratcheting)
        service_lvl = refEvent.service_lvl
        T_dpa = (T, dpa)
        # select allowable
        if service_lvl == "A" or service_lvl == "C":
            allowable1 = 3 * material.Sm_irr(T_dpa)
        elif service_lvl == "D":
            # warnings.warn(service_lvl +
            #               ' is not an admissible service level')
            return None
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = refEvent.Sm3_stress

        # -----IC 3131.1.1 'Efficiency Index Diagram'------#
        # Operating period with secondary membrane stress
        # thermal loads are considered mandatory for ratcheting
        sigma_nm = material.Nueber(T, refEvent.PmQm_ns)["stress"]
        sigma_nmb = material.Nueber(T, refEvent.PmPbQm_ns)["stress"]
        Em = material.Nueber(T, refEvent.PmQm_ns)["Young"]
        Emb = material.Nueber(T, refEvent.PmPbQm_ns)["Young"]

        try:
            sigma_mb = (
                0.5 * (refEvent.PmPb_ns + sigma_nmb)
                + (3 * material.E(T) / Emb) * refEvent.PmPbs
            )
            sigma_m = (
                0.5 * (refEvent.Pm_ns + sigma_nm)
                + (3 * material.E(T) / Em) * refEvent.Pms
            )

        except TypeError:  # no overstress of short duration
            sigma_nm = material.Nueber(T, refEvent.PmQm)["stress"]
            sigma_nmb = material.Nueber(T, refEvent.PmPbQm)["stress"]
            sigma_mb = 0.5 * (refEvent.PmPb + sigma_nmb)
            sigma_m = 0.5 * (refEvent.Pm + sigma_nm)

        dq = refEvent.dq  # secondary stress range

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

        # effective primary stress intensity (IC 3131.1.1.5)
        p1 = sigma_m / eff_idx[0]
        p2 = sigma_mb / eff_idx[1]
        T_dpa = (T, dpa)

        stress2 = p1
        stress3 = p2
        allowable2 = 1.3 * material.Sm_irr(T_dpa)
        allowable3 = 1.5 * allowable2

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

        return [(stress1, allowable1), (stress2, allowable2), (stress3, allowable3)]
