# -*- coding: utf-8 -*-
"""
Created on Thu Nov 26 14:11:14 2020

@author: Davide Laghi

"""

from __future__ import annotations

import os
import re
import shutil
from importlib.resources import files

import pandas as pd
import xlwings as xw
from tqdm import tqdm

from cassy.additional_data import materials, templates
from cassy.auxiliary.functions import stripfunc
from cassy.auxiliary.types import PathLike
from cassy.designcodes.rccmr import RCC_MR
from cassy.designcodes.rccmrx import RCC_MRx
from cassy.designcodes.sdcic import SDC_IC
from cassy.designcodes.sdcic_ml import SDC_IC_ML
from cassy.general.configuration import parse_cfg_files
from cassy.general.folder_tree import PathsFolderTree
from cassy.general.material import read_materials
from cassy.office.word_helper import WordOutput
from cassy.paths.linstress import LinStress, ReferenceEvent
from cassy.paths.submodel import Submodel

# #################### User Inputs ############################################
# local folders and files
TEMPLATE_EXCEL = files(templates).joinpath("template.xlsx")
TEMPLATE_WORD = files(templates).joinpath("template.docx")

# #################### Parameters #############################################
# Codes
CODES = {
    "SDC-IC": SDC_IC(),
    "RCC-MR": RCC_MR(),
    "SDC-IC multilayer": SDC_IC_ML(),
    "RCC-MRx": RCC_MRx(),
}


MATERIALS_PATH = files(materials)


# Word titles and captions
RECAP_TITLE = "Stress Assessment Recap"
RECAP_CAPTION = "Summary of results from the verification of the design rules against "
EXCELS_TITLE = "Stress Assessment Detail"
EXCELS_CAPTION = ": stress assessment summary for "
INPUT_CAPTION = "Input Summary: "
INPUT_TITLE = "Single Load Case stresses matrix"

WORDS_RECAPS = {"Immediate": 0, "Ratcheting": 1, "Fatigue": 2, "Fatigue ASME": 3}

PATNUM = re.compile(r"\d+")


# #################### Functions ##############################################
def readStep(file):
    """
    Read All paths in an Ansys step whose path is given by file.
    Returns all paths as a list of DataFrames
    """
    paths = {}
    # Skip the header
    skip = 1
    safety_counter = 0
    while True:
        safety_counter = safety_counter + 1
        df_name = pd.read_excel(file, skiprows=skip - 1, nrows=2, usecols="A:G")
        pathnum = df_name.columns[0]
        pathnum = PATNUM.search(pathnum).group()
        path = pd.read_excel(
            file, skiprows=skip, nrows=3, index_col=0, header=None, usecols="A:G"
        )
        path.columns = ["Sx", "Sy", "Sz", "Sxy", "Sxz", "Syz"]
        path.index = path.index.map(stripfunc)
        if not path.empty:
            paths[pathnum] = path

        # Adjourn skip only if we are not at the last path!
        skip = skip + 5
        df = pd.read_excel(
            file, skiprows=skip, nrows=1, index_col=0, header=None, usecols="A:G"
        )
        if df.empty or df.isnull().values.any():
            break  # exit when last path is reached
        if safety_counter > 100:
            raise ValueError(" Too many paths! or something went wrong")

    return paths


