from __future__ import annotations

import logging
import os
import shutil
from importlib.resources import files
from pathlib import Path

logger = logging.getLogger(__name__)

import pandas as pd

from cassy.additional_data import templates
from cassy.auxiliary.types import PathLike
from cassy.bolts.bolt_assess import FlangeAssessment
from cassy.bolts.bolt_config import FlangeAssessmentConfig
from cassy.bolts.geometry import BoltLikeGeom
from cassy.designcodes.EN13445_bolts import EN_13445_Bolts
from cassy.designcodes.sdcic_bolts import SDC_IC_Bolts
from cassy.general.folder_tree import FolderTree
from cassy.office.word_helper import WordOutput
from cassy.runners.run_common import new_tracer, save_trace, tracing

# #################### Parameters #############################################

# Templates
TEMPLATE_WORD = files(templates).joinpath("template.docx")

# Word titles and captions
RECAP_TITLE = "Stress Assessment Recap"
RECAP_CAPTION = "Summary of results from the verification of the design rules against "
EXCELS_TITLE = "Stress Assessment Detail"
EXCELS_CAPTION = ": summary for "
INPUT_CAPTION = "Input Summary: "
INPUT_TITLE = "Internal Bolt Action Used During the Assessment"


# #################### Code ###################################################
# --- Initializations ---
def run_bolts(
    root: PathLike,
    configs: dict[str, FlangeAssessmentConfig],
    geoms: dict[str, BoltLikeGeom],
    fatigue: bool = False,
    print_recap: bool = True,
    merge: bool = True,
    only_bolts: bool = False,
    trace: bool = False,
    geometry: dict | None = None,
) -> None:
    folder_tree = FolderTree(root)
    tracer = new_tracer(trace, "bolts")
    if tracer is not None:
        tracer.metadata["codes"] = sorted({c.code.name for c in configs.values()})

    recaps = {"Immediate": [], "Fatigue": []}
    connections: dict[str, FlangeAssessment] = {}

    for connection_name, flange_config in configs.items():
        # perform the assessment
        flange_assessment = FlangeAssessment(geoms, flange_config, fatigue=fatigue)

        # override insert assessment if only bolts are requested
        if only_bolts:
            flange_assessment.config.has_insert = False

        with tracing(tracer):
            flange_assessment.assess()
            if flange_assessment.config.has_insert:
                flange_assessment.assess(insert=True)

        # print the assessment
        assessment_folder = Path(folder_tree.assessment_folder, connection_name)
        connections[connection_name] = flange_assessment

        # override eventual old results
        if os.path.exists(assessment_folder):
            shutil.rmtree(assessment_folder)
        os.mkdir(assessment_folder)

        flange_assessment.print_global_df(assessment_folder)
        if flange_assessment.config.has_insert:
            flange_assessment.print_global_df(assessment_folder, insert=True)

    save_trace(tracer, folder_tree.assessment_folder, geometry)

    if not print_recap:
        logger.info("No word recap requested. Assessment completed")
        return  # Exit here if no word recap is requested

    for _, flange_assessment in connections.items():
        recap_immediate, recap_fatigue = flange_assessment.get_recap(fatigue=fatigue)
        if recap_immediate is not None:
            recaps["Immediate"].append(recap_immediate)
        if fatigue and recap_fatigue is not None:
            recaps["Fatigue"].append(recap_fatigue)

    logger.info("Assessing Completed")

    logger.info("Generating Word Recap")
    # Create Recaps from the collected infos during printing
    wordrecaps = {}
    immediate = False
    if recaps["Immediate"]:
        wordrecaps["Immediate"] = pd.concat(recaps["Immediate"])
        immediate = True
    if fatigue:
        wordrecaps["Fatigue"] = pd.concat(recaps["Fatigue"])

    # --- Generate the word output ---
    outp = WordOutput(template=TEMPLATE_WORD)
    # start with portrait
    outp.set_orientation("portrait")

    # --- Add the Immediate damage section ---
    if immediate:
        outp.doc.add_heading("Immediate damage", level=1)
        # Insert the recap
        outp.doc.add_heading(RECAP_TITLE, level=2)
        caption = RECAP_CAPTION + "Immediate damage"
        outp.add_table(
            None, wordrecaps["Immediate"], "damage recap", caption, merge=False
        )

        # Insert the detailed assessments in landscape
        outp.set_orientation("landscape")
        outp.doc.add_heading(EXCELS_TITLE, level=2)
        for name, flange_assessment in connections.items():
            # Immediate damage assessements
            outp.doc.add_heading(name, level=3)
            for boltID, assessment in flange_assessment.bolt_results.items():
                outp.doc.add_heading(f"Bolt {boltID}", level=4)
                complete_banner = flange_assessment.compute_banner(
                    boltID,
                    complete=True,
                )
                # add a table for each rule set
                tables = flange_assessment.get_assessment_tables(boltID, "Immediate")
                for key, table in tables.items():
                    # compute the banner
                    banner = complete_banner.copy()
                    banner["assessment"] = f"{key}, bolts"
                    caption = f"Bolt {boltID}{EXCELS_CAPTION}{key}"
                    outp.add_table(
                        banner, table, "immediate bolts", caption, merge=merge
                    )
                # try to get the insert assessment too if present
                try:
                    tables = flange_assessment.get_assessment_tables(
                        boltID, "Immediate", insert=True
                    )
                except ValueError:
                    continue
                for key, table in tables.items():
                    # compute the banner
                    banner = complete_banner.copy()
                    # material needs to be updated as it may differ
                    banner["material"] = list(
                        flange_assessment.insert_assessments[boltID].values()
                    )[0].poa.material.name
                    banner["assessment"] = f"{key}, base material"
                    caption = f"Base material {boltID}{EXCELS_CAPTION}{key}"
                    outp.add_table(
                        banner, table, "immediate bolts", caption, merge=merge
                    )

    if fatigue:
        outp.set_orientation("portrait")
        # --- Add the fatigue damage section
        outp.doc.add_heading("Fatigue damage", level=1)
        # Insert the recap in portrait
        outp.doc.add_heading(RECAP_TITLE, level=2)
        caption = RECAP_CAPTION + "Fatigue damage"
        outp.add_table(
            None, wordrecaps["Fatigue"], "fatigue recap", caption, merge=False
        )

        # Insert the detailed assessments in landscape
        outp.set_orientation("landscape")
        outp.doc.add_heading(EXCELS_TITLE, level=2)
        for name, flange_assessment in connections.items():
            # Immediate damage assessements
            outp.doc.add_heading(name, level=3)

            for boltID, assessment in flange_assessment.bolt_results.items():
                outp.doc.add_heading(f"Bolt {boltID}", level=4)
                banner = flange_assessment.compute_banner(
                    boltID,
                    complete=True,
                    assessment="Time-independent fatigue assessment",
                )
                # add the fatigue damage assessment
                fatigue_table = assessment["Fatigue"]
                caption = f"Bolt {boltID}{EXCELS_CAPTION}Fatigue damage"
                # select the correct table style
                if isinstance(flange_assessment.config.code, SDC_IC_Bolts):
                    table_type = "fatigue SDCIC bolts"
                elif isinstance(flange_assessment.config.code, EN_13445_Bolts):
                    table_type = "fatigue EN13445 bolts"
                else:
                    table_type = "fatigue bolts"
                table = outp.add_table(
                    banner, fatigue_table, table_type, caption, merge=False
                )
                table.add_total_fatigue_row(fatigue_table["Vj"].sum())

    # --- insert the inputs ---
    outp.set_orientation("portrait")
    outp.doc.add_heading(INPUT_TITLE, level=1)
    for connection_name, flange_assessment in connections.items():
        outp.doc.add_heading(connection_name, level=2)
        for boltID, assessment in flange_assessment.bolt_results.items():
            title = f"Bolt {boltID}"
            outp.doc.add_heading(title, level=3)
            caption = INPUT_CAPTION + title
            banner = flange_assessment.compute_banner(boltID)
            # add a table for each rule set
            table = assessment["Inputs"]
            outp.add_table(banner, table, "input bolts", caption, merge=merge)

    outp.save(folder_tree.out_word)

    logger.info("All done!")
