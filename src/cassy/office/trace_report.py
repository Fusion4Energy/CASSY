"""Self-contained HTML rendering of a cassy trace (see cassy.auxiliary.trace).

The trace data are embedded as JSON and rendered on demand by the browser, so that
large assessments stay responsive. The page logic and style are kept in
``trace_report.js`` and ``trace_report.css`` next to this module.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
from importlib.resources import files

import pandas as pd

from cassy.office.geometry_view import (
    geometry_payload,
    mesh_script,
    remove_stale_cache,
)

GROUP_LEVELS = ("item", "position", "event", "analysis", "rule_set", "rule", "equation")
RECORD_COLUMNS = ("kind", "name", "value", "text", "unit", "inputs", "source", "note")
RATIO = "applied/allowable"
FATIGUE_NAMES = ("N", "n cycles", "Vj")
# "screening" is the name used by older traces
SUPERSEDED_NAMES = ("superseded", "screening")
MAX_ROWS = 500
WARN_RATIO = 0.9
# three.js of the 3D location map, loaded from a CDN (the rest of the report works
# offline)
THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.170.0/"
# folder (next to the pages) of the meshes of the other flanges shown as context
CONTEXT_FOLDER = "geometry"

# verdicts of an equation, same wording of the excel/word outputs
OK, FAILED, NOT_REQUIRED = 0, 1, 2
VERDICTS = ("OK", "FAILED", "Assessment not required")
# damage types of the recap: the rules are grouped with the damage type recorded in the
# metadata (rules missing there are taken as immediate), fatigue comes from the fatigue
# analysis
IMMEDIATE, FATIGUE = "Immediate", "Fatigue"
DAMAGE_TYPES = (IMMEDIATE, "Ratcheting", FATIGUE)

_ASSETS = files("cassy.office")


def _asset(name: str) -> str:
    return _ASSETS.joinpath(name).read_text(encoding="utf-8")


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", name).strip("_") or "trace"


def _finite(value) -> float | None:
    if value is None or pd.isna(value) or not math.isfinite(value):
        return None
    return float(value)


def _verdict(applied: float | None, allowable: float | None) -> int | None:
    """Verdict of an equation, as in the excel output (applied < allowable)."""
    if allowable is None:
        return NOT_REQUIRED
    if applied is None:
        return None
    return OK if applied < allowable else FAILED


def _payload(df: pd.DataFrame, damage_types: dict | None = None) -> dict:
    """Compact, string-interned representation of the trace for the browser.

    ``damage_types`` maps the rule IDs to the damage type they are reported under.
    """
    strings: list[str] = []
    lookup: dict[str, int] = {}

    def intern(v) -> int:
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return -1
        v = str(v)
        idx = lookup.get(v)
        if idx is None:
            idx = lookup[v] = len(strings)
            strings.append(v)
        return idx

    groups: list[list[int]] = []
    group_idx: dict[tuple, int] = {}
    rows = []
    equations: dict[int, dict] = {}
    fatigue: dict[tuple, dict] = {}
    n_scope = len(GROUP_LEVELS)
    columns = list(GROUP_LEVELS + RECORD_COLUMNS)
    # pd.NA (from load_trace) is not usable in plain comparisons
    table = df[columns].astype(object)
    table = table.where(table.notna(), None)
    for rec in table.itertuples(index=False, name=None):
        scope = tuple(intern(v) for v in rec[:n_scope])
        g = group_idx.get(scope)
        if g is None:
            g = group_idx[scope] = len(groups)
            groups.append(list(scope))
        kind, name, value, text, unit, inputs, source, note = rec[n_scope:]
        text = None if text is None or pd.isna(text) else str(text)
        number = _finite(value)
        if value is not None and not pd.isna(value) and number is None:
            text = text or str(value)
        rows.append(
            [g, intern(kind), intern(name)]
            + [None if number is None else float(f"{number:.6g}"), intern(text)]
            + [intern(unit), intern(inputs), intern(source), intern(note)]
        )
        if scope[6] >= 0 and kind == "result" and name in ("applied", "allowable"):
            equations.setdefault(g, {})[name] = number
        elif scope[6] >= 0 and kind == "branch" and name in SUPERSEDED_NAMES:
            equations.setdefault(g, {})["superseded"] = True
        if rec[3] == "fatigue" and name in FATIGUE_NAMES and number is not None:
            fatigue.setdefault(scope[:4], {})[name] = number

    def rounded(v):
        return None if v is None else float(f"{v:.6g}")

    eq_rows = []
    for g, e in equations.items():
        if "applied" not in e:
            continue
        applied, allowable = e["applied"], e.get("allowable")
        ratio = None
        if applied is not None and allowable:
            ratio = applied / allowable
        eq_rows.append(
            [g, rounded(applied), rounded(allowable), rounded(ratio)]
            + [_verdict(applied, allowable), int(e.get("superseded", False))]
        )
    damage_types = damage_types or {}
    damage = {
        g[5]: damage_types.get(strings[g[5]], IMMEDIATE) for g in groups if g[5] >= 0
    }
    return {
        "strings": strings,
        "groups": groups,
        "rows": rows,
        # {rule: damage type}
        "damage": damage,
        # [group, applied [Pa], allowable [Pa], ratio, verdict, superseded]
        "equations": eq_rows,
        # [item, position, event, analysis, n cycles, N, Vj]
        "fatigue": [
            [*key, v.get("n cycles"), v.get("N"), v.get("Vj")]
            for key, v in fatigue.items()
        ],
    }


def _summary(payload: dict) -> dict:
    """Overall verdict of a component, shared by the index and the component page.

    The failed equations of a sequential rule superseded by the governing ones (the
    screening or the following equations, whichever has the lower ratio) do not
    affect the verdict (same as the word recap).
    """
    strings, groups = payload["strings"], payload["groups"]
    counts = dict.fromkeys(VERDICTS, 0)
    counts["superseded"] = 0
    worst, failed_items = None, set()
    # assessed and failed items for each damage type
    assessed: dict[str, set] = {}
    failed: dict[str, set] = {}
    for g, _, _, ratio, verdict, superseded in payload["equations"]:
        if verdict is None:
            continue
        item, damage = groups[g][0], payload["damage"].get(groups[g][5], IMMEDIATE)
        assessed.setdefault(damage, set()).add(item)
        if superseded and verdict == FAILED:
            counts["superseded"] += 1
            continue
        counts[VERDICTS[verdict]] += 1
        if verdict == FAILED:
            failed_items.add(item)
            failed.setdefault(damage, set()).add(item)
        if ratio is not None and (worst is None or ratio > worst[0]):
            worst = (ratio, g)
    usage: dict[tuple, float] = {}
    for item, pos, _, _, _, _, vj in payload["fatigue"]:
        if vj is not None:
            usage[(item, pos)] = usage.get((item, pos), 0.0) + vj
    worst_usage = max(usage.items(), key=lambda x: x[1], default=None)
    for (item, _), u in usage.items():
        assessed.setdefault(FATIGUE, set()).add(item)
        if u >= 1:
            failed_items.add(item)
            failed.setdefault(FATIGUE, set()).add(item)
    kind_warning = strings.index("warning") if "warning" in strings else None
    warnings = sum(1 for r in payload["rows"] if r[1] == kind_warning)

    def where(*idx):
        return " / ".join(strings[i] for i in idx if i >= 0)

    items = {g[0] for g in groups if g[0] >= 0}
    return {
        "failed": bool(failed_items),
        "counts": counts,
        "worst_ratio": None if worst is None else worst[0],
        "worst_where": None if worst is None else where(*groups[worst[1]][:3]),
        "worst_usage": None if worst_usage is None else worst_usage[1],
        "worst_usage_where": None if worst_usage is None else where(*worst_usage[0]),
        "items": len(items),
        "failed_items": len(failed_items),
        # {damage type: [failed items, assessed items]}, in the recap order
        "damage": {
            d: [len(failed.get(d, ())), len(assessed[d])]
            for d in sorted(assessed, key=_damage_order)
        },
        "warnings": warnings,
    }


def _damage_order(damage: str) -> tuple:
    if damage in DAMAGE_TYPES:
        return (DAMAGE_TYPES.index(damage), damage)
    return (len(DAMAGE_TYPES), damage)


def _json_for_script(obj) -> str:
    data = json.dumps(obj, separators=(",", ":"), allow_nan=False)
    # keep the embedded JSON from closing the script tag
    return data.replace("</", "<\\/").replace("<!--", "<\\u0021--")


def _component_page(title: str, payload: dict, metadata: dict | None) -> str:
    payload = dict(payload, summary=_summary(payload), title=title)
    payload["meta"] = metadata or {}
    payload["config"] = {"maxRows": MAX_ROWS, "warnRatio": WARN_RATIO}
    view3d = ""
    if payload.get("geometry"):
        imports = {
            "three": THREE_URL + "build/three.module.min.js",
            "three/addons/": THREE_URL + "examples/jsm/",
        }
        # meshes of the other flanges, registered before the 3D view starts (module
        # scripts are deferred); a missing file only hides that context
        context = "".join(
            f"<script src='{CONTEXT_FOLDER}/{html.escape(c['key'])}.js'></script>"
            for c in payload["geometry"].get("context", [])
        )
        view3d = (
            f"{context}<script type='importmap'>"
            f"{_json_for_script({'imports': imports})}</script>"
            f"<script type='module'>{_asset('trace_report_3d.js')}</script>"
        )
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_asset('trace_report.css')}"
        "</style></head><body>"
        f"<header><h1>{html.escape(title)}</h1><nav id='tabs'>"
        "<a href='#/summary' data-tab='summary'>Summary</a>"
        "<a href='#/explore' data-tab='explore'>Explore</a></nav></header>"
        "<main id='app'><p class='hint pad'>Loading…</p></main>"
        f"<script type='application/json' id='data'>{_json_for_script(payload)}"
        f"</script><script>{_asset('trace_report.js')}</script>"
        f"{view3d}</body></html>"
    )


def _format_meta(metadata: dict | None) -> str:
    rows = []
    for k, v in (metadata or {}).items():
        if isinstance(v, dict):
            continue
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v)
        elif k == "created":
            v = str(v).replace("T", " ")[:16]
        rows.append(f"<dt>{html.escape(str(k))}</dt><dd>{html.escape(str(v))}</dd>")
    return f"<dl class='meta'>{''.join(rows)}</dl>"


def _ratio_cell(value: float | None) -> str:
    if value is None:
        return "<td class='num na'>–</td>"
    css = "fail" if value >= 1 else "warn" if value >= WARN_RATIO else "ok"
    return f"<td class='num {css}'>{value:.3f}</td>"


def _index_page(components: list[tuple[str, str, dict]], metadata: dict | None) -> str:
    damages = sorted(
        {d for *_, s in components for d in s["damage"]}, key=_damage_order
    )
    rows = []
    for name, filename, summ in components:
        by_damage = ""
        for d in damages:
            if d not in summ["damage"]:
                by_damage += "<td class='num na'>–</td>"
                continue
            n_failed, n = summ["damage"][d]
            css = "fail" if n_failed else "ok"
            by_damage += f"<td class='num {css}'>{n_failed} / {n}</td>"
        status = "FAILED" if summ["failed"] else "OK"
        rows.append(
            f"<tr><td><a href='{html.escape(filename)}'>{html.escape(name)}</a></td>"
            f"<td><span class='verdict {status.lower()}'>{status}</span></td>"
            + _ratio_cell(summ["worst_ratio"])
            + f"<td>{html.escape(summ['worst_where'] or '')}</td>"
            + _ratio_cell(summ["worst_usage"])
            + by_damage
            + f"<td class='num'>{summ['counts']['FAILED']}</td>"
            + f"<td class='num'>{summ['warnings']}</td></tr>"
        )
    # a single component: go straight to its page
    redirect = ""
    if len(components) == 1:
        url = html.escape(components[0][1])
        redirect = f"<meta http-equiv='refresh' content='0; url={url}'>"
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"{redirect}<title>CASSY assessment trace</title>"
        f"<style>{_asset('trace_report.css')}</style></head><body>"
        "<header><h1>CASSY assessment trace</h1></header><main class='pad'>"
        f"{_format_meta(metadata)}<div class='scroll'><table class='grid'><thead><tr>"
        "<th>Component</th><th>Verdict</th><th>Max ratio</th><th>Where</th>"
        "<th>Max ΣVj</th>"
        + "".join(f"<th>{html.escape(d)}: failed items</th>" for d in damages)
        + "<th>Failed equations</th>"
        "<th>Warnings</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></main></body></html>"
    )


def _context(
    component: str, others: dict, folder: os.PathLike, cache: os.PathLike | None
) -> list[dict]:
    """Meshes of the other flanges shown with ``component`` (only their geometry, no
    items): [{"name": flange, "key": mesh script key}]. A file shared with the
    component or with another flange is shown once."""
    own = others.get(component)
    seen = {own}
    context = []
    for name, mesh in others.items():
        if name == component or mesh in seen:
            continue
        seen.add(mesh)
        key = mesh_script(mesh, os.path.join(folder, CONTEXT_FOLDER), cache)
        context.append({"name": name, "key": key})
    return context


def write_html(
    df: pd.DataFrame,
    folder: os.PathLike,
    metadata: dict | None = None,
    geometry: dict | None = None,
    stl_cache: os.PathLike | None = None,
):
    """Write one HTML report per component plus an index page.

    Parameters
    ----------
    df : pd.DataFrame
        trace table as produced by Tracer.to_dataframe() or load_trace().
    folder : os.PathLike
        output folder.
    metadata : dict | None, optional
        run information shown in the pages.
    geometry : dict | None, optional
        {component: (locations csv, geometry file)} of the components with a 3D
        location map (see cassy.office.geometry_view). The geometry file can be None.
        In the bolts reports, the geometries of the other flanges are shown as
        context, to help finding the way in the model.
    stl_cache : os.PathLike | None, optional
        folder where the simplified geometries are cached, by default no cache.

    Returns
    -------
    str
        path to the index page.
    """
    os.makedirs(folder, exist_ok=True)
    df = df.sort_values("seq")
    components = df["component"].fillna("General")

    module = (metadata or {}).get("module", "")
    # geometries of all the flanges, the context of each other in the 3D view
    others = {}
    if module == "bolts":
        others = {
            name: os.path.abspath(mesh)
            for name, (_, mesh) in (geometry or {}).items()
            if mesh
        }
    # meshes of a previous run in the same folder may be out of date
    context_folder = os.path.join(folder, CONTEXT_FOLDER)
    if os.path.isdir(context_folder):
        for name in os.listdir(context_folder):
            if name.endswith(".js"):
                os.remove(os.path.join(context_folder, name))

    pages = []
    for component, group in df.groupby(components, sort=False):
        filename = _safe_filename(str(component)) + ".html"
        payload = _payload(group, (metadata or {}).get("damage types"))
        if str(component) in (geometry or {}):
            locations, mesh = geometry[str(component)]
            items = [str(i) for i in group["item"].dropna().unique()]
            payload["geometry"] = geometry_payload(
                locations, mesh, module, items, str(component), stl_cache
            )
            if payload["geometry"] is not None:
                context = _context(str(component), others, folder, stl_cache)
                if context:
                    payload["geometry"]["context"] = context
        page = _component_page(str(component), payload, metadata)
        with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
            f.write(page)
        pages.append((str(component), filename, _summary(payload)))
    if stl_cache:
        remove_stale_cache([g[1] for g in (geometry or {}).values()], stl_cache)

    index = os.path.join(folder, "index.html")
    with open(index, "w", encoding="utf-8") as f:
        f.write(_index_page(pages, metadata))
    return index
