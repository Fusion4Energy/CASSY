# Scripting

Sometimes, creating all the configuration using the GUI can be painful, especiallyvfor a large number of bolts. It is possible to use ``cassy`` directly as a python library and prepare and run a script based on it.
This allows to programmatically create the configuration with arbitrary logic and limit the repetition of information. The following is an example on how to use cassy in this mode, the final version of the script will heavily depend on the specific application.

```python
from cassy.runners.run_bolts import run_bolts
from cassy.bolts.geometry import BoltGeom, InsertGeom
from cassy.runners.run_common import build_material_library
from cassy.bolts.bolt_config import FlangeAssessmentConfig
from cassy.bolts.bolt_config import BoltReferenceEvent, BoltReferenceEventFatigue
import pandas as pd
import os
import shutil
from copy import deepcopy
from cassy.designcodes.map import BOLT_CODES

# #### Some helper functions ####


def constant_spec(n_bolts: int, geom_data: str, preload: float) -> pd.DataFrame:
    """Use the same specs for all bolts and inserts in flanged connection

    Parameters
    ----------
    n_bolts : int
        number of bolts in the connection
    geom_data : str
        name of the geometry to be used for all bolts and inserts
    preload : float
        preload to be used for all bolts and inserts

    Returns
    -------
    pd.DataFrame
        DataFrame containing the specifications for all bolts and inserts
    """
    bolt_spec = {
        "Bolt ID": range(1, n_bolts + 1),
        "Geom data": [geom_data] * n_bolts,
        "Geom type": ["bolt"] * n_bolts,
        "Preload [N]": [preload] * n_bolts,
    }
    insert_spec = {
        "Bolt ID": range(1, n_bolts + 1),
        "Geom data": [geom_data] * n_bolts,
        "Geom type": ["insert"] * n_bolts,
        "Preload [N]": [preload] * n_bolts,
    }
    specs = pd.concat([pd.DataFrame(bolt_spec), pd.DataFrame(insert_spec)])
    specs["Bolt ID"] = specs["Bolt ID"].astype(str)
    return specs.set_index("Bolt ID")


# #### Main Code ####

root = "test"

# Get all default materials (or point to a personal library to add more)
materials = build_material_library()
configs = {}

# Define some geometries. It may be done programmatically or by reading from files
geometries = {
    "M16_bolt": BoltGeom(
        "M16_bolt",
        materials["Inconel 718 RCC-MRx"],
        p=2, d=16, Le=44, B=0, C=0, d_vh=0
    ),
    "M16_insert": InsertGeom(
        "M16_insert",
        materials["SS316L(N)-IG_SDC-IC"],
        p=3,
        d=24,
        Le=19.50,
        d_vh=3,
    ),
}

# These are usually the same for all geometries so we can set them once
for _, geom in geometries.items():
    geom.KF = 4
    geom.f = 0.15
    geom.f_prime = 0.15


# copy the actions in the new root for tracebility and parse them
shutil.copytree("actions", f"{root}/actions", dirs_exist_ok=True)
actions = {}
for file in os.listdir(f"{root}/actions"):
    name = file.split(".")[0]
    df = pd.read_csv(f"{root}/actions/{file}")
    # ensure bolt IDs are read as strings
    df["boltID"] = df["boltID"].astype(str)
    df.set_index(["boltID", "analysis", "loadstep"], inplace=True)
    actions[name] = df

# --- Reference event to be used across all configurations ---
# REs
# Reference Events
NO_01 = BoltReferenceEvent(
    name="NO.01",
    oper_cond="NO",
    init_event="VDE III",
    concat_event="-",
    temp=20.0,
    dpa=0.0,
    load_category="II",
    service_lvl="A",
    primary=("loads", "5-4+3-1"),
    all_loads=("loads", "5"),
)

# REs Fatigue
NO_01_fatigue = BoltReferenceEventFatigue(
    name="NO.01",
    oper_cond="NO",
    init_event="-",
    concat_event="-",
    temp=20.0,
    dpa=0.0,
    load_category="I",
    service_lvl="A",
    n_cycles=60000,
    delta_sigma=(("loads", "4"), ("loads", "400")),
    sigma_sustained=("loads", "3"),
)
NO_02_fatigue = BoltReferenceEventFatigue(
    name="NO.02",
    oper_cond="NO",
    init_event="VDE III",
    concat_event="-",
    temp=20.0,
    dpa=0.0,
    load_category="II",
    service_lvl="A",
    n_cycles=4545,
    delta_sigma=(("loads", "5"), ("loads", "4")),
    sigma_sustained=("loads", "3"),
)

# Now create the configurations for each flange
# --- M4 ---
# geometries
specs = constant_spec(n_bolts=4, geom_data="M16", preload=55.88e3)
# REs
ref_events = {}
for bolt_id in range(1, 5):
    events = []
    # assuming same T for each bolt here, more complex logic can be added
    for event, T, dpa in zip([NO_01], [130], [0]):
        event = deepcopy(event)
        event.temp = T
        event.dpa = dpa
        events.append(event)
    ref_events[str(bolt_id)] = events

# REs fatigue
ref_events_fatigue = {}
for bolt_id in range(1, 5):
    events = []
    # assuming same T for each bolt here, more complex logic can be added
    for event, T, dpa in zip([NO_01_fatigue, NO_02_fatigue], [130, 130], [0, 0]):
        event = deepcopy(event)
        event.temp = T
        event.dpa = dpa
        events.append(event)
    ref_events_fatigue[str(bolt_id)] = events

config = FlangeAssessmentConfig(
    actions=actions["M4"],
    code=BOLT_CODES["RCC-MRx"],
    bolts_spec=specs,
    REs=ref_events,
    REs_fatigue=ref_events_fatigue,
    name="M4",
)
configs["M4"] = config

# add here other configurations if needed

# Run assessment
run_bolts(
    root=root,
    fatigue=True,
    print_recap=True,
    only_bolts=False,
    geoms=geometries,
    config_dict=configs,
)
```