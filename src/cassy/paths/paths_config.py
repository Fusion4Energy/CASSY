from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from cassy.auxiliary.custom_errors import ConfigError, TensorInputError
from cassy.auxiliary.types import LoadTerm, PathLike


STRESS_ORDER = ["Sx", "Sy", "Sz", "Sxy", "Sxz", "Syz"]


class StressClassification(Enum):
    PRIMARY = "P"
    SECONDARY = "Q"


class LoadType(Enum):
    VOLUMETRIC = "Volumetric"
    INERTIAL = "Inertial"


class PathType(Enum):
    NORMAL = "normal"
    FILLET = "fillet"


class SpatialRecMethod(Enum):
    SRSS = "srss"
    ALGEBRAIC = "algebraic"
    ABS = "abs"


@dataclass
class LinStressConfig:
    """Stores the configuration of the single load

    name : str
        identifier of the stress. The default is None
    unit : str, optional
        Either 'MPa', 'KPa' or 'Pa'. The default is 'Pa'.
    stress_classification : StressClassification
        Stress classification of the single load (i.e., primary or secondary).
    load_type : LoadType
        Either volumetric or inertial
    isPD : bool
        if True the stress is a Plasma disruption induced stress.
    isCyclic : bool
        if True the stress should be considered cyclic
    scale : float
        scale factor for the stresses
    spatial_rec_method : SpatialRecMethod
        method to use for spatial recombination.
    ptype : PathType
        type of the path where the linstress is computed.
    isPressure : bool
        if True is a sustained loads. This causes different handling if
        the stress is evaluated in a "fillet" path.
    Welding_n : float
        Welded Joint coefficient of the path where the linstress is
        computed.
    Welding_f : float
        Fatigue Strength Reduction Factor f where the linstress is
        computed.
    isOccasional : bool
        if True is an Occasional load according to ASME B31.3.
    """

    name: str
    stress_classification: StressClassification
    load_type: LoadType
    unit: str = "Pa"
    isPD: bool = False
    isCyclic: bool = False
    scale: float = 1
    spatial_rec_method: SpatialRecMethod = SpatialRecMethod.ALGEBRAIC
    ptype: PathType = PathType.NORMAL
    isPressure: bool = False
    Welding_n: float = 1
    Welding_f: float = 1
    isShortOverstress: bool = False

    def __post_init__(self):
        if (
            self.stress_classification == StressClassification.SECONDARY
            and self.load_type == LoadType.INERTIAL
        ):
            raise ValueError("Inertial loads cannot be secondary")

    @classmethod
    def from_load(cls, load: LoadConfig, path: PathConfig) -> "LinStressConfig":
        return cls(
            name=load.name,
            stress_classification=load.stress_classification,
            load_type=load.load_type,
            unit=load.unit,
            isPD=load.isPD,
            isCyclic=load.isCyclic,
            scale=load.scale,
            spatial_rec_method=load.spatial_rec_method,
            ptype=path.ptype,
            isPressure=load.isPressure,
            Welding_n=path.welding_n,
            Welding_f=path.welding_f,
            isShortOverstress=load.isShortOverstress,
        )


@dataclass
class ReferenceEventConfig:
    service_lvl: str
    re_ID: str
    T: float  # °C
    dpa: float = 0
    oc: str = "N/A"
    ie: str = "N/A"
    ce: str = "N/A"
    load_ctg: str = "N/A"
    ncycles: int | None = None
    welding_n: float = 1
    welding_f: float = 1
    loads: list[str] = field(default_factory=list)


@dataclass
class LoadConfig:
    """Single load of a submodel and the FEM results it is built from."""

    name: str
    steps: list[LoadTerm]
    stress_classification: StressClassification
    load_type: LoadType
    unit: str = "Pa"
    scale: float = 1
    spatial_rec_method: SpatialRecMethod = SpatialRecMethod.ALGEBRAIC
    isPD: bool = False
    isCyclic: bool = False
    isPressure: bool = False
    isShortOverstress: bool = False


