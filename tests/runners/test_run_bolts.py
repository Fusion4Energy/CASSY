import shutil
from importlib.resources import files

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
    run_bolts(dest)
