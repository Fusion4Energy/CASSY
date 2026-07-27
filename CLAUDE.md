# CLAUDE.md — CASSY

CASSY automates nuclear structural integrity assessments (SDC-IC, RCC-MR, RCC-MRx, EN 13445) against linearized FEM stress tensors, producing Word/Excel reports. See [README.md](README.md) for the full project description.

## Commands

```bash
pip install -e .[dev]    # editable install with dev dependencies
pytest                   # run all tests
pytest --cov=cassy       # with coverage
ruff check src/          # lint
```

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

## Testing

Tests mirror `src/cassy/` under `tests/`. Each subdirectory has a `res/` folder with CSV stress tensors, YAML materials, and config files. Integration tests for runners live in `tests/runners/paths/` and `tests/runners/bolts/`.

`setuptools_scm` drives versioning from git tags; `_version.py` is auto-generated.
