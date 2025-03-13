# -*- coding: utf-8 -*-
"""
Created on Fri Dec  4 17:29:42 2020

@author: Davide Laghi
"""

import shutil
import math
import os
import xlwings as xw
import pythoncom
import pandas as pd
from copy import deepcopy
from PIL import ImageGrab

# from pythoncom import com_error
from xlwings.constants import InsertShiftDirection

pd.options.mode.chained_assignment = None  # default='warn'

# Some global variables
BORDERS = {
    "top": 7,
    "bottom": 8,
    "right": 9,
    "left": 10,
    "inside horizontal": 11,
    "inside Vertical": 12,
}
LINE_STYLES = {"standard": 1, "dashed mid": 3}


class ExcelOutput:
    def __init__(self, app, out_path):
        self.app = app
        # Ensure the path is correctly formatted
        out_path = os.path.expanduser(out_path)

        # try:
        wb = xw.Book(out_path)
        self.wb = wb
        self.startrow = 7
        self.startcolumn = 1
        try:
            self.SA_sheet = "SA_template"
            self.input_sheet = "Input_template"
            self.fatigue_sheet = "Fatigue_template"
        except pythoncom.com_error:
            print("The available sheets are :" + str(wb.sheets))

        # This sheets will be deleted when saving
        self.to_clean = [self.SA_sheet, self.input_sheet, self.fatigue_sheet]
        # except Exception as e:
        #    print(f"Failed to open workbook: {e}")

    def fill_banner(
        self,
        sheet_name,
        submodel,
        poa,
        material,
        code,
        component=None,
        template="SA_template",
        assessment=None,
        paragraph=None,
    ):
        """
        Fill a specific banner for paths

        Parameters
        ----------
        submodel : str
            submodel under assessment.
        poa : str
            point of application.
        material : str
            material of the path.
        code : code.Code
            code used.
        component : str, optional
            component  under assessment. The default is None.
        template : str
            specify the template for small deviation on the filling. The
            default is 'SA'
        assessment : str
            type of assessment
        paragraph : str
            code paragraph

        Returns
        -------
        None.

        """
        ws = self.wb.sheets(sheet_name)
        # Insert some features if not None
        inserts = {"C2": component}
        for cell, item in inserts.items():
            if item is not None:
                ws[cell].value = item

        ws["C3"].value = submodel
        ws["C4"].value = poa
        ws["C5"].value = material

        if template == "fatigue":
            ws["H3"].value = code.name
            inserts = {"H2": assessment, "H4": paragraph}
            for cell, item in inserts.items():
                if item is not None:
                    ws[cell].value = item

        elif template == "SA_template":
            ws["J3"].value = code.name
            inserts = {"J2": assessment, "J4": paragraph}
            for cell, item in inserts.items():
                if item is not None:
                    ws[cell].value = item

        elif template == "Input_template":
            pass

        else:
            raise ValueError(template + " is not an admissible template value")

    def insert_SA_df(
        self,
        df,
        sheet_name,
        divide_blocks=None,
        draw_border=True,
        start_row=None,
        start_column=None,
        word=False,
        print_header=True,
    ):
        """
        Insert a Stress Assessment DataFrame into the excel sheet
        A template sheet is copied and formatted.

        Parameters
        ----------
        df : pd.DataFrame
            Assessment to insert.
        sheet_name : str
            name of the resulting sheet.
        divide_blocks : str, optional
            Divide the dataframe in different dfs based on
            specified index column. The default is None.
        draw_border : bool, optional
            draw the border of the dataframe. if divide_block also the border
            bewteen the REs is drawn. The default is True.
        start_row : int
            override the starting row. The default is None
        start_column : int
            override starting columns. The default is None
        word : bool, optional
            if True the template sheet is the word one. The default is False
        print_header : bool, optional
            if True the header of the df is printed. The default is True

        Returns
        -------
        table : InsertedTable
            Object handling the data inserted and position

        """
        # Copy the template sheet
        if word:
            template_sheet = self.input_sheet
        else:
            template_sheet = self.SA_sheet
        ws = self._copy_sheet(template_sheet, sheet_name)

        # default values
        if start_row is None:
            start_row = self.startrow
        if start_column is None:
            start_column = self.startcolumn

        if divide_blocks is not None:
            # Split the df in other dfs
            groups = set(df.reset_index()[divide_blocks].values)
            for i, group in enumerate(sorted(groups)):
                # I did not have a better idea... sorry
                index = list(df.index.names)
                split_df = deepcopy(df.loc[group])
                split_df[divide_blocks] = group
                split_df.reset_index(inplace=True)
                split_df.set_index(index, inplace=True)

                if i == 0 and print_header:
                    print_header = True
                    additional = 1
                else:
                    print_header = False
                    additional = 0

                self._insert_df(
                    start_row,
                    start_column,
                    split_df,
                    ws,
                    print_index=True,
                    print_header=print_header,
                    draw_border=draw_border,
                )
                start_row = start_row + len(split_df) + additional
        else:
            self._insert_df(
                start_row,
                start_column,
                df,
                ws,
                print_index=True,
                draw_border=draw_border,
                print_header=print_header,
            )
        # ws.autofit()

        table = InsertedTable(
            df, sheet_name, (start_row, start_column), header=print_header
        )

        return table

    def insert_fatigue_df(self, fatigue_df, sheet_name, bolt=False):
        """
        Insert a fatigue assessment in the excel using the correct template

        Parameters
        ----------
        fatigue_df : pd.DataFrame
            table containing the data of the assessment.
        sheet_name : str
            name for the excel sheet that will be inserted.
        bolt : bool, optional
            if True the df is referred to a bolt assessment. The default is
            None

        Returns
        -------
        None.

        """
        # check that all the relevant values are floats and not arrays
        cols = ["de1", "de2", "de3", "de4", "N", "Vj"]
        for col in cols:
            try:
                fatigue_df[col] = fatigue_df[col].apply(lambda x: float(x[0]))
            except TypeError:
                pass
        fatigue_df["de_tot"] = (
            fatigue_df["de1"]
            + fatigue_df["de2"]
            + fatigue_df["de3"]
            + fatigue_df["de4"]
        )

        # Copy the template sheet
        template_sheet = self.fatigue_sheet
        ws = self._copy_sheet(template_sheet, sheet_name)

        # Offset Data
        startline = 9
        offset = 8
        inp_col = "G"
        comp_col = "I"

        # Create the formatted blocks for each RE
        rng_to_copy = ws.range("A9:J16")
        for i in range(1, len(fatigue_df)):
            anchor = "A" + str(startline + offset * i)
            # Handle new version of xlwing with built-in copy and insert func
            try:
                # Newer xlwings version
                rng_to_copy.copy()
                ws.range(anchor).insert()

            except AttributeError:
                try:
                    # older xlwings version
                    rng_to_copy.api.copy
                    ws.range(anchor).api.insert
                except AttributeError:
                    # Weird stuff, probably different version of COM
                    rng_to_copy.api.Copy()
                    ws.range(anchor).api.Insert(InsertShiftDirection.xlShiftDown)

        # --- Compile the recap for each RE ---
        # REs
        res = {
            "A": "ID",
            "B": "Operating conditions",
            "C": "Range",
            "D": "ctg",
            "E": "lvl",
        }
        if bolt:
            inputs = {"T": 0, "dpa": 1, "sigma N": 2, "epsilon N": 3, "n": 4, "Kf": 5}
            comp = {
                "sigma plasticity": 1,
                "epsilon plasticity": 2,
                "sigma pre": 3,
                "sigma bar": 4,
                "epsilon bar": 5,
                "N": 6,
            }
        else:
            inputs = {"T": 0, "dpa": 1, "sigma tot": 2, "n": 3}
            comp = {"de1": 1, "de2": 2, "de3": 3, "de4": 4, "de_tot": 5, "N": 6}

        for idx, row in fatigue_df.iterrows():
            # REs
            for col, name in res.items():
                cell = col + str(startline + idx * offset)
                ws.range(cell).value = row[name]

            # Inputs
            for name, rowplus in inputs.items():
                cell = inp_col + str(startline + rowplus + idx * offset)
                ws.range(cell).value = row[name]

            # Computation
            ws.range("H" + str(startline + idx * offset)).value = row["Rule ID"]
            for name, rowplus in comp.items():
                cell = comp_col + str(startline + rowplus + idx * offset)
                ws.range(cell).value = row[name]

        # --- Compile global results ---
        fatigue_df.set_index("ID", inplace=True)

        try:
            re_max = fatigue_df["Vj"].idxmax()
            Vjtot = fatigue_df["Vj"].sum()
            maxVj = fatigue_df["Vj"].max()
        except TypeError:
            fatigue_df["Vj"] = fatigue_df["Vj"].apply(lambda x: float(x[0]))
            re_max = fatigue_df["Vj"].idxmax()
            Vjtot = fatigue_df["Vj"].sum()
            maxVj = fatigue_df["Vj"].max()

        last_row = startline + offset * idx + offset + 2
        ws.range("B" + str(last_row)).value = maxVj
        ws.range("D" + str(last_row)).value = re_max
        ws.range("G" + str(last_row)).value = Vjtot

    def _clean_up(self):
        for sheet_name in self.to_clean:
            sheet = self.wb.sheets(sheet_name)
            sheet.delete()

    def _copy_sheet(self, template_sheet, newname):
        """
        Return a renamed copy of a particular sheet

        Parameters
        ----------
        template_sheet : xw.Sheet
            sheet to copy.
        newname : str
            name of the new sheet.

        Returns
        -------
        ws : xw.Sheet
            copied sheet.

        """
        # Copy the template sheet
        template_sheet1 = self.wb.sheets(template_sheet)
        template_sheet1.api.Copy(Before=template_sheet1.api)
        try:
            ws = self.wb.sheets(template_sheet1.name + " (2)")
        except pythoncom.com_error:
            print("The available sheets are :" + str(self.wb.sheets))
        try:
            ws.name = newname
        except pythoncom.com_error:
            ws.Name = newname
        return ws

    def _insert_df(
        self,
        startrow,
        startcolumn,
        df,
        ws,
        print_index=True,
        cols_head_size=12,
        print_header=True,
        draw_border=True,
    ):
        """
        Insert a DataFrame (df) into a Worksheet (ws) using xlwings.

        Parameters
        ----------
        startrow : int or str
            Starting row where to insert the DataFrame.
        startcolumn : int or str
            Starting column where to insert the DataFrame. It can be expressed
            both as an integer as a letter in Excel fashion.
        df : pandas.DataFrame
            DataFrame to insert in the excel sheet
        ws : str
            name of the Excel worksheet where to put the DataFrame.
        print_index : bool
            if True the DataFrame index is printed. DEAFAULT is True.
        cols_head_size : int
            Font size for columns header. DEFAULT is 12
        values_format : str
            how to format the values. DEFAULT is None
        print_index : bool
            if True the DataFrame header is printed. DEAFAULT is True.
        draw_border : Bool
            draw the border of the DataFrame

        Returns
        -------
        None

        """

        # Start column can be provided as a letter or number (up to Z)
        if type(startcolumn) is str:
            startcolumn = ord(startcolumn.lower()) - 96

        # Collect some anchors
        anchor = (startrow, startcolumn)

        # insert DF
        ws.range(anchor).options(index=print_index, header=print_header).value = df

        # Get the table object
        table = InsertedTable(df, ws.name, anchor, header=print_header, idx=print_index)

        if draw_border:
            # Draw the border of the table
            # Range of the DataFrame
            df_rng = ws.range(anchor, table.anchor_end)
            for border in ["top", "bottom", "right", "left"]:
                borders = df_rng.api.Borders(BORDERS[border])
                borders.LineStyle = LINE_STYLES["standard"]
                borders.Weight = 3
            for border in ["inside horizontal", "inside Vertical"]:
                borders = df_rng.api.Borders(BORDERS[border])
                borders.LineStyle = LINE_STYLES["dashed mid"]
                borders.Weight = 1

        if print_header:
            # Get the header range
            header_end = (startrow, table.end_column)
            header = (anchor, header_end)

            # Format header
            # ws.range(*header).api.Font.Size = cols_head_size
            ws.range(*header).api.Font.Bold = True
            ws.range(*header).color = (236, 236, 236)

        #  Format Index
        try:
            if print_index:
                idx = (table.idx_begin, table.idx_end)
                # ws.range(*idx).api.Font.Size = cols_head_size
                # ws.range(*idx).api.Font.Bold = True
                self._merge_index(ws, ws.range(*idx))
        except pythoncom.com_error:
            pass

    @staticmethod
    def _merge_index(ws, xlrange):
        """
        Given a range representing the index of a dataframe it merges all
        cell that have the same value

        Parameters
        ----------
        ws : xw.Sheet
            Sheet where we are operating.
        xlrange : xw.Range
            range where to operate (of the index part of the dataframe).

        Returns
        -------
        None.

        """
        # get the columns id
        startrow = xlrange.row
        startcol = xlrange.column
        endrow = xlrange.last_cell.row
        endcol = xlrange.last_cell.column

        for column_id in range(startcol, endcol + 1):
            start = (startrow, column_id)
            end = (endrow, column_id)
            col_range = ws.range(start, end)
            ExcelOutput._merge_column(ws, col_range)

    @staticmethod
    def _merge_column(ws, xlrange):
        """
        given a column range it iterates on it and merge the cells with same
        value

        Parameters
        ----------
        ws : xw.Sheet
            Sheet where we are operating.
        xlrange : xw.Range
            Column range where we are operating.

        Returns
        -------
        None.

        """
        # get the starting cell and starting value
        startrow = xlrange.row
        startcolumn = xlrange.column
        start = (startrow, startcolumn)
        end = (startrow, startcolumn)
        previous_value = "sdassadsads"

        for i, cell in enumerate(xlrange):
            # check if the current cell is in the same merge
            if cell.value == previous_value:
                # Put the value to None in order to avoid warnings during merge
                cell.value = None
                # adjourn end cell
                end = (startrow + i, startcolumn)
            else:  # Different value
                # Adjourn the previous value
                previous_value = cell.value
                # Merge the range and reinitialize
                ws.range(start, end).merge()
                # Adjourn start cell and end cell
                start = (startrow + i, startcolumn)
                end = (startrow + i, startcolumn)

        # Check if merge has to be performed at the end of the cycle
        if start[0] != end[0]:
            ws.range(start, end).merge()

    def grab_img(self, firstcell, lastcell, sheet, outpath):
        """
        Capture a screenshot of the Excel file and save it

        Parameters
        ----------
        firstcell : tuple
            indices of the starting row and column.
        lastcell : tuple
            indices of the last row and column.
        sheet : str
            name of the sheet where to operate.
        outpath : str or path, optional
            outpath for the image.

        Returns
        -------
        outpath : str or path, optional
            outpath for the image.

        """
        ws = self.wb.sheets(sheet)

        if firstcell == "all" or lastcell == "all":
            rng = ws.used_range
        else:
            rng = ws.range(firstcell, lastcell)

        rng.copy()

        # pic = ws.pictures[0]
        # pic.api.Copy()
        try:
            img = ImageGrab.grabclipboard()
        except OSError:
            # retry, it may work
            rng.copy()
            img = ImageGrab.grabclipboard()
        except MemoryError:
            # retry, it may work
            rng.copy()
            img = ImageGrab.grabclipboard()

        img.save(outpath)

        return outpath

    def save(self, path):
        """
        Operations to do when saving and closing the file

        Parameters
        ----------
        path : str or path
            path to the output file.

        Returns
        -------
        None.

        """
        self._clean_up()
        self.wb.save()
        self.wb.close()


