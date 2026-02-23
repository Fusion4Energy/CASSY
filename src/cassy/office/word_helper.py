from copy import deepcopy
from enum import Enum

import docx
import pandas as pd
from docx.document import Document
from docx.enum.section import WD_ORIENT

# from docx.enum.table import WD_ALIGN_VERTICAL
# from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

# from docx.shared import Inches, Pt
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from cassy.auxiliary.types import PathLike
from cassy.office.table_types import TABLES_LOCATION, TableFormatting

tablestyle = "python"
captionStyle = "Didascalia"
TABLE_BODY_STYLE = "Table"


class HighlightColor(Enum):
    # nice resource for new colors: https://htmlcolorcodes.com/
    YELLOW = "FFFF46"
    ORANGE = "FBD4B4"
    GREEN = "B4FBB4"


class NewTable:
    def __init__(self, table: Table, table_type: TableFormatting):
        """Get a docx table and add functionalities to it.

        Parameters
        ----------
        table : Table
            The docx table to enhance.
        table_type : TableType
            The type of the table, which defines its structure and formatting.
        """
        self.tbl = deepcopy(table)
        self.tbl.style = tablestyle
        self.tbl.autofit = False
        self.table_type = table_type

    def merge_repeated(self, max_col: int | None = None, min_row: int = 0):
        """
        Merge repeated cells in a table.

        Parameters
        ----------
        max_col : int | None, optional
            The maximum column to consider for merging, by default None which means all columns.
        min_row : int, optional
            The minimum row to start merging from, by default 0.
        """
        # iterate on the columns
        columns = self.tbl.columns
        for j, col in enumerate(columns):
            if max_col is not None and j > max_col:
                break
            # now start iterating on the rows. If the value of the row is the same
            # as the previous one merge them.
            prev_value = None
            prev_cell = None
            start_merge_cell = None
            during_merge_flag = False
            cells = col.cells  # Access once, outside the loop
            for i, current_cell in enumerate(cells):
                current_text = current_cell.text

                # do nothing if not requested
                if i < min_row:
                    continue

                # if the text is the same as before keep looking for merge end
                if current_text == prev_value:
                    if start_merge_cell is None:
                        start_merge_cell = prev_cell
                        during_merge_flag = True
                    # merge with the previous cell, delete the text
                    current_cell.text = ""
                # They are different but we are in a merge process
                elif during_merge_flag:
                    merged_cell = start_merge_cell.merge(prev_cell)
                    # Remove extra paragraphs in merged cell to avoid newlines
                    for par in merged_cell.paragraphs[1:]:
                        par._element.getparent().remove(par._element)
                    during_merge_flag = False
                    start_merge_cell = None

                prev_value = current_text
                prev_cell = current_cell
            # at the end of the loop merge if the mergeflag is still active
            if during_merge_flag:
                merged_cell = start_merge_cell.merge(prev_cell)
                # Remove extra paragraphs in merged cell to avoid newlines
                for par in merged_cell.paragraphs[1:]:
                    par._element.getparent().remove(par._element)
                during_merge_flag = False
                start_merge_cell = None

    def add_df(self, df: pd.DataFrame, formats: dict[int, str] | None = None):
        """Insert a DataFrame into the table.

        Parameters
        ----------
        df : pd.DataFrame
            The DataFrame to insert into the table.
        formats : dict[int, str] | None, optional
            A dictionary mapping column indices to formats, by default None.
        """
        # Get column widths from the last row (if any)
        col_widths = []
        if len(self.tbl.rows) > 0:
            for cell in self.tbl.rows[-1].cells:
                col_widths.append(cell.width)
        for i, (_, row) in enumerate(df.iterrows()):
            row_cells = self.tbl.add_row().cells
            for j, value in enumerate(row):
                # try to get the format
                format = formats.get(j, "{}") if formats else "{}"
                try:
                    row_cells[j].text = format.format(value)
                except Exception:  # in case of formatting error
                    row_cells[j].text = str(value)
                # formatting
                self._style_cell(row_cells[j])
                # # Copy column width from first row
                # if col_widths and j < len(col_widths) and col_widths[j] is not None:
                #     row_cells[j].width = col_widths[j]

    def insert_in_doc(self, doc: Document, caption: str | None = None):
        """Insert the table into a Word document.

        Parameters
        ----------
        doc : Document
            The Word document to insert the table into.
        caption : str | None, optional
            The caption to add above the table, by default None
        """
        paragraph = doc.add_paragraph()
        # After that, we add the previously copied table
        paragraph._p.addnext(self.tbl._tbl)
        newtable = doc.tables[-1]
        if caption is not None:
            paragraph = doc.add_paragraph("Table ", style=captionStyle)
            WordOutput._wrapper(paragraph, "table")
            paragraph.add_run(" - " + caption)

        return newtable

    def fill_banner(self, banner: dict):
        """
        Fill the banner of the table with the provided data.
        """
        component = banner.get("model", "")
        submodel = banner["submodel"]
        id = banner["id"]
        material = banner["material"]
        assessment = banner.get("assessment", None)
        code = banner.get("code", None)
        paragraph = banner.get("paragraph", None)

        # mandatory
        for string, position in zip([component, submodel, id, material], [1, 2, 3, 4]):
            cell = self.tbl.cell(position, 2)
            cell.text = string
            self._style_cell(cell)
        # optional
        for string, position in zip([assessment, code, paragraph], [1, 2, 3]):
            if string is not None:
                cell = self.tbl.cell(position, 9)
                cell.text = string
                self._style_cell(cell)

    def _style_cell(self, cell: _Cell, bold: bool = False):
        for par in cell.paragraphs:
            # par.style = self.body_style_ID
            # this is much much faster. Bypassing checks, not sure if the style is not
            # present which kind of error you get. maybe corrupted word file?
            par._p.style = TABLE_BODY_STYLE
            if bold:
                for run in par.runs:
                    run.bold = bold
        if cell.text in ["NOK", "FAILED"]:
            self._highlight_cell(cell, HighlightColor.ORANGE)
        elif cell.text in ["OK", "Assessment not required"]:
            self._highlight_cell(cell, HighlightColor.GREEN)

    def add_total_fatigue_row(self, tot_vj: float):
        """Add a total fatigue row to the fatigue table.

        Parameters
        ----------
        tot_vj : float
            The total fatigue value to add to the table."""
        # Add the total row to the table. It shall use only the last two columns of the
        # word table
        row_cells = self.tbl.add_row().cells
        row_cells[-2].text = "Total"
        row_cells[-1].text = f"{tot_vj:.2%}"
        # Style the total row
        for cell in row_cells:
            self._style_cell(cell, bold=True)
        if tot_vj < 1:
            self._highlight_cell(row_cells[-1], HighlightColor.GREEN)
        else:
            self._highlight_cell(row_cells[-1], HighlightColor.ORANGE)

    @staticmethod
    def _highlight_cell(cell: _Cell, color: HighlightColor):
        shading_elm_1 = parse_xml(
            r'<w:shd {} w:fill="'.format(nsdecls("w")) + color.value + r'"/>'
        )
        cell._tc.get_or_add_tcPr().append(shading_elm_1)


