import os
import shutil
from importlib.resources import files
from pathlib import Path

import pandas as pd
import pytest

from cassy.auxiliary.constants import EXCEL_AVAILABLE
from cassy.runners.run_bolts import run_bolts
from tests import runners


@pytest.mark.skipif(
    not EXCEL_AVAILABLE, reason="Excel is not installed on this system."
)
def test_run_bolts(tmpdir):
    to_copy = files(runners).joinpath("bolts")
    dest = tmpdir.join("bolts")
    shutil.copytree(to_copy, dest)
    run_bolts(dest, fatigue=True, matlib=Path(dest, "additional_materials"))
    assert len(os.listdir(os.path.join(dest, "assessment"))) == 1
    assert len(os.listdir(os.path.join(dest, "assessment", "Flange1"))) == 2
    excel_file = os.path.join(dest, "assessment", "Flange1", "Flange1_1.xlsx")
    assert os.path.exists(excel_file)
    # check number of sheets in an excel file with pandas
    with pd.ExcelFile(excel_file) as xls:
        assert len(xls.sheet_names) == 5
