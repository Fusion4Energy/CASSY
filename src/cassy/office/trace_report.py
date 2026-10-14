"""Self-contained HTML rendering of a cassy trace (see cassy.auxiliary.trace).

The trace data are embedded as JSON and rendered on demand by the browser, so that
large assessments stay responsive.
"""

from __future__ import annotations

import html
import json
import math
import os
import re

import pandas as pd

GROUP_LEVELS = ("item", "position", "event", "analysis", "rule_set", "rule", "equation")
RECORD_COLUMNS = ("kind", "name", "value", "text", "unit", "inputs", "source", "note")
RATIO = "applied/allowable"
EQUATION_RESULTS = ("applied", "allowable", RATIO)
FATIGUE_NAMES = ("N", "n cycles", "Vj")
MAX_ROWS = 500

_STYLE = """
*{box-sizing:border-box}
body{font-family:Segoe UI,Arial,sans-serif;font-size:13px;margin:0;color:#222}
header{position:sticky;top:0;z-index:2;background:#1f3a5f;color:#fff;
 padding:8px 16px;display:flex;align-items:center;gap:24px}
h1{font-size:18px;margin:0}
h2{font-size:16px;margin:4px 0 10px}
h3{font-size:14px;margin:6px 0}
#tabs button{background:none;border:none;color:#cfd8e3;font-size:14px;
 padding:6px 12px;cursor:pointer;border-bottom:3px solid transparent}
#tabs button.active{color:#fff;border-bottom-color:#f0b429}
.tab{padding:12px 16px}
#details:not([hidden]){display:flex;gap:16px;padding:0;height:calc(100vh - 50px)}
#nav{width:280px;flex:none;overflow:auto;border-right:1px solid #ddd;padding:8px}
#nav input{width:100%;padding:4px;margin-bottom:6px}
#nav summary{cursor:pointer;padding:3px 0;font-weight:600}
#nav .pos{color:#666;font-size:11px;margin:4px 0 2px 12px;text-transform:uppercase}
#nav a.ev{display:block;margin-left:20px;padding:1px 4px;color:#1f3a5f;
 text-decoration:none}
#nav a.ev:hover{background:#eef3f9}
#nav a.ev.sel{background:#1f3a5f;color:#fff}
#panel{flex:1;overflow:auto;padding:8px 16px}
.card{border:1px solid #ddd;border-radius:4px;padding:6px 10px;margin:8px 0}
.card.hl{border-color:#f0b429;box-shadow:0 0 0 2px #f0b42966}
.sub{color:#666;font-weight:normal;font-size:12px}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:6px 0}
.filters select{max-width:220px}
table{border-collapse:collapse;margin:4px 0 8px 0}
th,td{border:1px solid #ddd;padding:2px 6px;text-align:left;vertical-align:top}
th{background:#f3f3f3;position:sticky;top:0}
td.num{text-align:right;font-family:Consolas,monospace;white-space:nowrap}
tr.link{cursor:pointer}
tr.link:hover td{background:#eef3f9}
tr.hl td{background:#fff3c4}
tr.k-allowable td{background:#fff8e6}
tr.k-branch td{font-style:italic;color:#555}
.badge{margin-left:6px;font-size:11px;padding:0 4px;border-radius:3px;font-weight:normal}
.fail{color:#b00020;font-weight:bold}
.warn{color:#b26a00;font-weight:bold}
.ok{color:#1b7a1b}
.badge.fail{background:#fde7ea}.badge.warn{background:#fff1d6}.badge.ok{background:#e6f4e6}
.hint{color:#666}
.index{padding:12px 16px}
"""

