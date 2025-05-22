# -*- coding: utf-8 -*-
"""
Created on Thu Nov 26 15:15:07 2020

@author: Davide Laghi
"""

from __future__ import annotations

import os

import pandas as pd

from cassy.auxiliary.custom_errors import TensorInputError
from cassy.auxiliary.types import PathLike


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
        tensor = self.stress_tensors.loc[pathnum, analysis, timestep, pathpoint]

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
        submodel = conf_file.split(".")[0]
        confpath = os.path.join(cfg_root, conf_file)
        tensors_file = os.path.join(tensors_files, submodel + ".csv")
        config[submodel] = Configuration(submodel, confpath, tensors_file)
    return config
