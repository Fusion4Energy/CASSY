"""Self-contained HTML rendering of a cassy trace (see cassy.auxiliary.trace)."""

from __future__ import annotations

import html
import os
import re

import pandas as pd

TREE_LEVELS = ("item", "position", "event", "analysis", "rule_set", "rule", "equation")
TABLE_COLUMNS = ("kind", "name", "value", "unit", "inputs", "source", "note")
RATIO = "applied/allowable"

_STYLE = """
body{font-family:Segoe UI,Arial,sans-serif;font-size:13px;margin:16px;color:#222}
h1{font-size:20px}
#bar{position:sticky;top:0;background:#fff;padding:6px 0;border-bottom:1px solid #ccc}
#bar input{width:320px;padding:4px}
details{margin:2px 0 2px 14px;border-left:1px solid #ddd;padding-left:6px}
summary{cursor:pointer;padding:2px 0}
summary .lvl{color:#888;font-size:11px;margin-right:4px}
.fail{color:#b00020;font-weight:bold}
.ok{color:#1b7a1b}
.ratio{margin-left:8px;font-size:11px}
table{border-collapse:collapse;margin:4px 0 6px 0}
th,td{border:1px solid #ddd;padding:2px 6px;text-align:left;vertical-align:top}
th{background:#f3f3f3}
td.num{text-align:right;font-family:Consolas,monospace}
tr.k-result td{background:#f4f8ff}
tr.k-allowable td{background:#fff8e6}
tr.k-branch td{font-style:italic}
"""

_SCRIPT = """
function filterTrace(q){
  q=q.trim().toLowerCase();
  document.querySelectorAll('tr.rec').forEach(function(tr){
    tr.style.display=(!q||tr.textContent.toLowerCase().indexOf(q)>=0)?'':'none';
  });
  document.querySelectorAll('details').forEach(function(d){
    var hit=!q||d.textContent.toLowerCase().indexOf(q)>=0;
    d.style.display=hit?'':'none';
    if(q&&hit){d.open=true;}
  });
}
function toggleAll(open){
  document.querySelectorAll('details').forEach(function(d){d.open=open;});
}
"""


def _fmt_value(row: pd.Series) -> str:
    value = row.get("value")
    if value is not None and not pd.isna(value):
        return f"{value:.6g}"
    text = row.get("text")
    return "" if text is None or pd.isna(text) else str(text)


def _cell(value) -> str:
    return "" if value is None or pd.isna(value) else html.escape(str(value))


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    head = "".join(f"<th>{c}</th>" for c in TABLE_COLUMNS)
    rows = []
    for _, row in df.iterrows():
        kind = _cell(row["kind"])
        cells = []
        for col in TABLE_COLUMNS:
            if col == "value":
                cells.append(f'<td class="num">{html.escape(_fmt_value(row))}</td>')
            else:
                cells.append(f"<td>{_cell(row[col])}</td>")
        rows.append(f'<tr class="rec k-{kind}">{"".join(cells)}</tr>')
    return f"<table><tr>{head}</tr>{''.join(rows)}</table>"


def _ratio_badge(df: pd.DataFrame) -> str:
    ratios = df.loc[(df["kind"] == "result") & (df["name"] == RATIO), "value"]
    ratios = ratios.dropna()
    if ratios.empty:
        return ""
    worst = ratios.max()
    css = "fail" if worst >= 1 else "ok"
    return f'<span class="ratio {css}">max {RATIO} = {worst:.3g}</span>'


def _render(df: pd.DataFrame, levels: tuple[str, ...]) -> str:
    if not levels:
        return _table(df)
    level, rest = levels[0], levels[1:]
    keys = df[level]
    if keys.isna().all():
        return _render(df, rest)
    parts = [_table(df[keys.isna()])]
    for value, group in df[keys.notna()].groupby(level, sort=False):
        summary = (
            f'<span class="lvl">{level.replace("_", " ")}</span>'
            f"{html.escape(str(value))}{_ratio_badge(group)}"
        )
        parts.append(
            f"<details><summary>{summary}</summary>{_render(group, rest)}</details>"
        )
    return "".join(parts)


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style>"
        f"<script>{_SCRIPT}</script></head><body>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    )


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", name).strip("_") or "trace"


def write_html(df: pd.DataFrame, folder: os.PathLike, metadata: dict | None = None):
    """Write one HTML report per component plus an index page.

    Parameters
    ----------
    df : pd.DataFrame
        trace table as produced by Tracer.to_dataframe() or load_trace().
    folder : os.PathLike
        output folder.
    metadata : dict | None, optional
        run information shown in the index page.

    Returns
    -------
    str
        path to the index page.
    """
    os.makedirs(folder, exist_ok=True)
    df = df.sort_values("seq")
    components = df["component"].fillna("General")

    bar = (
        "<div id='bar'><input placeholder='Search (rule, property, value...)' "
        "oninput='filterTrace(this.value)'> "
        "<button onclick='toggleAll(true)'>Expand all</button> "
        "<button onclick='toggleAll(false)'>Collapse all</button></div>"
    )

    links = []
    for component, group in df.groupby(components, sort=False):
        filename = _safe_filename(str(component)) + ".html"
        body = bar + _render(group, TREE_LEVELS)
        with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
            f.write(_page(f"Trace - {component}", body))
        links.append(
            f"<li><a href='{html.escape(filename)}'>{html.escape(str(component))}"
            f"</a>{_ratio_badge(group)}</li>"
        )

    meta_rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in (metadata or {}).items()
    )
    body = f"<table>{meta_rows}</table><ul>{''.join(links)}</ul>"
    index = os.path.join(folder, "index.html")
    with open(index, "w", encoding="utf-8") as f:
        f.write(_page("cassy assessment trace", body))
    return index
