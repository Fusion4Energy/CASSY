from __future__ import annotations

import os
from enum import Enum
import pandas as pd
import numpy as np
from cassy.auxiliary.custom_errors import TensorInputError
from cassy.auxiliary.types import PathLike
from cassy.auxiliary.custom_errors import ConfigError
from dataclasses import dataclass
import re
import logging


class Configuration:
    _config_sheets = [
        "Reference Event",
        "Stresses",
        "Load Steps",
        "Paths",
        "Reference Event Fatigue",
        "General",
    ]

    def __init__(self, submodel: str, config_file: PathLike, tensors_file: PathLike):
        """Object storing the configuration of a submodel.

        Parameters
        ----------
        submodel : str
            name of the submodel
        config_file : PathLike
            path to the configuration file
        tensors_file : PathLike
            path to the stress tensors file
        """
        self.submodel = submodel

        sheets = {}
        for sheet in self._config_sheets:
            df = pd.read_excel(config_file, sheet_name=sheet)
            if sheet in ["Reference Event", "Reference Event Fatigue"]:
                df.set_index(["Path N", "ID"], inplace=True)
            else:
                df.set_index(df.columns[0], inplace=True)
            sheets[sheet] = df

        self.sheets = sheets
        self.paths = sheets["Paths"].index
        self.loads = sheets["Load Steps"].index

        # Get the general parameters
        gp = sheets["General"]
        gp = gp[["Value"]]
        self.code = str(gp.loc["Design Code", "Value"])

        # Load the stress tensors
        self.stress_tensors = (
            pd.read_csv(tensors_file)
            .set_index(["path", "analysis", "loadstep", "pathpoint", "stress_type"])
            .sort_index()
        )

        # Perform some consistency checks on the tensors file
        to_check = self.stress_tensors.reset_index()
        assert set(to_check["pathpoint"].unique().tolist()) == {"begin", "end"}
        assert set(to_check["stress_type"].unique().tolist()) == {"Pm", "Pb", "F"}
        for col in ["Sx", "Sy", "Sz", "Sxy", "Sxz", "Syz"]:
            assert to_check[col].dtype in [np.float64, np.int64], (
                f"Column {col} must be numeric"
            )

    def get_stress_tensor(
        self, load: str, pathnum: int, pathpoint: str
    ) -> pd.DataFrame:
        """Locate the correct stress tensor for a specified load

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
            Stress tensor for the specified load step, path number and pathpoint
        """
        if pathpoint not in ["begin", "end"]:
            raise ValueError(
                "Pathpoint must be either 'begin' or 'end'. "
                + f"Got {pathpoint} instead."
            )
        # Get the analysis and loadstep
        analysis = self.sheets["Load Steps"].loc[load]["Analysis Name"]
        timestep = self.sheets["Load Steps"].loc[load]["Time Step"]

        # timestep could be an int or a linear combination
        if isinstance(timestep, str):
            if len(timestep) == 1:
                tensor = self.stress_tensors.loc[
                    (pathnum, analysis, int(timestep), pathpoint), :
                ]
            else:
                timestep = parse_linear_combination(timestep)
                for i, (sign, step) in enumerate(timestep):
                    new_tensor = self.stress_tensors.loc[
                        (pathnum, analysis, step, pathpoint), :
                    ]
                    if sign == "+":
                        if i == 0:
                            tensor = new_tensor
                        else:
                            tensor = tensor + new_tensor
                    elif sign == "-":
                        if i == 0:
                            tensor = new_tensor
                        else:
                            tensor = tensor - new_tensor
        else:
            tensor = self.stress_tensors.loc[
                (pathnum, analysis, timestep, pathpoint), :
            ]

        # perform some consistency checks
        try:
            assert tensor.shape == (3, 6)
        except AssertionError:
            raise TensorInputError(
                f"Stress tensor must be a 3x6 matrix. {load} {pathnum} {pathpoint}"
            )

        return tensor

    def __len__(self):
        return len(self.sheets)

    def __repr__(self):
        return str(self.sheets)

    def __getitem__(self, sheet):
        return self.sheets[sheet]

    def get_REid_path(self, pathnum: int, fatigue: bool = False) -> list[str]:
        """
        Given the path number, returns the list of reference events ID
        associated with the path

        Parameters
        ----------
        pathnum : int
            path number.
        fatigue : bool, optional
            If true the fatigue reference events are considered.
            The default is False.

        Returns
        -------
        TYPE
            DESCRIPTION.

        """
        if fatigue:
            df = self.sheets["Reference Event Fatigue"]
        else:
            df = self.sheets["Reference Event"]

        return df.loc[(pathnum)].index

    def get_REloads(self, pathnum, ref_event_ID, fatigue=False):
        """
        Given a reference event ID returns the list of single loads to combine

        Parameters
        ----------
        pathnum : int
            number of the path
        ref_event_ID : str
            ID of the Reference event.

        fatigue : bool
            if True the fatigue REs table is considered

        Returns
        -------
        None.

        """
        # Select correct REs table
        if fatigue:
            df = self.sheets["Reference Event Fatigue"]
        else:
            df = self.sheets["Reference Event"]

        try:
            # If for some reason it is a pd.Series
            loads = df.loc[(pathnum, ref_event_ID), "Loads"].iloc[0]
        except IndexError:
            raise ValueError(
                "Unable to find the RE: "
                + str(ref_event_ID)
                + " in path number "
                + str(pathnum)
            )
        except AttributeError:
            # The string was correctly obtained and no iloc was needed
            loads = df.loc[(pathnum, ref_event_ID), "Loads"]
        loadlist = []
        for load in loads.split(","):
            loadlist.append(load.strip())  # No more than one space is allowed

        return loadlist


