# -*- coding: utf-8 -*-
"""
Created on Tue Dec 22 11:14:05 2020

@author: davide laghi
"""

import os
import shutil
from math import pi

import pandas as pd

from cassy.bolts.section_action import BoltSectionActions
from cassy.office.excel_helper import ExcelOutput


class Poa:
    def __init__(self, name, material, code):
        """
        Generic point of application

        Parameters
        ----------
        name : str
            identifier for the point of application.
        material : material.Material
            material of the bolt
        code : code.Code
            design code for assessment


        Returns
        -------
        None.

        """
        self.name = name
        self.material = material
        # Maybe we can get some infos from the name
        splitted = name.split("_")
        self.connection = splitted[0]
        self.ID = splitted[1]

        self.code = code


class Bolt(Poa):
    def __init__(
        self,
        material,
        name,
        p,
        d,
        dn,
        d1,
        df,
        D,
        Dp,
        Dm,
        Le,
        H,
        a,
        B,
        C,
        REs,
        REs_fatigue=None,
        Kf=4,
        f=0.15,
        f_prime=0.15,
        code=None,
        bolt_type="Bolt",
    ):
        """
        Bolt for assessment

        All units are in mm

        Parameters
        ----------
        material : material.Material
            material of the bolt
        name : str
            identifier for the bolt
        p : float
            thread pitch.
        d : float
            maximum nominal diameter.
        dn : float
            core diameter (minor).
        d1 : float
            diameter of smooth shank.
        df : float
            pitch diameter (mean).
        D : float
            minor diameter of tapping.
        Dp : float
            diameter of drilling circle.
        Dm : float
            mean diameter under head
        Le : float
            insertion length.
        H : float
            height of head.
        a : float
            diameter of head.
        B : float
            inside diameter of washer.
        C : float
            washer thickness
        REs : dic
            contains data to build actions related to REs
        REs_fatigue : dic, optional
            contains data to build actions related to Fatigue REs
        Kf : float, optional
            fatigue stress reduction factor (IC 2753) for the application
            of the Neuber's rule. The default value is 4.
        f : float, optional
            friction coefficient between engaged threads. The default is 0.15.
        f_prime : float, optional
            friction coefficient under head. The default is 0.15.
        code : code.Code, optional
            design code for assessment. The default is None.
        bolt_type : str, optional
            bolt type description

        Returns
        -------
        None.

        """
        super().__init__(name, material, code=code)
        # --- Geometrical data ---
        self.p = p
        self.d = d
        self.dn = dn
        self.d1 = d1
        self.df = df
        self.D = D
        self.Dp = Dp
        self.Dm = Dm
        self.Le = Le
        self.H = H
        self.a = a
        self.B = B
        self.C = C
        self.Kf = Kf
        self.f = f
        self.f_prime = f_prime
        self.bolt_type = bolt_type
        self.images = {"Immediate": {}, "Fatigue": {}}

        # --- Additional geometrical feature ---
        # length for shear calculation
        self.Le_shear = min(0.8 * d, Le)
        # Minimum cross-sectional area at the root of thread
        self.An = dn**2 * pi / 4
        # Section Module
        self.Z = dn**3 * pi / 32

        # --- Create the actions ---
        # REs
        RE_actions = {}
        for RE_ID, data in REs.items():
            preload = data["preload"]
            primary = data["primary"]
            all_loads = data["all_loads"]
            event_data = data["event data"]
            action = BoltSectionActions.from_series(
                preload, primary, all_loads, event_data, self, RE_ID, code=self.code
            )
            RE_actions[RE_ID] = action
        self.RE_actions = RE_actions

        # Fatigue REs
        if REs_fatigue is not None:
            RE_actions = {}
            for RE_ID, data in REs_fatigue.items():
                preload = data["preload"]
                primary = data["primary"]
                all_loads = data["all_loads"]
                event_data = data["event data"]
                action = BoltSectionActions.from_series(
                    preload, primary, all_loads, event_data, self, RE_ID, code=self.code
                )
                RE_actions[RE_ID] = action
        self.RE_fatigue_actions = RE_actions

    @classmethod
    def from_excel(
        cls, config, material_list, actionsfolder, codes, fatigue=True, insert=False
    ):
        """
        Initialize the bolt from a dataframe

        Parameters
        ----------
        cls : TYPE
            DESCRIPTION.
        config : str or path
            path to the excel configuration file of the bolt
        material_list : list
            list of material.Material
        actionsfolder : str or path
            path to the folder containing the different actions
        codes : dic
         dictionary of available design codes objects
        fatigue: bool, optional
            if True also the fatigue REs are read. The default is True.
        insert : bool, optional
            if True the insert data is read instead of the bolt one. The
            default is False.

        Returns
        -------
        Bolt
            return the Bolt object.

        """
        # --- get the bolt name from file ---
        name = os.path.basename(config).split(".")[0]
        boltID = name.split("_")[1]
        connection = name.split("_")[0]
        if insert:
            name = name + "_insert"
            bolt_type = "Insert"
        else:
            bolt_type = "Bolt"

        # --- Get the geometrical data ---
        if insert:
            sheetname = "Insert Data"
        else:
            sheetname = "Bolt Data"

        df = pd.read_excel(config, skiprows=1, sheet_name=sheetname)
        df.set_index("SYMBOL", inplace=True)
        col_name = "VALUE"
        material_name = df.loc["Material", col_name]
        material = material_list[material_name]

        # Get additional parameters
        additional = pd.read_excel(config, sheet_name="Additional Data")
        additional.set_index("Parameter", inplace=True)
        code = additional.loc["Code", "Value"]
        preload = additional.loc["Preload [N]", "Value"]

        # --- Build the section actions for the REs ---
        # Fatigue REs
        if fatigue:
            REs_data = pd.read_excel(config, sheet_name="REs Fatigue")
            _cleanNA(REs_data)
            REs_fatigue = {}
            for idx, row in REs_data.iterrows():
                mainfolder = os.path.join(actionsfolder, connection)

                # Get stress intensity actions
                pointers_str = row["Delta sigma"]
                all_loads = _get_actions(mainfolder, pointers_str, boltID)

                if code == "RCC-MRx":
                    primary = None
                else:
                    pointers_str = row["Sigma sustained"]
                    primary = _get_actions(mainfolder, pointers_str, boltID)

                dic = {
                    "preload": preload,
                    "primary": primary,
                    "all_loads": all_loads,
                    "event data": row,
                }

                REs_fatigue[row["ID"]] = dic
        else:
            REs_fatigue = None
        # Standard REs
        REs_data = pd.read_excel(config, sheet_name="REs")
        _cleanNA(REs_data)
        REs = {}
        for idx, row in REs_data.iterrows():
            mainfolder = os.path.join(actionsfolder, connection)
            # Get the primary actions
            pointers_str = row["Primary"]
            primary = _get_actions(mainfolder, pointers_str, boltID)
            # Get the all loads actions
            pointers_str = row["All"]
            all_loads = _get_actions(mainfolder, pointers_str, boltID)

            dic = {
                "preload": preload,
                "primary": primary,
                "all_loads": all_loads,
                "event data": row,
            }

            REs[row["ID"]] = dic

        # check if insert exists
        if df.loc["p", col_name] == 0:
            return False

        else:
            return cls(
                material,
                name,
                df.loc["p", col_name],
                df.loc["d", col_name],
                df.loc["dn", col_name],
                df.loc["d1", col_name],
                df.loc["df", col_name],
                df.loc["D", col_name],
                df.loc["Dp", col_name],
                df.loc["Dm", col_name],
                df.loc["Le", col_name],
                df.loc["H", col_name],
                df.loc["a", col_name],
                df.loc["B", col_name],
                df.loc["C", col_name],
                REs,
                REs_fatigue=REs_fatigue,
                Kf=df.loc["KF", col_name],
                f=df.loc["f", col_name],
                f_prime=df.loc["f_prime", col_name],
                code=codes[code],
                bolt_type=bolt_type,
            )

    def assess(self, fatigue=True, insert=False):
        """
        Assess all reference events

        Parameters
        ----------
        fatigue : bool, optional
            if true the assessment is also done for fatigue damage.
            The default is True.
        insert : bool, optional
            if true the assessment is considered for an insert. The default is
            False

        Returns
        -------
        None.

        """
        # immediate damage
        dfs = []
        inputs = []
        for RE_ID, RE_action in self.RE_actions.items():
            assessment = RE_action.assess(insert=insert)
            dfs.append(assessment)
            inputs.append(RE_action.get_df_actions())

        immediate_assessment = pd.concat(dfs)
        input_df = pd.concat(inputs)
        # fatigue damage
        if fatigue and "insert" not in self.name:
            rows = []
            for RE_ID, RE_action in self.RE_fatigue_actions.items():
                assessment = RE_action.computeVj()
                rows.append(assessment)
            fatigue_assessment = pd.DataFrame(rows)
        else:
            fatigue_assessment = None

        self.assessment = {
            "Immediate": immediate_assessment,
            "Fatigue": fatigue_assessment,
            "Inputs": input_df,
        }

    def print_assessment(
        self, mainfolder, app, template_path, fatigue=True, img_folder="Images"
    ):
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
            if true fatigue is assessed. The default is True.
        img_folder : str or path
            path to the images folder

        Raises
        ------
        ValueError
            If the assessment has not been run first.

        Returns
        -------
        dic
            recap row for the immediate damage assessment recap
        dic
            recap row for the fatigue damage assessment recap

        """
        if self.assessment is None:
            raise ValueError("Please assess the submodel first")

        print("Assessing " + self.name)

        # Safe creation of folder for imges
        imgs = os.path.join(img_folder, self.connection)
        if not os.path.exists(imgs):
            os.mkdir(imgs)

        # Compile one sheet for each rule set
        index = ["Rule Set"]
        df = self.assessment["Immediate"].set_index(index)
        sets = set(list(df.index))

        # Initialize the excel file
        # Write the excel file
        file = self.name + ".xlsx"  #########
        out_path = os.path.join(mainfolder, file)
        if os.path.isfile(out_path):
            os.remove(out_path)
        shutil.copyfile(template_path, out_path)
        out = ExcelOutput(app, out_path)
        i = 0
        for rule_set in sets:
            i = i + 1
            # Select the correct table
            table = df.loc[rule_set]
            table.reset_index(inplace=True)
            del table["Rule Set"]
            del table["Damage Type"]

            index = [
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
            table.set_index(index, inplace=True)
            sheet = "Assessment " + str(i)

            # Insert the df
            out.insert_SA_df(table, sheet, divide_blocks="ID")

            # Fill the banners
            out.fill_banner(
                sheet,
                self.connection,
                self.ID,
                self.material.name,
                self.code,
                assessment=rule_set,
                paragraph=None,
            )
            # Grab and save image
            file = self.name + "_" + sheet + ".png"
            outpath = os.path.join(imgs, file)

            self.images["Immediate"][sheet] = outpath
            out.grab_img("all", "all", sheet, outpath)

        # --- Handle input sheet ---
        # Fill the banners
        out.fill_banner(
            "Input_template",
            self.connection,
            self.ID,
            self.material.name,
            self.code,
            template="Input_template",
        )
        # Insert the df
        index = [
            "RE ID",
            "Operating Conditions",
            "Initiating Event",
            "Concatenated Event",
        ]
        input_df = self.assessment["Inputs"].set_index(index)
        out.insert_SA_df(
            input_df,
            "Input",
            divide_blocks="RE ID",
            word=True,
            print_header=False,
            start_row=10,
        )

        # Grab and save image
        file = self.name + "_Input.png"
        outpath = os.path.join(imgs, file)

        self.images["Input"] = outpath
        out.grab_img("all", "all", "Input", outpath)

        if fatigue:
            fatigue_table = self.assessment["Fatigue"]
            if fatigue_table is not None:
                # Insert the df
                if self.code.name == "SDC-IC (Bolts)":
                    bolt_flag = True
                else:
                    bolt_flag = False
                out.insert_fatigue_df(fatigue_table, "Fatigue", bolt=bolt_flag)
                assessment = "Time-independent fatigue assessment"

                # Fill the banners
                out.fill_banner(
                    "Fatigue",
                    self.connection,
                    self.ID,
                    self.material.name,
                    self.code,
                    assessment=assessment,
                    paragraph=None,
                    template="fatigue",
                )
                # Grab and save image
                file = self.name + "_Fatigue.png"
                outpath = os.path.join(imgs, file)

                self.images["Fatigue"] = outpath
                out.grab_img("all", "all", "Fatigue", outpath)

        # Collect and store data for recap tables
        # check if the assessment was good
        # adjust index
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

        row = {
            "Submodel": self.connection,
            "Path": str(self.ID),
            "Path Type": self.bolt_type,
            "Assessment": ass,
            "Reference Event": re,
            "Service lvl": slvl,
            "Rule": rule,
            "Safety Margin": sm,
        }

        if fatigue and fatigue_table is not None:
            Vtot = fatigue_table["Vj"].sum()
            if Vtot < 1:
                ass = "OK"
            else:
                ass = "NOK"

            tuf = round(Vtot * 100, 2)
            fatigue_recap_row = {
                "Submodel": self.connection,
                "Bolt": str(self.ID),
                "Assessment": ass,
                "Total Usage Fraction [%]": tuf,
            }
        else:
            fatigue_recap_row = None

        self.immediate_recap_row = row
        self.fatigue_recap_row = fatigue_recap_row

        file = self.name + ".xlsx"
        out.save(os.path.join(mainfolder, file))

        return self.immediate_recap_row, self.fatigue_recap_row


def _get_actions(mainfolder, pointers_str, boltID):
    """
    Find the correct data among the ones extracted from ANSYS and return
    the actions for a specific bolt and RE

    Parameters
    ----------
    mainfolder : path or str
        path to the mainfolder where actions of a submodel are contained.
    pointers_str : str
        contains pointers to the correct files for actions..
    boltID : TYPE
        DESCRIPTION.

    Raises
    ------
    ValueError
        DESCRIPTION.

    Returns
    -------
    TYPE
        DESCRIPTION.
    TYPE
        DESCRIPTION.

    """
    # this needs to handle both single pointers that differences of
    # pointers
    # individuate single pointers
    pointers = pointers_str.split("-")
    if len(pointers) == 2:  # No more than two should be allowed
        forward = _get_action(mainfolder, pointers[1], boltID)
        back = _get_action(mainfolder, pointers[0], boltID)
        actions = forward - back
    elif len(pointers) == 1:
        pointer = pointers[0]
        actions = _get_action(mainfolder, pointer, boltID)
    else:
        raise ValueError("No more than two pointers are allowed")

    return actions


def _get_action(mainfolder, pointer, boltID):
    analysis, step = pointer.split("_")
    file = os.path.join(mainfolder, analysis, pointer + ".txt")
    df = pd.read_csv(file).set_index("ID")
    try:
        return df.loc[int(boltID)]
    except KeyError:
        # Try both with string and int
        return df.loc[str(boltID)]


def _cleanNA(df):
    # Drop all rows containing only NaN
    df.dropna(axis=0, subset=["ID"], inplace=True)

    return df
