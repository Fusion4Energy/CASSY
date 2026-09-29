# Material Properties

Material properties in cassy are defined through yaml files, one for each material. The name of the file must correspond to the tag used in the configuration files when materials are assigned to paths or bolts.

cassy is shipped with a default library of such materials. The same material may be shipped in different versions depending on the design code it should be used with.

List of available materials:

- SS316L(N)-IG_SDC-IC
- SS316L(N)-IG_RCC-MRx
- CuCrZr-IG Tr B SDC-IC
- Inconel 718 (non leak tight) SDC-IC
- Inconel 718 RCC-MRx
- SS660 (non leak-tight)_SDC-IC
- SS660_RCC-MRx
- XM-19 SS_SDC-IC

Such files can be inspected [here](https://github.com/Fusion4Energy/CASSY/tree/main/src/cassy/additional_data/materials).

Nevertheless, there are many use cases which may find handy the possibility to provide user-defined additional materials using the ``--matlib`` option.

The name of the additional yaml file needs to be the same that will be used in the configuration files to assign such material to a path or a bolt.

The general structure of a material yaml file is the following:

```yaml
name: name of the material
description: some general info if needed
properties:
  # line comments in yaml
  Property name 1:  # inline commments in yaml
    ...
  Property name 2:
    ...
```

Each property can be defined in many different ways depending on the data format provided.

A complete list of supported data formats can be found [here](#supported-properties-data-formats), while the list of supported properties in cassy is listed in the [supported properties](#supported-properties) section. 

## Supported properties data formats

All properties have two pivotal attributes: the name and the format type. Names must be one of the supported properties from cassy (see [supported properties](#supported-properties) section), while the format type can be one of the many described in the following subsections.

There are attributes that are general and can be specified in each data format. They are all optional:

- `lower_bound`: a list of inferior bounds to delimit the range of validity of the data provided. A value for each argument needs to be provided. If there is no limit to the validity of a specific value, the keyword `null` can be used. By default, no bounds are applied. 
- `upper_bound`: a list of upper bounds to delimit the range of validity of the data provided. A value for each argument needs to be provided. If there is no limit to the validity of a specific value, the keyword `null` can be used. By default, no bounds are applied.
- `scale_result`: data may be provided in differen units than the standard (e.g. Young modulus in GPa instead of Pa). This factor can be used to scale the provided data accordingly. By default equal to 1.
- `scale_x`, `scale_y` and `scale_z`: to ensure a correct interpolation, especially on tables, it is
better to stick with the units the data is provided. cassy will enter these interpolation functions though with standard units (e.g. Pa, rel strain, etc.) hence, before entering into the interpolation range, this arguments (x, y, z) may need to be scaled accordingly. By default equal to 1.

This is an example of a general property would look like:

```yaml
Young Modulus: # property name from the supported ones
    type: equation # one of the supported format types
    lower_bound: [20, null] # degrees Celsius, dpa
    upper_bound: [700, null] # degrees Celsius, dpa
    scale_result: 1e9 # to convert GPa to Pa
    ...
```

### Constant
The easiest format, it provides a constant value

**type name:** `constant`

**mandatory attributes:**

- `value`: the constant value

**example**:
```yaml
Poisson Ratio:
    type: constant
    value: 0.3
```

### Polynomial
It allows to define coefficients for a polynomial function. The function may accept more than one argument but only the first one will be used for the polynomial function. The others can be used only for defining upper and lower bounds.

**type name:** `polynomial`

**mandatory attributes:**

- `coefficients`: list of coefficients for the polynomial. If equation is `a+bX+cX^2+...` then the list of coefficients should be `[a, b, c, ...]`.

**example**:
```yaml
Property name:
    type: polynomial
    lower_bound: [20, 0] # T, DPA
    upper_bound: [700, 0.1] # T, DPA
    coefficients: [225.75, -0.73683, 2.5036E-3] # MPa
    scale_result: 1e6 # to convert MPa to Pa
```

### Equation
It allows to define an arbitrary equation to be evaluated at runtime. At the moment, in addition to the arguments to be passed, it accepts the following math symbols:

- `EXP`: exp function
- `SQRT`: square root function
- `^`: power operation

these symbols can be easily extended if needed.

**type name:** `equation`

**mandatory attributes:**

- `equation`: string describing the equation to evaluate
- `args`: list of strings that are the parameters of the equations. Arguments of the property function will be substitued in these strings in the same order they are defined.

**example**:

```yaml
Young Modulus:
    type: equation
    lower_bound: [20, null] # degrees Celsius
    upper_bound: [700, null] # degrees Celsius
    equation: "(201660-84.8*T)/1000" # GPa
    args: ["T", "DPA"] # E(x,y) -> x will go to T and y to DPA
    scale_result: 1e9 # to convert GPa to Pa
```

### Table 1D
Simple 1D table interpolation where x is the argument of the function and y the result.

**Note:** *For tables upper and lower bounds are computed automatically based on the provided data.*

**type name:** `table1D`

**mandatory attributes:**

- `x`: x table points
- `y`: y table points.

These are to be set inside the `values` attribute.

**example**:
```yaml
K:
    type: table1D
    values:
        x: [20, 450, 600, 650] # degrees Celsius
        y: [798.3, 722, 722, 679] # Values of K in MPa
```

### Table 2D
2D interpolation table, given an x and y entry parameter the resulting interpolation value will be returned.

**Note:** *For tables upper and lower bounds are computed automatically based on the provided data.*

**type name:** `table2D`

**mandatory attributes:**

- `x`: x table points
- `y`: y table points.
- `vals`: interpolated values associated to x and y. Matrix in list of list format. One row for each x value.

These are to be set inside the `values` attribute.

**example**:
```yaml
Keps:
    type: table2D
    values:
        # if sigma < 100 MPa set Keps = 1
        x: [20, 450, 500, 550, 600, 650] # degrees Celsius
        y: [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000] # d_sigma MPa
        vals: [
        [1, 1.02, 1.08, 1.15, 1.23, 1.30, 1.37, 1.45, 1.51, 1.58, 1.64],
        [1, 1.01, 1.06, 1.12, 1.20, 1.28, 1.36, 1.43, 1.51, 1.58, 1.65],
        [1, 1.01, 1.06, 1.12, 1.20, 1.27, 1.35, 1.43, 1.50, 1.58, 1.65],
        [1, 1.01, 1.06, 1.12, 1.19, 1.27, 1.35, 1.42, 1.50, 1.57, 1.64],
        [1, 1.01, 1.05, 1.12, 1.19, 1.27, 1.34, 1.42, 1.49, 1.56, 1.63],
        [1, 1.00, 1.02, 1.07, 1.14, 1.22, 1.31, 1.39, 1.48, 1.57, 1.65],
        ]
    scale_y: 1e-6 # inputs to interpolate are in Pa, to be converted to MPa
```

### Table 3D

3D interpolation table, given an x, y and z entry parameter the resulting interpolation value will be returned.

**Note:** *For tables upper and lower bounds are computed automatically based on the provided data.*

**type name:** `table3D`

**mandatory attributes:**

- `columns`: specify the order with which the data is provided. The expected values are `x`, `y`, `z`, `val`, where val is the interpolation result.
- `values`: 2D table that lists interpolation points, `columns` values are used to interpret the values.

**example**:
```yaml
Property name:
    type: table3D
    scale_result: 1e-2 # to convert from percent to relative
    scale_x: 1e-6 # to convert from Pa to MPa for entering the table
    columns: ['val', 'x', 'y', 'z']
    values: [
        [0, 0, 20.0, 0.0],
        [0.01, 20.002, 20.0, 0.0],
        [0.019998, 40.008, 20.0, 0.0],
        [0.029997, 60.018, 20.0, 0.0],
        [0.040017, 80.03202, 20.0, 0.0],
        [0.050169, 100.0502, 20.0, 0.0],
        [0.060899, 120.0731, 20.0, 0.0],
        [0.073585, 140.1031, 20.0, 0.0],
        [0.091795, 160.1469, 20.0, 0.0],
        [0.123647, 180.2227, 20.0, 0.0],
        [0.185861, 200.3721, 20.0, 0.0],
        [0.310245, 220.6836, 20.0, 0.0],
        [0.553481, 241.332, 20.0, 0.0],
        [1.011009, 262.642, 20.0, 0.0],
        [1.36499, 273.7107, 20.0, 0.0],
        [1.835381, 285.1865, 20.0, 0.0],
        [50.31966, 868.35, 20.0, 0.0],
        ...
    ]
```

### Fatigue
Curves to retrieve the allow the allowable number of cycles in fatigue assessments require an ad-hoc property as they are provided often in weird formats and with many caveats. They are similar to tables but with extra attributes.

**Note:** *For fatigue properties upper and lower bounds are computed automatically*

**type name:** `fatigue`

**mandatory attributes:**

- `ftype`: either "strain" or "stress" depending if the numnber of cycles is given as a function of stress or strain range.
- `T` temperature vector of the table in Celsius.
- `N_cycles` number of cycles vector of the table.
- `y`: here either the strain or stress values will be placed. It is matrix where each point is evaluated at the correspondent T and N cycle. One row for each temperature.

**optional attributes:**

- `mean_stress`: either true or false. If true and the fatigue is stress based, it means that a table is provided for different values of mean stress during the cycle. Default is false. Mean stress must be expressed in MPa. Goodman correction is skipped in this case.
- `tables`: if `mean_stress` is true, then the different tables should be listed under `tables` using the mean stress value as key. See examples.

**examples**:

Example of a normal fatigue property

```yaml
Fatigue:
    type: fatigue
    ftype: strain
    scale_y: 1e2 # to from relative to percent when entering table (x is T)
    values:
        T: [20, 450, 500, 550, 600, 650] # degrees Celsius
        N_cycles: [10, 20, 40, 1e2, 2e2, 4e2, ...] # N cycles
        y: [
            [4.291, 2.552, 2.459, 2.361, 2.260, 2.155],
            [2.755, 1.931, 1.841, 1.748, 1.652, 1.553],
            [1.931, 1.485, 1.403, 1.316, 1.231, 1.139],
            ...
        ]
```

Example of a fatigue property using mean stress option:

```yaml
Fatigue:
    type: fatigue
    ftype: stress
    mean_stress: true
    tables:
      690: # MPa
        N_cycles: [1E1, 2E1, 5E1, 1E2, 2E2, 4E2, ...]
        T: [0, 350]
        y: [
          [5191, 5191], # MPa
          [3723, 3723], # MPa
          ...
        ]
      830: # MPa
        N_cycles: [1E1, 2E1, 5E1, 1E2, 2E2, 4E2, ...]
        T: [0, 350]
        y: [
          [5191, 5191], # MPa
          [3723, 3723], # MPa
          ...
        ]
    ...
```

### Multi-format

This properties allows to specify mutiple data formats depending on the input parameter range.
All supported property formats can be used in the "sub-properties". The code will start iterating in the different subproperties in the order they are provided. If input parameters are found to be out of the bounds of the subproperty, the next one is checked. If parameters are found to be out of all bounds, an error is thrown at runtime.

**Note:** *Upper and lower bounds are defined in each subproperty if needed, not in the multi one.*

**type name:** `multi`

**mandatory attributes:**

- `ranges`: is a list of properties. The format of such properties will be the one described in the previous subsections (without the name).

**example**:
```yaml
Min Yield Strength:
    type: multi
    ranges:
        # Unirradiated
        - type: equation
          lower_bound: [20, 0] # degrees Celsius
          upper_bound: [500, 0.01] # degrees Celsius
          equation: -1.63E-06*T**3 + 1.72E-03*T**2 - 7.43E-01*T + 1.05E+03
          args: ["T", "DPA"] # in Celsius
          scale_result: 1e6 # to convert MPa to Pa
        # Irradiated
        - type: table2D
          scale_result: 1e6 # to convert MPa to Pa
          values:
            x: [20, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600] # degrees Celsius
            y: [0.01, 10] # DPA
            vals: [
              [880, 880],
              [864, 864],
              [842, 842],
              [826, 826],
              [813, 813],
              [804, 804],
              [797, 797],
              [791, 791],
              [785, 785],
              [778, 778],
              [769, 769],
              [757, 757],
              [740, 740]
              ]
```

## Supported Properties

Not all these properties are necessary for all applications. Users/developers when adding a new material may use a subset of these. In case the property is called up during the assessment but it was not defined in the material file, an error will be thrown during execution.

### Material properties

#### Young Modulus
Young modulus. 

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

Output unit expected: Pa.

#### Poisson Ratio
Poisson's ratio. A single value is expected.

#### Min Yield Strength
Minimum Yield strength at 0.2% offset (irradiated).

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

Output unit expected: Pa.

#### Mean Yield Strength
Mean yield strength (irradiated).

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

#### Min Tensile Strength
Minimum tensile strength (irradiated).

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

Output unit expected: Pa.

#### Monotonic Min True Stress Strain
Monotonic (i.e. non-cyclic) stress-strain elasto-plastic curve.

Input parameters are:

- `x`, stress value in Pa.
- `y`, temperature in Celsius.
- `z`, DPA value.

Output unit expected: relative true strain.

### K factors

#### K
Coefficients for cyclic stress-strain curve. If not provided, no cyclic stress strain curve will be available.

Input parameters are:

- `x`, temperature in Celsius.

Output unit expected: MPa.

#### m
Coefficients for cyclic stress-strain curve. If not provided, no cyclic stress strain curve will be available.

Input parameters are:

- `x`, temperature in Celsius.

Output unit expected: N.A.

#### Keps
Coefficient for elastic follow up. (Used in fatigue)

Input parameters are:

- `x`, temperature in Celsius.
- `y`, stress in Pa.

Output unit expected: N.A.

#### Kmu
Coefficient for multiaxial Poisson's ratio. (Used in fatigue)

Input parameters are:

- `x`, temperature in Celsius.
- `y`, stress in Pa.

Output unit expected: N.A.

#### Keff_rec
Used to compute the effective bending shape factor.

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA value.

Output unit expected: N.A.

### Allowables
#### Sm

Allowable primary membrane stress intensity (under irradiation).

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

Output unit expected: Pa.

#### Smb

Allowable primary membrane stress intensity (under irradiation) for bolts.

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

Output unit expected: Pa.


#### Fatigue
See the [fatigue property format](#fatigue)


#### Se
Limit for combined primary plus secondary membrane stress intensity under irradiation (only SDC-IC).

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

Output unit expected: Pa.

#### Sd
Limit for total stress including peak and Triaxality Factor (TF)=2 under irradiation (only SDC-IC).

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

Output unit expected: Pa.

#### Sd_nopeak
Limit for total stress excluding peak and Triaxality Factor (TF)=2 under irradiation (only SDC-IC).

Input parameters are:

- `x`, temperature in Celsius.
- `y`, DPA.

Output unit expected: Pa.