# TODO move common configuration features to parent class
class AssessmentConfiguration:
    def __init__(self) -> None:
        pass


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
    def from_dict(cls, dic: dict | pd.Series) -> "LinStressConfig":
        rec = dic.get("Spatial Recombination", SpatialRecMethod.ALGEBRAIC)
        if isinstance(rec, str) and not rec == "":
            recombine = SpatialRecMethod(rec)
        elif np.isnan(rec) or rec == "" or rec is None:
            recombine = SpatialRecMethod.ALGEBRAIC
        else:
            raise ConfigError(f"Invalid spatial recombination method: {rec}")

        return cls(
            name=dic["name"],
            stress_classification=StressClassification(dic["Stress Type"]),
            load_type=LoadType(dic["Load Type"]),
            unit=dic["Unit"],
            isPD=dic.get("Derives from Plasma Disruption", False),
            isCyclic=dic["Is Cyclic"],
            scale=dic["Scale"],
            spatial_rec_method=recombine,
            ptype=PathType(dic["ptype"]),
            isPressure=dic["Is Pressure"],
            Welding_n=dic["Welding_n"],
            Welding_f=dic["Welding_f"],
            isShortOverstress=dic["Is Short Overstress"],
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


def parse_cfg_files(
    cfg_root: PathLike, tensors_files: PathLike
) -> dict[str, Configuration]:
    """Parse all configuration files in the given folder and divide them
    by submodel.

    Parameters
    ----------
    cfg_root : PathLike
        Path to the folder containing the configuration files
    tensors_file : PathLike
        Path to the folder containing the stress tensors files

    Returns
    -------
    dict[str, Configuration]
        Dictionary containing the configuration objects divided by submodel
    """
    config = {}
    for conf_file in os.listdir(cfg_root):
        if not conf_file.endswith(".xlsx") and not conf_file.startswith("~"):
            continue  # skip non excel files
        submodel = conf_file.split(".")[0]
        confpath = os.path.join(cfg_root, conf_file)
        tensors_file = os.path.join(tensors_files, submodel + ".csv")
        try:
            config[submodel] = Configuration(submodel, confpath, tensors_file)
        except ValueError as e:
            logging.error(f"Error parsing {confpath}")
            raise e

    return config


TOKENS = re.compile(r"[+-]*\d+")


def parse_linear_combination(expr: str) -> list[tuple[str, int]]:
    # Returns list of (sign, loadstep) tuples, e.g. [('+', 7), ('-', 5), ...]
    bits = TOKENS.findall(expr.replace(" ", ""))
    to_combine = []
    for bit in bits:
        if bit.startswith(("+", "-")):
            sign = bit[0]
            step = int(bit[1:])
        else:
            sign = "+"
            step = int(bit)
        to_combine.append((sign, step))
    return to_combine
