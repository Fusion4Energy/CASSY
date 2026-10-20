"""Project files saved by the GUIs: loading, saving (with portable paths) and running
them without opening the GUIs."""

from __future__ import annotations

import copy
import json
import ntpath
import os
from contextlib import contextmanager

from cassy.auxiliary.types import PathLike

PATHS, BOLTS = "paths", "bolts"
# keys of the data files referenced by the project, per section
LOCATIONS_KEY, GEOMETRY_KEY = "locations_file", "geometry_file"
_FILE_KEYS = {
    "submodels": ("tensors_file", GEOMETRY_KEY),
    "flanges": ("actions_file", GEOMETRY_KEY),
}


class ProjectError(ValueError):
    """The project file cannot be run."""


def project_module(project: dict) -> str:
    """Return the module of the project: 'paths' (submodels) or 'bolts' (flanges)."""
    if "submodels" in project and "flanges" not in project:
        return PATHS
    if "flanges" in project and "submodels" not in project:
        return BOLTS
    raise ProjectError(
        "Cannot tell if this is a paths or a bolts project: it must contain either "
        "'submodels' or 'flanges'."
    )


def _path_fields(project: dict):
    """Yield (container, key) of every file or folder path stored in a project."""
    for section, keys in _FILE_KEYS.items():
        for entry in project.get(section, []):
            for key in keys:
                yield entry, key
    for key in ("matlib_path", "root_dir", LOCATIONS_KEY):
        yield project.get("run_options", {}), key


def _is_absolute(value: str) -> bool:
    # windows absolute paths (C:\\...) are recognised on any platform
    return os.path.isabs(value) or ntpath.isabs(value)


def resolve_project_paths(project: dict, folder: PathLike) -> dict:
    """Make absolute, in place, the paths of a project relative to ``folder`` (the
    folder of the project file)."""
    for entry, key in _path_fields(project):
        value = entry.get(key)
        if value and not _is_absolute(value):
            entry[key] = os.path.normpath(os.path.join(folder, value))
    return project


def portable_path(value: str, folder: PathLike) -> str:
    """Path to store in a project file located in ``folder``.

    Paths inside ``folder`` (or its subfolders) become relative, with '/' separators
    so that they work on any platform, so that the project folder can be moved or
    shared. Paths outside it (e.g. a shared network drive) stay absolute.
    """
    if not value or (ntpath.isabs(value) and not os.path.isabs(value)):
        return value  # empty, or a windows path read on another platform
    path = os.path.abspath(value)
    folder = os.path.abspath(folder)
    try:
        inside = os.path.normcase(os.path.commonpath([path, folder])) == (
            os.path.normcase(folder)
        )
    except ValueError:  # different drives
        inside = False
    if not inside:
        return path
    return os.path.relpath(path, folder).replace(os.sep, "/")


def location_maps(project: dict) -> dict:
    """Visualization-only files of the submodels/flanges of a project, for the 3D
    location map of the trace report: {name: (locations csv, geometry file)}.

    The locations csv is shared by all the submodels/flanges (run option), the
    geometry is optional and given for each of them. Empty without locations csv.
    """
    locations = project.get("run_options", {}).get(LOCATIONS_KEY)
    if not locations:
        return {}
    return {
        entry["name"]: (locations, entry.get(GEOMETRY_KEY) or None)
        for section in _FILE_KEYS
        for entry in project.get(section, [])
    }


@contextmanager
def _config_errors():
    """Report the invalid entries found while building the configurations as
    ProjectError, to tell them apart from the errors of the assessment itself."""
    try:
        yield
    except ValueError as e:
        raise ProjectError(str(e)) from e


def load_project(path: PathLike) -> dict:
    """Load a project file saved by the GUIs.

    Projects saved by older versions of the GUIs are upgraded, and the relative paths
    (data files, material library, output folder) are resolved against the folder of
    the project file, so that a project folder can be moved or shared.

    Parameters
    ----------
    path : PathLike
        project .json file.

    Returns
    -------
    dict
        project, as handled by the GUIs (with absolute paths).
    """
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as f:
        project = json.load(f)
    if not isinstance(project, dict) or "run_options" not in project:
        raise ProjectError(f"{path} is not a CASSY project file (no 'run_options').")

    if project_module(project) == PATHS:
        from cassy.gui.paths_model import migrate_project
    else:
        from cassy.gui.bolts_model import migrate_project
    migrate_project(project)
    return resolve_project_paths(project, os.path.dirname(path))


def save_project(project: dict, path: PathLike) -> None:
    """Save a project file, storing the paths inside the project folder as relative
    (see :func:`portable_path`). ``project`` itself is not modified.

    Parameters
    ----------
    project : dict
        project, as handled by the GUIs.
    path : PathLike
        project .json file.
    """
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    data = copy.deepcopy(project)
    for entry, key in _path_fields(data):
        if entry.get(key):
            entry[key] = portable_path(entry[key], folder)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def run_project(path: PathLike) -> str:
    """Run the assessment defined in a project file saved by the GUIs, with the run
    options saved in it.

    Parameters
    ----------
    path : PathLike
        project .json file.

    Returns
    -------
    str
        output folder of the assessment.
    """
    project = load_project(path)
    opts = project["run_options"]
    root_dir = opts.get("root_dir")
    if not root_dir:
        raise ProjectError("No output folder: set it in the project (root_dir).")
    os.makedirs(root_dir, exist_ok=True)

    if project_module(project) == PATHS:
        from cassy.gui.paths_model import build_configs_from_project
        from cassy.runners.run_paths import run_paths

        if not project.get("submodels"):
            raise ProjectError("The project has no submodels.")
        with _config_errors():
            configs = build_configs_from_project(project)
        run_paths(
            root_dir,
            configs,
            fatigue=opts.get("fatigue", False),
            matlib=opts.get("matlib_path") or None,
            print_recap=opts.get("print_recap", True),
            merge=opts.get("merge", True),
            trace=opts.get("trace", False),
            geometry=location_maps(project),
        )
    else:
        from cassy.gui.bolts_model import build_bolts_from_project
        from cassy.runners.run_bolts import run_bolts

        if not project.get("flanges"):
            raise ProjectError("The project has no flanges.")
        with _config_errors():
            configs, geoms = build_bolts_from_project(project)
        run_bolts(
            root_dir,
            configs,
            geoms,
            fatigue=opts.get("fatigue", False),
            print_recap=opts.get("print_recap", True),
            merge=opts.get("merge", True),
            only_bolts=opts.get("only_bolts", False),
            trace=opts.get("trace", False),
            geometry=location_maps(project),
        )
    return root_dir
