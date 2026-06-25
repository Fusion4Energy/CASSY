import logging
import os
from typing import Union

import numpy as np
import pandas as pd
from tqdm import tqdm

logger = logging.getLogger(__name__)

from cassy.auxiliary.types import PathLike
from cassy.designcodes.codes import Code
from cassy.paths.paths_config import Configuration
from cassy.general.material import Material
from cassy.paths.linstress import (
    LinStress,
    ReferenceEvent,
    ReferenceEventConfig,
    LinStressConfig,
)


class Path:
    def __init__(
        self,
        pnum: int,
        material: Material,
        ptype: str = "normal",
        Welding_n: float = 1,
        Welding_f: float = 1,
        REs_beg: Union[list[ReferenceEvent], None] = None,
        REs_end: Union[list[ReferenceEvent], None] = None,
        REs_fatigue_beg: Union[list[ReferenceEvent], None] = None,
        REs_fatigue_end: Union[list[ReferenceEvent], None] = None,
    ):
        """
        Object representing a path

        Parameters
        ----------
        pnum : int
            Number assigned to the path in the submodel.
        material : material.Material
            material of the path.
        ptype : str, optional
            either 'fillet' or 'normal'. The default is 'normal'.
        REs_beg : list of linstress.ReferenceEvent, optional
            reference events objects in the path begin. The default is [].
        REs_end : list of linstress.ReferenceEven, optional
            reference events objects in the path end. The default is [].
        REs_fatigue_beg : list of linstress.ReferenceEvent, optional
            reference events objects for fatigue in the path begin.
            The default is [].
        REs_fatigue_end : list of linstress.ReferenceEven, optional
            reference events objects for fatigue in the path end.
            The default is [].

        Raises
        ------
        ValueError
            if ptype is not admissible.

        Returns
        -------
        None.

        """
        if REs_beg is None:
            REs_beg = []
        if REs_end is None:
            REs_end = []
        if REs_fatigue_beg is None:
            REs_fatigue_beg = []
        if REs_fatigue_end is None:
            REs_fatigue_end = []
        self.REs_beg = REs_beg
        self.REs_end = REs_end
        self.REs_fatigue_end = REs_fatigue_end
        self.REs_fatigue_beg = REs_fatigue_beg
        # Collect all loads acting on the path
        # original loads stress matrices
        self.basic_loads = self._update_loads()

        self.material = material
        if ptype in ["fillet", "normal"]:
            self.ptype = ptype
        else:
            raise ValueError(str(ptype) + " is not a valid path type")
        self.pnum = pnum
        self.Welding_n = Welding_n
        self.Welding_f = Welding_f

        # Assessment must be computed first
        self.ass_beg = None
        self.ass_end = None

    def add_RE(self, RE: ReferenceEvent, pos: str, fatigue: bool = False) -> None:
        """
        Add a ReferenceEvent to the path. Differentiate if it is a fatigue RE

        Parameters
        ----------
        RE : linstress.ReferenceEvent
            Event to add.
        pos : str
            either 'begin' or 'end'.
        fatigue : bool
            if true the reference event should be considered for fatigue
            assessment. The default is False

        Raises
        ------
        ValueError
            raised if pos is not admissible.

        Returns
        -------
        None.

        """
        if pos == "begin":
            if fatigue:
                self.REs_fatigue_beg.append(RE)
            else:
                self.REs_beg.append(RE)
        elif pos == "end":
            if fatigue:
                self.REs_fatigue_end.append(RE)
            else:
                self.REs_end.append(RE)
        else:
            raise ValueError(str(pos) + ' must be either "begin" or "end"')

        self._update_loads()

    def assess(self, code: Code) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Assess all reference events in path

        Parameters
        ----------
        code : code.Code
            Design code to use.

        Returns
        -------
        self.ass_beg, self.ass_end : tuple[pd.DataFrame, pd.DataFrame]
            pd.DataFrames containing the assessments of the begin and end
            position of the path
        """
        dfs_beg = []
        dfs_end = []
        # Standard REs
        for RE_beg, RE_end in zip(self.REs_beg, self.REs_end):
            df_beg = RE_beg.assess(code, self.material)
            dfs_beg.append(df_beg)

            df_end = RE_end.assess(code, self.material)
            dfs_end.append(df_end)

        self.ass_beg = pd.concat(dfs_beg)
        self.ass_end = pd.concat(dfs_end)

        return self.ass_beg, self.ass_end

    def assess_fatigue(self, code: Code) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Assess all fatigue reference events in path

        Parameters
        ----------
        code : code.Code
            Design code to use.

        Returns
        -------
        self.ass_fatigue_beg, self.ass_fatigue_end : tuple[pd.DataFrame, pd.DataFrame]
            pd.DataFrames containing the assessments of the begin and end
            position of the path

        """
        rows_beg = []
        rows_end = []
        # Fatigue REs
        for RE_beg, RE_end in zip(self.REs_fatigue_beg, self.REs_fatigue_end):
            row_beg = RE_beg.computeVj(code, self.material)
            rows_beg.append(row_beg)

            row_end = RE_end.computeVj(code, self.material)
            rows_end.append(row_end)

        self.ass_fatigue_beg = pd.DataFrame(rows_beg)
        self.ass_fatigue_end = pd.DataFrame(rows_end)

        return self.ass_fatigue_beg, self.ass_fatigue_end

    def _get_basic_loads_df(self, pos: str) -> pd.DataFrame:
        """
        build a DF from all the stress matrix of the single loads acting
        on the path

        Parameters
        ----------
        pos : str
         either begin or end.

        Returns
        -------
        df : pd.DataFrame
            dataframe collecting the input of the assessment.

        """
        dfs = []
        stress_names = [
            "Membrane stress",
            "Bending stress",
            "Peak stress",
        ]
        for linstress in self.basic_loads[pos]:
            # get it in MPa
            mtrx = linstress.original_mtrx.copy() * 1e-6
            # reorder the index
            mtrx = mtrx.loc[["M", "B", "F"]]
            stress_mtrx = mtrx.reset_index()
            stress_mtrx["Load Condition"] = linstress.config.name
            stress_mtrx["Stress breakdown"] = stress_names
            dfs.append(stress_mtrx)

        df = pd.concat(dfs)
        df.set_index(["Load Condition", "Stress breakdown"], inplace=True)

        return df

    def _update_loads(self) -> dict[str, list[LinStress]]:
        """
        Adjourn the loads conditions for instance when a RE is added.
        If the reference events of the fatigue are changed this does not
        produce any effect. It is expected that no basic loads should be added
        from fatigue reference events.

        Returns
        -------
        basic_loads : dict[str, list[LinStress]]
            load conditions.

        """
        basic_loads = {"begin": [], "end": []}
        basic_loads_names = []
        for RE_beg, RE_end in zip(self.REs_beg, self.REs_end):
            for beg_stress, end_stress in zip(RE_beg.stresses, RE_end.stresses):
                if beg_stress.config.name not in basic_loads_names:
                    basic_loads_names.append(beg_stress.config.name)
                    basic_loads["begin"].append(beg_stress)
                    basic_loads["end"].append(end_stress)
        self.basic_loads = basic_loads
        return basic_loads