_SCRIPT = r"""
(function () {
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const S = D.strings;
const MAX = __MAX__;
const s = i => (i < 0 ? '' : S[i]);

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : String(k));
  return e;
}
function fmt(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'string') return v === 'nan' ? 'no limit' : v;
  if (v === 0) return '0';
  const a = Math.abs(v);
  return (a >= 1e6 || a < 1e-3) ? v.toExponential(4) : String(parseFloat(v.toPrecision(6)));
}
const mpa = v => (typeof v === 'number' ? fmt(v / 1e6) : (v == null ? 'no limit' : fmt(v)));
const level = r => (r >= 1 ? 'fail' : r >= 0.9 ? 'warn' : 'ok');
const ratioCell = r => el('td', {class: 'num ' + (typeof r === 'number' ? level(r) : '')},
  typeof r === 'number' ? r.toFixed(3) : '');
const badge = r => (typeof r === 'number' ? el('span', {class: 'badge ' + level(r)}, r.toFixed(3)) : null);
const td = (x, cls) => el('td', cls ? {class: cls} : null, x);
function table(head, rows) {
  const t = el('table', null, el('tr', null, ...head.map(h => el('th', null, h))));
  t.append(...rows);
  return t;
}
const value = r => (r[3] !== null ? fmt(r[3]) : s(r[4]));

// --- indexes: events (item, position, event, analysis) and items ---
const EV = new Map();
const gEv = D.groups.map(g => {
  const k = g.slice(0, 4).join('|');
  if (!EV.has(k)) EV.set(k, {key: k, ids: g.slice(0, 4), rows: [], max: null});
  return k;
});
D.rows.forEach((r, i) => EV.get(gEv[r[0]]).rows.push(i));
D.summary.forEach(x => {
  const ev = EV.get(gEv[x[0]]);
  if (typeof x[3] === 'number' && (ev.max === null || x[3] > ev.max)) ev.max = x[3];
});
const ITEMS = new Map();
for (const ev of EV.values()) {
  const [item, pos] = ev.ids;
  if (!ITEMS.has(item)) ITEMS.set(item, {id: item, max: null, positions: new Map()});
  const it = ITEMS.get(item);
  if (!it.positions.has(pos)) it.positions.set(pos, []);
  it.positions.get(pos).push(ev);
  if (ev.max !== null && (it.max === null || ev.max > it.max)) it.max = ev.max;
}
const evLabel = ids => s(ids[2]) + (ids[3] >= 0 ? ' (' + s(ids[3]) + ')' : '');

// --- tabs ---
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => { t.hidden = t.id !== name; });
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
}
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
function goto(g) {
  showTab('details');
  renderEvent(g.slice(0, 4).join('|'), g);
}

// --- summary tab ---
function buildSummary() {
  const root = document.getElementById('summary');
  const govern = new Map(), fails = new Map();
  D.summary.forEach(x => {
    if (typeof x[3] !== 'number') return;
    const item = D.groups[x[0]][0];
    const cur = govern.get(item);
    if (!cur || x[3] > cur[3]) govern.set(item, x);
    if (x[3] >= 1) fails.set(item, (fails.get(item) || 0) + 1);
  });
  root.append(el('h2', null, 'Overview'), el('p', {class: 'hint'},
    'Governing equation of each item. Click a row to open its details.'));
  root.append(table(['Item', 'Max ratio', 'Position', 'Event', 'Rule', 'Equation', 'Equations with ratio \u2265 1'],
    [...ITEMS.values()].filter(it => govern.has(it.id)).map(it => {
      const x = govern.get(it.id), g = D.groups[x[0]];
      return el('tr', {class: 'link', onclick: () => goto(g)}, td(s(g[0])), ratioCell(x[3]),
        td(s(g[1])), td(evLabel(g)), td(s(g[5])), td(s(g[6])), td(fails.get(it.id) || 0, 'num'));
    })));

  root.append(el('h2', null, 'Equation results'));
  const form = el('form', {class: 'filters'});
  const uniq = lvl => [...new Set(D.summary.map(x => D.groups[x[0]][lvl]))].filter(v => v >= 0);
  const select = (label, lvl) => {
    const x = el('select', null, el('option', {value: ''}, 'All'), ...uniq(lvl).map(v => el('option', {value: v}, s(v))));
    form.append(el('label', null, label + ' ', x));
    return x;
  };
  const fItem = select('Item', 0), fPos = select('Position', 1), fEv = select('Event', 2), fRule = select('Rule', 5);
  const fMin = el('input', {type: 'number', step: 'any', placeholder: 'e.g. 0.9', style: 'width:80px'});
  form.append(el('label', null, 'Min ratio ', fMin), el('button', {type: 'submit'}, 'Apply'));
  const out = el('div');
  root.append(form, out);
  const num = x => (x.value === '' ? null : Number(x.value));
  function render() {
    const it = num(fItem), po = num(fPos), ev = num(fEv), ru = num(fRule), mn = num(fMin);
    const res = D.summary.filter(x => {
      const g = D.groups[x[0]];
      return (it === null || g[0] === it) && (po === null || g[1] === po) && (ev === null || g[2] === ev)
        && (ru === null || g[5] === ru) && (mn === null || (typeof x[3] === 'number' && x[3] >= mn));
    });
    const key = x => (typeof x[3] === 'number' ? x[3] : -1);
    res.sort((a, b) => key(b) - key(a));
    out.replaceChildren(
      el('p', {class: 'hint'}, res.length + ' equation results' +
        (res.length > MAX ? ', showing the ' + MAX + ' with the highest ratio' : '') + '. Click a row to open the details.'),
      table(['Item', 'Position', 'Event', 'Rule', 'Equation', 'Applied [MPa]', 'Allowable [MPa]', 'Ratio'],
        res.slice(0, MAX).map(x => {
          const g = D.groups[x[0]];
          return el('tr', {class: 'link', onclick: () => goto(g)}, td(s(g[0])), td(s(g[1])), td(evLabel(g)),
            td(s(g[5])), td(s(g[6])), td(mpa(x[1]), 'num'), td(mpa(x[2]), 'num'), ratioCell(x[3]));
        })));
  }
  form.addEventListener('submit', e => { e.preventDefault(); render(); });
  render();

  if (!D.fatigue.length) return;
  root.append(el('h2', null, 'Fatigue'));
  const usage = new Map();
  D.fatigue.forEach(f => {
    const k = f[0] + '|' + f[1];
    if (!usage.has(k)) usage.set(k, {item: f[0], pos: f[1], U: 0});
    if (typeof f[6] === 'number') usage.get(k).U += f[6];
  });
  root.append(table(['Item', 'Position', 'Cumulative usage \u03a3Vj'],
    [...usage.values()].sort((a, b) => b.U - a.U).slice(0, MAX).map(u =>
      el('tr', null, td(s(u.item)), td(s(u.pos)), ratioCell(u.U)))));
  root.append(table(['Item', 'Position', 'Event', 'n', 'N allowable', 'Vj'],
    [...D.fatigue].sort((a, b) => (b[6] || 0) - (a[6] || 0)).slice(0, MAX).map(f =>
      el('tr', {class: 'link', onclick: () => goto(f.slice(0, 4))}, td(s(f[0])), td(s(f[1])),
        td(evLabel(f)), td(fmt(f[4]), 'num'), td(fmt(f[5]), 'num'), ratioCell(f[6])))));
}

// --- details tab ---
const builders = new Map();
function buildNav() {
  const nav = document.getElementById('nav');
  const input = el('input', {type: 'search', placeholder: 'Filter items + Enter'});
  const list = el('div');
  const form = el('form', null, input);
  form.addEventListener('submit', e => {
    e.preventDefault();
    const q = input.value.trim().toLowerCase();
    list.querySelectorAll(':scope > details').forEach(d => { d.hidden = !!q && !d.dataset.name.includes(q); });
  });
  nav.append(form, list);
  for (const it of ITEMS.values()) {
    const d = el('details');
    d.dataset.name = s(it.id).toLowerCase();
    d.append(el('summary', null, s(it.id) || '(general)', badge(it.max)));
    const build = () => {
      if (d.dataset.built) return;
      d.dataset.built = '1';
      for (const [pos, evs] of it.positions) {
        if (pos >= 0) d.append(el('div', {class: 'pos'}, s(pos)));
        evs.forEach(ev => d.append(el('a', {href: '#', class: 'ev', 'data-key': ev.key,
          onclick: e => { e.preventDefault(); renderEvent(ev.key); }}, evLabel(ev.ids), badge(ev.max))));
      }
    };
    d.addEventListener('toggle', () => { if (d.open) build(); });
    builders.set(it.id, () => { build(); d.open = true; });
    list.append(d);
  }
}
function recTable(rows) {
  return table(['Kind', 'Name', 'Value', 'Unit', 'Inputs', 'Source', 'Note'], rows.map(r =>
    el('tr', {class: 'k-' + s(r[1])}, td(s(r[1])), td(s(r[2])), td(value(r), 'num'), td(s(r[5])),
      td(s(r[6])), td(s(r[7])), td(s(r[8])))));
}
function renderEvent(key, focus) {
  const ev = EV.get(key);
  if (!ev) return;
  const panel = document.getElementById('panel');
  const build = builders.get(ev.ids[0]);
  if (build) build();
  document.querySelectorAll('#nav a.ev').forEach(a => a.classList.toggle('sel', a.dataset.key === key));
  const selected = document.querySelector('#nav a.ev.sel');
  if (selected) selected.scrollIntoView({block: 'nearest'});

  panel.replaceChildren(el('h2', null, [s(ev.ids[0]), s(ev.ids[1]), evLabel(ev.ids)].filter(x => x).join(' / '), badge(ev.max)));
  const inputs = [], blocks = new Map();
  ev.rows.forEach(i => {
    const r = D.rows[i], g = D.groups[r[0]];
    if (g[4] < 0 && g[5] < 0) { inputs.push(r); return; }
    const k = g[4] + '|' + g[5];
    if (!blocks.has(k)) blocks.set(k, {set: g[4], rule: g[5], values: [], eqs: new Map()});
    const b = blocks.get(k);
    if (g[6] < 0) { b.values.push(r); return; }
    if (!b.eqs.has(g[6])) b.eqs.set(g[6], {});
    b.eqs.get(g[6])[s(r[2])] = r[3] !== null ? r[3] : s(r[4]);
  });
  if (inputs.length) panel.append(el('div', {class: 'card'}, el('h3', null, 'Inputs'), recTable(inputs)));
  let target = null;
  for (const b of blocks.values()) {
    const isFocus = focus && focus[4] === b.set && focus[5] === b.rule;
    const card = el('div', {class: 'card' + (isFocus ? ' hl' : '')},
      el('h3', null, s(b.rule) || s(b.set), b.rule >= 0 ? el('span', {class: 'sub'}, '  ' + s(b.set)) : null));
    if (b.values.length) card.append(recTable(b.values));
    if (b.eqs.size) card.append(table(['Equation', 'Applied [MPa]', 'Allowable [MPa]', 'Ratio', 'Note'],
      [...b.eqs].map(([eq, e]) => el('tr', {class: isFocus && focus[6] === eq ? 'hl' : ''}, td(s(eq)),
        td(e.applied === undefined ? '' : mpa(e.applied), 'num'),
        td(e.allowable === undefined ? '' : mpa(e.allowable), 'num'),
        ratioCell(e['applied/allowable']), td(e.equation || '')))));
    if (isFocus) target = card;
    panel.append(card);
  }
  if (target) target.scrollIntoView({block: 'start'}); else panel.scrollTop = 0;
}

// --- search tab ---
function buildSearch() {
  const root = document.getElementById('search');
  const kinds = [...new Set(D.rows.map(r => r[1]))].filter(k => k >= 0);
  const q = el('input', {type: 'search', size: 50, placeholder: 'e.g. Sm "Path 12" LS4'});
  const k = el('select', null, el('option', {value: ''}, 'All kinds'), ...kinds.map(x => el('option', {value: x}, s(x))));
  const form = el('form', {class: 'filters'}, q, k, el('button', {type: 'submit'}, 'Search'));
  const out = el('div', null, el('p', {class: 'hint'},
    'Type and press Enter. All words must match (use quotes for exact phrases). ' +
    'Searched fields: item, position, event, rule, equation, name, value, inputs, source, note.'));
  root.append(form, out);
  let hay = null;
  form.addEventListener('submit', e => {
    e.preventDefault();
    const terms = [...q.value.toLowerCase().matchAll(/"([^"]+)"|(\S+)/g)].map(m => m[1] || m[2]);
    const kind = k.value === '' ? null : Number(k.value);
    if (!terms.length && kind === null) return;
    out.replaceChildren(el('p', {class: 'hint'}, 'Searching\u2026'));
    setTimeout(() => {
      if (!hay) {
        const gtxt = D.groups.map(g => g.map(s).join(' '));
        hay = D.rows.map(r => [gtxt[r[0]], s(r[2]), value(r), s(r[6]), s(r[7]), s(r[8])].join(' ').toLowerCase());
      }
      const res = [];
      for (let i = 0; i < D.rows.length; i++) {
        if (kind !== null && D.rows[i][1] !== kind) continue;
        if (terms.every(t => hay[i].includes(t))) res.push(i);
      }
      out.replaceChildren(
        el('p', {class: 'hint'}, res.length + ' matches' + (res.length > MAX ? ', showing the first ' + MAX : '') + '. Click a row to open the details.'),
        table(['Item', 'Position', 'Event', 'Rule', 'Equation', 'Kind', 'Name', 'Value', 'Unit', 'Inputs', 'Note'],
          res.slice(0, MAX).map(i => {
            const r = D.rows[i], g = D.groups[r[0]];
            return el('tr', {class: 'link k-' + s(r[1]), onclick: () => goto(g)}, td(s(g[0])), td(s(g[1])),
              td(evLabel(g)), td(s(g[5])), td(s(g[6])), td(s(r[1])), td(s(r[2])), td(value(r), 'num'),
              td(s(r[5])), td(s(r[6])), td(s(r[8])));
          })));
    }, 10);
  });
}

buildSummary();
buildNav();
buildSearch();
})();
"""

