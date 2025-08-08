from __future__ import annotations

import os
import re
import shutil
from importlib.resources import files

import pandas as pd

from cassy.additional_data import templates
from cassy.auxiliary.types import PathLike
from cassy.designcodes.map import PATH_CODES as CODES
from cassy.general.configuration import parse_cfg_files
from cassy.general.folder_tree import PathsFolderTree
from cassy.office.word_helper import WordOutput
from cassy.paths.submodel import Submodel
from cassy.runners.run_common import build_material_library

# #################### User Inputs ############################################
# local folders and files
TEMPLATE_WORD = files(templates).joinpath("template.docx")

# Word titles and captions
RECAP_TITLE = "Stress Assessment Recap"
RECAP_CAPTION = "Summary of results from the verification of the design rules against "
EXCELS_TITLE = "Stress Assessment Detail"
EXCELS_CAPTION = ": stress assessment summary for "
INPUT_CAPTION = "Input Summary: "
INPUT_TITLE = "Single Load Case stresses matrix"

# WORDS_RECAPS = {"Immediate": 0, "Ratcheting": 1, "Fatigue": 2, "Fatigue ASME": 3}

PATNUM = re.compile(r"\d+")


# #################### Code ###################################################
def run_paths(
    root: PathLike,
    fatigue: bool = False,
    matlib: PathLike | None = None,
    print_recap: bool = True,
    merge: bool = True,
) -> None:
    folder_tree = PathsFolderTree(root)
    # --- Initializations ---
    materials = build_material_library(matlib)

    # --- Load Configuration files ---
    configs = parse_cfg_files(folder_tree.configurations, folder_tree.stress_tensors)
    # --- Reorganize and create the LinStresses and Combined ones + Assessment ---
    print("\nAssessing the results...")
    submodels: list[Submodel] = []
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

        submodels.append(submodel)

        if not print_recap:
            submodel.print_global_df(ass_path)
            continue  # skip printing the excel assessments

    if not print_recap:
        print("No word recap requested. Assessment completed")
        return  # Exit here if no word recap is requested

    for submodel in submodels:
        submodel_recap_rows = submodel.get_recap(fatigue=fatigue)
        for key, item in submodel_recap_rows.items():
            if key not in recap_rows:
                recap_rows[key] = []
            recap_rows[key].extend(item)
    print("Assessing Completed")

    print("Generating Word Recap")
    # Create Recaps from the collected infos during printing
    recaps = {}

    # --- Generate the word output ---
    outp = WordOutput(template=TEMPLATE_WORD)
    # start with portrait
    outp.set_orientation("portrait")

    for dtype, recap in recap_rows.items():
        recaps[dtype] = pd.DataFrame(recap)
        outp.doc.add_heading(dtype + " damage", level=1)
        # Insert the recap
        outp.doc.add_heading(RECAP_TITLE, level=2)
        caption = RECAP_CAPTION + dtype + " damage"
        if dtype == "Fatigue":
            table_type_recap = "fatigue recap"
            table_type_assessment = "fatigue bolts"
        else:
            table_type_recap = "damage recap"
            table_type_assessment = "immediate bolts"
        outp.add_table(None, recaps[dtype], table_type_recap, caption, merge=False)

        # Insert the excels
        outp.set_orientation("landscape")
        outp.doc.add_heading(EXCELS_TITLE, level=2)
        for submodel in submodels:
            outp.doc.add_heading(submodel.name, level=3)
            for pnum in submodel.paths:
                for pos in ["begin", "end"]:
                    if dtype == "Fatigue":
                        df = submodel.assessments[pnum][f"{pos} fatigue"]
                    else:
                        df = submodel.assessments[pnum][pos]
                        df = df[df["Damage Type"] == dtype]
                    tit = "Path " + str(pnum) + " " + pos
                    outp.doc.add_heading(tit, level=4)
                    caption = (
                        "Path "
                        + str(pnum)
                        + " "
                        + pos
                        + EXCELS_CAPTION
                        + dtype
                        + " damage"
                    )
                    banner = submodel.compute_banner(
                        pnum, pos, complete=True, assessment=dtype
                    )
                    table = outp.add_table(
                        banner, df, table_type_assessment, caption, merge=merge
                    )
                    if dtype == "Fatigue":
                        table.add_total_fatigue_row(df["Vj"].sum())

    # Add input
    outp.set_orientation("portrait")
    outp.doc.add_heading(INPUT_TITLE, level=1)
    for submodel in submodels:
        outp.doc.add_heading(submodel.name, level=2)
        for pnum in submodel.paths:
            for pos in ["begin", "end"]:
                tit = "Path " + str(pnum) + " " + pos
                outp.doc.add_heading(tit, level=3)
                caption = INPUT_CAPTION + "Path " + str(pnum) + " " + pos
                df = submodel.paths[pnum]._get_basic_loads_df(pos)
                banner = submodel.compute_banner(pnum, pos)
                outp.add_table(
                    banner, df.reset_index(), "input paths", caption, merge=merge
                )

    outp.save(folder_tree.out_word)

    print("All done!")
