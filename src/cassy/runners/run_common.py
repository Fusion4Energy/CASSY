from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
import logging
import os
from collections.abc import Generator

from cassy.additional_data import materials
from cassy.auxiliary import trace
from cassy.auxiliary.types import PathLike
from cassy.general.material import Material, read_materials
from cassy.office.trace_report import write_html

MATERIALS_PATH = files(materials)
TRACE_FOLDER = "trace"


def new_tracer(enabled: bool, module: str) -> trace.Tracer | None:
    """Return a tracer for the run if requested, None otherwise."""
    if not enabled:
        return None
    try:
        cassy_version = version("cassy-f4e")
    except PackageNotFoundError:
        cassy_version = "unknown"
    return trace.Tracer({"module": module, "cassy version": cassy_version})


def events_table(columns: list[str], rows) -> dict:
    """Table of reference events for the trace index page.

    The events are shared by many items, so identical rows are kept once.
    """
    unique = dict.fromkeys(
        tuple("–" if v is None or v == "" else str(v) for v in row) for row in rows
    )
    return {"columns": list(columns), "rows": [list(r) for r in unique]}


@contextmanager
def tracing(tracer: trace.Tracer | None) -> Generator[None, None, None]:
    """Activate the tracer (if any) for the duration of the context."""
    if tracer is None:
        yield
        return
    with trace.activate(tracer), trace.scope(module=tracer.metadata["module"]):
        yield


def save_trace(
    tracer: trace.Tracer | None,
    assessment_folder: PathLike,
    geometry: dict | None = None,
    stl_cache: PathLike | None = None,
) -> None:
    """Save the trace table and its HTML report in the assessment folder.

    ``geometry`` ({component: (locations csv, geometry file)}) adds the 3D location
    map to the report of those components, ``stl_cache`` is the folder where their
    simplified geometries are cached.
    """
    if tracer is None:
        if geometry:
            logging.warning(
                "Locations and geometry files are only used in the HTML report of "
                "the trace: enable the trace to get the 3D location map."
            )
        return
    folder = os.path.join(assessment_folder, TRACE_FOLDER)
    tracer.save(folder)
    write_html(tracer.to_dataframe(), folder, tracer.metadata, geometry, stl_cache)
    logging.info("Trace of intermediate results saved in %s", folder)


def build_material_library(
    custom_path: PathLike | None = None,
) -> dict[str, Material]:
    """Build the material lib using default and custom

    Parameters
    ----------
    custom_path : PathLike | None, optional
        additional materials path, by default None

    Returns
    -------
    dict[str, Material]
        material library
    """
    materials = read_materials(MATERIALS_PATH)
    # by default also adds custom materials in the default additional folde
    default_additional = os.path.join(os.getcwd(), "additional_materials")
    if os.path.exists(default_additional):
        additional_materials = read_materials(default_additional)
        materials.update(additional_materials)
    if custom_path is not None:
        additional_materials = read_materials(custom_path)
        materials.update(additional_materials)
    return materials