def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", name).strip("_") or "trace"


def _payload(df: pd.DataFrame) -> dict:
    """Compact, string-interned representation of the trace for the browser."""
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
        if value is None or pd.isna(value):
            value = None
        elif not math.isfinite(value):
            text, value = text or str(value), None
        else:
            value = float(f"{value:.6g}")
        rows.append(
            [g, intern(kind), intern(name), value, intern(text), intern(unit)]
            + [intern(inputs), intern(source), intern(note)]
        )
        if kind == "result" and name in EQUATION_RESULTS and scope[6] >= 0:
            equations.setdefault(g, {})[name] = value if value is not None else text
        if rec[3] == "fatigue" and name in FATIGUE_NAMES and value is not None:
            fatigue.setdefault(scope[:4], {})[name] = value

    return {
        "strings": strings,
        "groups": groups,
        "rows": rows,
        "summary": [
            [g, e.get("applied"), e.get("allowable"), e.get(RATIO)]
            for g, e in equations.items()
        ],
        "fatigue": [
            [*key, v.get("n cycles"), v.get("N"), v.get("Vj")]
            for key, v in fatigue.items()
        ],
    }


def _component_page(title: str, df: pd.DataFrame) -> str:
    data = json.dumps(_payload(df), separators=(",", ":"), allow_nan=False)
    # keep the embedded JSON from closing the script tag
    data = data.replace("</", "<\\/").replace("<!--", "<\\u0021--")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head><body>"
        f"<header><h1>{html.escape(title)}</h1><nav id='tabs'>"
        "<button data-tab='summary' class='active'>Summary</button>"
        "<button data-tab='details'>Details</button>"
        "<button data-tab='search'>Search</button></nav></header>"
        "<section id='summary' class='tab'></section>"
        "<section id='details' class='tab' hidden><aside id='nav'></aside>"
        "<main id='panel'><p class='hint'>Select a reference event on the left, "
        "or click a row in the Summary or Search tabs.</p></main></section>"
        "<section id='search' class='tab' hidden></section>"
        f"<script type='application/json' id='data'>{data}</script>"
        f"<script>{_SCRIPT.replace('__MAX__', str(MAX_ROWS))}</script>"
        "</body></html>"
    )