def _round_ass_df(df: pd.DataFrame) -> pd.DataFrame:
    dic = {"Applied [MPa]": 0, "Allowable [MPa]": 0, "Safety Margin": 2}
    df = df.round(dic)
    return df


class Submodel:
    def __init__(self, name: str, config: Configuration, mat_dict: dict[str, Material]):
        """
        Object representing a submodel where paths have to be assessed

        Parameters
        ----------
        name : str
            Submodel name.
        config : Configuration
            Contains information on the paths stress tensors and load combinations
            to assess.
        mat_dict : dict[str, Material]
            Material library available for the assessment

        Returns
        -------
        None.

        """
        self.name = name
        self.config = config
        self.mat_dict = mat_dict

        # Initialize all paths
        paths: dict[int, Path] = {}
        for idx, row in config["Paths"].iterrows():
            pnum = int(idx)
            ptype = row["Type"]
            welding_n = float(row["Welding-n"])
            welding_f = float(row["Welding-f"])
            material = mat_dict[row["Material"]]

            path = Path(
                pnum, material, ptype=ptype, Welding_n=welding_n, Welding_f=welding_f
            )
            paths[pnum] = path
        self.paths = paths

        self.assessments = None
        self.recap_rows = {}
        self.images = {}

    def assess(self, code: Code, fatigue: bool = True) -> None:
        """
        Assess all paths in the submodel

        Parameters
        ----------
        code : code.Code
            Design code to use for the assessment.
        fatigue: bool, optional
            if False the fatigue assessment is skipped. The default is True

        Returns
        -------
        None.

        """
        assessments = {}
        for idx, path in self.paths.items():
            beg, end = path.assess(code)
            assessments[path.pnum] = {"begin": beg, "end": end}

            if fatigue:
                beg_f, end_f = path.assess_fatigue(code)
                assessments[path.pnum]["begin fatigue"] = beg_f
                assessments[path.pnum]["end fatigue"] = end_f

        self.assessments = assessments
        self.code = code

    def print_global_df(self, outpath: PathLike) -> None:
        """dump a global dataframe with all the assessment results.

        Parameters
        ----------
        outpath : PathLike
            path to the output folder.

        Raises
        ------
        ValueError
            If the assessment has not been run yet.
        """
        if self.assessments is None:
            raise ValueError("Please assess the submodel first")
        outfile = os.path.join(outpath, f"{self.name}_global_assessment.xlsx")
        outfile_fatigue = os.path.join(
            outpath, f"{self.name}_global_assessment_fatigue.xlsx"
        )
        dfs = []
        dfs_fatigue = []
        for pnum, dfs_dict in self.assessments.items():
            for pos, df in dfs_dict.items():
                if df is not None:
                    df["Path"] = pnum
                    df["Position"] = pos
                    if "fatigue" in pos:
                        dfs_fatigue.append(df)
                    else:
                        dfs.append(df)
        global_df = pd.concat(dfs).set_index(["Path", "Position", "ID"])
        global_df.to_excel(outfile)

        if dfs_fatigue:
            global_df_fatigue = pd.concat(dfs_fatigue).set_index(
                ["Path", "Position", "ID"]
            )
            global_df_fatigue.to_excel(outfile_fatigue)

    def compute_banner(
        self,
        pnum: int,
        pos: str,
        complete: bool = False,
        assessment: str | None = None,
        paragraph: str | None = None,
    ) -> dict[str, str]:
        """Compute the banner for a single assessment table

        Parameters
        ----------
        pnum : int
            Path number.
        pos : str
            Position (begin or end).
        complete : bool, optional
            If True, the complete banner is returned, by default False.
        assessment : str | None, optional
            Assessment type, by default None
        paragraph : str | None, optional
            Paragraph text, by default None

        Returns
        -------
        dict[str, str]
            A dictionary containing the banner information.
        """

        poa = "Path " + str(pnum) + " " + pos
        material = self.paths[pnum].material.name
        banner = {
            "model": "",
            "submodel": self.config.submodel,
            "id": poa,
            "material": material,
        }
        if complete:
            banner.update(
                {
                    "assessment": assessment,
                    "code": self.config.code,
                    "paragraph": paragraph,
                }
            )
        return banner

    def get_recap(
        self,
        fatigue: bool = True,
    ):
        """
        Get the recap rows for the assessment.

        Parameters
        ----------
        fatigue: bool, optional
            if False the fatigue assessment is skipped. The default is True

        Raises
        ------
        ValueError
            If the assessment has not been run yet.

        Returns
        -------
        recap_rows : dic
            the keys are the damage type and the items are dictionaries
            containing the rows for the final recap table.

        """

        if self.assessments is None:
            raise ValueError("Please assess the submodel first")

        logger.info("Assessing %s with %s", self.name, self.code.name)

        # Cycling on all paths
        # recap_rows = {'Immediate': [], 'Ratcheting': [], 'Fatigue': []}
        recap_rows = {}
        for pnum, dfs in tqdm(self.assessments.items(), desc="Path"):
            # Cycling on begin and end
            for pos in ["begin", "end"]:
                df = dfs[pos]
                col = "Damage Type"
                # get the damage type names
                df_types = {}
                damage_types = self.code.damage_types
                for key in damage_types:
                    df_type = df[df[col] == key]
                    df_type = _round_ass_df(df_type)
                    df_type = df_type.drop(col, axis=1)
                    df_types[key] = df_type

                for sheet, df in df_types.items():
                    if sheet not in recap_rows.keys():
                        recap_rows[sheet] = []

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

                    row = {
                        "Submodel": self.name,
                        "Path": "Path " + str(pnum) + " " + pos,
                        "Path Type": self.paths[pnum].ptype,
                        "Assessment": ass,
                        "Reference Event": re,
                        "Service lvl": slvl,
                        "Rule": rule,
                        "Safety Margin": sm,
                    }

                    recap_rows[sheet].append(row)

                if fatigue:
                    if "Fatigue" not in recap_rows.keys():
                        recap_rows["Fatigue"] = []

                    Vtot = dfs[pos + " fatigue"]["Vj"].sum()
                    if Vtot < 1:
                        ass = "OK"
                    else:
                        ass = "NOK"

                    tuf = round(Vtot * 100, 2)
                    row = {
                        "Submodel": self.name,
                        "ID": "Path " + str(pnum) + " " + pos,
                        "Assessment": ass,
                        "Total Usage Fraction [%]": tuf,
                    }

                    recap_rows["Fatigue"].append(row)

            self.recap_rows = recap_rows

        return recap_rows

    def build_REs(self, fatigue: bool = False) -> None:
        """Build all the reference events for all paths in the submodel.

        Parameters
        ----------
        fatigue : bool, optional
            if True also fatigue events are built, by default False
        """
        for pathnum in self.config.paths:
            # identify all reference events of the path
            re_list = self.config.get_REid_path(pathnum)
            for re in re_list:
                self._build_RE(pathnum, re)

            if fatigue:
                re_list_fatigue = self.config.get_REid_path(pathnum, fatigue=True)
                for re in re_list_fatigue:
                    self._build_RE(pathnum, re, fatigue=True)

    def _build_RE(self, pathnum: int, re_ID: str, fatigue: bool = False) -> None:
        """
        build a reference event to assign to a specific path and submodel

        Parameters
        ----------
        pathnum : int
            number of the path onto which operate
        conf : configuration.Configuration
            Configuration object of the submodel
        re_ID : str
            ID of the reference event to add.
        fatigue : bool, optional
            If true, the RE is a fatigue one. The default is False.

        Returns
        -------
        None.

        """
        if fatigue:
            des = " Fatigue"
        else:
            des = ""

        idx = (pathnum, re_ID)

        load_names = self.config.get_REloads(pathnum, re_ID, fatigue=fatigue)
        try:
            oc = (
                self.config["Reference Event" + des]
                .loc[idx, "Operating Conditions"]
                .iloc[0]
            )
            ie = (
                self.config["Reference Event" + des]
                .loc[idx, "Initiating Event"]
                .iloc[0]
            )
            ce = (
                self.config["Reference Event" + des]
                .loc[idx, "Concatenated Event"]
                .iloc[0]
            )
            service_lvl = (
                self.config["Reference Event" + des].loc[idx, "Service Level"].iloc[0]
            )
            load_ctg = (
                self.config["Reference Event" + des].loc[idx, "Loading ctg."].iloc[0]
            )
            T = self.config["Reference Event" + des].loc[idx, "T [°C]"].iloc[0]
            dpa = self.config["Reference Event" + des].loc[idx, "DPA"].iloc[0]

            # Additional data for fatigue event
            if fatigue:
                ncycles = (
                    self.config["Reference Event" + des].loc[idx, "N of cycles"].iloc[0]
                )
            else:
                ncycles = None
        except AttributeError:
            oc = self.config["Reference Event" + des].loc[idx, "Operating Conditions"]
            ie = self.config["Reference Event" + des].loc[idx, "Initiating Event"]
            ce = self.config["Reference Event" + des].loc[idx, "Concatenated Event"]
            service_lvl = self.config["Reference Event" + des].loc[idx, "Service Level"]
            load_ctg = self.config["Reference Event" + des].loc[idx, "Loading ctg."]
            T = self.config["Reference Event" + des].loc[idx, "T [°C]"]
            dpa = self.config["Reference Event" + des].loc[idx, "DPA"]

            # Additional data for fatigue event
            if fatigue:
                ncycles = self.config["Reference Event" + des].loc[idx, "N of cycles"]
            else:
                ncycles = None

        # Recover the corresponding LinStress
        for pos in ["begin", "end"]:
            stresses = []
            for load in load_names:
                linstress = self._build_linearized_stress(load, pathnum, pos)
                stresses.append(linstress)
            config = ReferenceEventConfig(
                service_lvl=service_lvl,
                re_ID=re_ID,
                T=T,
                dpa=dpa,
                oc=oc,
                ie=ie,
                ce=ce,
                load_ctg=load_ctg,
                ncycles=ncycles,
            )
            RE = ReferenceEvent(stresses, config)
            # Add the reference event to the correct path
            self.paths[pathnum].add_RE(RE, pos, fatigue=fatigue)

    def _build_linearized_stress(self, load: str, pathnum: int, pos: str) -> LinStress:
        """
        Build a LinStress object using the data contained in the submodel configuration

        Parameters
        ----------
        load : str
            name of the single load
        pathnum : int
            number of the path
        pos : str
            either 'begin' or 'end'.

        Returns
        -------
        LinStress
            Linearized Stress object.
        """
        ptype = self.config["Paths"].loc[pathnum, "Type"]
        welding_n = self.config["Paths"].loc[pathnum, "Welding-n"]
        welding_f = self.config["Paths"].loc[pathnum, "Welding-f"]

        data = self.config["Stresses"].loc[load]
        data["name"] = load
        data["ptype"] = ptype
        data["Welding_n"] = welding_n
        data["Welding_f"] = welding_f

        tensor = self.config.get_stress_tensor(load, pathnum, pos)

        config = LinStressConfig.from_dict(data)
        stress = LinStress(tensor, config)
        return stress
