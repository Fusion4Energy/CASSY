import os
from abc import ABC
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from cassy.auxiliary.custom_errors import ConfigError
from cassy.auxiliary.functions import cleanNA
from cassy.auxiliary.types import PathLike
from cassy.designcodes.codes import Code
from cassy.designcodes.map import BOLT_CODES


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
    primary : tuple[str, str]
        primary actions of the event. The first element is the name of analysis
        and the second element is the load step.
    all_loads : tuple[str, str]
        all actions of the event. The first element is the name of analysis
        and the second element is the load step.

    Raises
    ------
    ConfigError
        if wrong service level or load category is provided
    """

    primary: tuple[str, str]
    all_loads: tuple[str, str]

    def __post_init__(self):
        super().__post_init__()
        # check that both primary and all_loads are of size 2
        if len(self.primary) != 2:
            raise ConfigError(
                f"Primary actions {self.primary} not allowed. "
                f"If building from excel use the notation analysis_loadstep "
            )
        if len(self.all_loads) != 2:
            raise ConfigError(
                f"All actions {self.all_loads} not allowed. "
                f"If building from excel use the notation analysis_loadstep "
            )


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
    delta_sigma : tuple[tuple[str, str], tuple[str, int]]
        delta sigma of the event. in each tuple, the first element is the name of
        analysis and the second element is the load step. The difference between the
        two load steps is the delta sigma.
    sigma_sustained : tuple[str, str] | None
        sustained sigma of the event. The first element is the name of the analysis and
        the second element is the load step.

    Raises
    ------
    ConfigError
        if wrong service level or load category is provided
    """

    n_cycles: int
    delta_sigma: tuple[tuple[str, str], tuple[str, str]]
    sigma_sustained: tuple[str, str] | None = None

    def __post_init__(self):
        super().__post_init__()
        # check that both delta_sigma and sigma_sustained are of size 2
        if len(self.delta_sigma[0]) != 2:
            raise ConfigError(
                f"Delta sigma {self.delta_sigma} not allowed. "
                f"If building from excel use the notation analysis_loadstep "
            )
        if self.sigma_sustained is not None and len(self.sigma_sustained) != 2:
            raise ConfigError(
                f"Sustained sigma {self.sigma_sustained} not allowed. "
                f"If building from excel use the notation analysis_loadstep "
            )


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

    @classmethod
    def from_excel(
        cls, config_file: PathLike, actions_file: PathLike, fatigue: bool = True
    ) -> "FlangeAssessmentConfig":
        """Build a FlangeAssessmentConfig from an excel files and a csv file containing
        the actions on the bolts.

        Parameters
        ----------
        config_file : PathLike
            path to the excel file containing all the configuration data needed for
            the assessment of a flange.
        actions_file : PathLike
            path to the .csv file containing all the actions on the bolts extracted
            from FEM.
        fatigue : bool, optional
            if True fatigue assesment should also be performed, by default True

        Returns
        -------
        FlangeAssessmentConfig
            An instance of FlangeAssessmentConfig with the provided data.
        """
        # --- Build the section actions for the REs ---
        actions = pd.read_csv(actions_file)
        actions["boltID"] = actions["boltID"].astype(str)
        actions.set_index(["boltID", "analysis", "loadstep"], inplace=True)
        name = os.path.basename(config_file).split(".")[0]
        additional_data = pd.read_excel(config_file, sheet_name="Additional Data")
        additional_data = additional_data.set_index("Parameter")["Value"].to_dict()
        code = BOLT_CODES[additional_data["Code"]]

        bolts_spec = cleanNA(
            pd.read_excel(config_file, sheet_name="Bolts"), column_id="Bolt ID"
        ).set_index("Bolt ID")

        # Parse the Reference Events
        REs_df = cleanNA(pd.read_excel(config_file, sheet_name="REs")).set_index(
            "Bolt ID"
        )
        REs = {}
        for bolt_id in REs_df.index.unique():
            re_list = []

            event_data = REs_df.loc[bolt_id]
            if isinstance(event_data, pd.Series):
                # If only one row for the bolt ID, convert to DataFrame
                event_data = event_data.to_frame().T

            for _, row in event_data.iterrows():
                re = BoltReferenceEvent(
                    name=row["ID"],
                    oper_cond=row["Operating Conditions"],
                    init_event=row["Initiating Event"],
                    concat_event=row["Concatenated Event"],
                    temp=float(row["T [°C]"]),
                    dpa=float(row["DPA"]),
                    load_category=row["Load Category"],
                    service_lvl=row["Service Level"],
                    primary=tuple(row["Primary"].split("_")),
                    all_loads=tuple(row["All"].split("_")),
                )
                re_list.append(re)
            REs[str(bolt_id)] = re_list

        # Parse the Reference Events for fatigue
        if fatigue:
            REs_fatigue = {}
            REs_fatigue_df = cleanNA(
                pd.read_excel(config_file, sheet_name="REs Fatigue")
            ).set_index("Bolt ID")
            for bolt_id in REs_fatigue_df.index.unique():
                re_fatigue_list = []

                event_data = REs_fatigue_df.loc[bolt_id]
                if isinstance(event_data, pd.Series):
                    # If only one row for the bolt ID, convert to DataFrame
                    event_data = event_data.to_frame().T

                for _, row in event_data.iterrows():
                    delta_sigma = (
                        tuple(row["Delta sigma +"].split("_")),
                        tuple(row["Delta sigma -"].split("_")),
                    )
                    if code.name == "RCC-MR (Bolts)":
                        sustained = None
                    else:
                        sustained = tuple(row["Sigma sustained"].split("_"))
                    re_fatigue = BoltReferenceEventFatigue(
                        name=row["ID"],
                        oper_cond=row["Operating Conditions"],
                        init_event=row["Initiating Event"],
                        concat_event=row["Concatenated Event"],
                        temp=float(row["T [°C]"]),
                        dpa=float(row["DPA"]),
                        load_category=row["Load Category"],
                        service_lvl=row["Service Level"],
                        n_cycles=int(row["Total number of cycles"]),
                        delta_sigma=delta_sigma,
                        sigma_sustained=sustained,
                    )
                    re_fatigue_list.append(re_fatigue)
                REs_fatigue[str(bolt_id)] = re_fatigue_list

        else:
            REs_fatigue = None

        return cls(
            actions=actions,
            code=code,
            bolts_spec=bolts_spec,
            REs=REs,
            REs_fatigue=REs_fatigue,
            name=name,
        )

    def get_actions(self, bolt_id: str, analysis: str, loadstep: str) -> pd.Series:
        """
        Get the primary or all loads actions for a given bolt ID and pointer.

        Parameters
        ----------
        bolt_id : str
            The ID of the bolt.
        analysis : str
            The analysis type (e.g., "thermal").
        loadstep : str
            The load step (e.g., "1").

        Returns
        -------
        pd.Series
            The primary actions for the given bolt ID and ref event.
        """
        try:
            return self.actions.loc[bolt_id, analysis, int(loadstep)]
        except KeyError:
            raise ConfigError(
                f"Actions for bolt {bolt_id} with analysis {analysis} and load step {loadstep} not found."
            )
