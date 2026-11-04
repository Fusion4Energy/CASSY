from __future__ import annotations

import re
from typing import TYPE_CHECKING

from cassy.auxiliary.types import LoadTerm

if TYPE_CHECKING:
    import pandas as pd
# import xlwings as xw


# helper func for sort
def helper_func_sort(item: str) -> int:
    _, num = item.split("_")
    num, _ = num.split(".")
    return int(num)


def stripfunc(string: str) -> str:
    return string.strip("$")


# def is_excel_installed() -> bool:
#     # check if excel is installed
#     try:
#         xw.App(visible=False).quit()
#         return True
#     except xw.XlwingsError:
#         logging.warning("Excel is not installed on this system.")
#         return False
#     except AttributeError:
#         logging.warning("No active engine of excel.")
#         return False


# optional column of the input CSVs, allows to share one file among several
# submodels/flanges
COMPONENT_COLUMN = "component"


def select_component(df: pd.DataFrame, name: str, source: str = "") -> pd.DataFrame:
    """Keep only the rows of component ``name`` if ``df`` has a ``component``
    column, which is then dropped. ``df`` is returned unchanged otherwise.

    Raises
    ------
    ValueError
        If the column exists but no row belongs to ``name``.
    """
    if COMPONENT_COLUMN not in df.columns:
        return df
    labels = df[COMPONENT_COLUMN].astype(str).str.strip()
    mask = labels == str(name).strip()
    if not mask.any():
        available = sorted(labels.unique())
        raise ValueError(
            f"{source}: no rows with {COMPONENT_COLUMN} '{name}'. "
            f"Available: {available}"
        )
    return df.loc[mask].drop(columns=COMPONENT_COLUMN).reset_index(drop=True)


_LEGACY_TOKEN = re.compile(r"([+-]?)(\d+)")


def parse_legacy_combination(analysis: str, expr: str | int) -> list[LoadTerm]:
    """Convert the old (analysis, '4-3+2') notation into LoadTerms.

    Only used to migrate project files saved before per-term analyses existed.
    """
    text = str(expr).replace(" ", "")
    if not text or _LEGACY_TOKEN.sub("", text):
        raise ValueError(f"Invalid load step combination: {expr!r}")
    return [
        LoadTerm(sign or "+", str(analysis), int(step))
        for sign, step in _LEGACY_TOKEN.findall(text)
    ]


def format_terms(terms: list) -> str:
    """Readable form of a load combination, e.g. 'X:2 - Y:5'."""
    parts = []
    for i, term in enumerate(terms):
        if isinstance(term, dict):
            term = LoadTerm.from_dict(term)
        body = f"{term.analysis}:{term.step}"
        if i == 0:
            parts.append(body if term.sign == "+" else f"-{body}")
        else:
            parts.append(f"{term.sign} {body}")
    return " ".join(parts)
