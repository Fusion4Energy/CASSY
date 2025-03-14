import shutil
from importlib.resources import files

import pytest

from cassy.auxiliary.functions import is_excel_installed
from cassy.runners.run_bolts import run_bolts
from tests import runners


@pytest.mark.skipif(
    not is_excel_installed(), reason="Excel is not installed on this system."
)
def test_run_bolts(tmpdir):
    to_copy = files(runners).joinpath("bolts")
    dest = tmpdir.join("bolts")
    shutil.copytree(to_copy, dest)
    run_bolts(dest)
