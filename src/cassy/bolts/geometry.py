import math
import os
from abc import ABC
from dataclasses import dataclass

import pandas as pd

from cassy.auxiliary.types import PathLike
from cassy.general.material import Material


@dataclass
class BoltLikeGeom(ABC):
    """
    stores data related to a bolt-like geometry. All units are in mm.

    Parameters
    ----------
    name : str
        identifier for the point of application.
    material : material.Material
        material of the bolt
    p : float
        thread pitch.
    d : float
        maximum nominal diameter.
    dn : float
        core diameter (minor).
    d1 : float
        diameter of smooth shank.
    df : float
        pitch diameter (mean).
    D : float
        minor diameter of tapping.
    Dp : float
        diameter of drilling circle.
    Dm : float
        mean diameter under head
    Le : float
        insertion length.
    d_vh : float
        diameter of the venting hole.
    f : float, optional
        friction coefficient between engaged threads.
    f_prime : float, optional
        friction coefficient under head.
    """

    name: str
    material: Material

    p: float
    d: float
    dn: float
    d1: float
    df: float
    D: float
    Dp: float
    Dm: float
    Le: float
    f: float
    f_prime: float
    d_vh: float

    def __post_init__(self):
        # --- Additional geometrical feature ---
        # length for shear calculation
        self.Le_shear = min(0.8 * self.d, self.Le)
        # Minimum cross-sectional area at the root of thread
        self.An = self.dn**2 * math.pi / 4 - self.d_vh**2 * math.pi / 4
        # Section Module
        self.Z = (self.dn**4 - self.d_vh**4) * math.pi / 32 / self.dn

    @classmethod
    def from_excel(
        cls, excel_data: PathLike, material_list: dict[str, Material]
    ) -> "BoltLikeGeom":
        """
        Create a BoltLikeGeom instance from an Excel file.

        Parameters
        ----------
        excel_data : PathLike
            path to the excel data containing the geometrical data.

        Returns
        -------
        BoltLikeGeom
            An instance of BoltLikeGeom with the provided data.
        """
        df = pd.read_excel(excel_data, skiprows=1)
        df.set_index("SYMBOL", inplace=True)
        geom_data = df["VALUE"].to_dict()
        geom_data["material"] = material_list[geom_data["material"]]
        geom_data["name"] = os.path.basename(excel_data).split(".")[0]
        return cls(**geom_data)


@dataclass
class InsertGeom(BoltLikeGeom):
    """
    stores data related to an insert. All units are in mm.

    Parameters
    ----------
    name : str
        identifier for the point of application.
    material : material.Material
        material of the bolt
    p : float
        thread pitch.
    d : float
        maximum nominal diameter.
    dn : float
        core diameter (minor).
    d1 : float
        diameter of smooth shank.
    df : float
        pitch diameter (mean).
    D : float
        minor diameter of tapping.
    Dp : float
        diameter of drilling circle.
    Dm : float
        mean diameter under head
    Le : float
        insertion length.
    f : float, optional
        friction coefficient between engaged threads.
    f_prime : float, optional
        friction coefficient under head.
    """

    # no additional data needed for an insert
    pass


@dataclass
class BoltGeom(BoltLikeGeom):
    """
    stores data related to an insert. All units are in mm.

    Parameters
    ----------
    name : str
        identifier for the point of application.
    material : material.Material
        material of the bolt
    p : float
        thread pitch.
    d : float
        maximum nominal diameter.
    dn : float
        core diameter (minor).
    d1 : float
        diameter of smooth shank.
    df : float
        pitch diameter (mean).
    D : float
        minor diameter of tapping.
    Dp : float
        diameter of drilling circle.
    Dm : float
        mean diameter under head
    Le : float
        insertion length.
    H : float
        height of head.
    a : float
        diameter of head.
    B : float
        inside diameter of washer.
    C : float
        washer thickness
    KF : float, optional
        fatigue stress reduction factor (IC 2753) for the application
        of the Neuber's rule. The default value is 4.
    f : float, optional
        friction coefficient between engaged threads.
    f_prime : float, optional
        friction coefficient under head.
    """

    H: float
    a: float
    B: float
    C: float
    KF: float = 4


def read_geometries(
    files: PathLike, materials: dict[str, Material]
) -> dict[str, BoltLikeGeom]:
    """
    Read geometries from the specified folder.

    Parameters
    ----------
    files : PathLike
        Path to the folder containing geometry files.
    materials : dict[str, Material]
        A dictionary mapping material names to Material instances.

    Returns
    -------
    dict[str, BoltLikeGeom]
        A dictionary mapping geometry names to BoltLikeGeom instances.
    """
    geometries = {}
    for file in os.listdir(files):
        if file.endswith(".xlsx"):
            if "bolt" in file:
                geomOb = BoltGeom
            elif "insert" in file:
                geomOb = InsertGeom
            else:
                raise ValueError(f"Unknown geometry type in file: {file}")

            geom = geomOb.from_excel(os.path.join(files, file), materials)
            geometries[geom.name] = geom
    return geometries
