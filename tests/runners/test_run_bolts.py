import os
import shutil
from importlib.resources import files
from pathlib import Path

from cassy.runners.run_bolts import run_bolts
from tests import runners


def test_run_bolts(tmpdir):
    to_copy = files(runners).joinpath("bolts")
    dest = tmpdir.join("bolts")
    shutil.copytree(to_copy, dest)
    run_bolts(dest, fatigue=True, matlib=Path(dest, "additional_materials"))
    # check that the recap has been produced
    assert os.path.exists(Path(dest, "Recap.docx"))


def test_run_bolts_no_recap(tmpdir):
    to_copy = files(runners).joinpath("bolts")
    dest = tmpdir.join("bolts")
    shutil.copytree(to_copy, dest)
    run_bolts(dest, fatigue=True, print_recap=False)
