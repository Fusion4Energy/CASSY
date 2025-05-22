import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from cassy.auxiliary.functions import is_excel_installed
from cassy.runners.run_paths import run_paths
from tests import runners


@pytest.mark.skipif(
    not is_excel_installed(), reason="Excel is not installed on this system."
)
def test_run_paths(tmpdir):
    to_copy = files(runners).joinpath("paths")
    dest = tmpdir.join("paths")
    shutil.copytree(to_copy, dest)
    run_paths(dest, fatigue=True)
