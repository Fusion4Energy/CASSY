from abc import ABC
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from cassy.auxiliary.custom_errors import ConfigError
from cassy.auxiliary.types import LoadTerm
from cassy.designcodes.codes import Code


@dataclass
class Event(ABC):
    """
    General event for an assessment.

    Parameters
    ----------
    name : str
        identifier of the event.
    oper_cond : str
        operational condition of the event.
    init_event : str
        initial event of the event.
    concat_event : str
        concatenation event of the event.
    temp : float
        temperature for the event in celsius.
    dpa : float
        displacement per atom for the event.
    load_category : str
        load category of the event. Either A, C or D.
    service_lvl : str
        service level of the event. Either I, II, III or IV.

    Raises
    ------
    ConfigError
        if wrong service level or load category is provided
    """

    name: str
    oper_cond: str
    init_event: str
    concat_event: str
    temp: float
    dpa: float
    load_category: str
    service_lvl: str

    def __post_init__(self):
        # allowable service levels
        if self.service_lvl not in ["A", "C", "D"]:
            raise ConfigError(
                f"Service level {self.service_lvl} not allowed. "
                f"Allowed service levels are: A, C, D"
            )
        if self.load_category not in ["I", "II", "III", "IV"]:
            raise ConfigError(
                f"Load category {self.load_category} not allowed. "
                f"Allowed load categories are: I, II, III, IV"
            )


@dataclass
class BoltReferenceEvent(Event):
    """
    General event for an assessment.

    Parameters
    ----------
    name : str
        identifier of the event.
    oper_cond : str
        operational condition of the event.
    init_event : str
        initial event of the event.
    concat_event : str
        concatenation event of the event.
    temp : float
        temperature for the event in celsius.
    dpa : float
        displacement per atom for the event.
    load_category : str
        load category of the event. Either A, C or D.
    service_lvl : str
        service level of the event. Either I, II, III or IV.
    primary : list[LoadTerm]
        linear combination of load steps giving the primary actions.
    all_loads : list[LoadTerm]
        linear combination of load steps giving all actions.

    Raises
    ------
    ConfigError
        if wrong service level or load category is provided
    """

    primary: list[LoadTerm]
    all_loads: list[LoadTerm]


@dataclass
class BoltReferenceEventFatigue(Event):
    """
    General event for an assessment.

    Parameters
    ----------
    name : str
        identifier of the event.
    oper_cond : str
        operational condition of the event.
    init_event : str
        initial event of the event.
    concat_event : str
        concatenation event of the event.
    temp : float
        temperature for the event in celsius.
    dpa : float
        displacement per atom for the event.
    load_category : str
        load category of the event. Either A, C or D.
    service_lvl : str
        service level of the event. Either I, II, III or IV.
    n_cycles : int
        number of cycles for the event.
    delta_sigma : tuple[list[LoadTerm], list[LoadTerm]]
        the two load combinations whose difference is the delta sigma (+, -).
    sigma_sustained : list[LoadTerm] | None
        load combination giving the sustained sigma of the event.

    Raises
    ------
    ConfigError
        if wrong service level or load category is provided
    """

    n_cycles: int
    delta_sigma: tuple[list[LoadTerm], list[LoadTerm]]
    sigma_sustained: list[LoadTerm] | None = None


class FlangeAssessmentConfig:
    def __init__(
        self,
        actions: pd.DataFrame,
        code: Code,
        bolts_spec: pd.DataFrame,
        REs: dict[str, list[BoltReferenceEvent]],
        REs_fatigue: Optional[dict[str, list[BoltReferenceEventFatigue]]] = None,
        name: str = "Flange XXX",
    ):
        """
        Configuration for the flange assessment.

        Parameters
        ----------
        actions : pd.DataFrame
            Actions on the bolts for each analysis, loadstep and boltID.
        code : Code
            Design code to be used for the assessment.
        bolts_spec : pd.DataFrame
            Geometrical and material specifications of the bolts.
        REs : dict[str, list[BoltReferenceEvent]]
            List of reference events for the assessment of each bolt ID
        REs_fatigue : dict[str, list[BoltReferenceEventFatigue]], optional
            List of fatigue reference events for the assessment of each bolt ID.
            The default is None.
        name : str, optional
            Name of the flange assessment, by default "Flange XXX".
        """
        self.actions = actions
        self.code = code
        self.bolts_spec = bolts_spec
        self.REs = REs
        self.REs_fatigue = REs_fatigue
        self.name = name
        if "insert" in bolts_spec["Geom type"].values:
            self.has_insert = True
        else:
            self.has_insert = False

    def get_actions(self, bolt_id: str, terms: list[LoadTerm]) -> pd.Series:
        """
        Sum the actions on a bolt over a linear combination of load steps.

        Parameters
        ----------
        bolt_id : str
            The ID of the bolt.
        terms : list[LoadTerm]
            The signed (analysis, load step) terms to combine.

        Returns
        -------
        pd.Series
            The combined actions for the given bolt ID.
        """
        if not terms:
            raise ConfigError(f"Empty load combination for bolt {bolt_id}.")
        actions = self.actions.iloc[0].copy()
        actions[:] = 0

        for term in terms:
            try:
                to_add = self.actions.loc[bolt_id, term.analysis, term.step]
            except KeyError:
                raise ConfigError(
                    f"Actions for bolt {bolt_id} with analysis {term.analysis} "
                    f"and load step {term.step} not found."
                )
            if term.sign == "+":
                actions += to_add
            else:
                actions -= to_add
        return actions
