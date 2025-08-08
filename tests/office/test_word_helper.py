from importlib.resources import as_file, files

import pytest

from cassy.additional_data import templates
from cassy.bolts.bolt_assess import FlangeAssessment
from cassy.designcodes.sdcic_bolts import SDC_IC_Bolts
from cassy.office.word_helper import WordOutput
from tests.bolts.test_bolt_assess import flange_assessment, geometries
from tests.office import res

RESOURCES = files(res)
TEMPLATE_FOLDER = files(templates)


class TestWordOutput:
    @pytest.fixture
    def word_output(self) -> WordOutput:
        with as_file(TEMPLATE_FOLDER.joinpath("template.docx")) as file:
            doc = WordOutput(file)
        return doc

    @pytest.mark.parametrize(
        ["table_type", "complete", "tag"],
        [
            ("input bolts", False, "Inputs"),
            ("immediate bolts", True, "Immediate"),
            ("fatigue bolts", True, "Fatigue"),
        ],
    )
    def test_add_table_bolts(
        self,
        word_output: WordOutput,
        flange_assessment: FlangeAssessment,
        tmpdir,
        table_type: str,
        complete: bool,
        tag: str,
    ):
        flange_assessment.assess()
        input_df = flange_assessment.bolt_results[1][tag]
        banner = flange_assessment.compute_banner(1, complete=complete)
        # Add the input table to the Word document
        word_output.add_table(banner, input_df, table_type, "Test Input Table")
        # Save the document for inspection
        word_output.doc.save(tmpdir.join("test_input_table.docx"))

    def test_fatigue_sdcic_table(
        self,
        word_output: WordOutput,
        flange_assessment: FlangeAssessment,
        tmpdir,
    ):
        flange_assessment.config.code = SDC_IC_Bolts()
        flange_assessment.assess()
        fatigue_df = flange_assessment.bolt_results[1]["Fatigue"]
        banner = flange_assessment.compute_banner(1, complete=True)
        # Add the fatigue SDCIC table to the Word document
        table = word_output.add_table(
            banner, fatigue_df, "fatigue SDCIC bolts", "Test Fatigue Table", merge=False
        )
        table.add_total_fatigue_row(fatigue_df["Vj"].sum())
        # Save the document for inspection
        word_output.doc.save(tmpdir.join("test_fatigue_table.docx"))