class InsertedTable:
    def __init__(self, df, sheet, anchor, header=True, idx=True):
        """
        Help with the handling of idnices of an inserted table

        Parameters
        ----------
        df : pd.DataFrame
            inserted dataframe.
        sheet : str
            sheet where we are operating.
        anchor : (startrow, startcolumn)
            tuple indicatin the start of the table.
        header : bool, optional
            the header has been printed. The default is True.
        idx : bool, optional
            the index have been printed. The default is True.

        Returns
        -------
        None.

        """
        # --- Some globally useful parameters ---
        self.sheet = sheet
        self.anchor = anchor  # Starting cell of the dataframe
        startrow = anchor[0]
        startcolumn = anchor[1]
        self.startcolumn = startcolumn  # index of the first column
        self.startrow = startrow  # index of the first row

        # idx of the last column
        if idx:
            end_column = startcolumn + len(df.columns) + len(df.index[0]) - 1

        else:
            end_column = startcolumn + len(df.columns) - 1
        self.end_column = end_column

        # idx of the last row
        if header:
            idx_begin = (startrow + 1, startcolumn)
            end_row = startrow + len(df)
            idx_end = (end_row, startcolumn + len(df.index[0]))

        else:
            idx_begin = (startrow, startcolumn)
            end_row = startrow + len(df) - 1
            idx_end = (end_row, startcolumn + len(df.index[0]))

        self.end_row = end_row  # last row index
        self.anchor_end = (end_row, end_column)  # Last cell of the DF

        # Data for the index range
        self.idx_begin = idx_begin
        self.idx_end = idx_end
