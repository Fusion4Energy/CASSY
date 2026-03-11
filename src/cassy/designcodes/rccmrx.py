import math
import logging

from cassy.designcodes.codes import Code, Rule
from cassy.general.material import Material
from cassy.paths.linstress import ReferenceEvent


class RCC_MRx(Code):
    def __init__(self):
        super().__init__(name="RCC-MRx")
        # --- Initiate all elastic rules, negligible creep ---
        # P-Type and S-Type
        rules = {
            "Immediate or time-dependent excessive deformation and plastic instability": RB_3251_112(),
            "progressive deformation": RB_3261_111(),
        }
        # 'Progressive deformation or ratcheting':RB_3261_116()}
        self.rules = rules
        self.damage_types = ("Immediate", "Ratcheting")
        self.fatigue = True

    def computeVj(self, refEvent: ReferenceEvent, material: Material):
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
        name = "RB 3261.1123"
        # Fatigue Strength Reduction Factor defined in RB 3292.112:
        # ds is multiplied by f which depends on the type of joint
        f = refEvent.config.welding_f
        ds = f * refEvent.PQF
        T_ds = (T, ds)
        # de calculation
        de1 = 2 / 3 * (1 + material.nu()) * (ds / material.E(T, dpa))
        if refEvent.tresca is not None:
            # tresca for shells Pm+0.67*(Pb+Pl-Pm)
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
        else:
            # there is no primary stress
            de2 = 0

        # de3 is derived assuming de_i = 0
        de3 = material.Keps(T_ds) * math.sqrt(de1 * (de1 + de2)) - de2 - de1
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
            "de tot": detot,
            "N": N_all,
            "Rule ID": name,
            "sigma tot": ds * 1e-6,
        }  # Mpa
        return assessment


class RB_3251_112(Rule):
    def __init__(self):
        self.damage_type = "Immediate"
        self.ref = "RB 3251.112"
        self.description = ["Primary membrane", "Primary Membrane plus Bending"]

    def assess(self, refEvent: ReferenceEvent, material: Material):
        """
        Assess the rule

        Parameters
        ----------
        refEvent : LinStress.ReferenceEvent
            reference event to assess.
        material : material.Material
            Material data.

        Returns
        -------
        list
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).

        """
        T = refEvent.config.T
        dpa = refEvent.config.dpa
        n = refEvent.config.welding_n
        service_lvl = refEvent.config.service_lvl
        T_dpa = (T, dpa)  # dpa is set to zero in RCC_MR
        # select allowable
        if service_lvl == "A":
            allowable1 = n * material.Sm(T_dpa)
            allowable2 = 1.5 * n * material.Sm(T_dpa)
        elif service_lvl == "C":
            allowable1 = min(1.35 * n * material.Sm(T_dpa), material.Sy_min(T_dpa))
            allowable2 = 1.5 * allowable1
        elif service_lvl == "D":
            allowable1 = min(2.4 * n * material.Sm(T_dpa), 0.7 * material.Su_min(T_dpa))
            allowable2 = 1.5 * allowable1
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = refEvent.Pm
        stress2 = refEvent.PmPb

        return [(stress1, allowable1), (stress2, allowable2)]


class RB_3261_111(Rule):
    def __init__(self):
        self.damage_type = "Ratcheting"
        self.ref = "RB 3261.111"
        # self.description = ['3Sm rule', 'Efficiency Index',
        #                     'Efficiency Index']
        self.description = ["3Sm rule"]

    def assess(
        self,
        refEvent: ReferenceEvent,
        material: Material,
    ):
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
            Each item in the list represents an equation result, each equation
            is of the type (stress, allowable).

        """
        T = refEvent.config.T
        dpa = refEvent.config.dpa
        # n = refEvent.config.welding_n ( base metal properties for ratcheting)
        service_lvl = refEvent.config.service_lvl
        T_dpa = (T, dpa)
        # ------IC 3131.1.2 '3Sm Rule'-------#
        # select allowable
        if service_lvl == "A":
            allowable1 = 3 * material.Sm(T_dpa)
        elif service_lvl == "D" or service_lvl == "C":
            # warnings.warn(service_lvl +
            #               ' is not an admissible service level')
            return None
        else:
            raise KeyError(service_lvl + " is not an admissible service level")

        stress1 = refEvent.PmPb + refEvent.dQ

        return [(stress1, allowable1)]
