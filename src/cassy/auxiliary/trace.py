"""Structured tracing of intermediate results of a code assessment.

Tracing is inactive by default and every call in this module is then a cheap no-op.
Activate it with :func:`activate`, nest hierarchy information with :func:`scope` and
log values with :func:`record`. Records are stored as flat rows (one value per row),
so that the saved trace can be explored with plain pandas.
"""

from __future__ import annotations

import datetime
import functools
import json
import math
import os
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Callable, Generator
from typing import Any

import numpy as np
import pandas as pd

SCOPE_KEYS = (
    "module",
    "component",
    "item",
    "position",
    "event",
    "analysis",
    "rule_set",
    "rule",
    "equation",
)
RECORD_KEYS = ("kind", "name", "value", "text", "unit", "inputs", "source", "note")
COLUMNS = ("seq",) + SCOPE_KEYS + RECORD_KEYS

TRACE_FILE = "trace.csv.gz"
META_FILE = "trace_meta.json"


class Tracer:
    def __init__(self, metadata: dict | None = None) -> None:
        """Container of the recorded intermediate values.

        Parameters
        ----------
        metadata : dict | None, optional
            General information on the run (code, project, etc.), by default None
        """
        self.records: list[dict] = []
        self.metadata = dict(metadata or {})
        self.metadata.setdefault("created", datetime.datetime.now().isoformat())

    def to_dataframe(self) -> pd.DataFrame:
        """Return the records as a long-format DataFrame."""
        return pd.DataFrame(self.records, columns=list(COLUMNS))

    def save(self, folder: os.PathLike) -> str:
        """Save the trace as a compressed CSV plus a JSON file with metadata.

        Parameters
        ----------
        folder : os.PathLike
            Folder where to save the trace. It is created if missing.

        Returns
        -------
        str
            path to the saved trace table
        """
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, TRACE_FILE)
        self.to_dataframe().to_csv(path, index=False, compression="gzip")
        with open(os.path.join(folder, META_FILE), "w") as f:
            json.dump(self.metadata, f, indent=2, default=str)
        return path


_active: ContextVar[Tracer | None] = ContextVar("cassy_tracer", default=None)
_scope: ContextVar[dict] = ContextVar("cassy_trace_scope", default={})
_depth: ContextVar[int] = ContextVar("cassy_trace_depth", default=0)


def is_active() -> bool:
    return _active.get() is not None


@contextmanager
def activate(tracer: Tracer) -> Generator[Tracer, None, None]:
    """Make ``tracer`` the destination of all records issued in the context."""
    token = _active.set(tracer)
    scope_token = _scope.set({})
    try:
        yield tracer
    finally:
        _scope.reset(scope_token)
        _active.reset(token)


@contextmanager
def scope(**keys: Any) -> Generator[None, None, None]:
    """Add hierarchy keys (see SCOPE_KEYS) to all records issued in the context."""
    if _active.get() is None:
        yield
        return
    unknown = set(keys) - set(SCOPE_KEYS)
    if unknown:
        raise KeyError(f"Unknown trace scope keys: {unknown}")
    new_scope = dict(_scope.get())
    new_scope.update({k: None if v is None else str(v) for k, v in keys.items()})
    token = _scope.set(new_scope)
    try:
        yield
    finally:
        _scope.reset(token)


@contextmanager
def nested() -> Generator[bool, None, None]:
    """Suppress records issued inside the context. Yields True if this is the
    outermost nested call, i.e. the caller is the one that should record."""
    depth = _depth.get()
    token = _depth.set(depth + 1)
    try:
        yield depth == 0
    finally:
        _depth.reset(token)


def _to_number(value: Any) -> tuple[float | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, (bool, np.bool_)):
        return None, str(bool(value))
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value), None
    if isinstance(value, np.ndarray) and value.size == 1:
        return float(value.item()), None
    return None, str(value)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    return str(obj)


def record(
    name: str,
    value: Any,
    kind: str = "value",
    unit: str | None = None,
    inputs: Any = None,
    source: str | None = None,
    note: str | None = None,
) -> None:
    """Record an intermediate value in the active tracer (no-op if inactive).

    Parameters
    ----------
    name : str
        name of the quantity (e.g. 'Sm', 'allowable 1').
    value : Any
        numeric value or text (e.g. the selected branch).
    kind : str, optional
        category of the record: input, stress, material, factor, allowable,
        result, branch, value. By default 'value'.
    unit : str | None, optional
        unit of measure of the value.
    inputs : Any, optional
        inputs used to compute the value (JSON serialized).
    source : str | None, optional
        where the value comes from (e.g. material name).
    note : str | None, optional
        free text, e.g. the formula used.
    """
    tracer = _active.get()
    if tracer is None or _depth.get() > 0:
        return
    number, text = _to_number(value)
    if number is not None and math.isnan(number):
        text = "nan"
    row = dict(_scope.get())
    row.update(
        seq=len(tracer.records),
        kind=kind,
        name=name,
        value=number,
        text=text,
        unit=unit,
        inputs=None if inputs is None else json.dumps(inputs, default=_json_default),
        source=source,
        note=note,
    )
    tracer.records.append(row)


def traced_method(func: Callable) -> Callable:
    """Decorator for material methods: record the returned value once, hiding the
    property calls performed internally."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if _active.get() is None:
            return func(self, *args, **kwargs)
        with nested() as outermost:
            result = func(self, *args, **kwargs)
        if outermost:
            inputs = {"args": list(args), **kwargs} if kwargs else list(args)
            record(
                func.__name__,
                result,
                kind="material",
                inputs=inputs,
                source=getattr(self, "name", None),
            )
        return result

    return wrapper


def load_trace(folder: os.PathLike) -> pd.DataFrame:
    """Load a trace saved with :meth:`Tracer.save`.

    Parameters
    ----------
    folder : os.PathLike
        folder containing the trace files.

    Returns
    -------
    pd.DataFrame
        long-format table of records. Metadata are available in ``df.attrs``.
    """
    df = pd.read_csv(
        os.path.join(folder, TRACE_FILE),
        compression="gzip",
        dtype={k: "string" for k in SCOPE_KEYS + RECORD_KEYS if k != "value"},
    )
    meta_path = os.path.join(folder, META_FILE)
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            df.attrs["metadata"] = json.load(f)
    return df
