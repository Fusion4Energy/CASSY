# -*- coding: utf-8 -*-
"""
Created on Mon Jul 29 15:24:04 2019

@author: Davide Laghi
"""

# import docx
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
from docx.shared import Inches
from docx.shared import Pt
from copy import deepcopy
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL


tablestyle = "python"
captionStyle = "Didascalia"


class TableTemplate:
    """
    This class is built to create a table template starting from a table and
    that can be added to the document later through the 'insert' method
    """

    def __init__(self, table):
        self.tbl = deepcopy(table._tbl)

    def insert(self, doc, caption=None):
        newtbl = deepcopy(self.tbl)

        paragraph = doc.add_paragraph()
        # After that, we add the previously copied table
        paragraph._p.addnext(newtbl)
        newtable = doc.tables[-1]
        if caption is not None:
            paragraph = doc.add_paragraph("Table ", style=captionStyle)
            WordOutput._wrapper(paragraph, "table")
            paragraph.add_run(" - " + caption)

        return newtable


class WordOutput:
    def __init__(self, template=None):
        # Open Word Template
        if template is not None:
            doc = Document(template)
            # Register all template tables
            tables = []
            for table in doc.tables:
                tables.append(TableTemplate(table))
        else:
            doc = Document()
            tables = []

        self.doc = doc
        self.template_tables = tables

    def insert_df(
        self, df, caption, highlight=False, template_idx=None, tablestyle=None
    ):
        """
        Inser a dataframe as a table in a Word file

        Parameters
        ----------
        df : pd.DataFrame
            dataframe to insert.
        caption : str
            caption of the table.
        highlight : bool, optional
            Very specific for stress assessment. The default is False.
        template_idx : int
            index of the template table to use. The default is None
        tablestyle : str
            table word style to apply. The default is None

        Returns
        -------
        table : docx.Table
            table inserted.

        """
        # Create the table or inherit a template
        if template_idx is None:
            table = self.doc.add_table(1, len(df.columns))
        else:
            template = self.template_tables[template_idx]
            table = template.insert(self.doc)

        # Assign style if provided
        if table.style is not None:
            table.style = tablestyle

        # If template is not provided, the header row must be filled
        if template_idx is None:
            # add the header rows.
            for j in range(df.shape[-1]):
                table.cell(0, j).text = df.columns[j]

        # Add the rest of the data frame
        for i, (idx, row) in enumerate(df.iterrows()):
            # Understand is safety margin is barely acceptable
            flag_almost = False
            try:
                sm = float(row["Safety Margin"])
                if sm > 1 and sm < 1.1:
                    flag_almost = True
            except KeyError:
                pass
            except ValueError:
                pass
            except TypeError:
                # cannot convert to float
                pass

            row_cells = table.add_row().cells
            for j, item in enumerate(row):
                cell = row_cells[j]
                cell.text = str(item)
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                for par in cell.paragraphs:
                    par.style = "Table"
                if highlight is not None:
                    if cell.text == "NOK":
                        self._highlightCell(cell)
                    elif cell.text == "OK" and flag_almost:
                        self._highlightCell(cell, color="FFFF46")

        paragraph = self.doc.add_paragraph("Table ", style=captionStyle)
        self._wrapper(paragraph, "table")
        paragraph.add_run(" - " + caption)
        # paragraph = doc.add_paragraph('Figure Text', style='Didascalia')

        return table

    def add_figure(self, img, caption=None):
        """
        Add a figure to the word document. It is guaranteed that the height
        will never be more than one word vertical page.

        Parameters
        ----------
        img : str or path
            path to the image to add.
        caption : str, optional
            caption of the figure. The default is None.

        Returns
        -------
        None.

        """
        # Resizing
        initial_width = 7  # in Inches
        max_height = 8.2  # in Inches

        pic = self.doc.add_picture(img, width=Inches(initial_width))
        initial_height = pic.height.inches
        if initial_height > max_height:
            scale = max_height / initial_height
            pic.height = Inches(max_height)
            pic.width = Inches(initial_width * scale)

        # centering
        last_paragraph = self.doc.paragraphs[-1]
        last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Add caption
        if caption is not None:
            paragraph = self.doc.add_paragraph("Figure ", style=captionStyle)
            self._wrapper(paragraph, "figure")
            paragraph.add_run(" - " + caption)

    def save(self, outpath):
        self.doc.save(outpath)

    @staticmethod
    def _wrapper(paragraph, ptype):
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

        run = run = paragraph.add_run()
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

    @staticmethod
    def _highlightCell(cell, color="FBD4B4"):
        shading_elm_1 = parse_xml(
            r'<w:shd {} w:fill="'.format(nsdecls("w")) + color + r'"/>'
        )
        cell._tc.get_or_add_tcPr().append(shading_elm_1)

    @staticmethod
    def set_paragraph(paragraph, text, bold, fontsize=8):
        if text is not None:
            run = paragraph.add_run(text)
            run.bold = bold
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run.font.size = Pt(fontsize)
