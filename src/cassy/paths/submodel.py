# -*- coding: utf-8 -*-
"""
Created on Tue Dec  1 09:24:31 2020

@author: davide laghi
"""

import os
import shutil

import numpy as np
import pandas as pd
from tqdm import tqdm

from cassy.office.excel_helper import ExcelOutput


class Submodel:
    def __init__(self, name, paths):
        """
        Object representing a submodel where paths have to be assessed

        Parameters
        ----------
        name : str
            Submodel name.
        paths : list of Path
            paths in the submodel.

        Returns
        -------
        None.

        """
        self.name = name
        self.paths = paths

        self.assessments = None
        self.code = None
        self.recap_rows = {}
        self.images = {}

    @classmethod
    def from_df(cls, name, conf_df, mat_dic):
        """
        Generate a submodel with an auxiliary df

        Parameters
        ----------
        cls : TYPE
            DESCRIPTION.
        name : str
            Name of the submodel.
        conf_df : pandas.DataFrame
            auxiliary dataframe.
        mat_dic : dic
            contains the materials to use

        Returns
        -------
        TYPE
            DESCRIPTION.

        """
        paths = {}
        for idx, row in conf_df.iterrows():
            path = Path.from_series(idx, row, [], [], [], [], mat_dic)
            paths[idx] = path
        return cls(name, paths)

    def assess(self, code, fatigue=True):
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
                if code.name == "ASME B31.3":
                    beg_f, end_f = path.assess_Se(code)

                else:
                    beg_f, end_f = path.assess_fatigue(code)
                assessments[path.pnum]["begin fatigue"] = beg_f
                assessments[path.pnum]["end fatigue"] = end_f

        self.assessments = assessments
        self.code = code

    def print_assessment(
        self, mainfolder, app, template_path, img_folder="Images", fatigue=True
    ):
        """
        Prints the excel assessment for each path (both begin and end) and at
        the same time grabs and saves the images of the assessment in the
        img_folder. Additionally it returns the rows for the final recap table
        of the assessment.

        Parameters
        ----------
        mainfolder : str or path
            path to the submodel assessment (i.e. where to put excels).
        app : xw.App
            Excel app from xlwings.
        template_path : str or path
            path to the excel template.
        img_folder : str or path, optional
            path to the folder where to store the images.
            The default is 'Images'.
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

        print("Assessing " + self.name + " with " + self.code.name)

        # Safe creation of folder for images
        imgs = os.path.join(img_folder, self.name)
        if not os.path.exists(img_folder):
            os.mkdir(img_folder)
        if os.path.exists(imgs):
            shutil.rmtree(imgs)
        os.mkdir(imgs)

        # Cycling on all paths
        # recap_rows = {'Immediate': [], 'Ratcheting': [], 'Fatigue': []}
        recap_rows = {}
        for pnum, dfs in tqdm(self.assessments.items(), desc="Path"):
            self.images[pnum] = {}
            # Cycling on begin and end
            for pos in ["begin", "end"]:
                self.images[pnum][pos] = {}
                # Get all needed data for compilation
                poa = "Path " + str(pnum) + " " + pos
                material = self.paths[pnum].material.name
                idx = [
                    "ID",
                    "Operating Conditions",
                    "Initiating Event",
                    "Concatenated Event",
                    "Loading Category",
                    "Service Level",
                    "Rule Extended Description",
                    "Rule ID",
                    "Sub-Rule",
                    "T [°C]",
                    "dpa",
                ]
                df = dfs[pos].set_index(idx)

                col = "Damage Type"
                # get the damage type names
                df_types = {}
                damage_types = self.code.damage_types
                for key in damage_types:
                    df_type = df[df[col] == key]
                    df_type = _round_ass_df(df_type)
                    df_type = df_type.drop(col, axis=1)
                    df_types[key] = df_type

                # Get the input df
                input_df = self.paths[pnum]._get_basic_loads_df(pos)
                df_types["Input"] = input_df

                # Write the excel file
                file = self.name + "_" + str(pnum) + "_" + pos + ".xlsx"
                out_path = os.path.join(mainfolder, file)
                if os.path.isfile(out_path):
                    os.remove(out_path)
                shutil.copyfile(template_path, out_path)

                out = ExcelOutput(app, out_path)

                # Fill the banners
                out.fill_banner("SA_template", self.name, poa, material, self.code)
                out.fill_banner(
                    "Input_template",
                    self.name,
                    poa,
                    material,
                    None,
                    template="Input_template",
                )

                if fatigue:
                    # no further actions needed on the df
                    fatigue_df = dfs[pos + " fatigue"]
                    if self.code.name == "ASME B31.3":
                        idx = ["Rule ID", "loads"]
                        fatigue_df.set_index(idx, inplace=True)
                        # Fill the banner
                        out.fill_banner("Fatigue", self.name, poa, material, self.code)

                    else:
                        # Fill banner
                        out.fill_banner(
                            "Fatigue_template",
                            self.name,
                            poa,
                            material,
                            self.code,
                            template="fatigue",
                        )

                    df_types["Fatigue"] = fatigue_df

                for sheet, df in df_types.items():
                    if sheet == "Input":
                        out.insert_SA_df(
                            df,
                            sheet,
                            divide_blocks="Load Condition",
                            print_header=False,
                            word=True,
                            start_row=10,
                        )
                    elif sheet == "Fatigue":
                        if self.code.name == "ASME B31.3":
                            out.insert_SA_df(df, sheet)
                        else:
                            out.insert_fatigue_df(df, sheet)

                    else:
                        out.insert_SA_df(df, sheet, divide_blocks="ID")

                    # lastcell = tab .anchor_end
                    file = (
                        self.name + "_" + str(pnum) + "_" + pos + "_" + sheet + ".png"
                    )
                    outpath = os.path.join(imgs, file)
                    self.images[pnum][pos][sheet] = outpath
                    out.grab_img("all", "all", sheet, outpath)

                # file = self.name+'_'+str(pnum)+'_'+pos+'.xlsx'
                out.save(out_path)

                for sheet, df in df_types.items():
                    if sheet in ["Fatigue", "Input"]:
                        continue
                    else:
                        if sheet not in recap_rows.keys():
                            recap_rows[sheet] = []

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
                                    # If the DF is too long we can have siries
                                    sm = df.loc[idx, "Safety Margin"].iloc[0]
                                except AttributeError:
                                    # If the DF is shorter
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
                        except ValueError:  # they are all >10
                            sm = ""
                            re = "No driver"
                            slvl = ""
                            rule = ""

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
                    if self.code.name == "ASME B31.3":
                        df = fatigue_df
                        if len(df[df["Result"] == "FAILED"]) > 0:
                            ass = "NOK"
                            sm = "-"
                        else:
                            ass = "OK"
                            try:
                                sm = float(df.loc["302.3.5 d", "Safety Margin"])
                            except ValueError:  # sm > 10
                                sm = "-"
                        row = {
                            "Submodel": self.name,
                            "Path": "Path " + str(pnum) + " " + pos,
                            "Path Type": self.paths[pnum].ptype,
                            "Assessment": ass,
                            "Safety Margin": sm,
                        }

                        recap_rows["Fatigue"].append(row)

                    else:
                        Vtot = fatigue_df["Vj"].sum()
                        if Vtot < 1:
                            ass = "OK"
                        else:
                            ass = "NOK"

                        tuf = round(Vtot * 100, 2)
                        row = {
                            "Submodel": self.name,
                            "Path": "Path " + str(pnum) + " " + pos,
                            "Assessment": ass,
                            "Total Usage Fraction [%]": tuf,
                        }

                        recap_rows["Fatigue"].append(row)

            self.recap_rows = recap_rows

        return recap_rows


class Path:
    def __init__(
        self,
        pnum,
        material,
        ptype="normal",
        Welding_n=1,
        Welding_f=1,
        REs_beg=[],
        REs_end=[],
        REs_fatigue_beg=[],
        REs_fatigue_end=[],
    ):
        """
        Object representing a path

        Parameters
        ----------
        pnum : str/float
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

    @classmethod
    def from_series(
        cls, pnum, row, REs_beg, REs_end, REs_fatigue_beg, REs_fatigue_end, mat_dic
    ):
        """
        Create a path with the help of a Series

        Parameters
        ----------
        cls : TYPE
            DESCRIPTION.
        pnum : str/float
            number assigned to the path.
        row : pd.Series
            contains the useful data.
        REs_beg : list of linstress.ReferenceEvent, optional
            reference events objects in the path begin.
        REs_end : list of linstress.ReferenceEven, optional
            reference events objects in the path end.
        REs_fatigue_beg : list of linstress.ReferenceEvent, optional
            reference events objects in the path begin.
        REs_fatigue_end : list of linstress.ReferenceEven, optional
            reference events objects in the path end.
        mat_dic : dic
            contains the Material objects to use.

        Returns
        -------
        Path
            Creates a Path object.

        """
        ptype = row["Type"]
        Welding_n = float(row["Welding-n"])
        Welding_f = float(row["Welding-f"])
        material = mat_dic[row["Material"]]

        return cls(
            pnum,
            material,
            ptype=ptype,
            Welding_n=Welding_n,
            Welding_f=Welding_f,
            REs_beg=REs_beg,
            REs_end=REs_end,
            REs_fatigue_beg=REs_fatigue_beg,
            REs_fatigue_end=REs_fatigue_end,
        )

    def add_RE(self, RE, pos, fatigue=False):
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

    def assess(self, code):
        """
        Assess all reference events in path

        Parameters
        ----------
        code : code.Code
            Design code to use.

        Returns
        -------
        self.ass_beg, self.ass_end
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

    def assess_fatigue(self, code):
        """
        Assess all fatigue reference events in path

        Parameters
        ----------
        code : code.Code
            Design code to use.

        Returns
        -------
        self.ass_beg, self.ass_end
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

    def assess_Se(self, code):
        """
        Assess fatigue according to ASME B31.3

        Parameters
        ----------
        code : code.Code
            Design code to use

        Returns
        -------
        self.ass_fatigue_beg, self.ass_fatigue_end

        pd.DataFrames containing the assessments of the begin and end

        """

        # List of Fatigue REs for ASME B31.3, usually Thernal NO and Baking
        refEvent_list_beg = self.REs_fatigue_beg
        refEvent_list_end = self.REs_fatigue_end

        # get the assessment dictionary of compute Se
        assessment_beg = code.compute_Se(refEvent_list_beg, self.material)
        assessment_end = code.compute_Se(refEvent_list_end, self.material)
        # begin
        try:
            applied_beg = round(assessment_beg["Se [MPa]"] * 1e-6)
            try:
                allowable_beg = round(assessment_beg["Sa [MPa]"] * 1e-6)
            except ValueError:
                # it means is NaN
                allowable_beg = assessment_beg["Sa [MPa]"] * 1e-6
        except TypeError:
            return None
            # The assessment is None, hence the assessment was not
            # valid, return None

        if applied_beg < allowable_beg:
            res_beg = "OK"
            try:
                sm_beg = round(allowable_beg / applied_beg, 2)
                if sm_beg > 10:
                    sm_beg = "> 10"
            except ZeroDivisionError:
                sm_beg = "> 10"
        elif np.isnan(allowable_beg):
            # This happens also for interpolations out of range!
            allowable_beg = "No Limit"
            res_beg = "Assessment not required"
            sm_beg = None
        else:
            res_beg = "FAILED"
            sm_beg = None

        assessment_beg["Sa [MPa]"] = allowable_beg
        assessment_beg["Se [MPa]"] = applied_beg
        assessment_beg["Result"] = res_beg
        assessment_beg["Safety Margin"] = sm_beg

        # end
        try:
            applied_end = round(assessment_end["Se [MPa]"] * 1e-6)
            try:
                allowable_end = round(assessment_end["Sa [MPa]"] * 1e-6)
            except ValueError:
                # it means is NaN
                allowable_end = assessment_end["Sa [MPa]"] * 1e-6
        except TypeError:
            return None
            # The assessment is None, hence the assessment was not
            # valid, return None

        if applied_end < allowable_end:
            res_end = "OK"
            try:
                sm_end = round(allowable_end / applied_end, 2)
                if sm_end > 10:
                    sm_end = "> 10"
            except ZeroDivisionError:
                sm_end = "> 10"
        elif np.isnan(allowable_end):
            # This happens also for interpolations out of range!
            allowable_end = "No Limit"
            res_end = "Assessment not required"
            sm_end = None
        else:
            res_end = "FAILED"
            sm_end = None

        assessment_end["Sa [MPa]"] = allowable_end
        assessment_end["Se [MPa]"] = applied_end
        assessment_end["Result"] = res_end
        assessment_end["Safety Margin"] = sm_end

        row_beg = []
        row_end = []

        row_beg.append(assessment_beg)
        row_end.append(assessment_end)

        df_beg = pd.DataFrame(row_beg)
        df_end = pd.DataFrame(row_end)
        self.ass_fatigue_beg = df_beg
        self.ass_fatigue_end = df_end

        return self.ass_fatigue_beg, self.ass_fatigue_end

    def _get_basic_loads_df(self, pos):
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
        stress_names = ["Membrane stress", "Bending stress", "Peak stress"]
        for linstress in self.basic_loads[pos]:
            # get it in MPa
            mtrx = linstress.original_mtrx.copy() * 1e-6
            stress_mtrx = mtrx.reset_index()
            stress_mtrx["Load Condition"] = linstress.name
            stress_mtrx["Stress breakdown"] = stress_names
            dfs.append(stress_mtrx)

        df = pd.concat(dfs)
        df.set_index(["Load Condition", "Stress breakdown"], inplace=True)

        return df

    def _update_loads(self):
        """
        Adjourn the loads conditions for instance when a RE is added.
        If the reference events of the fatigue are changed this does not
        produce any effect. It is expected that no basic loads should be added
        from fatigue reference events.

        Returns
        -------
        basic_loads : dic
            load conditions.

        """
        basic_loads = {"begin": [], "end": []}
        basic_loads_names = []
        for RE_beg, RE_end in zip(self.REs_beg, self.REs_end):
            for beg_stress, end_stress in zip(
                RE_beg.lin_stress_list, RE_end.lin_stress_list
            ):
                if beg_stress.name not in basic_loads_names:
                    basic_loads_names.append(beg_stress.name)
                    basic_loads["begin"].append(beg_stress)
                    basic_loads["end"].append(end_stress)
        self.basic_loads = basic_loads
        return basic_loads


def _round_ass_df(df):
    dic = {"Applied [MPa]": 0, "Allowable [MPa]": 0, "Safety Margin": 2}
    df = df.round(dic)
    return df
