"""Geometry data of the 3D location map of the HTML trace report.

The locations of paths and bolts are read from a visualization-only csv and, together
with an optional mesh of the component, are embedded in the report so that the
selected item can be shown on the model. They are not used by the assessment.

Reading and simplifying a large mesh can take a while, so the simplified meshes are
cached on disk (see :func:`cache_folder`) and reused as long as the mesh file is not
changed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sys
import time
import zipfile
from collections.abc import Iterable

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
# bump to invalidate the meshes cached by older versions
CACHE_VERSION = 1
CACHE_ENV = "CASSY_CACHE_DIR"


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


def cache_folder() -> str:
    """Folder of the simplified meshes: $CASSY_CACHE_DIR if set, otherwise the user
    cache folder (%LOCALAPPDATA%\\cassy\\geometry on windows, ~/.cache/cassy/geometry
    elsewhere)."""
    folder = os.environ.get(CACHE_ENV)
    if folder:
        return folder
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "cassy", "geometry")


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _cache_file(file: PathLike) -> str:
    """Cache entry of a mesh file: named after its path and its size and
    modification time, so that a changed file is processed again."""
    path = os.path.normcase(os.path.abspath(file))
    stat = os.stat(file)
    version = f"{stat.st_size}:{stat.st_mtime_ns}:{MAX_TRIANGLES}:{CACHE_VERSION}"
    return os.path.join(cache_folder(), f"{_digest(path)}_{_digest(version)}.npz")


def is_cached(file: PathLike) -> bool:
    """True if the simplified mesh of ``file`` is in the cache and up to date."""
    return os.path.exists(file) and os.path.exists(_cache_file(file))


def _process_mesh(file: PathLike) -> tuple[np.ndarray, np.ndarray]:
    import pyvista as pv

    name = os.path.basename(file)
    start = time.perf_counter()
    logger.info("Reading the geometry '%s'", name)
    mesh = pv.read(file)
    if isinstance(mesh, pv.MultiBlock):
        mesh = mesh.combine()
    if not isinstance(mesh, pv.PolyData):
        mesh = mesh.extract_surface()
    mesh = mesh.triangulate().clean()
    if mesh.n_cells > MAX_TRIANGLES:
        logger.info(
            "Simplifying the geometry '%s' from %d to about %d triangles for the 3D "
            "view, this may take a while",
            name,
            mesh.n_cells,
            MAX_TRIANGLES,
        )
        mesh = mesh.decimate(1 - MAX_TRIANGLES / mesh.n_cells)
    logger.info(
        "Geometry '%s' processed in %.1f s (%d triangles)",
        name,
        time.perf_counter() - start,
        mesh.n_cells,
    )
    vertices = np.asarray(mesh.points, dtype=np.float32)
    faces = np.asarray(mesh.regular_faces, dtype=np.uint32)
    return vertices, faces


def _save_cache(cache: str, vertices: np.ndarray, faces: np.ndarray) -> None:
    folder, name = os.path.split(cache)
    try:
        os.makedirs(folder, exist_ok=True)
        tmp = f"{cache}.{os.getpid()}.tmp.npz"
        np.savez_compressed(tmp, vertices=vertices, faces=faces)
        os.replace(tmp, cache)
    except OSError as e:
        logger.warning("Cannot cache the simplified geometry in '%s': %s", folder, e)
        return
    # older entries of the same file (it has been changed since)
    prefix = name.split("_")[0] + "_"
    for old in os.listdir(folder):
        if old.startswith(prefix) and old != name and old.endswith(".npz"):
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass


def load_mesh(file: PathLike) -> tuple[np.ndarray, np.ndarray]:
    """Surface triangles of a mesh (any format read by pyvista, e.g. STL), decimated
    above MAX_TRIANGLES. The result is cached (see :func:`cache_folder`).

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        float32 vertices (n, 3) and uint32 triangles (m, 3).
    """
    if not os.path.exists(file):
        raise FileNotFoundError(f"Geometry file not found: '{file}'")
    cache = _cache_file(file)
    if os.path.exists(cache):
        try:
            with np.load(cache) as data:
                vertices, faces = data["vertices"], data["faces"]
            logger.info("Using the pre-processed geometry '%s'", os.path.basename(file))
            return vertices, faces
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
            # corrupted entry: processed again
            logger.warning("Cannot read the cached geometry '%s': %s", cache, e)
    vertices, faces = _process_mesh(file)
    _save_cache(cache, vertices, faces)
    return vertices, faces


def mesh_payload(file: PathLike) -> dict:
    """Surface triangles of a mesh for the browser (see :func:`load_mesh`).

    Returns
    -------
    dict
        {"vertices": base64 float32 xyz, "faces": base64 uint32 triangles}
    """
    vertices, faces = load_mesh(file)
    return {"vertices": _b64(vertices), "faces": _b64(faces)}


def mesh_script(file: PathLike, folder: PathLike) -> str:
    """Write the mesh of ``file`` as a script in ``folder`` (if not there yet), for
    the pages showing it as context: it registers the mesh in
    window.CASSY_MESHES[key]. Shared by the pages, so that each mesh is written once.

    Returns
    -------
    str
        key of the mesh, the script is ``<key>.js``.
    """
    key = _digest(os.path.normcase(os.path.abspath(file)))
    target = os.path.join(folder, f"{key}.js")
    if not os.path.exists(target):
        os.makedirs(folder, exist_ok=True)
        data = json.dumps(mesh_payload(file), separators=(",", ":"))
        with open(target, "w", encoding="utf-8") as f:
            f.write(
                f"(window.CASSY_MESHES = window.CASSY_MESHES || {{}})"
                f"[{json.dumps(key)}] = {data};\n"
            )
    return key


def preprocess_geometries(files: Iterable[PathLike]) -> int:
    """Simplify and cache the meshes, so that the trace reports are written without
    processing them again. Already cached meshes are skipped.

    Returns
    -------
    int
        number of meshes processed (not already in the cache).
    """
    unique = list(dict.fromkeys(os.path.abspath(f) for f in files if f))
    processed = 0
    for i, file in enumerate(unique, start=1):
        logger.info("Geometry %d of %d: %s", i, len(unique), file)
        if is_cached(file):
            logger.info("Already pre-processed, skipped")
            continue
        load_mesh(file)
        processed += 1
    logger.info(
        "%d geometries pre-processed, %d already up to date in %s",
        processed,
        len(unique) - processed,
        cache_folder(),
    )
    return processed


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
