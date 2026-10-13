# Bolts Assesment GUI

CASSY allows to perform the assessment of one or more flanged connections (i.e. collections of bolts) at the same time. The inputs for the assessment are the geometrical parameters of the bolts and the forces and moments acting on them (actions).


# The actions file
One action file must be specified for each flanged connection/model to be assessed. This file will contain the actions used to create load combinations. All the actions at all loadsteps and analyses of interest
are included here for all the bolts of the model.

The columns of the csv file are:

* **boltID**: ID of the bolt
* **analysis**: name of the analysis from which the actions are extracted from
* **loadstep**: loadstep of the analysis from which the actions are extracted from
* **Fx**: Fx shear force acting on the bolt section
* **Fy**: Fy shear force acting on the bolt section
* **Fz**: Fz **normal** force acting on the bolt section
* **Mz**: Mz moment action on the bolt section
* **Mx**: Mx moment action on the bolt section
* **My**: My moment action on the bolt section

CASSY is FEM code agnostic, but a collection of script to extract data from different workflows (e.g., APDL, Mechanical, ABAQUS, etc.) in a suitable format ready to be used in CASSY can be found [here](https://github.com/Fusion4Energy/CASSY_support).

## General Tab
Once the csv files are ready, the GUI can be opened using:

```python
python -m cassy --boltsgui
```

The GUI will open on the *General* Tab where the main run options can be set:

* **Fatigue assessment**, controls if the fatigue assessment is performed or not
* **Generate Word recap**, if unchecked only the Excel results are written (faster)
* **Merge repeated cells in Word tables**, makes the Word tables more readable but is slower
* **Assess only bolts (skip inserts)**, skip the assessment of the base material threads
* **Additional materials folder**, allows the user to point to folder that can contain additional material files that are not included in CASSY default library. These must be in yaml format, see [materials](materials).
* **Output root folder**, browse to a destination folder where to output all CASSY results

!!! note
    Configuration settings can be imported from and exported to .json format. This is done using `File->Open` and `File->Save as` respectively.

## Geometries Tab
Here you can build/modify the geometry library for bolts and inserts dimensions.These libraries can be used cross projects and can be exported and imported as json files using the `Export library` and `Import library` buttons.

When adding a new bolt, an ID (usually something like 'M16') a material, and a number of geometrical parameters will need to be provided. Users can insert all of them or just the minimum set that allows to compute the remaining ones using ISO formulas. This can be done using the `Auto-compute` button in the pop-up dialogue that opens when adding a new bolt geometry.

Base material threads also have to be checked. At the end of the pop-up dialogue the user can mark the `has dedicated insert geometry` which will allow to define geometrical properties of an insert (if present). If no insert is defined, the base material threads are assumed to have the same geometry of the bolts one. If an insert is provided, the base material thread geometry will be the same as the outer threads of the insert.

## Flanges Tab
In this tab, all flanges/submodels will need to be defined. The GUI will ask for:
* **Name**, name of the submodel that will be used in the outputs
* **Design Code**, drop-down menu that allows you to select one of the available design codes.
* **Stress tensor CSV**, browse to link each submodel with its forces and moments input .csv as discussed [above](#the-actions-file).

## Bolts Specs Tab
For each of the flanges/submodel, a number of bolts to assess needs to be defined. For each bolt an ID (use progressive integers), a geometry and a preload value must be assigned.

!!! note
    use the `Duplicate` button to speed up the process

## Ref. Events tab
Once the single loads have been defined, Reference Events (i.e. load combinations)
can be built. For each reference event, the following data is specified:

* **RE ID**, identifier for the reference event.
* **Service Level**, either "A", "C" or "D".
* **Load Ctg.** loading category for the event (eg. I, II, ...) it is not mandatory for 
    the assessment, it will only be used in reporting. 
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Primary Action**, linear combination of actions giving the primary loads (see [load combinations](#load-combinations)).
* **All Loads Action**, linear combination of actions giving all loads (see [load combinations](#load-combinations)).

### Load combinations
Each action is defined as a list of terms, added with the `+ Add term` button. Every term
requires a sign (`+` or `-`), an **analysis** and a **step**, which must match the *analysis* and
*loadstep* columns of the actions .csv file. Terms can come from different analyses, e.g.
`+ X:1` and `- Y:5` computes step 1 of analysis X minus step 5 of analysis Y.

## Fat. Ref. Event tab
Similarly to what is done for regular reference events, fatigue ones also have to be defined:

* **RE ID**, identifier for the reference event.
* **Service Level**, either "A", "C" or "D".
* **Load Ctg.** loading category for the event (eg. I, II, ...) it is not mandatory for 
    the assessment, it will only be used in reporting. 
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment, it will only be used in reporting.
* **N cycles**, number of cycles to be considered for the specific
    load combination.
* **Delta sigma+**, **Delta sigma-**, the [load combinations](#load-combinations) that compose
the delta of the actions. The resulting cyclic actions are computed as `sigma+` - `sigma-`.
* **Sigma sustained**, optional [load combination](#load-combinations) giving the sustained
primary actions.

## T & DPA Tab
For each combination of Reference Event, submodel and bolt, a temperature and DPA value must 
be associated. Once all the previous configurations have been set, click on ``Refresh grid`` to compute the grid that needs to be filled.

!!! note
    The grid can also be completed by importing a .csv whose columns are *flange*, *bolt*, *event*, *T*, *DPA*.