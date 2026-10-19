import base64
import logging

import numpy as np
import pytest
import pyvista as pv

from cassy.office import geometry_view
from cassy.office.geometry_view import geometry_payload, mesh_payload, read_locations


def _decode(payload: dict) -> tuple[np.ndarray, np.ndarray]:
    vertices = np.frombuffer(base64.b64decode(payload["vertices"]), dtype=np.float32)
    faces = np.frombuffer(base64.b64decode(payload["faces"]), dtype=np.uint32)
    return vertices.reshape(-1, 3), faces.reshape(-1, 3)


PATHS_CSV = (
    "component,path_number,xi,yi,zi,xj,yj,zj,comment\n"
    "SM1,1,0,0,0,1,0,0,a\n"
    "SM1,2,5,1,2,6,1,2,b\n"
    "SM2,1,9,9,9,9,9,8,c\n"
)


def test_read_locations_paths(tmp_path):
    file = tmp_path / "loc.csv"
    file.write_text(PATHS_CSV)
    # only the paths of the component, extra columns ignored
    locations = read_locations(file, "paths", "SM1")
    assert set(locations) == {"Path 1", "Path 2"}
    assert locations["Path 1"] == {"p": [[0, 0, 0], [1, 0, 0]], "axis": None}
    assert read_locations(file, "paths", "SM2")["Path 1"]["p"][1] == [9, 9, 8]
    assert read_locations(file, "paths", "SM3") == {}


def test_read_locations_bolts(tmp_path):
    file = tmp_path / "loc.csv"
    file.write_text(
        "flange,boltID,x,y,z,nx,ny,nz\n"
        "F1,B1,1,2,3,0,0,1\n"
        "F1,7,4,5,6,,,\n"
        "F2,B1,0,0,0,1,0,0\n"
    )
    locations = read_locations(file, "bolts", "F1")
    assert locations["B1"] == {"p": [[1, 2, 3]], "axis": [0, 0, 1]}
    # numeric bolt ids are kept as they are, no axis when it is not complete
    assert locations["7"] == {"p": [[4, 5, 6]], "axis": None}
    assert read_locations(file, "bolts", "F2") == {
        "B1": {"p": [[0, 0, 0]], "axis": [1, 0, 0]}
    }


@pytest.mark.parametrize(
    "module, content, match",
    [
        ("paths", "component,path_number,xi,yi,zi\nA,1,0,0,0\n", "missing columns"),
        (
            "paths",
            "component,path_number,xi,yi,zi,xj,yj,zj\nA,1,0,0,0,1,a,0\n",
            "non numeric",
        ),
        (
            "paths",
            "component,path_number,xi,yi,zi,xj,yj,zj\nA,1,0,0,0,1,0,0\nA,1,0,0,0,2,0,0\n",
            "Repeated",
        ),
        ("bolts", "flange,boltID,x,y\nA,1,0,0\n", "missing columns"),
        ("bolts", "flange,boltID,x,y,z\nA,1,0,a,0\n", "non numeric"),
        ("bolts", "flange,boltID,x,y,z\nA,1,0,0,0\nA,1,1,0,0\n", "Repeated"),
    ],
)
def test_read_locations_errors(tmp_path, module, content, match):
    file = tmp_path / "loc.csv"
    file.write_text(content)
    with pytest.raises(ValueError, match=match):
        read_locations(file, module, "A")


def test_mesh_payload(tmp_path):
    file = tmp_path / "cube.stl"
    pv.Cube().save(file)
    vertices, faces = _decode(mesh_payload(file))
    assert len(faces) == 12  # 6 quads split in triangles
    assert faces.max() < len(vertices)
    np.testing.assert_allclose(vertices.min(axis=0), -0.5)
    with pytest.raises(FileNotFoundError):
        mesh_payload(tmp_path / "missing.stl")


def test_mesh_payload_decimated(tmp_path, monkeypatch):
    file = tmp_path / "sphere.stl"
    pv.Sphere(theta_resolution=60, phi_resolution=60).save(file)
    monkeypatch.setattr(geometry_view, "MAX_TRIANGLES", 1000)
    _, faces = _decode(mesh_payload(file))
    assert len(faces) <= 1000


def test_geometry_payload(tmp_path, caplog):
    file = tmp_path / "loc.csv"
    file.write_text(PATHS_CSV)
    assert geometry_payload(None, None, "paths") is None
    with caplog.at_level(logging.WARNING):
        payload = geometry_payload(file, None, "paths", ["Path 1", "Path 3"], "SM1")
    # the location of an item not in the assessment is dropped
    assert set(payload["items"]) == {"Path 1"}
    assert "mesh" not in payload
    assert "SM1: no location for 1 items" in caplog.text
    assert "Path 2" in caplog.text
