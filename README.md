![Coverage](https://eng-gitlab.f4e.europa.eu/f4e-projects/cassy/badges/main/coverage.svg)
![Tests](https://eng-gitlab.f4e.europa.eu/f4e-projects/cassy/badges/main/pipeline.svg)
![Latest release](https://eng-gitlab.f4e.europa.eu/f4e-projects/cassy/-/badges/release.svg)

# CASSY
CASSY is an automated tool for stress assessment following design codes.

Authors: F4E engineering analyses unit

## Installation

### User Installation
The procedure to install cassy is the following:

1) Create a new environment. If you are using anaconda as python package manager you can do this with:

    ```
    conda create -n cassy python=3.12
    ```

2) Activate the newly created python environment. If you are using anaconda:

    ```
    conda activate cassy
    ```

2) Install the cassy package. To do that, download the python wheels from the latest cassy release (GitLab website) and use:

    ```
    pip install <name_of_the_wheel>.whl
    ```
  
### Developer installation

To perform a developer installation, follow the same step 1) and 2) of the 
User installation.

Then, you should clone the GitLab repository into a folder of your choice.
Move into the chosen folder and type:

    ```
    git clone https://eng-gitlab.f4e.europa.eu/f4e-projects/cassy.git
    ```

If it is the first time that you connect to the F4E GitLab you will be requested
to autenthicate yourself. In case of an SSL certificate error, you can solve it
through:

    ```
    git config --global http.sslBackend schannel
    ```

After the repository has been cloned, perform an "editable" installation:

    ```
    pip install -e .[dev]
    ```

