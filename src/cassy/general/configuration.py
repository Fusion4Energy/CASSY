# -*- coding: utf-8 -*-
"""
Created on Thu Nov 26 15:15:07 2020

@author: Davide Laghi
"""

from __future__ import annotations

import os

import pandas as pd

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

    def __init__(self, submodel, file):
        """
        Initialize MatList

        materials: (list)(Material) materials of the list
        """
        self.submodel = submodel

        sheets = {}
        for sheet in self._config_sheets:
            df = pd.read_excel(file, sheet_name=sheet)
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

    def __len__(self):
        return len(self.sheets)

    def __repr__(self):
        return str(self.sheets)

    def __getitem__(self, sheet):
        return self.sheets[sheet]

    def get_REid_path(self, pathnum, fatigue=False):
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


def parse_cfg_files(cfg_root: PathLike) -> dict[str, Configuration]:
    """Parse all configuration files in the given folder and divide them
    by submodel.

    Parameters
    ----------
    cfg_root : PathLike
        Path to the folder containing the configuration files

    Returns
    -------
    dict[str, Configuration]
        Dictionary containing the configuration objects divided by submodel
    """
    config = {}
    for conf_file in os.listdir(cfg_root):
        submodel = conf_file.split(".")[0]
        confpath = os.path.join(cfg_root, conf_file)
        config[submodel] = Configuration(submodel, confpath)
    return config
