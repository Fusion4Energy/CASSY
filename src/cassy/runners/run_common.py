from importlib.resources import files
import os

from cassy.additional_data import materials
from cassy.auxiliary.types import PathLike
from cassy.general.material import Material, read_materials

MATERIALS_PATH = files(materials)


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
