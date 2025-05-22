from __future__ import annotations

import os
import re
import shutil
from importlib.resources import files

import pandas as pd

from cassy.additional_data import materials, templates
from cassy.auxiliary.constants import EXCEL_AVAILABLE
from cassy.auxiliary.types import PathLike
from cassy.designcodes.rccmr import RCC_MR
from cassy.designcodes.rccmrx import RCC_MRx
from cassy.designcodes.sdcic import SDC_IC
from cassy.designcodes.sdcic_ml import SDC_IC_ML
from cassy.general.configuration import parse_cfg_files
from cassy.general.folder_tree import PathsFolderTree
from cassy.general.material import read_materials
from cassy.office.word_helper import WordOutput
from cassy.paths.submodel import Submodel

if EXCEL_AVAILABLE:
    import xlwings as xw

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


# #################### Code ###################################################
def run_paths(root: PathLike, fatigue: bool = False):
    folder_tree = PathsFolderTree(root)
    # --- Initializations ---
    with xw.App(visible=False) as app:
        app.display_alerts = False  # Suppress merge warnings
        materials = read_materials(MATERIALS_PATH)

        # --- Load Configuration files ---
        configs = parse_cfg_files(
            folder_tree.configurations, folder_tree.stress_tensors
        )
        # --- Reorganize and create the LinStresses and Combined ones + Assessment ---
        print("\nAssessing the results...")
        submodels = []
        recap_rows = {}
        for submodel_name, conf in configs.items():
            submodel = Submodel(submodel_name, conf, materials)
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
            submodel.build_REs(fatigue=fatigue)
            submodel.assess(CODES[conf.code], fatigue=fatigue)
            # Generate the assessment folder
            ass_path = os.path.join(folder_tree.assessment_folder, submodel.name)
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