def buildRE(paths, pathnum, submodel, conf, re_ID, fatigue=False):
    """
    build a reference event to assign to a specific path and submodel

    Parameters
    ----------
    paths : dic
        containes the submodel.Path objects of the submodel.
    pathnum : int
        number of the path onto which operate
    submodel : submodel.Submodel
        submodel where to add the RE.
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

    load_names = conf.get_REloads(pathnum, re_ID, fatigue=fatigue)
    try:
        oc = conf["Reference Event" + des].loc[idx, "Operating Conditions"].iloc[0]
        ie = conf["Reference Event" + des].loc[idx, "Initiating Event"].iloc[0]
        ce = conf["Reference Event" + des].loc[idx, "Concatenated Event"].iloc[0]
        service_lvl = conf["Reference Event" + des].loc[idx, "Service Level"].iloc[0]
        load_ctg = conf["Reference Event" + des].loc[idx, "Loading ctg."].iloc[0]
        T = conf["Reference Event" + des].loc[idx, "T [°C]"].iloc[0]
        dpa = conf["Reference Event" + des].loc[idx, "DPA"].iloc[0]

        # Additional data for fatigue event
        if fatigue:
            ncycles = conf["Reference Event" + des].loc[idx, "N of cycles"].iloc[0]
        else:
            ncycles = None
    except AttributeError:
        oc = conf["Reference Event" + des].loc[idx, "Operating Conditions"]
        ie = conf["Reference Event" + des].loc[idx, "Initiating Event"]
        ce = conf["Reference Event" + des].loc[idx, "Concatenated Event"]
        service_lvl = conf["Reference Event" + des].loc[idx, "Service Level"]
        load_ctg = conf["Reference Event" + des].loc[idx, "Loading ctg."]
        T = conf["Reference Event" + des].loc[idx, "T [°C]"]
        dpa = conf["Reference Event" + des].loc[idx, "DPA"]

        # Additional data for fatigue event
        if fatigue:
            ncycles = conf["Reference Event" + des].loc[idx, "N of cycles"]
        else:
            ncycles = None

    # Recover the corresponding LinStress
    for pos in ["begin", "end"]:
        stresses = []
        for load in load_names:
            stress = paths[pathnum][load][pos]
            stresses.append(stress)
        RE = ReferenceEvent.from_recombination(
            stresses,
            service_lvl,
            re_ID,
            T,
            dpa,
            oc=oc,
            ie=ie,
            ce=ce,
            load_ctg=load_ctg,
            ncycles=ncycles,
        )
        # Add the stress to the correct path
        submodel.paths[pathnum].add_RE(RE, pos, fatigue=fatigue)


# #################### Code ###################################################
def run_paths(root: PathLike, fatigue: bool = False):
    folder_tree = PathsFolderTree(root)
    # --- Initializations ---
    try:
        app = xw.App(visible=False)
        app.display_alerts = False  # Suppress merge warnings
        materials = read_materials(MATERIALS_PATH)

        # --- Load Configuration files ---
        config = parse_cfg_files(folder_tree.configurations)

        # --- Read and organize ANSYS results ---
        # -- Read --
        results = {}
        for submodel in tqdm(
            os.listdir(folder_tree.paths_folder), desc="Reading all paths stress: "
        ):
            conf = config[submodel]
            sub_path = os.path.join(folder_tree.paths_folder, submodel)

            results[submodel] = {}

            for analysis in os.listdir(sub_path):
                analysis_path = os.path.join(sub_path, analysis)
                results[submodel][analysis] = {}
                for file in os.listdir(analysis_path):
                    # Check for xlsx files
                    if file.split(".")[-1] == "xlsx":
                        file_path = os.path.join(analysis_path, file)
                        splitted = file.split("_")
                        # every int allowed
                        stepnum = PATNUM.search(splitted[0]).group()
                        # stepnum = splitted[0][-1]  # ! no more than 9
                        pos = splitted[-1].split(".")[0]  # i.e. begin or end
                        read_paths = readStep(file_path)
                        if stepnum not in results[submodel][analysis].keys():
                            results[submodel][analysis][stepnum] = {pos: read_paths}
                        else:
                            results[submodel][analysis][stepnum][pos] = read_paths

        # --- Reorganize and create the LinStresses and Combined ones + Assessment ---
        print("\nAssessing the results...")
        paths = {}
        submodels = []
        recap_rows = {}
        for submodel_name, dic in results.items():
            conf = config[submodel_name]
            submodel = Submodel.from_df(submodel_name, conf["Paths"], materials)
            for pathnum in conf.paths:
                paths[pathnum] = {}
                ptype = submodel.paths[pathnum].ptype
                Welding_n = submodel.paths[pathnum].Welding_n
                Welding_f = submodel.paths[pathnum].Welding_f
                # Get the material of the path
                mat_name = conf["Paths"].loc[pathnum, "Material"]
                material = materials[mat_name]
                # -- Get all single Loads --
                for load in conf.loads:
                    # Check for potential difference
                    analysis = conf["Load Steps"].loc[load, "Analysis Name"].split("-")
                    if len(analysis) > 1:
                        # max 2
                        stepnum = conf["Load Steps"].loc[load, "Time Step"].split("-")
                        if len(analysis) != len(stepnum):
                            raise ValueError(
                                "The number of analyses and steps must be equal"
                            )
                        elif len(analysis) > 2:
                            raise ValueError("Max 2 analysis allowed")
                        else:
                            # First
                            main1 = results[submodel_name][analysis[0]][str(stepnum[0])]
                            beg_df1 = main1["begin"][str(pathnum)]
                            end_df1 = main1["end"][str(pathnum)]
                            # Second
                            main2 = results[submodel_name][analysis[1]][str(stepnum[1])]
                            beg_df2 = main2["begin"][str(pathnum)]
                            end_df2 = main2["end"][str(pathnum)]
                            # Final difference
                            beg_df = beg_df1 - beg_df2
                            end_df = end_df1 - end_df2
                    else:
                        # Should be one
                        analysis = analysis[0]
                        stepnum = conf["Load Steps"].loc[load, "Time Step"]
                        main = results[submodel_name][analysis][str(stepnum)]
                        beg_df = main["begin"][str(pathnum)]
                        end_df = main["end"][str(pathnum)]

                    # Generate the LinStress objects
                    beg = LinStress.from_config(
                        load, beg_df, conf["Stresses"], ptype, Welding_n, Welding_f
                    )
                    end = LinStress.from_config(
                        load, end_df, conf["Stresses"], ptype, Welding_n, Welding_f
                    )
                    # Record in paths
                    paths[pathnum][load] = {"begin": beg, "end": end}

                # -- Combined Loads (Reference Events) + Assessment --a
                for re_ID in conf.get_REid_path(pathnum):
                    buildRE(paths, pathnum, submodel, conf, re_ID)
                if fatigue:
                    for re_ID in conf.get_REid_path(pathnum, fatigue=True):
                        buildRE(paths, pathnum, submodel, conf, re_ID, fatigue=True)
            if fatigue:
                try:
                    CODES[conf.code].fatigue
                except AttributeError:
                    raise KeyError(
                        "For "
                        + CODES[conf.code].name
                        + " fatigue needs to"
                        + " be set as False"
                    )
            submodel.assess(CODES[conf.code], fatigue=fatigue)
            # Generate the assessment folder
            ass_path = os.path.join(folder_tree.paths_folder, submodel.name)
            if os.path.exists(ass_path):
                shutil.rmtree(ass_path)
            os.mkdir(ass_path)

            submodel.print_assessment(
                ass_path,
                app,
                TEMPLATE_EXCEL,
                img_folder=folder_tree.img_folder,
                fatigue=fatigue,
            )
            submodels.append(submodel)
            for key, item in submodel.recap_rows.items():
                if key not in recap_rows:
                    recap_rows[key] = []
                recap_rows[key].extend(item)

        app.kill()  # kill the excel app we do not need it anymore
    except:
        # Whatever the exception, kill excel first and re-raise
        app.kill()
        raise

    print("Assessing Completed")

    print("Generating Word Recap")
    # Create Recaps from the collected infos during printing
    recaps = {}

    # --- Generate the word output ---
    outp = WordOutput(template=TEMPLATE_WORD)
    code_name = submodels[0].code.name  # get the used code
    for dtype, recap in recap_rows.items():
        recaps[dtype] = pd.DataFrame(recap)
        outp.doc.add_heading(dtype + " damage", level=1)
        # Insert the recap
        outp.doc.add_heading(RECAP_TITLE, level=2)
        caption = RECAP_CAPTION + dtype + " damage"
        if code_name == "ASME B31.3" and dtype == "Fatigue":
            template_idx = WORDS_RECAPS["Fatigue ASME"]
            # outp.insert_df(recaps[dtype], caption,
            #                template_idx=WORDS_RECAPS['Fatigue ASME'],
            #                highlight=True)
        else:
            template_idx = WORDS_RECAPS[dtype]

        outp.insert_df(
            recaps[dtype], caption, template_idx=template_idx, highlight=True
        )

        # Insert the excels
        outp.doc.add_heading(EXCELS_TITLE, level=2)
        for submodel in submodels:
            outp.doc.add_heading(submodel.name, level=3)
            for pnum in submodel.paths:
                for pos in ["begin", "end"]:
                    tit = "Path " + str(pnum) + " " + pos
                    outp.doc.add_heading(tit, level=4)
                    img = submodel.images[pnum][pos][dtype]
                    caption = (
                        "Path "
                        + str(pnum)
                        + " "
                        + pos
                        + EXCELS_CAPTION
                        + dtype
                        + " damage"
                    )
                    outp.add_figure(img, caption=caption)

    # Add input
    outp.doc.add_heading(INPUT_TITLE, level=1)
    for submodel in submodels:
        outp.doc.add_heading(submodel.name, level=2)
        for pnum in submodel.paths:
            for pos in ["begin", "end"]:
                tit = "Path " + str(pnum) + " " + pos
                outp.doc.add_heading(tit, level=3)
                img = submodel.images[pnum][pos]["Input"]
                caption = INPUT_CAPTION + "Path " + str(pnum) + " " + pos
                outp.add_figure(img, caption=caption)

    outp.save(folder_tree.out_word)

    print("All done!")