class WordOutput:
    def __init__(self, template: PathLike):
        """Initialize the WordOutput object.

        Parameters
        ----------
        template : PathLike
            The path to the Word template file.
        """
        # Open Word Template
        doc = docx.Document(template)
        self.doc = doc
        self.template_tables = self._parse_template_tables()

    def _parse_template_tables(self) -> dict[str, NewTable]:
        """
        Parse the template tables to create a list of TableTemplate objects.
        """
        # Register all template tables
        tables = {}
        for i, table in enumerate(self.doc.tables):
            if i in TABLES_LOCATION:
                table_type = TABLES_LOCATION[i]
                tables[table_type.name] = NewTable(table, table_type)
        return tables

    def save(self, outpath: PathLike) -> None:
        self.doc.save(outpath)

    @staticmethod
    def _wrapper(paragraph: Paragraph, ptype: str) -> None:
        """
        Wrap a paragraph in order to add cross reference

        Parameters
        ----------
        paragraph : docx.Paragraph
            image to wrap.
        ptype : str
            type of paragraph to wrap

        Returns
        -------
        None.

        """
        if ptype == "table":
            instruction = " SEQ Table \\* ARABIC"
        elif ptype == "figure":
            instruction = " SEQ Figure \\* ARABIC"
        else:
            raise ValueError(ptype + " is not a supported paragraph type")

        run = paragraph.add_run()
        r = run._r
        fldChar = OxmlElement("w:fldChar")
        fldChar.set(qn("w:fldCharType"), "begin")
        r.append(fldChar)
        instrText = OxmlElement("w:instrText")
        instrText.text = instruction
        r.append(instrText)
        fldChar = OxmlElement("w:fldChar")
        fldChar.set(qn("w:fldCharType"), "end")
        r.append(fldChar)

    # @staticmethod
    # def set_paragraph(
    #     paragraph: Paragraph, text: str, bold: bool, fontsize: int = 8
    # ) -> None:
    #     if text is not None:
    #         run = paragraph.add_run(text)
    #         run.bold = bold
    #         paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    #         run.font.size = Pt(fontsize)

    def _insert_split_df(
        self,
        table: NewTable,
        df: pd.DataFrame,
        caption: str,
    ):
        """insert a split dataframe into a table."""
        # always ensure that it is a dataframe. If series, convert to dataframe of
        # length 1
        try:
            df = df[table.table_type.col_order]
        except KeyError:
            # if the columns are not found it may be a series problem
            df = df.set_index("index").T.reset_index()
            df = df[table.table_type.col_order]
        REs = df[table.table_type.block_identifier].unique()
        min_row = len(table.tbl.rows)
        for re_id in REs:
            # filter the dataframe for the current RE ID
            df_re = df[df[table.table_type.block_identifier] == re_id]
            table.add_df(df_re, formats=table.table_type.formats)
            table.merge_repeated(
                max_col=table.table_type.max_col_merge, min_row=min_row
            )
            min_row += len(df_re)
        # insert the table in the document
        table.insert_in_doc(self.doc, caption=caption)

    def _insert_simple_df(
        self,
        table: NewTable,
        df: pd.DataFrame,
        caption: str,
    ):
        """Insert a simple dataframe into a table."""
        df = df[table.table_type.col_order]
        table.add_df(df, formats=table.table_type.formats)
        table.insert_in_doc(self.doc, caption=caption)

    def add_table(
        self,
        banner: dict | None,
        df: pd.DataFrame,
        table_type: str,
        caption: str,
        merge: bool = True,
    ) -> NewTable:
        """Add a table to the Word document.

        Parameters
        ----------
        banner : dict | None
            Banner information to fill the table. If None, no banner is added.
        df : pd.DataFrame
            DataFrame containing the data to be added to the table.
        table_type : str
            Type of the table to be added.
        caption : str
            Caption for the table.
        merge : bool, optional
            Whether to merge repeated cells, by default True. This operation has
            been optimized but is still expensive.

        Returns
        -------
        NewTable
            The table object that has been added to the document.
        """
        # get the correct table type
        table = deepcopy(self.template_tables[table_type])
        # fill the banner
        if banner is not None:
            table.fill_banner(banner)
        # insert the dataframe into the table
        if merge:
            self._insert_split_df(
                table,
                df,
                caption,
            )
        else:
            self._insert_simple_df(
                table,
                df,
                caption,
            )
        return table

    def set_orientation(self, orientation: str = "portrait"):
        """Set the orientation of the document.

        Parameters
        ----------
        orientation : str, optional
            The orientation to switch to, either 'portrait' or 'landscape', by default 'portrait'.
        """
        if orientation not in ["portrait", "landscape"]:
            raise ValueError("Orientation must be either 'portrait' or 'landscape'.")

        current_orientation = self.doc.sections[-1].orientation

        if orientation == "landscape":
            new_orientation = WD_ORIENT.LANDSCAPE
        else:
            new_orientation = WD_ORIENT.PORTRAIT

        if new_orientation == current_orientation:
            return  # no further action if orientation was already set

        section = self.doc.add_section()
        section.orientation = new_orientation
        # Swap width and height for landscape
        new_width, new_height = section.page_height, section.page_width
        section.page_width = new_width
        section.page_height = new_height
