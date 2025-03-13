# -*- coding: utf-8 -*-
"""
Created on Mon Jan  4 10:43:44 2021

@author: davide laghi
"""

import os
import shutil

import pandas as pd
import xlwings as xw

from cassy.bolts.bolt import Bolt
from cassy.designcodes.rccmr_bolts import RCCMR_Bolts
from cassy.designcodes.rccmrx_bolts_nl import RCCMRx_Bolts
from cassy.designcodes.sdcic_bolts import SDC_IC_Bolts
from cassy.general.material import Material
from cassy.office.word_helper import WordOutput

# #################### User Inputs ############################################
MAIN_IO = r""

fatigue = False

# #################### Parameters #############################################
# Additional folders
additional_data = os.path.join(os.path.dirname(__file__), "additional_data")
MATERIALS_PATH = os.path.join(additional_data, "materials")
MAIN_ASSESSMENT = os.path.join(MAIN_IO, "Assessment")
CONFIGURATION = os.path.join(MAIN_IO, "Configuration")
ACTIONS = os.path.join(MAIN_IO, "Actions")
IMAGES = os.path.join(MAIN_IO, "Images")

# Templates
TEMPLATE_BOLT = os.path.join(additional_data, "templates", "template bolt.xlsx")
TEMPLATE_WORD = os.path.join(additional_data, "templates", "template bolts.docx")

# Sheet additional data
ADD_DATA = "Additional Data"

# Outputfile
OUT_WORD = os.path.join(MAIN_IO, "Recap.docx")

# Word titles and captions
RECAP_TITLE = "Stress Assessment Recap"
RECAP_CAPTION = "Summary of results from the verification of the design rules against "
EXCELS_TITLE = "Stress Assessment Detail"
EXCELS_CAPTION = ": stress assessment summary for "
INPUT_CAPTION = "Input Summary: "
INPUT_TITLE = "Internal Bolt Action Used During the Assessment"


# #################### Functions ##############################################
# helper func for sort
def helper_func_sort(item):
    _, num = item.split("_")
    num, _ = num.split(".")
    return int(num)


# #################### Code ###################################################
# --- Initializations ---
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

    # Safe generate folders
    folders = [MAIN_ASSESSMENT, IMAGES]
    for path in folders:
        if os.path.exists(path):
            shutil.rmtree(path)
        os.mkdir(path)

    # Generate the materials library
    materials = {}
    for materialfile in os.listdir(MATERIALS_PATH):
        print("Reading " + materialfile)
        mat_name = materialfile.split(".")[0]

        material = Material(os.path.join(MATERIALS_PATH, materialfile), name=mat_name)
        materials[mat_name] = material

    sdcic = SDC_IC_Bolts()

    recaps = {"Immediate": [], "Fatigue": []}
    connections = {}
    for connection in os.listdir(CONFIGURATION):
        connection_config = os.path.join(CONFIGURATION, connection)
        connections[connection] = []
        ass_folder = os.path.join(MAIN_ASSESSMENT, connection)
        if not os.path.exists(ass_folder):
            os.mkdir(ass_folder)

        # Reorganize following the number order
        conf_files = list(os.listdir(connection_config))
        conf_files.sort(key=helper_func_sort)

        for conf_file in conf_files:
            flag_insert = True
            # print('Assessing '+conf_file.split('.')[0])
            bolt_file = os.path.join(connection_config, conf_file)

            bolt = Bolt.from_excel(bolt_file, materials, ACTIONS, codes)
            insert = Bolt.from_excel(bolt_file, materials, ACTIONS, codes, insert=True)

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
                ass_folder, app, TEMPLATE_BOLT, img_folder=IMAGES
            )

            recaps["Fatigue"].append(recap_fat)

            recaps["Immediate"].append(recap_imm)
            connections[connection].append(bolt)

            # Assess and print insert
            if flag_insert:
                insert.assess(fatigue=fatigue, insert=True)
                recap_imm, recap_fat = insert.print_assessment(
                    ass_folder, app, TEMPLATE_BOLT, img_folder=IMAGES
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
                            tit + " " + EXCELS_CAPTION + damage + " damage, " + rule_set
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

    outp.save(OUT_WORD)
except:
    # After whatever un-handled exception safely save the word recap
    outp.save(OUT_WORD)
    # re-raise the exception
    raise

print("All done!")
