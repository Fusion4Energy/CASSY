!!! warning

    This section is outdated, excel config files are being phased out.
    Only GUI should be documented.

cassy allows to perform the assessment of one or more submodels at the same time. The inputs for the assessment are the linearized stresses in all loading conditions to be assessed and a configuration file for each submodel which contains the instructions to perform the assessment.

These inputs are organized in a specific [folder structure](#folder-structure) which is described hereafter.

# Folder structure
The first step in performing a paths assessment is to create a `<root>` folder for the assessment. This can be located anywhere on your computer. Inside `<root>`, 2 additional directories must be created by the user:

* `config`, that contains one configuration file for each submodel to be assessed. See [the configuration file](#the-configuration-file) section for additional details.
* `stresses`, that contains 1 CSV file for each submodel (named as the correspondent configuration file). See [the linearized stresses](#the-linearized-stresses-file) for additional details.

The final input tree should look like this:
```
<root>
    |
    |------ config
    |         |------ <model1>.xlsx
    |         |------ <model2>.xlsx
    |         |------ ...
    |
    |------ stresses
    |         |------ <model1>.csv
    |         |------ <model2>.csv
    |         |------ ...

```

CASSY provides a handy method to initialize this structure directly with:

```
python -m cassy --init paths
```

Examples of this structure (and relative files) can be found on the [cassy tests](https://eng-gitlab.f4e.europa.eu/f4e-projects/cassy/-/tree/main/tests/runners/paths?ref_type=heads)

# The configuration file
The configuration file contains the core instructions to perform the assessment. One file needs to be specified for each submodel. The excel is composed by 6 sheets which are described hereafter.

## General
This sheet contains the general parameters for the assesment:
* **Design Code**, name of the design code. Available design codes can be found [here](/Limitations)

## Paths
This sheet is related to the definition of the paths parameters. For each path,
the following data is specified:
* **Path N**, this is the identification number of the path that identifies it 
    and that needs to be the same as the one specified in the load excel files;
* **Type**, this accepts "normal" or "fillet". The distinction is due to the fact that if a path is directed radially through a fillet, bending componenet of pressure induced stress shall be considered secondaryin SDC-IC. See the relevant [code interpretation](/Theory/Code-interpretations#distinction-between-normal-and-fillet-paths) for additional details.
* **Material**, this specifies the material in which the path is defined. The complete list of default materials available in cassy can be found [here](/Usage/Materials#default-cassy-materials).
* **Welding-n**, factor to be specified in case of paths on welds. If that is not the case, set equal to 1. This reduces the allowable in immediate damage type.
* **Welding-f**, factor to be specified in case of paths on welds. If that is not the case, set equal to 1. This increases the applicable stress/strain range in fatigue assessments.

## Load steps
This sheet is related to the configuration of the single loads. For each load,
the following data is specified:
* **Load**, this is the name of the single loads that identify it and that needs
    to be recalled in loads recombination.
* **Analysis Name**, this is the name of the analysis that is found in the
    the *analysis* column of the .csv inputs.
* **Timestep**, this specifies the timestep of the ANSYS analysis related to this 
    specific single load (*loadstep* column). It is also possible to define a linear combination
    of the steps in the same analysis (e.g., 2-3+5).

## Stresses
This sheet is related to the configuration of the single loads. For each load,
the following data is specified:
* **Load**, this is the name of the single loads that identify it and that needs
    to be the same as the one specified in the `Load step` sheet.
* **Unit**, this is the units used for the linearized stress tensors in the excel
    load files. Typycally MPa or Pa.
* **Stress Type**, this is the type of stress related to the specific load, 
    either P (primary) or Q (secondary).
* **Load Type**, this is the type of the specific load, either Inertial or Volumetric;
* **Scale**, factor that scales the stress tensors related to the specific load.
* **Spatial Recombination**, type of spatial recombination of inertial stresses,
    typically "srss" for inertial loads. Other options are "algebraic" and "abs". Do not specify anything for volumetric load, they are always algebraically combined.
* **Is Cyclic**, either True or False.
* **Derives from Plasma Disruption**, either True or False. See [here](/Theory/Code-interpretations#plasma-disruption-derived-stresses) for additional details.
* **Is Pressure**, either True or False. See [here](/Theory/Code-interpretations#distinction-between-normal-and-fillet-paths) on why this is relevant.
* **Is Short Overstress**, This is used only in the computation of efficiency index in ratcheting rules. If the load is cyclic and of brief duration it will cause a short-duration overstress that needs to be categorized differently in the rules.

## Reference Event
This sheet is related to the configuration of the reference events (i.e. load
combination). For each reference event, the following data is specified:
* **Path N**, this is the identification number of the path as specified in the 
    Paths sheet.
* **ID**, identified for the reference event.
* **Loads**, list of single loads (separated by commas) that compose the event.
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Loading ctg**, either "I", "II", "III" or "IV".
* **Service Level**, either "A", "C" or "D".
* **T**, maximum temperature for the specific path during the specific reference
    event.
* **DPA**, maximum displacements per atom for the specific path during the
    specific reference event.

## RE fatigue
This sheet is related to the configuration of the reference events (i.e. load
combination) for fatigue. For each reference event, the following data is
specified:
* **Path N**, this is the identification number of the path as specified in the 
    Paths sheet.
* **ID**, identified for the reference event.
* **Loads**, list of single loads (separated by commas) that compose the event.
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Loading ctg**, either "I", "II", "III" or "IV".
* **Service Level**, either "A", "C" or "D".
* **N cycles**, number of cycles to be considered for the specific load combination.
* **T**, maximum temperature for the specific path during the specific reference
    event.
* **DPA**, maximum displacements per atom for the specific path during the
    specific reference event.

# The linearized stresses file
As specified before, one lin. stress file must be included for each submodel. This file will contain the linearized stress tensors used to create load combinations through the corresponding configuration file.

The columns of the file are:
* *path*: number (ID) of the path
* *analysis*: name of the analysis to which the stress are extracted from
* *loadstep*: loadstep of the analysis from which the stresses are extracted from
* *pathpoint*: either "begin" or "end", indicate the position of the stresses in the path.
* *stress_type*: Either "Pm" (primary), "Pb" (bending) or "F" (peak)
* *Sx*: Sx component of the stress
* *Sy*: Sy component of the stress
* *Sz*: Sz component of the stress
* *Sxy*: Sxy component of the stress
* *Sxz*: Sxz component of the stress
* *Syz*: Syz component of the stress

CASSY if FEM code agnostic, but a collection of script to extract data from different workflows in a suitable format ready to be used in CASSY can be found [here](https://github.com/Fusion4Energy/CASSY_support)

# Outputs
once the input folders have been correctly populated, the code can be run.
Different outputs will be provided in the `<root>` folder. All subfolders
are automatically generated.

* `assessment`, filled only if ``--norecap`` option is used. Here are stored the global unformatted assessment dataframes;
* `Recap.docx`, a word file containing summary tables of the results.