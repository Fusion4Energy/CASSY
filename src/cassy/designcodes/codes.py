# -*- coding: utf-8 -*-
"""
Created on Tue Nov  3 12:06:35 2020

@author: Davide Laghi
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cassy.bolts.code_assessor import BoltActionAssessor
from cassy.general.material import Material


class Code:
    def __init__(self, failure_modes=None, name=None):
        """
        Abstract class for a design code

        Parameters
        ----------
        failure_modes : pd.DataFrame
            columns are: ID, Description, Mechanical Damages.
        name : str
            name of the code

        Returns
            None

        """
        self.service_lvls = ["A", "C", "D"]  # Service levels
        self.failure_modes = failure_modes
        self.name = name
        self.custom_rules = {}  # No custom rules by default

    def assess(self, combined_stress, material, T=None, dpa=None, selection="All"):
        """
        Assess a reference event according to code

        Parameters
        ----------
        combined_stress : linstress.ReferenceEvent
            event to assess.
        material : material.Material
            material to assess.
        T : float
            temperature for the assessment.
        dpa : float
            displacement per atom to use for assessment.
        selection : dic, optional
            {<rule set>: <list of rules>}. The default is 'All'. other string
            can be passed, they are used to check in the custom_rule dictionary
            of the code.

        Returns
        -------
        assessments : {rulename: (assessed, rule)}
            assesed: [(allowable1, stress1), ...])
            rule: code.Rule

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
                    if T is None:
                        assessed = rule2.assess(combined_stress, material)
                    else:
                        assessed = rule2.assess(combined_stress, material, T, dpa)
                    assessments[rule_name][rule_name2] = (assessed, rule2)
            else:
                if T is None:
                    assessed = rule.assess(combined_stress, material)
                else:
                    assessed = rule.assess(combined_stress, material, T, dpa)
                assessments[rule_name] = (assessed, rule)

        return assessments


class Rule(ABC):
    def __init__(self):
        self.ref = None
        self.description = None
        self.damage_type = None
        super().__init__()

    @abstractmethod
    def assess(self):
        # The returned object has to be a list as follows
        # (stress, allowable)
        pass


class BoltCode(Code):
    @abstractmethod
    def computeVj(
        self, bolt_assessor: "BoltActionAssessor", material: Material
    ) -> dict:
        """Compute the Vj value for the bolt assessment.

        Parameters
        ----------
        bolt_assessor : BoltActionAssessor
            Assessor for the bolt actions, geometry, ref event etc.
        material : Material
            Material to be used during the assessment.

        Returns
        -------
        dict
            Dictionary containing the results of the Vj computation.
        """
        pass
