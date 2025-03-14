import shutil
from importlib.resources import files

from cassy.runners.run_paths import run_paths
from tests import runners


def test_run_paths(tmpdir):
    to_copy = files(runners).joinpath("paths")
    dest = tmpdir.join("paths")
    shutil.copytree(to_copy, dest)
    run_paths(dest)
