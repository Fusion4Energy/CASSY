from cassy.designcodes.codes import BoltCode, Rule
from cassy.general.material import Material
import numpy as np
from typing import TYPE_CHECKING
from scipy.optimize import fsolve

if TYPE_CHECKING:
    from cassy.bolts.code_assessor import BoltActionAssessor


class EN_13445_Bolts(BoltCode):
    def __init__(
        self,
    ):
        super().__init__(name="EN 13445 (Bolts)")
        self.rules = {}
        self.custom_rules = {"Insert": {}}

    def computeVj(
        self,
        boltAction: "BoltActionAssessor",
        material: Material,
    ):
        pass
        ruleID = "Part 3, 18.12"
        temp = boltAction.ref_event.temp
        dpa = boltAction.ref_event.dpa
        ds = boltAction.applicable_stresses["all"][
            "Stress intensity range"
        ]  # convert to MPa
        Rm = material.Su_min((temp, dpa)) * 1e-6  # convert to MPa
        d = boltAction.poa.d

        if Rm > 785:
            Rm = 785

        def _compute_fe(N: float):
            if d > 25:  # mm
                Fe = (25 / d) ** 0.182
                if N >= 2e6:
                    fe = Fe
                else:
                    fe = Fe ** (0.1 * np.log(N) - 0.465)
            else:
                fe = 1
            return fe

        def _compute_N(N: float):
            # Compute fe
            fe = _compute_fe(N)
            fb = material.ft_star(temp) * fe

            return N - 285 * (Rm * fb / ds) ** 3

        if ds / Rm >= 0.0522:
            N = fsolve(_compute_N, 100)[0]
        else:
            N = 2e6

        return {
            "delta sigma": ds,
            "Rm": Rm,
            "fe": _compute_fe(N),
            "ft_star": material.ft_star(temp),
            "fb": material.ft_star(temp) * _compute_fe(N),
            "N": N,
            "Rule ID": ruleID,
            "-": "-",
        }