def _index_page(links: list[str], metadata: dict | None) -> str:
    meta_rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in (metadata or {}).items()
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>cassy assessment trace</title><style>{_STYLE}</style></head><body>"
        "<header><h1>cassy assessment trace</h1></header><div class='index'>"
        f"<table>{meta_rows}</table><ul>{''.join(links)}</ul></div></body></html>"
    )


def _max_ratio(df: pd.DataFrame) -> float | None:
    ratios = df.loc[(df["kind"] == "result") & (df["name"] == RATIO), "value"]
    ratios = ratios.dropna()
    return None if ratios.empty else float(ratios.max())


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

    links = []
    for component, group in df.groupby(components, sort=False):
        filename = _safe_filename(str(component)) + ".html"
        with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
            f.write(_component_page(f"Trace - {component}", group))
        worst = _max_ratio(group)
        badge = ""
        if worst is not None:
            css = "fail" if worst >= 1 else "warn" if worst >= 0.9 else "ok"
            badge = f" <span class='badge {css}'>max ratio {worst:.3f}</span>"
        links.append(
            f"<li><a href='{html.escape(filename)}'>{html.escape(str(component))}"
            f"</a>{badge}</li>"
        )

    index = os.path.join(folder, "index.html")
    with open(index, "w", encoding="utf-8") as f:
        f.write(_index_page(links, metadata))
    return index
