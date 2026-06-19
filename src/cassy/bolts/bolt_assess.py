import os

import numpy as np
import pandas as pd

from cassy.auxiliary.types import PathLike
from cassy.bolts.bolt_config import (
    FlangeAssessmentConfig,
)
from cassy.bolts.code_assessor import BoltActionAssessor
from cassy.bolts.geometry import BoltLikeGeom
from cassy.designcodes.codes import BoltCode
import logging


class FlangeAssessment:
    def __init__(
        self,
        geometries: dict[str, BoltLikeGeom],
        config: FlangeAssessmentConfig,
        fatigue: bool = False,
    ):
        """
        Perform the assessment of all bolts/inserts in a flange.

        Parameters
        ----------
        geometries : dict[BoltLikeGeom]
            dictionary of available bolts/inserts geometries.
        config : FlangeAssessmentConfig
            Configuration object containing the assessment rules.
        fatigue : bool, optional
            If True, fatigue damage assessment is included. The default is False.

        Returns
        -------
        None.

        """
        self.name = config.name
        self.geometries = geometries
        self.config = config
        self.input_imgs = {}
        self.immediate_imgs = {}
        self.fatigue_imgs = {}

        # Intitialize the assessments
        self.bolts_assessments, self.insert_assessments = (
            self._build_bolts_assessments()
        )
        if fatigue:
            self.assessments_fatigue = self._build_fatigue_assessments()
        else:
            self.assessments_fatigue = None

        self.bolt_results = None
        self.insert_results = None

    def _build_fatigue_assessments(self) -> dict[str, dict[str, BoltActionAssessor]]:
        """build all the fatigue assessments using the config file. In each dict, the
        keys are the bolt ID and the ref event."""
        fatigue_assessments = {}
        for boltID, row in self.config.bolts_spec.iterrows():
            if row["Geom type"] == "bolt":
                fatigue_assessments[boltID] = self._build_fatigue_assessors(
                    row, str(boltID)
                )

        return fatigue_assessments

    def _build_bolts_assessments(
        self,
    ) -> tuple[
        dict[str | int, dict[str, BoltActionAssessor]],
        dict[str | int, dict[str, BoltActionAssessor]],
    ]:
        """build all the bolts assessments using the config file. In each dict, the
        keys are the bolt ID and the ref event."""
        bolts_assessments = {}
        insert_assessments = {}
        for boltID, row in self.config.bolts_spec.iterrows():
            if row["Geom type"] == "bolt":
                bolts_assessments[boltID] = self._build_assessors(row, str(boltID))
            elif row["Geom type"] == "insert":
                insert_assessments[boltID] = self._build_assessors(row, str(boltID))

        return bolts_assessments, insert_assessments

    def _build_assessors(
        self, row: pd.Series, boltID: str
    ) -> dict[str, BoltActionAssessor]:
        geom_data = self.geometries[f"{row['Geom data']}_{row['Geom type']}"]
        preload = row["Preload [N]"]
        ref_events = self.config.REs[str(boltID)]

        assessors = {}
        for ref_event in ref_events:
            primary_actions = self.config.get_actions(
                boltID, ref_event.primary[0], ref_event.primary[1]
            )
            all_actions = self.config.get_actions(
                boltID, ref_event.all_loads[0], ref_event.all_loads[1]
            )

            assessor = BoltActionAssessor(
                f"{boltID}",
                primary_actions,
                all_actions,
                ref_event,
                geom_data,
                preload,
            )
            assessors[ref_event.name] = assessor

        return assessors

    def _build_fatigue_assessors(
        self, row: pd.Series, boltID: str
    ) -> dict[str, BoltActionAssessor]:
        assert self.config.REs_fatigue is not None, (
            "Fatigue reference events are not defined in the configuration."
        )
        geom_data = self.geometries[f"{row['Geom data']}_{row['Geom type']}"]
        preload = row["Preload [N]"]
        ref_events = self.config.REs_fatigue[str(boltID)]

        assessors = {}
        for ref_event in ref_events:
            if ref_event.sigma_sustained is None:
                # If no sustained stress is defined, use the primary actions
                primary_actions = pd.Series(
                    {"Fx": 0, "Fy": 0, "Fz": 0, "Mx": 0, "My": 0, "Mz": 0}
                )
            else:
                primary_actions = self.config.get_actions(
                    boltID, ref_event.sigma_sustained[0], ref_event.sigma_sustained[1]
                )
            delta_plus = self.config.get_actions(
                boltID, ref_event.delta_sigma[0][0], ref_event.delta_sigma[0][1]
            )
            delta_minus = self.config.get_actions(
                boltID, ref_event.delta_sigma[1][0], ref_event.delta_sigma[1][1]
            )
            all_actions = delta_plus - delta_minus
            assessor = BoltActionAssessor(
                f"{boltID}",
                primary_actions,
                all_actions,
                ref_event,
                geom_data,
                preload,
            )
            assessors[ref_event.name] = assessor

        return assessors

    def assess(self, insert: bool = False) -> dict[str, dict[str, pd.DataFrame]]:
        """
        Assess all reference events

        Parameters
        ----------
        insert : bool, optional
            if true the assessment is considered for an insert. The default is
            False

        Returns
        -------
        dict[str, dict[str, pd.DataFrame]]
            A dictionary containing the assessment results for each bolt ID.
            The keys are the bolt IDs, and the values are dictionaries with
            keys "Immediate", "Fatigue", and "Inputs" containing the respective
            DataFrames.

        """
        # --- immediate damage ---
        # Assess bolts
        results = {}
        code = self.config.code
        assert isinstance(code, BoltCode), (
            f"The code must be a code specific for bolts, not {code.name}"
        )
        if insert:
            assessors = self.insert_assessments
        else:
            assessors = self.bolts_assessments
        for bolt_id, assessors in assessors.items():
            dfs = []
            inputs = []
            for _, assessor in assessors.items():
                df = assessor.assess(code, insert=insert)
                dfs.append(df)
                inputs.append(assessor.get_df_actions())

            immediate_assessment = pd.concat(dfs)
            input_df = pd.concat(inputs)

            # --- fatigue damage ---
            if self.assessments_fatigue and not insert:
                rows = []
                for assessor in self.assessments_fatigue[bolt_id].values():
                    vj = assessor.computeVj(code)
                    rows.append(vj)
                fatigue_assessment = pd.DataFrame(rows)
            else:
                fatigue_assessment = None

            results[bolt_id] = {
                "Immediate": immediate_assessment,
                "Fatigue": fatigue_assessment,
                "Inputs": input_df,
            }
        if insert:
            self.insert_results = results
        else:
            self.bolt_results = results
        return results

    def print_global_df(self, mainfolder: PathLike, insert: bool = False):
        """
        Print the global DataFrame of the bolts assessment to an Excel file.

        Parameters
        ----------
        mainfolder : PathLike
            The folder where the global DataFrame will be saved.
        insert : bool, optional
            If true, the insert results are printed. The default is False.

        Returns
        -------
        None.

        """
        if insert:
            if self.insert_results is None:
                raise ValueError("Please assess the insert first")
            results = self.insert_results
            tag = "base_material"
        else:
            if self.bolt_results is None:
                raise ValueError("Please assess the submodel first")
            results = self.bolt_results
            tag = "bolt"

        # Create a DataFrame to hold all results
        dfs = []
        fatigue_dfs = []
        for bolt_id, assessment in results.items():
            immediate = assessment["Immediate"]
            fatigue = assessment["Fatigue"]
            for df, list_df in zip([immediate, fatigue], [dfs, fatigue_dfs]):
                if df is not None and not df.empty:
                    df["Bolt ID"] = bolt_id
                    list_df.append(df)

        if len(dfs) == 0:
            logging.warning("No immediate assessment results to print.")
            return
        else:
            df = pd.concat(dfs, ignore_index=True).set_index(["Bolt ID", "ID"])
            df.to_excel(os.path.join(mainfolder, f"{self.name}_{tag}_immediate.xlsx"))

        if fatigue_dfs:
            fatigue_df = pd.concat(fatigue_dfs, ignore_index=True).set_index(
                ["Bolt ID", "ID"]
            )
            fatigue_df.to_excel(
                os.path.join(mainfolder, f"{self.name}_{tag}_fatigue.xlsx")
            )

    def get_recap(
        self, fatigue: bool = False
    ) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
        """get recap dataframes for the assessments

        Parameters
        ----------
        fatigue : bool, optional
            If True, include fatigue assessments, by default False

        Returns
        -------
        tuple[pd.DataFrame | None, pd.DataFrame | None]
            Immediate and fatigue recap dataframes
        """
        recaps = {"Fatigue": [], "Immediate": []}
        # print all the bolts
        for boltID, assessment in self.bolt_results.items():
            # Collect recap data
            row, fatigue_row = self._collect_recap_data(
                assessment, boltID, fatigue=fatigue
            )
            if row is not None:
                recaps["Immediate"].append(row)
            if fatigue_row is not None:
                recaps["Fatigue"].append(fatigue_row)

        if len(recaps["Immediate"]) == 0:
            immediate_recap = None
        else:
            immediate_recap = pd.DataFrame(recaps["Immediate"])
        if fatigue:
            fatigue_recap = pd.DataFrame(recaps["Fatigue"])
        else:
            fatigue_recap = None

        return immediate_recap, fatigue_recap

    def _collect_recap_data(
        self,
        assessment: dict[str, pd.DataFrame],
        boltID: str,
        fatigue: bool = False,
    ) -> tuple[dict[str, str] | None, dict[str, str] | None]:
        # Collect and store data for recap tables
        # check if the assessment was good
        # adjust index
        if self.insert_results is not None:
            insert_df = self.insert_results[boltID]["Immediate"]
            df = pd.concat([assessment["Immediate"], insert_df])
        else:
            df = assessment["Immediate"]

        if df.empty:
            row = None
        else:
            df.reset_index(inplace=True)
            # first check if the assessment was successful
            if len(df[df["Result"] == "FAILED"]) > 0:
                ass = "NOK"
            else:
                ass = "OK"

            # --- Individuate design driver ---
            # take out the > 10 and assessment not required
            df1 = df[df["Safety Margin"] != "> 10"]
            df1 = df1[df1["Result"] != "Assessment not required"]
            # it may be now that there are no rows left, no driver
            if len(df1) == 0:
                # No driver found
                re = "No driver"
                sm = ""
                slvl = ""
                rule = ""
            else:
                margins = df1["Safety Margin"].astype(float).values
                idx = np.argmin(margins)

                sm = margins[idx]
                re = df1.iloc[idx]["ID"]
                slvl = df1.iloc[idx]["Service Level"]
                rule = df1.iloc[idx]["Sub-Rule"]

            # recover the bolt geometry
            geom = self.config.bolts_spec.loc[boltID, "Geom data"]
            if isinstance(geom, pd.DataFrame) or isinstance(geom, pd.Series):
                geom = geom.values[0]

            row = {
                "Submodel": self.config.name,
                "Path": str(boltID),
                "Path Type": str(geom),
                "Assessment": ass,
                "Reference Event": re,
                "Service lvl": slvl,
                "Rule": rule,
                "Safety Margin": sm,
            }

        if fatigue:
            fatigue_table = assessment["Fatigue"]
            Vtot = fatigue_table["Vj"].sum()
            if Vtot < 1:
                ass = "OK"
            else:
                ass = "NOK"

            tuf = round(Vtot * 100, 2)
            fatigue_recap_row = {
                "Submodel": self.config.name,
                "ID": str(boltID),
                "Assessment": ass,
                "Total Usage Fraction [%]": tuf,
            }
        else:
            fatigue_recap_row = None

        return row, fatigue_recap_row

    def compute_banner(
        self,
        bolt_id: int,
        complete: bool = False,
        assessment: str | None = None,
        paragraph: str | None = None,
    ) -> dict[str, str]:
        """
        Compute the banner information for a specific bolt.

        Returns
        -------
        dict[str, str]
            A dictionary containing the banner information.
        """
        banner = {
            "model": "",
            "submodel": self.config.name,
            "id": str(bolt_id),
            "material": list(self.bolts_assessments[bolt_id].values())[
                0
            ].poa.material.name,
        }
        if complete:
            banner.update(
                {
                    "assessment": assessment,
                    "code": self.config.code.name,
                    "paragraph": paragraph,
                }
            )
        return banner

    def get_assessment_tables(
        self, bolt_id: str, damage_type: str, insert: bool = False
    ) -> dict[str, pd.DataFrame]:
        """
        Get the assessment tables for each rule set for a specific bolt ID and
        damage type

        Parameters
        ----------
        bolt_id : str
            The ID of the bolt for which to retrieve the assessment table.
        damage_type : str
            The type of damage for which to retrieve the assessment table.
        insert : bool, optional
            If True, retrieves the insert assessment table. The default is False.

        Returns
        -------
        dict[str, pd.DataFrame]
            A dictionary where keys are rule sets and values are DataFrames
            containing the assessment results for the specified damage type.
        """
        if insert:
            if self.insert_results is None:
                raise ValueError("Please assess the insert first")
            assessment = self.insert_results[bolt_id]
        else:
            if self.bolt_results is None:
                raise ValueError("Please assess the submodel first")
            assessment = self.bolt_results[bolt_id]

        # add a table for each rule set
        tables = {}
        df = assessment[damage_type].set_index("Rule Set")
        sets = set(df.index)
        for rule_set in sets:
            # Select the correct table
            try:
                table = df.loc[rule_set]
                table = table.reset_index()
            except KeyError:
                # If the rule set is not present, skip it
                continue
            tables[rule_set] = table
        return tables
