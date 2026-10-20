"""Geometry data of the 3D location map of the HTML trace report.

The locations of paths and bolts are read from a visualization-only csv and, together
with an optional mesh of the component, are embedded in the report so that the
selected item can be shown on the model. They are not used by the assessment.
"""

from __future__ import annotations

import base64
import logging
import os

import numpy as np
import pandas as pd

from cassy.auxiliary.types import PathLike

logger = logging.getLogger(__name__)

# one row per item, the first column tells the submodel/flange so that one file can
# hold all of them. Paths are segments from point i to point j, bolts points.
PATH_COLUMNS = ("component", "path_number", "xi", "yi", "zi", "xj", "yj", "zj")
BOLT_COLUMNS = ("flange", "boltID", "x", "y", "z")
AXIS_COLUMNS = ("nx", "ny", "nz")
# the mesh is decimated above this number of triangles to keep the report light
MAX_TRIANGLES = 50_000


def _item_name(item, module: str) -> str:
    """Name of the item in the trace (see Submodel.assess and FlangeAssessment)."""
    if isinstance(item, float) and item.is_integer():
        item = int(item)
    item = str(item).strip()
    if module == "paths":
        return f"Path {item}"
    return item


def _numeric(df: pd.DataFrame, columns: tuple, file: PathLike) -> pd.DataFrame:
    values = df[list(columns)].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any():
        raise ValueError(f"Locations CSV has non numeric coordinates: '{file}'")
    return values


def read_locations(
    file: PathLike, module: str, component: str | None = None
) -> dict[str, dict]:
    """Read the locations of the items of a component.

    Parameters
    ----------
    file : PathLike
        csv of the locations, any other column is ignored. Paths: component,
        path_number, xi, yi, zi, xj, yj, zj (one segment per path). Bolts: flange,
        boltID, x, y, z and optionally the axis nx, ny, nz. The file can hold several
        submodels/flanges.
    module : str
        'paths' or 'bolts'.
    component : str | None, optional
        submodel/flange whose items are read, by default all the rows.

    Returns
    -------
    dict[str, dict]
        {item name in the trace: {"p": [[x, y, z], ...], "axis": [nx, ny, nz] or None}}
    """
    df = pd.read_csv(file)
    df.columns = [str(c).strip() for c in df.columns]
    paths = module == "paths"
    columns = PATH_COLUMNS if paths else BOLT_COLUMNS
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Locations CSV is missing columns {missing}: '{file}'")
    if component is not None:
        owner = df[columns[0]].astype(str).str.strip()
        df = df[owner == str(component).strip()]
    names = [_item_name(i, module) for i in df[columns[1]]]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise ValueError(f"Repeated items {repeated} in the locations CSV: '{file}'")

    if paths:
        i = _numeric(df, PATH_COLUMNS[2:5], file).to_numpy(dtype=float)
        j = _numeric(df, PATH_COLUMNS[5:], file).to_numpy(dtype=float)
        return {
            n: {"p": [a.tolist(), b.tolist()], "axis": None}
            for n, a, b in zip(names, i, j)
        }
    points = _numeric(df, BOLT_COLUMNS[2:], file).to_numpy(dtype=float)
    axes = [None] * len(df)
    if all(c in df.columns for c in AXIS_COLUMNS):
        values = df[list(AXIS_COLUMNS)].apply(pd.to_numeric, errors="coerce")
        axes = [
            v.tolist() if np.isfinite(v).all() and np.linalg.norm(v) > 0 else None
            for v in values.to_numpy(dtype=float)
        ]
    return {n: {"p": [p.tolist()], "axis": a} for n, p, a in zip(names, points, axes)}


def _b64(array: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode("ascii")


def mesh_payload(file: PathLike) -> dict:
    """Surface triangles of a mesh (any format read by pyvista, e.g. STL), decimated
    above MAX_TRIANGLES.

    Returns
    -------
    dict
        {"vertices": base64 float32 xyz, "faces": base64 uint32 triangles}
    """
    import pyvista as pv

    if not os.path.exists(file):
        raise FileNotFoundError(f"Geometry file not found: '{file}'")
    mesh = pv.read(file)
    if isinstance(mesh, pv.MultiBlock):
        mesh = mesh.combine()
    if not isinstance(mesh, pv.PolyData):
        mesh = mesh.extract_surface()
    mesh = mesh.triangulate().clean()
    if mesh.n_cells > MAX_TRIANGLES:
        mesh = mesh.decimate(1 - MAX_TRIANGLES / mesh.n_cells)
    return {
        "vertices": _b64(np.asarray(mesh.points, dtype=np.float32)),
        "faces": _b64(np.asarray(mesh.regular_faces, dtype=np.uint32)),
    }


def geometry_payload(
    locations_file: PathLike | None,
    geometry_file: PathLike | None,
    module: str,
    items: list[str] | None = None,
    component: str = "",
) -> dict | None:
    """Data of the location map of a component, None if no locations are given.

    ``items`` are the items of the trace: the ones without a location are reported.
    """
    if not locations_file:
        return None
    locations = read_locations(locations_file, module, component or None)
    if not locations:
        logger.warning("%s: no locations in '%s'", component, locations_file)
    if items is not None:
        missing = [i for i in items if i not in locations]
        unknown = [i for i in locations if i not in set(items)]
        if missing:
            logger.warning(
                "%s: no location for %d items (not shown in the 3D view): %s",
                component,
                len(missing),
                ", ".join(missing[:10]) + (" ..." if len(missing) > 10 else ""),
            )
        if unknown:
            logger.warning(
                "%s: locations of items not in the assessment ignored: %s",
                component,
                ", ".join(unknown[:10]) + (" ..." if len(unknown) > 10 else ""),
            )
            locations = {k: v for k, v in locations.items() if k not in unknown}
    payload = {"items": locations}
    if geometry_file:
        payload["mesh"] = mesh_payload(geometry_file)
    return payload
