import shutil
from importlib.resources import files

from cassy.runners.run_bolts import run_bolts
from tests import runners


def test_run_bolts(tmpdir):
    to_copy = files(runners).joinpath("bolts")
    dest = tmpdir.join("bolts")
    shutil.copytree(to_copy, dest)
    run_bolts(dest)
