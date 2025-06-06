from __future__ import annotations

import os
import shutil
from importlib.resources import files
from pathlib import Path

import pandas as pd
import xlwings as xw

from cassy.additional_data import materials, templates
from cassy.auxiliary.types import PathLike
from cassy.bolts.bolt_assess import FlangeAssessment
from cassy.bolts.bolt_config import FlangeAssessmentConfig
from cassy.bolts.geometry import read_geometries
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
    with xw.App(visible=False) as app:
        app.display_alerts = False  # Suppress merge warnings

        folder_tree = BoltsFolderTree(root)

        # Generate the materials library
        materials = read_materials(MATERIALS_PATH)

        # Read the available geometries
        geometries = read_geometries(folder_tree.geom_folder, materials)

        recaps = {"Immediate": [], "Fatigue": []}
        connections = {}
        for connection in os.listdir(folder_tree.configurations):
            connection_name = connection.split(".")[0]
            config_path = os.path.join(folder_tree.configurations, connection)

            # intialize the config of the flange
            actions_path = Path(folder_tree.actions_folder, f"{connection_name}.csv")
            flange_config = FlangeAssessmentConfig.from_excel(
                config_path, actions_path, fatigue=fatigue
            )

            # perform the assessment
            flange_assessment = FlangeAssessment(
                geometries, flange_config, fatigue=fatigue
            )
            flange_assessment.assess()
            flange_assessment.assess(insert=True)

            # print the assessment
            assessment_folder = Path(folder_tree.assessment_folder, connection_name)
            # override eventual old results
            if os.path.exists(assessment_folder):
                shutil.rmtree(assessment_folder)
            os.mkdir(assessment_folder)

            recap_immediate, recap_fatigue = flange_assessment.print_assessment(
                assessment_folder,
                app,
                TEMPLATE_BOLT,
                img_folder=folder_tree.img_folder,
                fatigue=fatigue,
                insert=True,
            )
            recaps["Immediate"].append(recap_immediate)
            if fatigue:
                recaps["Fatigue"].append(recap_fatigue)
            connections[connection_name] = flange_assessment
        print("Assessing Completed")

    print("Generating Word Recap")
    # Create Recaps from the collected infos during printing
    wordrecaps = {}
    wordrecaps["Immediate"] = pd.concat(recaps["Immediate"])
    if fatigue:
        wordrecaps["Fatigue"] = pd.concat(recaps["Fatigue"])

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
            for name, flange_assessment in connections.items():
                if damage == "Fatigue":
                    imgs_dict = flange_assessment.fatigue_imgs
                elif damage == "Immediate":
                    imgs_dict = flange_assessment.immediate_imgs
                outp.doc.add_heading(name, level=3)
                for boltID, imgs in imgs_dict.items():
                    tit = f"Bolt {boltID}"
                    if damage == "Fatigue":
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
        for connection_name, flange_assessment in connections.items():
            outp.doc.add_heading(connection_name, level=2)
            for boltID, img in flange_assessment.input_imgs.items():
                tit = f"Bolt {boltID}"
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
