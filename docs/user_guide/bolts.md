!!! warning

    This section is outdated, excel config files are being phased out.
    Only GUI should be documented.

cassy allows to perform the assessment of one or more flanged connections (i.e. collections of bolts) at the same time. The inputs for the assessment are the geometrical parameters) of the bolts, forces and moments acting on them and a configuration file describing the load combinations to be assessed.

These inputs are organized in a specific [folder structure](#folder-structure) which is described hereafter.

# Folder structure

The first step in performing a bolts assessment is to create a `<root>` folder for the assessment. This can be located anywhere on your computer. Inside `<root>`, 3 additional directories must be created by the user:
* `actions`, that contains 1 CSV file for each flanged connection/model. See [actions file](#the-actions-file) for additional details.
* `geometries`, this folder will contain a library of bolt geometries to be considered during the assessment. See [the geometry library chapter](#the-geometry-library) for additional details.
* `config`, that contains one [configuration files](#the-configuration-file) for each flanged connection/model to be assessed (named as the correspondent actions CSV file).


The final input tree should look like this:
```
<root>
    |
    |------ config
    |         |------ <flange1>.xlsx
    |         |------ <flange2>.xlsx
    |         |------ ...
    |
    |------ actions
    |         |------ <flange1>.csv
    |         |------ <flange2>.csv
    |         |------ ...
    |
    |------ geometries
    |         |------ <GeomID>_bolt.xlsx
    |         |------ <GeomID>_insert.xlsx
    |         |------ ...

```

CASSY provides a handy method to initialize this structure directly with:

```
python -m cassy --init bolts
```

Examples of this structure (and relative files) can also be found on the [cassy tests](https://eng-gitlab.f4e.europa.eu/f4e-projects/cassy/-/tree/main/tests/runners/bolts?ref_type=heads)

# The actions file
As specified before, one action file must be included for each flanged connection/model to be assessed. This file will contain the actions used to create load combinations through the corresponding configuration file. All the actions at all loadsteps and analyses of interest
are included here for all the bolts of the model.

The columns of the csv file are:

* *boltID*: ID of the bolt
* *analysis*: name of the analysis from which the actions are extracted from
* *loadstep*: loadstep of the analysis from which the actions are extracted from
* *Fx*: Fx shear force acting on the bolt section
* *Fy*: Fy shear force acting on the bolt section
* *Fz*: **Fz normal force** acting on the bolt section
* *Mz*: Mz moment action on the bolt section
* *Mx*: Mx moment action on the bolt section
* *My*: My moment action on the bolt section

cassy is FEM code agnostic. Nevertheless, a few tools are mantained at F4E that allow to extract such actions from ANSYS APDL and Mechanical [here](https://github.com/Fusion4Energy/CASSY_support).

# The geometry library
This folder contains the library of bolt geometries (and inserts) that are used in the assessment. One file needs to be provided for each different type of geometry of bolts and inserts.

Each geometry (excel) file contains only one sheet listing the specification of the geometrical and material data. The naming convention for this files should be `<GeomID>_<bolt/insert>.xlsx`. `GeomID` will be used in the config file to assign a specific geometry to a bolt while the tag `insert` or `bolt` specifies to which kind of geometry the data is related to. A complete description of the geometrical parameters to be specified is out of scope of this wiki, more details can be found in the example excel files themselves.

# The configuration file
The configuration file contains the core instructions to perform the assessment. One file needs to be specified for each flanged connection/model. The excel is composed by 4 sheets which are described hereafter.

## Additional Data
This sheet contains the general parameters for the assesment:
* **Code**, name of the design code. Available design codes can be found [here](/Limitations)

## Bolts
This sheet lists all the bolts that need to be assessed and are part of the flanged
connection. The following data needs to be specified:
* **Bolt ID**, identifier of the bolt (use the same ID for insert)
* **Geom Data**, geometry ID (`GeomID`) as per `<root>/geometries` files.
* **Geom type**, either "bolt" or "insert".
* **Preload [N]** Preload in Newton. Sign is important. Or better, the sign relative to the normal force `N` is important. Preload may be substracted from the all loads hence users must ensure to use the same convention for the bolts actions and the preload.

## REs
This sheet is related to the configuration of the reference events (i.e. load
combination). For each bolt a set of reference events need to be specified.
For each reference event, the following data is specified:

* **Bolt ID**, must match the same ID of the "Bolts" sheet.
* **ID**, identified for the reference event.
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **T**, maximum temperature for the bolt during the specific reference
    event in celsius.
* **DPA**, maximum Displacements Per Atom (DPA) for the specific bolt during the
    specific reference event.
* **Primary**, pointer to the combined primary loads actions. It is of the type
`<analysis_name>, <loadstep>` or `(<analysis_name>, <loadstep>)`. These must be consistent with the columns *analysis* and *loadstep* of the actions .csv files. `<loadstep>` can be
a single loadstep or a linear combination (e.g. '4-3+2').
* **All**, pointer to the combined all loads actions. It is of the type
`<analysis_name>, <loadstep>` or `(<analysis_name>, <loadstep>)`. These must be consistent with the columns *analysis* and *loadstep* of the actions .csv files. `<loadstep>` can be
a single loadstep or a linear combination (e.g. '4-3+2').
* **Loading category**, either "I", "II", "III" or "IV".
* **Service Level**, either "A", "C" or "D".

## REs fatigue
This sheet is related to the configuration of the reference events (i.e. load
combination) for fatigue. For each reference event (and bolt), the following data is
specified:
* **Bolt ID**, must match the same ID of the "Bolts" sheet;
* **ID**, identified for the reference event.
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **T**, maximum temperature for the bolt during the specific reference
    event.
* **DPA**, maximum displacements per atom for the specific bolt during the
    specific reference event.
* **Total number of cycles**, number of cycles to be considered for the specific
    load combination.
* **Sigma sustained**, pointer to the combined primary loads actions. It is of the type
`<analysis_name>_<loadstep>`. These must be consistent with the columns *analysis*
and *loadstep* of the actions .csv files;
* **Delta sigma+**, **Delta sigma-**, pointer to the combined cyclic loads that compose the delta of the actions. It is of the type `<analysis_name>_<loadstep>`.
These must be consistent with the columns *analysis*
and *loadstep* of the actions .csv files. The result cyclic actions will be computed as
`sigma+` - `sigma-`.
* **Loading category**, either "I", "II", "III" or "IV".
* **Service Level**, either "A", "C" or "D".

# Outputs
Once the input folders have been correctly populated, the code can be run.
Different outputs will be provided in the `<root>` folder. All subfolders
are automatically generated.

* `assessment`, filled only if the ``--norecap`` option is used. Here are stored the global unformatted assessment dataframes;
* `recap.docx`, a word file containing summary tables of the results.

# Advanced mode
Sometimes, creating all the configuration and geometry files can be a tedious job if much of the information simply need to be repeated
for a large number of bolts. It is possible to use ``cassy`` directly as a python library and run it as a script.
This allows to programmatically create the configuration files with arbitrary logic and limit the repetition of information.
The following is an example on how to use cassy in this mode, the final version of the script will heavily depend on the specific application.

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