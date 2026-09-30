# Paths assessment GUI

CASSY allows to perform the assessment of one or more submodels at the same time. 
For each submodel one .csv will need to be provided that contains the linearized
stress trensors that are to be used as inputs for CASSY.

## The linearized stresses file
Before even starting the configuration of the assessment, one linearized stress file must be generatted as input data for each submodel. This file will contain the linearized stress tensors that can be later combined and assessed in CASSY.

The columns of the file must be:
* **path**: number (ID) of the path
* **analysis**: name of the analysis to which the stress are extracted from
* **loadstep**: loadstep of the analysis from which the stresses are extracted from
* **pathpoint**: either "begin" or "end", indicate the position of the stresses in the path.
* **stress_type**: Either "Pm" (primary), "Pb" (bending) or "F" (peak)
* **Sx**: Sx component of the stress
* **Sy**: Sy component of the stress
* **Sz**: Sz component of the stress
* **Sxy**: Sxy component of the stress
* **Sxz**: Sxz component of the stress
* **Syz**: Syz component of the stress

CASSY if FEM code agnostic, but a collection of script to extract data from different workflows (e.g., APDL, Mechanical, ABAQUS, etc.) in a suitable format ready to be used in CASSY can be found [here](https://github.com/Fusion4Energy/CASSY_support)

## General Tab
Once the csv files are ready, the GUI can be opened using:

```python
python -m cassy --pathsgui
```

The GUI will open on the *General* Tab where the main run options can be set:

* **Fatigue assessment**, controls if the fatigue assessment is performed or not
* **Additional materials folder**, allows the user to point to folder that can contain additional material files that are not included in CASSY default library. These must be in yaml format, see [materials](user_guide/materials).
* **Output root folder**, browse to a destination folder where to output all CASSY results

!!! note
    Configuration settings can be imported from and exported to .json format. This is done using `File->Open` and `File->Save as` respectively. 

Once the configuration is complete, the assessment can be launched using the `Run Cassy Assessment` button.

## Submodel Tab
In this tab all the submodels onto which performing the assessment must be defined. For each submodel the GUI will ask for:

* **Name**, name of the submodel that will be used in the outputs
* **Design Code**, drop-down menu that allows you to select one of the available design codes.
* **Stress tensor CSV**, browse to link each submodel with its tensor data input .csv as discussed [above](#the-linearized-stresses-file).

## Loads Tab
Here all single loads (i.e., their correspondent stress tensors) are classified. For each load the following input is needed:

* **Name**, this is the name of the single loads that identify it.
* **Analysis name**, the csv can contain multiple analyses with different loadsteps. This identifies the *analysis* column of the .csv inputs.
* **Time Step**, can be a linear combination of different time steps as per what defined in the input csv. An example is `2-1`.
* **Stress Type**, this is the type of stress related to the specific load, 
    either P (primary) or Q (secondary).
* **Load Type**, this is the type of the specific load, either Inertial or Volumetric.
* **Unit**, this is the units used for the linearized stress tensors in the excel
    load files. Typycally MPa or Pa.
* **Scale**, factor that scales the stress tensors related to the specific load.
* **Spatial Recombination**, type of spatial recombination of inertial stresses,
    typically "srss" for inertial loads. Other options are "algebraic" and "abs". Do not specify anything for volumetric load, they are always algebraically combined.
* **Is Cyclic**, mark if the load is cyclic.
* **Derives from Plasma Disruption**, mark if the load derives from plasma disruption. See [here](theory/code-interpretations#plasma-disruption-derived-stresses) for additional details.
* **Is Pressure**, mark if the load is pressure. See [here](theory/code-interpretations#distinction-between-normal-and-fillet-paths) on why this is relevant.
* **Is Short Overstress**, mark if the load can be considered a short overstress. This is used only in the computation of efficiency index in ratcheting rules. If the load is cyclic and of brief duration it will cause a short-duration overstress that needs to be categorized differently in the rules.

## Reference Event Tab
Once the single loads have been defined, Reference Events (i.e. load combinations)
can be built. For each reference event, the following data is specified:

* **RE ID**, identifier for the reference event.
* **Service Level**, either "A", "C" or "D".
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Load Ctg.** loading category for the event (eg. I, II, ...) it is not mandatory for 
    the assessment, it will only be used in reporting. 
* **Loads**, select all the single loads that compose the event.

## Fatigue Reference Event Tab
It is exactly the same as the normal reference event but, in addition, number of cycles
have to be provided.

## Paths Tab
For each submodel a number of paths must be defined. For each path,
the following data is specified:

* **Path number**, this is the identification number of the path that identifies it 
    and that needs to be the same as the one specified in the csv input file;
* **Material**, this specifies the material in which the path is defined. The complete list of default materials available in cassy can be found [here](user_guide/materials#default-cassy-materials).
* **Path Type**, this accepts "normal" or "fillet". The distinction is due to the fact that if a path is directed radially through a fillet, bending componenet of pressure induced stress shall be considered secondary in SDC-IC. See the relevant [code interpretation](theory/code-interpretations#distinction-between-normal-and-fillet-paths) for additional details.
* **Welding-n**, factor to be specified in case of paths on welds. If that is not the case, set equal to 1. This reduces the allowable in immediate damage type.
* **Welding-f**, factor to be specified in case of paths on welds. If that is not the case, set equal to 1. This increases the applicable stress/strain range in fatigue assessments.

## T & DPA Tab
For each combination of Reference Event, submodel and path, a temperature and DPA value must 
be associated. Once all the previous configurations have been set, click on ``Refresh grid`` to compute the grid that needs to be filled.

!!! note
    The grid can also be completed by importing a .csv whose columns are *submodel*, *path*, *event*, *T*, *DPA*.