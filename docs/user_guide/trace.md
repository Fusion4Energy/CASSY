# Intermediate results trace

When CASSY results have to be compared with other tools, the final applied and allowable
stresses are often not enough to explain a discrepancy. The trace option records every
intermediate value used during the assessment so that it can be inspected afterwards.

## Enabling the trace

In the GUI, tick **Save trace of intermediate results (HTML + CSV)** in the run options.
The option is saved in the project file (``"trace": true`` in ``run_options``), so it is
also used when the project is run from the command line with ``python -m cassy --run``.
From a script, pass ``trace=True`` to the runners:

```python
run_paths(root, configs, fatigue=True, trace=True)
run_bolts(root, configs, geoms, fatigue=True, trace=True)
```

The trace is off by default and has no impact on the results. The files are written to
``<root>/assessment/trace/``:

- ``index.html``: entry page with one row per submodel/flange: verdict, highest
  applied/allowable ratio and where it occurs, highest cumulative fatigue usage ΣVj,
  failed items per damage type, number of failed equations and of warnings. With a
  single submodel/flange it opens its report directly.
- ``<component>.html``: browsable report, one per submodel/flange (see
  [HTML report](#html-report)).
- ``trace.csv.gz``: all the recorded values as a flat table.
- ``trace_meta.json``: run information (module, codes, CASSY version, date) and the
  damage type (Immediate, Ratcheting) under which each rule is reported.

## What is recorded

Each row of the trace is a single value. Its position in the assessment is identified by
the following columns (empty when not applicable):

| Column | Meaning |
| --- | --- |
| ``module`` | ``paths`` or ``bolts`` |
| ``component`` | submodel or flange name |
| ``item`` | path number or bolt ID |
| ``position`` | ``begin``/``end`` for paths, ``bolt``/``insert base material`` for bolts |
| ``event`` | reference event ID |
| ``analysis`` | ``immediate`` or ``fatigue`` |
| ``rule_set`` | rule set (extended description) |
| ``rule`` | rule ID (e.g. ``IC 3121.1.1.2a``) |
| ``equation`` | sub-rule description. When a rule has two sub-rules with the same description, ``(eq. n)`` is appended (e.g. ``Efficiency Index (eq. 2)``) |

The value itself is described by:

| Column | Meaning |
| --- | --- |
| ``kind`` | ``input``, ``stress``, ``material``, ``factor``, ``allowable``, ``result``, ``branch``, ``warning``, ``value`` |
| ``name`` | name of the quantity (e.g. ``Sm``, ``PmPb``, ``allowable 1``) |
| ``value`` / ``text`` | numeric value, or text for non-numeric entries (e.g. the selected branch). A NaN value is stored as ``text == "nan"``: the HTML report shows it as *no limit* for allowables and equation results, *not defined (NaN)* otherwise |
| ``unit`` | unit, when known. Paths stresses, allowables, stress-like material properties and equation results are in Pa, bolt stress components in MPa |
| ``inputs`` | inputs of material lookups, e.g. ``{"T": 69.6, "dpa": 0.0}`` (a plain list when the argument names are not known) |
| ``source`` | material name for material lookups. For the ``applied`` and ``allowable`` results of an equation, the name of the recorded quantity compared (e.g. ``PmPb`` and ``allowable 2``, or ``Mean stress (all)`` for bolts) |
| ``note`` | formula used (e.g. ``min(1.2 * n * Sm, Sy_min)``) |
| ``seq`` | recording order |

Identical records issued in the same scope (e.g. the same property looked up twice
with the same inputs) are stored only once.

In particular, the trace contains:

- the reference event inputs (T, dpa, service level, welding factors, loads/actions);
- every material property interpolation, with its inputs;
- every combined stress used by a rule (Pm, PmPb, PQF, ...) and, for bolts, the single
  stress components (sigma_N, sigma_M, tau_T, ...);
- the formula and value of each allowable, the branch selected (service level, short
  duration overstress, Su > 700 MPa, ...) and the factors used;
- applied stress, allowable and their ratio for every equation (``result`` records
  named ``applied`` and ``allowable`` in Pa, and ``applied/allowable``), linked to the
  quantities they come from. Rules not applicable and equations not evaluated are
  recorded as a ``branch``;
- the screening equations of sequential rules (e.g. the SDC-IC 3Sm rule, superseded by
  the efficiency index), recorded as a ``screening`` branch;
- the calculation warnings (``kind == "warning"``), e.g. a property out of its bounds
  or a curve not available for the material, with the assumption made;
- all fatigue intermediate values and the resulting Vj.

## Exploring the trace in Python

The trace can be loaded with pandas only. ``load_trace`` is a convenience function that also
attaches the metadata:

```python
from cassy.auxiliary.trace import load_trace

df = load_trace("<root>/assessment/trace")
df.attrs["metadata"]

# everything that led to a specific rule result
sel = df[
    (df["item"] == "Path 1")
    & (df["position"] == "begin")
    & (df["event"] == "RE1")
    & (df["rule"] == "IC 3121.1.1.2a")
]
sel[["equation", "kind", "name", "value", "text", "unit", "inputs", "note"]]

# all Sm interpolations performed
df[(df["kind"] == "material") & (df["name"] == "Sm")]
```

### Comparing with another tool

Put the results of the other tool in a table with the same identifying columns and merge:

```python
import pandas as pd

other = pd.read_excel("other_tool.xlsx")  # columns: item, event, rule, name, value_other
keys = ["item", "event", "rule", "name"]
cassy = df[df["kind"].isin(["allowable", "material", "stress"])][keys + ["value"]]
cmp = cassy.merge(other, on=keys)
cmp["rel diff"] = (cmp["value"] - cmp["value_other"]) / cmp["value_other"]
cmp[cmp["rel diff"].abs() > 0.01]
```

## HTML report

The HTML report is a single self-contained file per submodel/flange, with two tabs.
The browser address changes with each view, so the back button works and a link to an
event, an equation or a filtered table can be shared.

- **Summary**: the verdict of the component and the key figures. These are the highest
  applied/allowable ratio and the highest cumulative fatigue usage, both with their
  location, the counts of failed, OK and not required equations, of equations near
  the limit and of warnings. The failed and near the limit counts open the matching
  equations in *Explore*. Below them:
    - the *Recap by damage type*: one row per path/bolt with the verdict of immediate
      damage, ratcheting and fatigue in separate columns. Each cell gives the highest
      ratio (ΣVj for fatigue) and where it occurs, and links to that calculation. Rules
      are grouped as in the Word recap: for bolts all the code rules are immediate damage.
      The damage type of each rule is stored in ``trace_meta.json`` (rules missing there
      are taken as immediate). Items can be filtered by name, restricted to the failed
      ones and sorted with the failed first;
    - the *Needs attention* list: failed equations, positions with cumulative fatigue
      usage ΣVj ≥ 1 and calculation warnings (grouped by message), each linking to the
      detailed calculation;
    - the *Utilisation map*: one row per path/bolt and one column per rule equation
      (plus fatigue ΣVj). Each cell holds the highest ratio over all positions and
      reference events. Cells are coloured green, amber (≥ 0.9) or red (≥ 1); cells
      where only a superseded screening equation failed are marked separately, and a
      ``*`` flags superseded screening failures. Items can be filtered by name and by
      minimum ratio, and sorted worst first.
- **Explore**: the list of items on the left (filter by name, sort in assessment order
  or worst first) and, until an item is opened, a table with two modes:
    - *Equation results*: every equation result (applied, allowable, ratio, verdict),
      filtered by verdict and minimum ratio;
    - *All values*: every recorded value, filtered by kind.

    Both modes have a free text search (all the words must match, quotes for exact
    phrases) and filters on position, event, rule and equation; the item filter of the
    list also applies. The columns can be sorted and the table can be exported to CSV.
    The first 500 rows are shown, the export contains all of them. The filters are kept
    in the browser address.

    Clicking an item or a row opens the item or the calculation:
    - the *item page* has one section per position, with a table with events as rows
      and equations as columns, together with the event inputs (T, dpa, service level,
      loading category, loads). Each cell gives the ratio (``n.r.`` when not required,
      ``s`` for a superseded screening equation) and opens its calculation. For fatigue,
      the n cycles, N allowable and Vj of each event and the cumulative usage ΣVj;
    - the *event page* shows the warnings, the reference event inputs and each rule as a
      calculation: the applied stress and allowable (with the quantity and formula they
      come from), the ratio and the verdict, followed by all the intermediate values of
      the rule. The equation or value the page was opened from is highlighted.

    *prev*/*next* buttons move between items and between the events of an item.
    Stresses are shown in MPa.

Verdicts use the same definitions as the Excel and Word outputs: ``FAILED`` when the
applied stress is not lower than the allowable, ``Assessment not required`` when there is
no limit. A failed screening equation (e.g. the 3Sm rule followed by the efficiency
index) is marked as *screening* and, as in the Word recap, does not count in the verdict.

!!! note

    The trace of large submodels can contain hundreds of thousands of rows. The HTML report
    can then become slow to open, while the CSV remains easy to handle with pandas.

## 3D location map

Paths and bolts are identified only by their IDs. To see where they are, a locations
CSV can be given in the *General* tab of the GUIs: a single file with the locations of
the items of all the submodels/flanges. Optionally, a geometry of each submodel/flange
can be given in the *Submodels* (paths) or *Flanges* (bolts) tab. These files are only
used to draw the report: they have no effect on the assessment. They are stored in the
project file (``locations_file`` of the run options, ``geometry_file`` of each
submodel/flange) and, from a script, are passed to the runners as
``geometry={name: (locations csv, geometry file)}``.

The **locations CSV** of the paths has one row per path, drawn as the segment from
point i to point j:

| Column | Meaning |
| --- | --- |
| ``component`` | submodel name: only the rows of the submodel are used, so one file can hold the paths of all the submodels |
| ``path_number`` | path number, as in the assessment |
| ``xi``, ``yi``, ``zi`` | first point of the path, in the units of the geometry |
| ``xj``, ``yj``, ``zj`` | second point of the path |

The **locations CSV** of the bolts has one row per bolt:

| Column | Meaning |
| --- | --- |
| ``flange`` | flange name: only the rows of the flange are used, so one file can hold the bolts of all the flanges |
| ``boltID`` | bolt ID, as in the assessment and in the actions file |
| ``x``, ``y``, ``z`` | position of the bolt, in the units of the geometry |
| ``nx``, ``ny``, ``nz`` | optional, axis of the bolt |

Any other column is ignored. Items without a location are reported in the log and not
drawn. The **geometry** is any surface or volume mesh readable by pyvista (STL, VTK,
OBJ, PLY, ...); it is decimated to 50,000 triangles at most to keep the report light.
Without a geometry only the items are drawn.

The map is part of the HTML report, so the trace option must be enabled. It appears
in the *Summary* tab, with the items coloured by their highest applied/allowable ratio
(or ΣVj), and next to the item and event pages of the *Explore* tab, where the item
open is highlighted and the view zooms on it. Hovering an item shows its name and
ratio, clicking it opens it. The model can be shown as x-ray (default, to see the
paths through the thickness), solid or hidden.

!!! note

    The 3D view loads the [three.js](https://threejs.org) library from the internet
    when the report is opened. Without internet access the rest of the report works as
    usual and the 3D view is not shown.

## Adding a rule

When writing a new rule, record its allowables (``record_allowables``) and declare the
quantities compared by each returned equation just before returning them, so that the
trace and the HTML report can link every equation to its stress and allowable:

```python
trace.equation_terms(("Pm", "allowable 1"), ("PmPb", "allowable 2"))
return [(stress1, allowable1), (stress2, allowable2)]
```

The names must be those of recorded values: path stresses are recorded with the name of
the ``ReferenceEvent`` property, bolt stresses with ``bolt_stress_name(group, key)``.
A stress computed inside the rule must be recorded first (``trace.record(..., kind="stress")``).
