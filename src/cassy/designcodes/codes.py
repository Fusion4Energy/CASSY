from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from cassy.bolts.code_assessor import BoltActionAssessor
    from cassy.paths.linstress import ReferenceEvent
from cassy.auxiliary import trace
from cassy.general.material import Material


class Rule(ABC):
    def __init__(self):
        self.ref = None
        self.description: list[str] = []
        self.damage_type = None
        self.sequential = (
            False  # True when sub-rules are hierarchical (e.g., 3Sm screens EI)
        )
        super().__init__()

    @abstractmethod
    def assess(self, *args, **kwargs) -> list[tuple[float, float]]:
        # The returned object has to be a list as follows
        # (stress, allowable)
        pass


class Code:
    # factor bringing the applied stress returned by the rules to Pa
    APPLIED_TO_PA = 1.0

    def __init__(self, name: str | None = None):
        """
        Abstract class for a design code

        """
        self.name = name
        self.service_lvls = ["A", "C", "D"]  # Service levels
        self.custom_rules = {}  # No custom rules by default
        self.rules: dict[str, dict[str, Rule]] = {}  # No rules by default

    def assess(
        self,
        combined_stress,
        material: Material,
        selection: str | dict | None = "All",
    ) -> dict[str, tuple[tuple[float, float], Rule]]:
        """
        Assess a reference event according to code

        Parameters
        ----------
        combined_stress : linstress.ReferenceEvent | BoltActionAssessor
            event to assess.
        material : material.Material
            material to assess.
        selection : dic, optional
            {<rule set>: <list of rules>}. The default is 'All'. other string
            can be passed, they are used to check in the custom_rule dictionary
            of the code.

        Returns
        -------
        dict[str, tuple[tuple[float, float], Rule]]

        """
        rules2assess = {}
        if selection == "All":
            # default option
            rules2assess = self.rules

        elif type(selection) is str:
            # Then the custom rule set is checked
            try:
                rules2assess = self.custom_rules[selection]
            except KeyError:
                raise ValueError(selection + " is not an implemented custom rule set")

        else:
            # Normal selection from the dictionary
            for rule_set, rules in selection.items():
                rules2assess[rule_set] = {}
                for rule in rules:
                    rules2assess[rule_set][rule] = self.rules[rule_set][rule]

        assessments = {}
        for rule_name, rule in rules2assess.items():
            if type(rule) is dict:
                # This means that this is still not a rule
                assessments[rule_name] = {}
                for rule_name2, rule2 in rule.items():
                    with trace.scope(rule_set=rule_name, rule=rule2.ref):
                        assessed = rule2.assess(combined_stress, material)
                        _record_equations(rule2, assessed, self.APPLIED_TO_PA)
                    assessments[rule_name][rule_name2] = (assessed, rule2)
            else:
                with trace.scope(rule_set=rule_name, rule=rule.ref):
                    assessed = rule.assess(combined_stress, material)
                    _record_equations(rule, assessed, self.APPLIED_TO_PA)

                assessments[rule_name] = (assessed, rule)

        return assessments


def record_allowables(allowables: tuple, formulas: tuple | None = None) -> None:
    """Record the allowables of a rule, numbered as its equations."""
    for i, allowable in enumerate(allowables):
        note = None if formulas is None else formulas[i]
        trace.record(f"allowable {i + 1}", allowable, kind="allowable", note=note)


def _record_equations(
    rule: Rule, assessed: list | None, applied_to_pa: float = 1.0
) -> None:
    """Record the (stress, allowable) couples returned by a rule, in Pa."""
    if not trace.is_active():
        return
    if assessed is None:
        trace.record("rule", "not applicable", kind="branch")
        return
    for i, couple in enumerate(assessed):
        try:
            equation = rule.description[i]
        except IndexError:
            equation = f"equation {i + 1}"
        with trace.scope(equation=equation):
            if couple is None or couple[0] is None:
                trace.record("equation", "not evaluated", kind="branch")
                continue
            stress = couple[0] * applied_to_pa
            allowable = couple[1]
            trace.record("applied", stress, kind="result", unit="Pa")
            trace.record("allowable", allowable, kind="result", unit="Pa")
            try:
                ratio = float(stress) / float(allowable)
            except (TypeError, ValueError, ZeroDivisionError):
                ratio = None
            trace.record("applied/allowable", ratio, kind="result")


class BoltCode(Code):
    # bolt rules return the applied stress in MPa and the allowable in Pa
    APPLIED_TO_PA = 1e6

    @abstractmethod
    def computeVj(
        self, bolt_assessor: "BoltActionAssessor", material: Material
    ) -> dict:
        """Compute the Vj value for the bolt assessment.

        Parameters
        ----------
        bolt_assessor : BoltActionAssessor
            Assessor for the bolt
        material : Material
            Material to be used during the assessment.

        Returns
        -------
        dict
            Dictionary containing the results of the Vj computation.
        """
        pass