@dataclass
class PathConfig:
    pnum: int
    material: str
    ptype: PathType = PathType.NORMAL
    welding_n: float = 1
    welding_f: float = 1


@dataclass
class Configuration:
    """Configuration of a submodel.

    Parameters
    ----------
    submodel : str
        name of the submodel.
    code : str
        key of the design code in ``PATH_CODES``.
    loads : dict[str, LoadConfig]
        single loads keyed by name.
    paths : dict[int, PathConfig]
        paths keyed by path number.
    stress_tensors : pd.DataFrame
        linearized stress tensors, see :func:`read_stress_tensors`.
    reference_events : dict[int, list[ReferenceEventConfig]]
        reference events to assess on each path.
    fatigue_reference_events : dict[int, list[ReferenceEventConfig]]
        fatigue reference events to assess on each path.
    """

    submodel: str
    code: str
    loads: dict[str, LoadConfig]
    paths: dict[int, PathConfig]
    stress_tensors: pd.DataFrame
    reference_events: dict[int, list[ReferenceEventConfig]] = field(
        default_factory=dict
    )
    fatigue_reference_events: dict[int, list[ReferenceEventConfig]] = field(
        default_factory=dict
    )

    def get_reference_events(
        self, pathnum: int, fatigue: bool = False
    ) -> list[ReferenceEventConfig]:
        source = self.fatigue_reference_events if fatigue else self.reference_events
        return [copy.copy(re) for re in source.get(pathnum, [])]

    def get_stress_tensor(
        self, load: str, pathnum: int, pathpoint: str
    ) -> pd.DataFrame:
        """Combine the stress tensors of a load at a path point.

        Parameters
        ----------
        load : str
            Name of the load
        pathnum : int
            path number
        pathpoint : str
            Name of the pathpoint, either 'begin' or 'end'

        Returns
        -------
        pd.DataFrame
            Stress tensor for the specified load, path number and pathpoint
        """
        if pathpoint not in ["begin", "end"]:
            raise ValueError(
                "Pathpoint must be either 'begin' or 'end'. "
                + f"Got {pathpoint} instead."
            )
        terms = self.loads[load].steps
        if not terms:
            raise ConfigError(f"Load {load} has no load steps.")

        tensor = None
        for term in terms:
            try:
                part = self.stress_tensors.loc[
                    (pathnum, term.analysis, term.step, pathpoint), :
                ]
            except KeyError:
                raise TensorInputError(
                    f"No stress tensor for load {load}: path {pathnum}, "
                    f"analysis {term.analysis}, step {term.step}, {pathpoint}"
                )
            if term.sign == "-":
                part = -part
            tensor = part if tensor is None else tensor + part

        if tensor.shape != (3, 6):
            raise TensorInputError(
                f"Stress tensor must be a 3x6 matrix. {load} {pathnum} {pathpoint}"
            )
        return tensor


def read_stress_tensors(tensors_file: PathLike) -> pd.DataFrame:
    """Read and validate a linearized stress tensors CSV."""
    stress_tensors = pd.read_csv(tensors_file)
    stress_tensors["loadstep"] = stress_tensors["loadstep"].astype(int)
    stress_tensors["path"] = stress_tensors["path"].astype(int)
    stress_tensors["analysis"] = stress_tensors["analysis"].astype(str)

    if set(stress_tensors["pathpoint"].unique()) != {"begin", "end"}:
        raise TensorInputError(f"{tensors_file}: pathpoint must be begin/end")
    if set(stress_tensors["stress_type"].unique()) != {"Pm", "Pb", "F"}:
        raise TensorInputError(f"{tensors_file}: stress_type must be Pm/Pb/F")
    for col in STRESS_ORDER:
        if stress_tensors[col].dtype not in [np.float64, np.int64]:
            raise TensorInputError(f"{tensors_file}: column {col} must be numeric")

    return stress_tensors.set_index(
        ["path", "analysis", "loadstep", "pathpoint", "stress_type"]
    ).sort_index()
