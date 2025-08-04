import os
import shutil

import pandas as pd

from cassy.auxiliary.constants import EXCEL_AVAILABLE
from cassy.auxiliary.types import PathLike
from cassy.bolts.bolt_config import (
    FlangeAssessmentConfig,
)
from cassy.bolts.code_assessor import BoltActionAssessor
from cassy.bolts.geometry import BoltLikeGeom
from cassy.designcodes.codes import BoltCode
from cassy.office.excel_helper import ExcelOutput

if EXCEL_AVAILABLE:
    import xlwings as xw

    # # Fatigue REs
    # if fatigue:
    #     REs_data = pd.read_excel(config_file, sheet_name="REs Fatigue")
    #     _cleanNA(REs_data)
    #     REs_fatigue = {}
    #     for idx, row in REs_data.iterrows():
    #         # Get stress intensity actions
    #         pointers_str = row["Delta sigma"]
    #         all_loads = FlangeAssessmentConfig._get_actions(
    #             mainfolder, pointers_str, boltID
    #         )

    #         if code == "RCC-MRx":
    #             primary = None
    #         else:
    #             pointers_str = row["Sigma sustained"]
    #             primary = _get_actions(mainfolder, pointers_str, boltID)

    #         dic = {
    #             "preload": preload,
    #             "primary": primary,
    #             "all_loads": all_loads,
    #             "event data": row,
    #         }

    #         REs_fatigue[row["ID"]] = dic
    # else:
    #     REs_fatigue = None
    # # Standard REs
    # REs_data = pd.read_excel(config_file, sheet_name="REs")
    # _cleanNA(REs_data)
    # REs = {}
    # for idx, row in REs_data.iterrows():
    #     mainfolder = os.path.join(actionsfolder, connection)
    #     # Get the primary actions
    #     pointers_str = row["Primary"]
    #     primary = _get_actions(mainfolder, pointers_str, boltID)
    #     # Get the all loads actions
    #     pointers_str = row["All"]
    #     all_loads = _get_actions(mainfolder, pointers_str, boltID)

    #     dic = {
    #         "preload": preload,
    #         "primary": primary,
    #         "all_loads": all_loads,
    #         "event data": row,
    #     }

    #     REs[row["ID"]] = dic


# TODO remove after runner is updated
INDEX_SA = [
    "ID",
    "Operating Conditions",
    "Initiating Event",
    "Concatenated Event",
    "Loading Category",
    "T [°C]",
    "DPA",
    "Service Level",
    "Rule Extended Description",
    "Rule ID",
    "Sub-Rule",
]

