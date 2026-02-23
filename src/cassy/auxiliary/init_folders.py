from pathlib import Path
from cassy.additional_data import templates
from cassy.additional_data.templates import bolts
from cassy.auxiliary.types import PathLike
import shutil
from importlib.resources import files, as_file


def init_paths_assessment(root: PathLike) -> None:
    """Initialize an assessment structure for linearizes stress paths.

    Parameters
    ----------
    root : PathLike
        root path where the folders will be created.
    """
    # create folders if not exist
    root = Path(root)
    if not root.exists():
        root.mkdir()
    for folders in ["config", "stresses", "additional_materials"]:
        path = root / folders
        if not path.exists():
            path.mkdir()

    # copy the default config file into the config folder
    default_config = files(templates) / "path_config_template.xlsx"
    with as_file(default_config) as config_file:
        shutil.copy(config_file, root / "config" / "model_example.xlsx")


def init_bolts_assessment(root: PathLike) -> None:
    """Initialize an assessment structure for bolts.

    Parameters
    ----------
    root : PathLike
        root path where the folders will be created.
    """
    # create folders if not exist
    root = Path(root)
    if not root.exists():
        root.mkdir()
    for folders in ["config", "actions", "additional_materials", "geometries"]:
        path = root / folders
        if not path.exists():
            path.mkdir()

    # copy the default files
    src_files = ["M12_insert.xlsx", "M12_bolt.xlsx", "Flange1.xlsx"]
    destinations = ["geometries", "geometries", "config"]

    for file, dest in zip(src_files, destinations):
        default_file = files(bolts) / file
        with as_file(default_file) as source_file:
            shutil.copy(source_file, root / dest / file)
