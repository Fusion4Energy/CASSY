# Intermediate results trace

When CASSY results have to be compared with other tools, the final applied and allowable
stresses are often not enough to explain a discrepancy. The trace option records every
intermediate value used during the assessment so that it can be inspected afterwards.

## Enabling the trace

In the GUI, tick **Save trace of intermediate results (HTML + CSV)** in the run options.
From a script, pass ``trace=True`` to the runners:

```python
run_paths(root, configs, fatigue=True, trace=True)
run_bolts(root, configs, geoms, fatigue=True, trace=True)
```

The trace is off by default and has no impact on the results. The files are written to
``<root>/assessment/trace/``:

- ``index.html``: entry page with one link per submodel/flange.
- ``<component>.html``: browsable report, one per submodel/flange.
- ``trace.csv.gz``: all the recorded values as a flat table.
- ``trace_meta.json``: run information (module, codes, CASSY version, date).

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
| ``equation`` | sub-rule description |

The value itself is described by:

| Column | Meaning |
| --- | --- |
| ``kind`` | ``input``, ``stress``, ``material``, ``factor``, ``allowable``, ``result``, ``branch``, ``value`` |
| ``name`` | name of the quantity (e.g. ``Sm``, ``PmPb``, ``allowable 1``) |
| ``value`` / ``text`` | numeric value, or text for non-numeric entries (e.g. the selected branch) |
| ``unit`` | unit, when known. Paths stresses are in Pa, bolt stresses in MPa |
| ``inputs`` | inputs of material lookups, e.g. ``[T, dpa]`` |
| ``source`` | material name for material lookups |
| ``note`` | formula used (e.g. ``min(1.2 * n * Sm, Sy_min)``) |
| ``seq`` | recording order |

In particular, the trace contains:

- the reference event inputs (T, dpa, service level, welding factors, loads/actions);
- every material property interpolation, with its inputs;
- every combined stress used by a rule (Pm, PmPb, PQF, ...) and, for bolts, the single
  stress components (sigma_N, sigma_M, tau_T, ...);
- the formula and value of each allowable, the branch selected (service level, short
  duration overstress, Su > 700 MPa, ...) and the factors used;
- applied stress, allowable and their ratio for every equation;
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

The HTML report is a single self-contained file per submodel/flange. Records are organised
in collapsible sections (item, position, event, analysis, rule set, rule, equation). Each
section shows the maximum ``applied/allowable`` ratio found inside it, highlighted in red
when the ratio is 1 or more. The search box filters the rows and opens the sections that
contain the searched text (rule ID, property name, value, ...).

!!! note

    The trace of large submodels can contain hundreds of thousands of rows. The HTML report
    can then become slow to open, while the CSV remains easy to handle with pandas.