INDEX_INPUT = [
    "RE ID",
    "Operating Conditions",
    "Initiating Event",
    "Concatenated Event",
]


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
        dict[str, dict[str, BoltActionAssessor]],
        dict[str, dict[str, BoltActionAssessor]],
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

    if EXCEL_AVAILABLE:

        def print_assessment(
            self,
            mainfolder: PathLike,
            app: xw.App,
            template_path: PathLike,
            fatigue: bool = False,
            insert: bool = False,
            img_folder: PathLike = "images",
        ) -> tuple[pd.DataFrame, pd.DataFrame | None]:
            """
            Print the bolt assessment as excel file.

            Parameters
            ----------
            mainfolder : str
                mainfolder where to store excels.
            app : xlwings.App
                Excel App.
            template_path : str or path
                path to the excel template.
            fatigue : bool, optional
                if true fatigue is assessed. The default is False.
            insert : bool, optional
                if true the assessment is considered for an insert. The default is
                False, for bolts.
            img_folder : str or path
                path to the images folder

            Raises
            ------
            ValueError
                If the assessment has not been run first.

            Returns
            -------
            tuple[pd.DataFrame, pd.DataFrame | None]
                A tuple containing two DataFrames:
                - Immediate recap table
                - Fatigue recap table (if fatigue is True, otherwise None)

            """
            if self.bolt_results is None:
                raise ValueError("Please assess the submodel first")
            if insert and self.insert_results is None:
                raise ValueError("Please assess the insert first")

            print("Printing " + self.name)

            # Safe creation of folder for imges
            imgs = os.path.join(img_folder, f"{self.name}")
            if not os.path.exists(imgs):
                os.mkdir(imgs)

            recaps = {"Fatigue": [], "Immediate": []}
            # print all the bolts
            for boltID, assessment in self.bolt_results.items():
                # Initialize the excel file
                # Write the excel file
                if insert:
                    insert_assessment = self.insert_results[boltID]
                else:
                    insert_assessment = None

                file = f"{self.name}_{boltID}.xlsx"
                outpath = os.path.join(mainfolder, file)
                out = self._init_excel(app, outpath, template_path)
                # Print the immemdiate damage rules
                self._print_assessment_sheets(
                    assessment,
                    out,
                    boltID,
                    imgs,
                    insert_assessment=insert_assessment,
                )
                # Print the input actions
                self._print_input_sheet(assessment, out, boltID, imgs)
                # print the fatigue
                if fatigue:
                    self._print_fatigue_sheet(assessment, out, boltID, imgs)

                # Save the excel file
                out.save()

                # Collect recap data
                row, fatigue_row = self._collect_recap_data(
                    assessment, boltID, fatigue=fatigue
                )
                recaps["Immediate"].append(row)
                if fatigue_row is not None:
                    recaps["Fatigue"].append(fatigue_row)

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
        ) -> tuple[dict[str, str], dict[str, str] | None]:
            # Collect and store data for recap tables
            # check if the assessment was good
            # adjust index
            if self.insert_results is not None:
                insert_df = self.insert_results[boltID]["Immediate"]
                df = pd.concat([assessment["Immediate"], insert_df])
            else:
                df = assessment["Immediate"]

            df.reset_index(inplace=True)
            index = ["ID", "Service Level", "Sub-Rule"]
            df.set_index(index, inplace=True)
            if len(df[df["Result"] == "FAILED"]) > 0:
                ass = "NOK"
                sm = "-"
                re = "-"
                slvl = "-"
                rule = "-"
            else:
                ass = "OK"
                # Individuate design driver
                try:
                    # take out the > 10
                    df = df[df["Safety Margin"] != "> 10"]
                    df["Safety Margin"] = df["Safety Margin"].astype(float)
                    idx = df["Safety Margin"].idxmin()

                    # Get the idxs of indices
                    names = df.index.names
                    try:
                        try:
                            # If DF is too long we can have series
                            sm = df.loc[idx, "Safety Margin"].iloc[0]
                        except AttributeError:
                            # If DF is shorter we have directly the value
                            sm = df.loc[idx, "Safety Margin"]
                        re = idx[names.index("ID")]
                        slvl = idx[names.index("Service Level")]
                        rule = idx[names.index("Sub-Rule")]
                    except KeyError:
                        # should be key error nan hence sm > 10
                        re = "No driver"
                        sm = ""
                        slvl = ""
                        rule = ""
                except TypeError:  # most likely nan
                    sm = ""
                    re = "No driver"
                    slvl = ""
                    rule = ""
                except ValueError:  # there are only >10
                    sm = "> 10"
                    re = "No driver"
                    slvl = ""
                    rule = ""

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
                    "Bolt": str(boltID),
                    "Assessment": ass,
                    "Total Usage Fraction [%]": tuf,
                }
            else:
                fatigue_recap_row = None

            return row, fatigue_recap_row

        def _init_excel(
            self, app: xw.App, out_path: PathLike, template_path: PathLike
        ) -> ExcelOutput:
            """Intialize the excel object support"""
            if os.path.isfile(out_path):
                os.remove(out_path)
            shutil.copyfile(template_path, out_path)
            out = ExcelOutput(app, out_path)
            return out

        def _print_assessment_sheets(
            self,
            assessment: dict[str, pd.DataFrame],
            out: ExcelOutput,
            boltID: str,
            imgs: PathLike,
            insert_assessment: dict[str, pd.DataFrame] | None = None,
        ):
            """Print the Immediate damage sheets. It should include the insert data
            if present"""
            self.immediate_imgs[boltID] = {}
            # Compile one sheet for each rule set
            index = ["Rule Set"]
            df = assessment["Immediate"].set_index(index)
            sets = set(df.index)

            i = 0
            for rule_set in sets:
                i = i + 1
                sheet = "Assessment " + str(i)
                outpath = self._insert_rule_set(df, rule_set, out, boltID, imgs, sheet)
                self.immediate_imgs[boltID][sheet] = outpath

            if insert_assessment:
                df = insert_assessment["Immediate"].set_index(index)
                for i, rule_set in enumerate(df.index.unique()):
                    sheet = "Assessment_base_material " + str(i + 1)
                    outpath = self._insert_rule_set(
                        df,
                        rule_set,
                        out,
                        boltID,
                        imgs,
                        sheet,
                    )
                    if outpath is not None:
                        self.immediate_imgs[boltID][sheet] = outpath

        def _insert_rule_set(
            self,
            df: pd.DataFrame,
            rule_set: str,
            out: ExcelOutput,
            boltID: str,
            imgs: PathLike,
            sheet: str,
        ) -> str | None:
            # Select the correct table
            try:
                table = df.loc[rule_set]
            except KeyError:
                # If the rule set is not present, skip it
                return None
            table.reset_index(inplace=True)
            del table["Rule Set"]
            del table["Damage Type"]

            table.set_index(INDEX_SA, inplace=True)

            # Insert the df
            out.insert_SA_df(table, sheet, divide_blocks="ID")

            # Fill the banners
            bolt_material = list(self.bolts_assessments[boltID].values())[
                0
            ].poa.material.name
            out.fill_banner(
                sheet,
                self.name,
                boltID,
                bolt_material,
                self.config.code,
                assessment=rule_set,
                paragraph=None,
            )
            # Grab and save image
            file = f"{self.name}_{boltID}_{sheet}.png"
            outpath = os.path.join(imgs, file)
            out.grab_img("all", "all", sheet, outpath)
            return outpath

        def _print_input_sheet(
            self,
            assessment: dict[str, pd.DataFrame],
            out: ExcelOutput,
            boltID: str,
            imgs: PathLike,
        ):
            # --- Handle input sheet ---
            # Fill the banners
            bolt_material = list(self.bolts_assessments[boltID].values())[
                0
            ].poa.material.name
            out.fill_banner(
                "Input_template",
                self.name,
                boltID,
                bolt_material,
                self.config.code,
                template="Input_template",
            )
            # Insert the df
            input_df = assessment["Inputs"].set_index(INDEX_INPUT)
            out.insert_SA_df(
                input_df,
                "Input",
                divide_blocks="RE ID",
                word=True,
                print_header=False,
                start_row=10,
            )

            # Grab and save image
            file = f"{self.name}_{boltID}_input.png"
            outpath = os.path.join(imgs, file)

            self.input_imgs[boltID] = outpath
            out.grab_img("all", "all", "Input", outpath)

        def _print_fatigue_sheet(
            self,
            assessment: dict[str, pd.DataFrame],
            out: ExcelOutput,
            boltID: str,
            imgs: PathLike,
        ):
            fatigue_table = assessment["Fatigue"]
            # Insert the df
            if self.config.code.name == "SDC-IC (Bolts)":
                bolt_flag = True
            else:
                bolt_flag = False
            out.insert_fatigue_df(fatigue_table, "Fatigue", bolt=bolt_flag)
            assessment_label = "Time-independent fatigue assessment"

            # Fill the banners
            bolt_material = list(self.bolts_assessments[boltID].values())[
                0
            ].poa.material.name
            out.fill_banner(
                "Fatigue",
                self.name,
                boltID,
                bolt_material,
                self.config.code,
                assessment=assessment_label,
                paragraph=None,
                template="fatigue",
            )
            # Grab and save image
            file = f"{self.name}_{boltID}_fatigue.png"
            outpath = os.path.join(imgs, file)

            self.fatigue_imgs[boltID] = outpath
            out.grab_img("all", "all", "Fatigue", outpath)


def _cleanNA(df):
    # Drop all rows containing only NaN
    df.dropna(axis=0, subset=["ID"], inplace=True)

    return df
