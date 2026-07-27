# CLAUDE.md — CASSY

CASSY automates nuclear structural integrity assessments (SDC-IC, RCC-MR, RCC-MRx, EN 13445) against linearized FEM stress tensors, producing Word/Excel reports. See [README.md](README.md) for the full project description and the [wiki](../cassy.wiki/Home.md) for user documentation.

## Commands

```bash
pip install -e .[dev]          # editable install with dev dependencies
pytest                         # run all tests
pytest --cov=cassy             # with coverage
ruff check src/                # lint

python -m cassy --assess paths           # run paths assessment in cwd
python -m cassy --assess bolts           # run bolts assessment in cwd
python -m cassy --assess paths --fatigue # include fatigue
python -m cassy --pathsgui               # launch paths GUI (beta)
python -m cassy --boltsgui               # launch bolts GUI (beta)
python -m cassy --init paths             # scaffold input folder structure
```

Key optional CLI flags: `--root <dir>`, `--matlib <dir>`, `--norecap` (skip Word, dump df only), `--nomerge` (faster Word, no merged cells), `--onlybolts`.

## Source Layout

```
src/cassy/
  designcodes/   # Code and Rule implementations (sdcic.py, rccmr.py, rccmrx.py, …)
  paths/         # LinStress, ReferenceEvent, Path, Submodel, configuration parsing
  general/       # Material class (reads YAML), folder tree
  bolts/         # Bolt-specific assessment: geometry, config, code assessor
  runners/       # Top-level orchestrators: run_paths.py, run_bolts.py
  office/        # Word output via python-docx
  gui/           # Tkinter GUIs (excluded from coverage)
  additional_data/ # Bundled YAML material files and Word templates
tests/           # Mirrors src/cassy/; each subdirectory has res/ with fixtures
```

## Input Folder Structure (paths assessment)

```
<root>/
  config/        # one .xlsx config file per submodel (6 sheets: General, Paths,
  |              #   Load steps, Stresses, Reference Event, RE fatigue)
  stresses/      # one .csv per submodel — columns: path, analysis, loadstep,
                 #   pathpoint (begin/end), stress_type (Pm/Pb/F), Sx, Sy, Sz, Sxy, Sxz, Syz
```

See [`tests/runners/paths/`](tests/runners/paths/) for complete working examples.

## Core Abstractions

### Rule / Code

- `Rule` (abstract, `codes.py`): one assessment equation set. Key attributes:
  - `description: list[str]` — names each sub-rule; **length must match** `assess()` return list.
  - `damage_type: str` — groups rows in recap tables (`"Immediate"`, `"Ratcheting"`, …).
  - `sequential: bool` — `True` when sub-rules are hierarchical (screening + follow-up). Default `False`.
  - `assess(refEvent, material) → list[tuple[float, float]]` — returns `(stress_Pa, allowable_Pa)` per sub-rule.
- `Code` subclass holds `rules: dict[str, Rule]` and `damage_types: tuple[str, ...]`.

### Assessment DataFrame columns
`ID`, `Sub-Rule`, `Rule ID`, `Applied [MPa]`, `Allowable [MPa]`, `Result`, `Safety Margin`, `Damage Type`, `Screening`, `Service Level`, `T [°C]`, `DPA`, …

### Material
`Material` loads a YAML file. Properties (`Sm`, `Sy_min`, `E`, `Se`, …) accept `(T, dpa)` as positional args or a single `(T, dpa)` tuple (legacy). Bounds violations raise `OutOfBoundsError`.

## Key Conventions

**Units are Pascals internally.** `ReferenceEvent` stresses are in Pa. The row-builder in `linstress.py` converts to MPa via `* 1e-6` when writing DataFrame rows. Never mix units.

**`(None, None)` sub-rule entries are normal** — they mean "not applicable", not an error. The row-builder silently skips them via `except TypeError`. Example: `IC3131_1_2` returns `(None, None)` for Efficiency Index sub-rules when 3Sm passes.

**`assess()` returning `None`** (not a list) also means "not applicable" (e.g., service level D for some rules). The outer loop skips the whole rule.

**Sequential rules (3Sm → Efficiency Index):** When `rule.sequential = True` and the first sub-rule fails with follow-up sub-rules having real values, `linstress.py` marks that row `Screening=True`. `get_recap()` then excludes `Screening=True AND Result=FAILED` rows from the verdict — the follow-up (EI) rows are the final determination. The `Screening` column is dropped before Word output in `run_paths.py`.

**`damage_types` is on the `Code` instance**, not on `Rule`. Adding a new damage category requires updating `Code.damage_types`.

**Fatigue is a separate flow** (`computeVj` / `assess_fatigue`), gated by `fatigue=True` in runners and `code.fatigue` attribute.

**Values are stored raw (float) in the assessment DataFrames.** Rounding to integers for display happens only at output time: in `linstress.py` for paths (via `_round_ass_df` for Excel recap, rounding in `run_paths.py` for Word tables) and in `bolt_assess.py` for bolts.

## Design Code Interpretations

These interpretations are baked into the implementations — do not change them without updating the corresponding [wiki page](../cassy.wiki/Theory/code-interpretations.md):

- **Stress intensity** — always computed as Von Mises; for inertial loads (unsigned) the upper-limit formulation is used.
- **P_L** — always interpreted as the membrane stress Pm.
- **K = 1.5** — fixed for `IC3121_1_1_2a`; Keff is computed from it.
- **Fillet vs normal paths** — pressure-induced bending is secondary on fillet paths. Controlled by the `Type` column in the config and the `Is Pressure` flag per load.
- **EI in ratcheting (SDC-IC)** — only the route with secondary membrane stresses (thermal loads always present) is implemented. Short-duration overstress is handled via the `Is Short Overstress` flag.
- **Triaxiality factor** — hardcoded to 2 (conservative).
- **Goodman correction (bolts)** — not applied when the fatigue curve already has mean-stress dependence.

## Known Limitations

- Only linear elastic analysis routes.
- **Paths**: RCC-MRx, RCC-MR, SDC-IC only. No stress-based fatigue curves. RCC-MRx EI ratcheting rules are commented out. RCC-MRx significant irradiation rules (RB 3251.21) not implemented.
- **Bolts**: RCC-MRx, SDC-IC, EN 13445 (fatigue only). EN 13445 bolt fatigue: `T_min = 25 °C` is hardcoded for the $f_{t^*}$ parameter.

## Testing

Tests mirror `src/cassy/` under `tests/`. Each subdirectory has a `res/` folder with CSV stress tensors, YAML materials, and config files. Integration tests for runners live in `tests/runners/paths/` and `tests/runners/bolts/`.

`setuptools_scm` drives versioning from git tags; `_version.py` is auto-generated.