the flag ``-e`` tells pip that this is an editable installation. This means
that the code of the package is not stored in the manager folders but a link
is created with the cloned repository instead. Changing the code in the repo
(i.e. modifications or switching branches) will change the behaviour of the
package in real time.
The ``[dev]`` tells pip to install some additional dependencies that are
useful for development purposes such as ``pytest`` or ``ruff`.

## Usage

Once the package has been installed, the user should create a folder
where a specific assessment will be performed. From now on, such folder is referred as ``<root>``

1. Setup the correct folder structure in ``<root>`` depending on the type of assessment.
   Jump to [Path config](#Paths) or [Bolts config](#Bolts) for additional details.
2. open an anaconda prompt shell and change directory to ``<root>`` Then type:
    ```
    python -m cassy
    ```

There a few arguments that can be provided through command line and are listed in the sections below.
Here is an example to run a paths assessment including fatigue assessment:

    ```
    python -m cassy --assess paths --fatigue
    ```

### Mandatory arguments

- `--assess` this accepts either "paths" or "bolts" and it is used to specify which kind of assessment should
be performed

### Optional arguments
- `--fatigue` if the argument is passed, the fatigue assessment will also be performed
- `--root` by default is the current working directory, but with this command it can be changed to any other folder

## Input-output folder structure
### Paths
The `<root>` will need to be populated with all necessary inputs for the code to run. Outputs will be dumped in the same  `<root>` folder.
Inside `<root>`, 2 folders need to be created by the user:
* `config`, that contains all the configuration file for each model to be assessed excel configuration files examples can be found in the example folder;
* `stresses`, that contains 1 CSV file for each submodel (named as the correspondent configuration file).
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
#### The configuration file
As specified in the previous section, for each model to be assessed, a
configuration file needs to be generated and stored inside the `<root>/config`
folder. The excel is composed by 6 sheets which are described hereafter.

###### General
This sheet contains the general parameters for the assesment:
* `Design Code`, name of the design code as specified in the allowable codes in the same sheet.

###### Paths
This sheet is related to the definitionof the paths parameters. For each path,
the following data is specified:
* **Path N**, this is the identification number of the path that identifies it 
    and that needs to be the same as the one specified in the load excel files;

###### Load steps
This sheet is related to the configuration of the single loads. For each load,
the following data is specified:
* **Load**, this is the name of the single loads that identify it and that needs
    to be recalled in loads recombination;
* **Analysis Name**, this is the name of the analysis that is found in the
    the *analysis* column of the .csv inputs
* **Timestep**, this specifies the timestep of the ANSYS analysis related to this 
    specific single load (*loadstep* column).

###### Stresses
This sheet is related to the configuration of the single loads. For each load,
the following data is specified:
* **Load**, this is the name of the single loads that identify it and that needs
    to be the same as the one specified in the `Load step` sheet;
* **Unit**, this is the units used for the linearized stress tensors in the excel
    load files. Typycally MPa or Pa;
* **Stress Type**, this is the type of stress related to the specific load, 
    either P or Q;
* **Load Type**, this is the type of the specific load, either Inertial or Volumetric;
* **Scale**, factor that scales the stress tensors related to the specific load;
* **Spatial Recombination**, type of spatial recombination of inertial stresses,
    typically srss;
* **Is Cyclic**, either True or False;
* **Derives from Plasma Disruption**, either True or False;
* **Is Pressure**, either True or False;
* **Is Occasional**, either True or False.

##### Reference Event
This sheet is related to the configuration of the reference events (i.e. load
combination). For each reference event, the following data is specified:
* **Path N**, this is the identification number of the path as specified in the 
    Paths sheet;
* **ID**, identified for the reference event;
* **Loads**, list of single loads (separated by commas) that compose the event;
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment;
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment;
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment;
* **Loading ctg**, either I, II, III or IV;
* **Service Level**, either "A", "C" or "D";
* **T**, maximum temperature for the specific path during the specific reference
    event;
* **DPA**, maximum displacements per atom for the specific path during the
    specific reference event.

##### RE fatigue
This sheet is related to the configuration of the reference events (i.e. load
combination) for fatigue. For each reference event, the following data is
specified:
* **Path N**, this is the identification number of the path as specified in the 
    Paths sheet;
* **ID**, identified for the reference event;
* **Loads**, list of single loads (separated by commas) that compose the event;
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment;
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment;
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment;
* **Loading ctg**, either I, II, III or IV;
* **Service Level**, either "A", "C" or "D";
* **N cycles**, number of cycles to be considered for the specific load combination;
* **T**, maximum temperature for the specific path during the specific reference
    event;
* **DPA**, maximum displacements per atom for the specific path during the
    specific reference event.

#### Outputs
once the input folders have been correctly populated, the code can be run.
Different outputs will be provided in the `<root>` folder. All subfolders
are automatically generated.

* `assessment`, a folder containing assessment excel files for each path;
* `images`, a folder containing summary picturestaken from the assessment excel files;
* `Recap.docx`, a word file containing summary tables of the results and the pictures
  from the `images` folder.

### Bolts
Inside `<root>`, 3 folders need to be created by the user:
* `config`, that contains all the configuration file for each model to be assessed excel configuration files examples can be found in the example folder;
* `actions`, that contains 1 CSV file for each submodel (named as the correspondent configuration file).
The columns of the file are:
    * *boltID*: ID of the bolt
    * *analysis*: name of the analysis to which the stress are extracted from
    * *loadstep*: loadstep of the analysis from which the stresses are extracted from
    * *Fx*: Fx shear force acting on the bolt section
    * *Fy*: Fy shear force acting on the bolt section
    * *Fz*: Fz normal force acting on the bolt section
    * *Mz*: Mz moment action on the bolt section
    * *Mx*: Mx moment action on the bolt section
    * *My*: My moment action on the bolt section
* `geometries`, this folder will contain the library of bolt geometries to be considered during the
assessment. They contain only one sheet listing the specification of the geometrical and material data 
for the bolt/insert. The naming convention for this files should be `<GeomID>_<bolt/insert>.xlsx`.
`GeomID` will be used in the config file to assign a specific geometry to a bolt while the tag `insert`
or `bolt` specifies to which kind of geometry the data is related to.

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

#### The configuration file
As specified in the previous section, for each flanged connection to be assessed, a
configuration file needs to be generated and stored inside the `<root>/configurations`
folder. The excel is composed by 4 sheets which are described hereafter.

###### Additional Data
This sheet contains the general parameters for the assesment:
* **Code**, name of the design code, either RCC-MRx, or SDC-IC

##### Bolts
This sheet lists all the bolts that need to be assessed and are part of the flanged
connection. The following data needs to be specified:
* **Bolt ID**, identifier of the bolt (use the same ID for insert)
* **Geom Data**, geometry ID (`GeomID`) as per `<root>/geometries` files.
* **Geom type**, either "bolt" or "insert".
* **Preload [N]** Preload in Newton.

##### REs
This sheet is related to the configuration of the reference events (i.e. load
combination). For each bolt a set of reference events need to be specified.
For each reference event, the following data is specified:

* **Bolt ID**, must match the same ID of the "Bolts" sheet;
* **ID**, identified for the reference event;
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment;
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment;
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment;
* **T**, maximum temperature for the bolt during the specific reference
    event;
* **DPA**, maximum displacements per atom for the specific bolt during the
    specific reference event.
* **Primary**, pointer to the combined primary loads actions. It is of the type
`<analysis_name>_<loadstep>`. These must be consistent with the columns *analysis*
and *loadstep* of the actions .csv files;
* **All**, pointer to the combined all loads actions. It is of the type
`<analysis_name>_<loadstep>`. These must be consistent with the columns *analysis*
and *loadstep* of the actions .csv files;
* **Loading category**, either I, II, III or IV;
* **Service Level**, either "A", "C" or "D".

##### REs fatigue
This sheet is related to the configuration of the reference events (i.e. load
combination) for fatigue. For each reference event (and bolt), the following data is
specified:
* **Bolt ID**, must match the same ID of the "Bolts" sheet;
* **ID**, identified for the reference event;
* **Operating Conditions**, description of the event, it is not mandatory for 
    the assessment;
* **Initiating Event**, description of the event, it is not mandatory for 
    the assessment;
* **Concatenated Event**, description of the event, it is not mandatory for 
    the assessment;
* **T**, maximum temperature for the bolt during the specific reference
    event;
* **DPA**, maximum displacements per atom for the specific bolt during the
    specific reference event;
* **Total number of cycles**, number of cycles to be considered for the specific
    load combination;
* **Sigma sustained**, pointer to the combined primary loads actions. It is of the type
`<analysis_name>_<loadstep>`. These must be consistent with the columns *analysis*
and *loadstep* of the actions .csv files;
* **Delta sigma+**, **Delta sigma-**, pointer to the combined cyclic loads that compose impose the delta of the actions. It is of the type `<analysis_name>_<loadstep>`.
These must be consistent with the columns *analysis*
and *loadstep* of the actions .csv files. The result cyclic actions will be computed as
`sigma+` - `sigma-`;
* **Loading category**, either I, II, III or IV;
* **Service Level**, either "A", "C" or "D".

#### Outputs
once the input folders have been correctly populated, the code can be run.
Different outputs will be provided in the `<root>` folder. All subfolders
are automatically generated.

* `assessment`, a folder containing assessment one excel file for each bolt;
* `images`, a folder containing summary pictures taken from the assessment excel files;
* `recap.docx`, a word file containing summary tables of the results and the pictures
  from the `images` folder.

## Usage
### Implemented design codes
Hereinafter are listed the design codes that have been implemented in the tool.
#### On linearized Stresses
- RCC-MRx
- RCC-MR
- SDC-IC

#### On Bolts
- RCC-MRx
- SDC-IC

## Known Limitations
Hereinafter are listed the known limitation for the tool.
### General
- material properties should be always double checked, in particular the validity ranges that not always are taken into account by the code;
#### Trixiality factor
- triaxility factor has been considered equal to 2 by default. This is a conservative assumption considering the related allowable stresses.
- only linear elastic analysis routes are implemented;
- the assessment may be considered valid only if creep can be neglected.
### Paths
- fatigue for materials with a fatigue curve depending on stress is not currently supported;
- RCC-MRx rules for significant irradiation (RB 3251.21) are not yet implemented;
- In RCC-MRx ratcheting efficieny index rules are commented out and should be double checked if are to be used.
### Bolts
- fatigue for SDC-IC/RCC-MR is implemented without Neuber's rule since all materials tested up to know had the cyclic stress-strain curve missing;
- fatigue for materials with a fatigue curve depending on strain is not currently supported.


