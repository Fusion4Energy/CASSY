# -*- coding: utf-8 -*-
"""
Created on Mon Jan  4 10:43:44 2021

@author: davide laghi
"""

from __future__ import annotations

import os
from importlib.resources import files

import pandas as pd
import xlwings as xw

from cassy.additional_data import materials, templates
from cassy.auxiliary.functions import helper_func_sort
from cassy.auxiliary.types import PathLike
from cassy.bolts.bolt import Bolt
from cassy.designcodes.rccmr_bolts import RCCMR_Bolts
from cassy.designcodes.rccmrx_bolts_nl import RCCMRx_Bolts
from cassy.designcodes.sdcic_bolts import SDC_IC_Bolts
from cassy.general.folder_tree import BoltsFolderTree
from cassy.general.material import read_materials
from cassy.office.word_helper import WordOutput

# #################### Parameters #############################################
# Additional folders
MATERIALS_PATH = files(materials)

# Templates
TEMPLATE_BOLT = files(templates).joinpath("template bolt.xlsx")
TEMPLATE_WORD = files(templates).joinpath("template bolts.docx")

# Sheet additional data
ADD_DATA = "Additional Data"


# Word titles and captions
RECAP_TITLE = "Stress Assessment Recap"
RECAP_CAPTION = "Summary of results from the verification of the design rules against "
EXCELS_TITLE = "Stress Assessment Detail"
EXCELS_CAPTION = ": stress assessment summary for "
INPUT_CAPTION = "Input Summary: "
INPUT_TITLE = "Internal Bolt Action Used During the Assessment"


# #################### Code ###################################################
# --- Initializations ---
def run_bolts(root: PathLike, fatigue: bool = False) -> None:
    try:
        # Open excel
        app = xw.App(visible=False)
        app.display_alerts = False  # Suppress merge warnings

        # Code
        codes = {
            "SDC-IC": SDC_IC_Bolts(),
            "RCC-MR": RCCMR_Bolts(),
            "RCC-MRx": RCCMRx_Bolts(),
        }
        folder_tree = BoltsFolderTree(root)

        # Generate the materials library
        materials = read_materials(MATERIALS_PATH)

        recaps = {"Immediate": [], "Fatigue": []}
        connections = {}
        for connection in os.listdir(folder_tree.configurations):
            connection_config = os.path.join(folder_tree.configurations, connection)
            connections[connection] = []
            ass_folder = os.path.join(folder_tree.assessment_folder, connection)
            if not os.path.exists(ass_folder):
                os.mkdir(ass_folder)

            # Reorganize following the number order
            conf_files = list(os.listdir(connection_config))
            conf_files.sort(key=helper_func_sort)

            for conf_file in conf_files:
                flag_insert = True
                # print('Assessing '+conf_file.split('.')[0])
                bolt_file = os.path.join(connection_config, conf_file)

                bolt = Bolt.from_excel(
                    bolt_file, materials, folder_tree.actions_folder, codes
                )
                insert = Bolt.from_excel(
                    bolt_file, materials, folder_tree.actions_folder, codes, insert=True
                )

                if bolt.code.name == "RCC-MR (Bolts)":
                    flag_insert = False
                    print(
                        "RCC-MR rules for assessment of the base material"
                        + " /insert threads are not implemented. Insert assessment for bolt "
                        + bolt.name
                        + " will not be performed"
                    )

                # Assess and print bolt
                bolt.assess(fatigue=fatigue)
                recap_imm, recap_fat = bolt.print_assessment(
                    ass_folder, app, TEMPLATE_BOLT, img_folder=folder_tree.img_folder
                )

                recaps["Fatigue"].append(recap_fat)

                recaps["Immediate"].append(recap_imm)
                connections[connection].append(bolt)

                # Assess and print insert
                if flag_insert:
                    insert.assess(fatigue=fatigue, insert=True)
                    recap_imm, recap_fat = insert.print_assessment(
                        ass_folder,
                        app,
                        TEMPLATE_BOLT,
                        img_folder=folder_tree.img_folder,
                    )
                    recaps["Immediate"].append(recap_imm)
                    connections[connection].append(insert)

        # app.kill()  # kill the excel app we do not need it anymore
        print("Assessing Completed")
    finally:
        # need to kill the app if something goes wrong
        app.kill()

    print("Generating Word Recap")
    # Create Recaps from the collected infos during printing
    wordrecaps = {}
    wordrecaps["Immediate"] = pd.DataFrame(recaps["Immediate"])
    if fatigue:
        wordrecaps["Fatigue"] = pd.DataFrame(recaps["Fatigue"])

    # --- Generate the word output ---
    outp = WordOutput(template=TEMPLATE_WORD)
    try:
        if fatigue:
            iterables = ["Immediate", "Fatigue"]
        else:
            iterables = ["Immediate"]

        for i, damage in enumerate(iterables):
            outp.doc.add_heading(damage + " damage", level=1)
            # Insert the recap
            outp.doc.add_heading(RECAP_TITLE, level=2)
            caption = RECAP_CAPTION + damage + " damage"
            outp.insert_df(wordrecaps[damage], caption, template_idx=i, highlight=True)

            # Insert the excels
            outp.doc.add_heading(EXCELS_TITLE, level=2)
            for connection, bolts in connections.items():
                outp.doc.add_heading(connection, level=3)
                for bolt in bolts:
                    tit = "Bolt " + bolt.name
                    # Override insert with base material
                    tit = tit.replace("_insert", " (base material)")
                    imgs = bolt.images[damage]
                    if damage == "Fatigue" and "insert" not in bolt.name:
                        outp.doc.add_heading(tit, level=4)
                        caption = tit + " " + EXCELS_CAPTION + damage + " damage"
                        outp.add_figure(imgs, caption=caption)
                    elif damage == "Immediate":
                        outp.doc.add_heading(tit, level=4)
                        for rule_set, path in imgs.items():
                            caption = (
                                tit
                                + " "
                                + EXCELS_CAPTION
                                + damage
                                + " damage, "
                                + rule_set
                            )
                            outp.add_figure(path, caption=caption)

        # Add input
        outp.doc.add_heading(INPUT_TITLE, level=1)
        for connection, bolts in connections.items():
            outp.doc.add_heading(connection, level=2)
            for bolt in bolts:
                tit = "Bolt " + bolt.name
                # Override insert with base material
                tit = tit.replace("_insert", " (base material)")
                img = bolt.images["Input"]
                outp.doc.add_heading(tit, level=3)
                caption = INPUT_CAPTION + tit
                outp.add_figure(img, caption=caption)

        outp.save(folder_tree.out_word)
    except:
        # After whatever un-handled exception safely save the word recap
        outp.save(folder_tree.out_word)
        # re-raise the exception
        raise

    print("All done!")
