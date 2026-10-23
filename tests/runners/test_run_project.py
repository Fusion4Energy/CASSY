import json
import os
import shutil
from pathlib import Path

import pytest

from cassy.__main__ import main
from cassy.runners.run_project import (
    geometry_files,
    ProjectError,
    load_project,
    location_maps,
    portable_path,
    project_module,
    run_project,
    save_project,
)

HERE = Path(__file__).parent
PATHS_PROJECT = HERE / "paths" / "project.json"
BOLTS_PROJECT = HERE / "bolts" / "Flange1.json"


def _copy_project(src: Path, dest: Path, **run_options) -> Path:
    """Copy a project folder and set its run options."""
    shutil.copytree(src.parent, dest)
    path = dest / src.name
    project = json.loads(path.read_text())
    project["run_options"].update(run_options)
    path.write_text(json.dumps(project))
    return path


def test_load_project_resolves_relative_paths():
    project = load_project(PATHS_PROJECT)
    assert project_module(project) == "paths"
    tensors = project["submodels"][0]["tensors_file"]
    assert os.path.isabs(tensors) and os.path.exists(tensors)
    # empty options stay empty
    assert project["run_options"]["root_dir"] == ""
    assert project_module(load_project(BOLTS_PROJECT)) == "bolts"


def test_load_project_keeps_windows_paths(tmp_path):
    windows = r"C:\Users\me\model.csv"
    path = _copy_project(PATHS_PROJECT, tmp_path / "p", root_dir=r"D:\out")
    project = json.loads(path.read_text())
    project["submodels"][0]["tensors_file"] = windows
    path.write_text(json.dumps(project))
    project = load_project(path)
    assert project["submodels"][0]["tensors_file"] == windows
    assert project["run_options"]["root_dir"] == r"D:\out"


def test_load_project_errors(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"loads": []}))
    with pytest.raises(ProjectError):
        load_project(bad)
    with pytest.raises(ProjectError):
        project_module({"run_options": {}, "submodels": [], "flanges": []})


def test_run_project_paths(tmp_path):
    # a project folder moved elsewhere, with the output folder relative to it
    folder = tmp_path / "project"
    path = _copy_project(
        PATHS_PROJECT, folder, root_dir="out", print_recap=False, trace=True
    )
    root = run_project(path)
    assert Path(root) == folder / "out"
    assert (folder / "out" / "assessment" / "trace" / "index.html").exists()
    assert not (folder / "out" / "Recap.docx").exists()


def test_run_project_location_map(tmp_path):
    folder = tmp_path / "project"
    path = _copy_project(
        PATHS_PROJECT, folder, root_dir="out", print_recap=False, trace=True
    )
    (folder / "locations.csv").write_text(
        "component,path_number,xi,yi,zi,xj,yj,zj\nModel_B,1,0,0,0,0,0,1\n"
    )
    project = json.loads(path.read_text())
    project["run_options"]["locations_file"] = "locations.csv"
    path.write_text(json.dumps(project))

    # relative to the project folder, as the other data files
    maps = location_maps(load_project(path))
    assert maps == {"Model_B": (str(folder / "locations.csv"), None)}
    save_project(load_project(path), path)
    saved = json.loads(path.read_text())
    assert saved["run_options"]["locations_file"] == "locations.csv"
    # no locations csv, no location map
    assert location_maps(load_project(PATHS_PROJECT)) == {}

    run_project(path)
    page = folder / "out" / "assessment" / "trace" / "Model_B.html"
    assert '"geometry":{"items":{"Path 1":' in page.read_text(encoding="utf-8")


def test_run_project_needs_root():
    with pytest.raises(ProjectError, match="output folder"):
        run_project(PATHS_PROJECT)


def test_cli_run_bolts(tmp_path):
    folder = tmp_path / "project"
    path = _copy_project(
        BOLTS_PROJECT,
        folder,
        root_dir="out",
        matlib_path="additional_materials",
        fatigue=False,
        print_recap=False,
        trace=True,
    )
    main(["--run", str(path)])
    assert (folder / "out" / "assessment" / "trace" / "Flange1.html").exists()
    assert not (folder / "out" / "Recap.docx").exists()


def test_cli_errors(tmp_path):
    with pytest.raises(SystemExit, match="output folder"):
        main(["--run", str(PATHS_PROJECT)])
    with pytest.raises(SystemExit, match="Stress tensors CSV not found"):
        path = _copy_project(PATHS_PROJECT, tmp_path / "p", root_dir="out")
        os.remove(tmp_path / "p" / "stresses" / "Model_B.csv")
        main(["--run", str(path)])


def test_portable_path(tmp_path):
    folder = tmp_path / "project"
    assert portable_path(str(folder / "data" / "a.csv"), folder) == "data/a.csv"
    assert portable_path(str(folder), folder) == "."
    outside = str(tmp_path / "shared" / "a.csv")
    assert portable_path(outside, folder) == outside
    # a sibling folder with a common prefix is outside
    sibling = str(tmp_path / "project2" / "a.csv")
    assert portable_path(sibling, folder) == sibling
    assert portable_path(r"C:\Users\me\a.csv", folder) == r"C:\Users\me\a.csv"
    assert portable_path("", folder) == ""


def test_save_project_portable_round_trip(tmp_path):
    folder = tmp_path / "project"
    path = _copy_project(PATHS_PROJECT, folder, matlib_path=str(tmp_path / "mats"))
    project = load_project(path)
    project["run_options"]["root_dir"] = str(folder / "out")
    tensors = project["submodels"][0]["tensors_file"]
    save_project(project, path)
    # the project in memory keeps absolute paths
    assert project["submodels"][0]["tensors_file"] == tensors

    saved = json.loads(path.read_text())
    assert saved["submodels"][0]["tensors_file"] == "stresses/Model_B.csv"
    assert saved["run_options"]["root_dir"] == "out"
    # outside the project folder: absolute
    assert saved["run_options"]["matlib_path"] == str(tmp_path / "mats")

    # the project folder can be moved
    moved = tmp_path / "moved"
    shutil.move(folder, moved)
    project = load_project(moved / path.name)
    assert project["submodels"][0]["tensors_file"] == str(
        moved / "stresses" / "Model_B.csv"
    )
    assert project["run_options"]["root_dir"] == str(moved / "out")


def test_geometry_files():
    project = {
        "flanges": [
            {"name": "F1", "geometry_file": "/a.stl"},
            {"name": "F2"},
            {"name": "F3", "geometry_file": "/b.stl"},
            {"name": "F4", "geometry_file": "/a.stl"},
        ],
        "run_options": {},
    }
    assert geometry_files(project) == ["/a.stl", "/b.stl"]
