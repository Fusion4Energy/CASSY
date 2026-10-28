(function () {
'use strict';
// Data layout (see trace_report.py):
//   rows      [group, kind, name, value, text, unit, inputs, source, note]
//   groups    [item, position, event, analysis, rule_set, rule, equation]
//   equations [group, applied [Pa], allowable [Pa], ratio, verdict, superseded]
//   fatigue   [item, position, event, analysis, n cycles, N, Vj]
// All the text fields are indexes in D.strings (-1 when missing).
const D = JSON.parse(document.getElementById('data').textContent);
const S = D.strings;
const MAX = D.config.maxRows, WARN = D.config.warnRatio;
const R = {G: 0, KIND: 1, NAME: 2, VAL: 3, TEXT: 4, UNIT: 5, INPUTS: 6, SRC: 7, NOTE: 8};
const G = {ITEM: 0, POS: 1, EV: 2, AN: 3, SET: 4, RULE: 5, EQ: 6};
const E = {G: 0, APP: 1, ALW: 2, RATIO: 3, VERD: 4, SCREEN: 5};
const OK = 0, FAILED = 1, NOT_REQUIRED = 2;
const s = i => (i < 0 ? '' : S[i]);
const SIDX = new Map(S.map((x, i) => [x, i]));
const sid = x => (SIDX.has(x) ? SIDX.get(x) : -2);

// ---------- helpers ----------
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) e.append(k instanceof Node ? k : String(k));
  return e;
}
const td = (x, cls, title) => el('td', {class: cls, title}, x);
const natural = (a, b) => a.localeCompare(b, undefined, {numeric: true});
function fmt(v) {
  if (v === null || v === undefined) return '';
  if (typeof v !== 'number') return String(v);
  if (v === 0) return '0';
  const a = Math.abs(v);
  return (a >= 1e6 || a < 1e-3) ? v.toExponential(4) : String(parseFloat(v.toPrecision(6)));
}
const mpa = v => (typeof v === 'number' ? fmt(v / 1e6) : 'no limit');

// ---------- display mode ----------
// the equation results are shown as usage factor (applied/allowable, the stored
// ratio) or as safety margin (allowable/applied). Only the display changes: verdicts,
// colours and "worst first" orders always follow the ratio. The fatigue usage ΣVj
// stays a usage factor in both modes
const MODES = {
  uf: {label: 'Usage factor', name: 'applied/allowable ratio', col: 'Ratio', worst: 'max', Worst: 'Max',
    tile: 'Max applied / allowable', better: 'lower ratio'},
  sm: {label: 'Safety margin', name: 'allowable/applied safety margin', col: 'Margin', worst: 'min', Worst: 'Min',
    tile: 'Min allowable / applied', better: 'higher margin'},
};
let MODE = 'uf';
try { if (localStorage.getItem('cassy.mode') === 'sm') MODE = 'sm'; } catch (e) { /* ignore */ }
const T = () => MODES[MODE];
const isSM = () => MODE === 'sm';
// ratio -> displayed value, and back (the inversion is its own inverse)
const disp = r => (isSM() && typeof r === 'number' ? (r > 0 ? 1 / r : Infinity) : r);
// a displayed threshold on the "fail side" (ratio ≥ r is margin ≤ 1/r)
const atLeast = r => (isSM() ? '≤ ' : '≥ ') + fmt(disp(r));
const below = r => (isSM() ? '> ' : '< ') + fmt(disp(r));
const level = r => (r >= 1 ? 'fail' : r >= WARN ? 'warn' : 'ok');
function ratioTxt(r, digits) {
  if (typeof r !== 'number') return '';
  const v = disp(r);
  if (v === Infinity) return '∞';
  return v > 0 && (v < 1e-3 || v >= 1e4) ? v.toExponential(1) : v.toFixed(digits || 3);
}
// the fatigue usage is a usage factor in both modes
const usageTxt = (u, digits) => (u > 0 && u < 1e-3 ? u.toExponential(1) : u.toFixed(digits || 3));
// failed equation of a rule that could not be assessed (no applied stress)
const invalid = e => e[E.VERD] === FAILED && typeof e[E.APP] !== 'number';
const ratioCell = r => td(typeof r === 'number' ? ratioTxt(r) : '–', 'num ' + (typeof r === 'number' ? level(r) : 'na'));
// worst result of an item or event: the equations, or the fatigue usage u when it is
// higher (shown as such, it is a usage factor in both modes)
function badge(r, u, uLabel) {
  if (typeof u === 'number' && !(typeof r === 'number' && r >= u))
    return el('span', {class: 'badge ' + level(u), title: 'fatigue usage'}, (uLabel || 'ΣVj') + ' ' + usageTxt(u, 2));
  return typeof r === 'number' ? el('span', {class: 'badge ' + level(r), title: T().worst + ' ' + T().name}, ratioTxt(r, 2)) : null;
}
function verdictChip(verdict, screening) {
  if (verdict === FAILED && screening) return el('span', {class: 'verdict screening', title: 'Superseded by the governing equations of the sequential rule (' + T().better + '), not counted in the verdict'}, 'superseded');
  if (verdict === FAILED) return el('span', {class: 'verdict failed'}, 'FAILED');
  if (verdict === OK) return el('span', {class: 'verdict ok'}, 'OK');
  if (verdict === NOT_REQUIRED) return el('span', {class: 'verdict notreq', title: 'No allowable defined (no limit)'}, 'not required');
  return null;
}
const verdictText = (v, sc) => (v === FAILED && sc ? 'superseded' : v === FAILED ? 'FAILED' : v === OK ? 'OK' : v === NOT_REQUIRED ? 'Assessment not required' : '');
function displayValue(r) {
  // returns [value text, unit]
  const unit = s(r[R.UNIT]);
  if (r[R.VAL] !== null) return unit === 'Pa' ? [fmt(r[R.VAL] / 1e6), 'MPa'] : [fmt(r[R.VAL]), unit];
  const t = s(r[R.TEXT]);
  if (t !== 'nan') return [t, unit === 'Pa' ? 'MPa' : unit];
  const kind = s(r[R.KIND]);
  return [kind === 'allowable' || kind === 'result' ? 'no limit' : 'not defined (NaN)', ''];
}
function fmtInputs(i) {
  if (i < 0) return '';
  let x;
  try { x = JSON.parse(S[i]); } catch (e) { return S[i]; }
  const f = v => (typeof v === 'number' ? fmt(v) : Array.isArray(v) ? '(' + v.map(f).join(', ') + ')' : String(v));
  if (Array.isArray(x)) return x.length ? '(' + x.map(f).join(', ') + ')' : '';
  if (x && typeof x === 'object') return Object.entries(x).map(([k, v]) => k + ' = ' + f(v)).join(', ');
  return f(x);
}
function table(head, rows, opts) {
  const t = el('table', {class: opts && opts.class}, el('thead', null, el('tr', null, head.map(h => (h instanceof Node ? h : el('th', null, h))))));
  t.append(el('tbody', null, rows));
  return opts && opts.noscroll ? t : el('div', {class: 'scroll'}, t);
}
function debounce(f, ms) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => f(...a), ms); };
}
function download(name, text) {
  const a = el('a', {href: URL.createObjectURL(new Blob([text], {type: 'text/csv'})), download: name});
  document.body.append(a); a.click(); a.remove();
}
const csv = rows => rows.map(r => r.map(x => {
  const v = x === null || x === undefined ? '' : String(x);
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}).join(',')).join('\n');

// ---------- indexes ----------
const isFatigue = an => s(an) === 'fatigue';
const evLabel = ids => s(ids[2]) + (ids[3] >= 0 && s(ids[3]) !== 'immediate' ? ' (' + s(ids[3]) + ')' : '');
const EV = new Map();
const gEv = D.groups.map(g => {
  const k = g.slice(0, 4).join('|');
  if (!EV.has(k)) EV.set(k, {key: k, ids: g.slice(0, 4), rows: [], eqs: [], fat: null, max: null, eqMax: null, warnings: 0});
  return k;
});
const KIND_WARNING = sid('warning'), KIND_INPUT = sid('input');
D.rows.forEach((r, i) => {
  const ev = EV.get(gEv[r[R.G]]);
  ev.rows.push(i);
  if (r[R.KIND] === KIND_WARNING) ev.warnings++;
});
// effective ratio: a failed superseded equation of a sequential rule is not counted
const effective = e => (e[E.SCREEN] && e[E.VERD] === FAILED ? null : e[E.RATIO]);
const higher = (a, b) => (typeof b === 'number' && (a === null || b > a) ? b : a);
D.equations.forEach(e => {
  const ev = EV.get(gEv[e[E.G]]);
  ev.eqs.push(e);
  ev.eqMax = higher(ev.eqMax, effective(e));
  ev.max = higher(ev.max, effective(e));
});
D.fatigue.forEach(f => {
  const ev = EV.get(f.slice(0, 4).join('|'));
  if (!ev) return;
  ev.fat = f;
  ev.max = higher(ev.max, f[6]);
});
const ITEMS = new Map();
for (const ev of EV.values()) {
  const [item, pos] = ev.ids;
  // max: worst of the equations (eqMax) and of the fatigue usage (useMax)
  if (!ITEMS.has(item)) ITEMS.set(item, {id: item, max: null, eqMax: null, useMax: null, positions: new Map(), events: [], usage: new Map(), warnings: 0, failed: false, order: ITEMS.size});
  const it = ITEMS.get(item);
  if (!it.positions.has(pos)) it.positions.set(pos, []);
  it.positions.get(pos).push(ev);
  it.warnings += ev.warnings;
  for (const e of ev.eqs) {
    it.eqMax = higher(it.eqMax, effective(e));
    if (e[E.VERD] === FAILED && !e[E.SCREEN]) it.failed = true;
  }
  if (ev.fat && typeof ev.fat[6] === 'number') it.usage.set(pos, (it.usage.get(pos) || 0) + ev.fat[6]);
}
for (const it of ITEMS.values()) {
  for (const evs of it.positions.values()) it.events.push(...evs);
  for (const u of it.usage.values()) { it.useMax = higher(it.useMax, u); if (u >= 1) it.failed = true; }
  it.max = higher(it.eqMax, it.useMax);
}
const itemName = id => s(id) || '(general)';
// heatmap columns: one per rule equation, in assessment order
const COLS = [], COLIDX = new Map();
D.equations.forEach(e => {
  const g = D.groups[e[E.G]], k = g[G.RULE] + '|' + g[G.EQ];
  if (!COLIDX.has(k)) { COLIDX.set(k, COLS.length); COLS.push({rule: g[G.RULE], eq: g[G.EQ], set: g[G.SET]}); }
});
const HAS_FATIGUE = D.fatigue.length > 0;
// damage types of the recap (fatigue from the fatigue analysis, the rules from D.damage)
const FATIGUE = 'Fatigue';
const DAMAGES = ['Immediate', 'Ratcheting', FATIGUE];
const damageOf = g => D.damage[g[G.RULE]] || 'Immediate';
for (const d of Object.values(D.damage)) if (!DAMAGES.includes(d)) DAMAGES.splice(DAMAGES.length - 1, 0, d);

// ---------- 3D location map ----------
// drawn by trace_report_3d.js (only when locations were given) in the .view3d
// containers: this is the data it needs and the route it follows
const HAS_GEOMETRY = Boolean(D.geometry);
const view3d = (cls, ...kids) => (HAS_GEOMETRY ? el('div', {class: 'view3d ' + (cls || '')},
  el('p', {class: 'hint pad'}, 'Loading the 3D view (it needs internet access to load the three.js library)…'), ...kids) : null);
if (HAS_GEOMETRY) window.CASSY = {
  geometry: D.geometry, warnRatio: WARN, route: {view: null, item: null}, hasFatigue: D.fatigue.length > 0,
  items: new Map([...ITEMS.values()].map(it => [itemName(it.id), {max: it.max, eqMax: it.eqMax, useMax: it.useMax, failed: it.failed}])),
  open: name => go(itemHash(sid(name))),
  // display mode and its formatting, followed by the legend and the tooltips
  get mode() { return MODE; }, ratioTxt, atLeast, below, label: () => T(),
};

// ---------- routing ----------
const enc = i => encodeURIComponent(i < 0 ? '-' : S[i]);
const dec = t => (t === '-' ? -1 : sid(t));
const qs = o => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o || {})) if (v !== null && v !== undefined && v !== '') p.set(k, v);
  const t = p.toString();
  return t ? '?' + t : '';
};
const itemHash = id => '#/item/' + enc(id);
const evHash = (ids, focus) => '#/event/' + ids.slice(0, 4).map(enc).join('/') + qs(focus);
const groupHash = (g, row) => evHash(g, {rule: g[G.RULE] >= 0 ? s(g[G.RULE]) : null, eq: g[G.EQ] >= 0 ? s(g[G.EQ]) : null, row});
const go = h => { location.hash = h; };
const link = (text, h, cls) => el('a', {href: h, class: cls}, text);
function parse() {
  const h = location.hash.replace(/^#\/?/, '');
  const i = h.indexOf('?');
  const path = i < 0 ? h : h.slice(0, i);
  const parts = path.split('/').map(p => { try { return decodeURIComponent(p); } catch (e) { return p; } });
  return {view: parts[0] || 'summary', args: parts.slice(1), q: new URLSearchParams(i < 0 ? '' : h.slice(i + 1))};
}

// ---------- views ----------
const app = document.getElementById('app');
const views = {};
function view(name, build) {
  if (!views[name]) { views[name] = {node: el('section', {id: name}), state: {}}; build(views[name]); app.append(views[name].node); }
  for (const [k, v] of Object.entries(views)) v.node.hidden = k !== name;
  document.querySelectorAll('#tabs a').forEach(a => a.classList.toggle('active', a.dataset.tab === name));
  return views[name];
}
function route() {
  if (app.firstChild && app.firstChild.tagName === 'P') app.firstChild.remove();
  const r = parse();
  if (r.view === 'explore' || r.view === 'item' || r.view === 'event') { const v = view('explore', buildExplore); v.state.show(r); }
  else view('summary', buildSummary);
  window.scrollTo(0, 0);
  if (HAS_GEOMETRY) {
    const item = (r.view === 'item' || r.view === 'event') && r.args[0] !== '-' ? r.args[0] : null;
    window.CASSY.route = {view: item ? 'explore' : r.view === 'explore' ? 'explore' : 'summary', item};
    document.dispatchEvent(new CustomEvent('cassy:route', {detail: window.CASSY.route}));
  }
}
window.addEventListener('hashchange', route);

// display mode toggle, in the header: the views are rebuilt in the new mode (the
// explore filters are kept in the url, the scroll positions are restored)
const displayButtons = Object.entries(MODES).map(([k, m]) => el('button', {type: 'button', 'data-mode': k,
  title: k === 'uf' ? 'Show the results as applied/allowable' : 'Show the results as allowable/applied (fatigue usage ΣVj stays a usage factor)',
  onclick: () => setDisplay(k)}, m.label));
const markMode = () => displayButtons.forEach(b => b.classList.toggle('active', b.dataset.mode === MODE));
document.querySelector('header').append(el('span', {class: 'seg mode'}, displayButtons));
markMode();
function setDisplay(m) {
  if (m === MODE) return;
  MODE = m;
  try { localStorage.setItem('cassy.mode', m); } catch (e) { /* ignore */ }
  markMode();
  const panel = document.getElementById('panel'), y = window.scrollY, py = panel ? panel.scrollTop : 0;
  for (const k of Object.keys(views)) { views[k].node.remove(); delete views[k]; }
  if (HAS_GEOMETRY) document.dispatchEvent(new CustomEvent('cassy:mode', {detail: MODE}));
  route();
  setTimeout(() => {
    window.scrollTo(0, y);
    const p = document.getElementById('panel');
    if (p) p.scrollTop = py;
  }, 0);
}

// ---------- summary ----------
function buildSummary(v) {
  const root = v.node, sm = D.summary, c = sm.counts;
  root.className = 'pad';
  const meta = D.meta || {};
  const materials = [...new Set(D.rows.filter(r => r[R.SRC] >= 0).map(r => s(r[R.SRC])))];
  const info = [
    meta.module && 'Module: ' + meta.module,
    meta.codes && 'Code: ' + [].concat(meta.codes).join(', '),
    materials.length && 'Materials: ' + materials.join(', '),
    meta.created && 'Run: ' + String(meta.created).replace('T', ' ').slice(0, 16),
    meta['cassy version'] && 'CASSY ' + meta['cassy version'],
  ].filter(Boolean).join(' · ');
  root.append(el('p', {class: 'runinfo'}, info));

  // worst location links
  let worstEq = null;
  D.equations.forEach(e => { const r = effective(e); if (typeof r === 'number' && (!worstEq || r > worstEq[E.RATIO])) worstEq = e; });
  let worstUse = null;
  for (const it of ITEMS.values()) for (const [pos, u] of it.usage) if (!worstUse || u > worstUse.u) worstUse = {it, pos, u};
  const tile = (label, big, small, cls) => el('div', {class: 'tile ' + (cls || '')}, el('div', {class: 'label'}, label), el('div', {class: 'big'}, big), small ? el('div', {class: 'small'}, small) : null);
  const bar = el('div', {class: 'verdict-bar'},
    tile('Verdict', sm.failed ? 'FAILED' : 'OK', sm.failed ? sm.failed_items + ' of ' + sm.items + ' items failing' : 'all ' + sm.items + ' items pass', 'status ' + (sm.failed ? 'fail' : 'ok')),
    tile('Failed items by damage type', el('span', null, Object.entries(sm.damage).map(([d, [f]], i) =>
      el('span', {class: f ? 'fail' : 'ok'}, (i ? ' \u00b7 ' : '') + f)), ''),
    Object.keys(sm.damage).join(' \u00b7 ')));
  if (worstEq) {
    const g = D.groups[worstEq[E.G]];
    bar.append(tile(T().tile, el('span', {class: level(worstEq[E.RATIO])}, ratioTxt(worstEq[E.RATIO])),
      link([itemName(g[0]), s(g[1]), evLabel(g)].filter(Boolean).join(' / ') + ' – ' + s(g[G.EQ]), groupHash(g))));
  }
  if (worstUse) bar.append(tile('Max fatigue usage ΣVj', el('span', {class: level(worstUse.u)}, usageTxt(worstUse.u)),
    link(itemName(worstUse.it.id) + ' / ' + s(worstUse.pos), itemHash(worstUse.it.id))));
  bar.append(tile('Equations', String(c.FAILED + c.OK + c['Assessment not required']),
    el('span', null, link(c.FAILED + ' failed', '#/explore' + qs({verdict: 'FAILED'})), ' · ', c.OK + ' OK · ',
      c['Assessment not required'] + ' not required', c.superseded ? ' · ' + c.superseded + ' superseded' : '')));
  const near = D.equations.filter(e => { const r = effective(e); return typeof r === 'number' && r >= WARN && r < 1; }).length;
  bar.append(tile('Near the limit', String(near), link(T().col.toLowerCase() + ' ' + atLeast(WARN) + ' and ' + below(1), '#/explore' + qs({min: WARN}))));
  bar.append(tile('Warnings', String(sm.warnings), sm.warnings ? 'see below' : 'none', sm.warnings ? 'warnbox' : ''));
  root.append(bar);
  if (HAS_GEOMETRY) {
    root.append(el('h2', null, 'Location map'));
    root.append(el('p', {class: 'hint'}, 'Location of the items on the model, coloured by their ' + (isSM() ? 'minimum ' : 'maximum ') + T().name + ' (or ΣVj). ' +
      'Hover a marker to see the item, click it to open it.'));
    root.append(view3d('large'));
  }
  buildRecap(root);

  // needs attention
  root.append(el('h2', null, 'Needs attention'));
  const att = [];
  D.equations.filter(e => e[E.VERD] === FAILED && !e[E.SCREEN]).sort((a, b) => (b[E.RATIO] || 0) - (a[E.RATIO] || 0)).forEach(e => {
    const g = D.groups[e[E.G]];
    att.push({type: el('span', {class: 'verdict failed'}, 'FAILED'), g, what: s(g[G.EQ]),
      value: el('span', {class: 'fail'}, ratioTxt(e[E.RATIO])), note: invalid(e) ? 'invalidated: see the warnings' : mpa(e[E.APP]) + ' > ' + mpa(e[E.ALW]) + ' MPa', h: groupHash(g)});
  });
  for (const it of ITEMS.values()) for (const [pos, u] of it.usage) if (u >= 1) {
    att.push({type: el('span', {class: 'verdict failed'}, 'FATIGUE'), g: [it.id, pos, -1, sid('fatigue'), -1, -1, -1], what: 'ΣVj',
      value: el('span', {class: 'fail'}, usageTxt(u)), note: 'cumulative usage ≥ 1', h: itemHash(it.id)});
  }
  // warnings grouped by message
  const wg = new Map();
  D.rows.forEach((r, i) => {
    if (r[R.KIND] !== KIND_WARNING) return;
    const g = D.groups[r[R.G]], k = g[G.RULE] + '|' + r[R.NAME] + '|' + r[R.TEXT];
    if (!wg.has(k)) wg.set(k, {r, i, n: 0, items: new Set()});
    const w = wg.get(k); w.n++; w.items.add(g[0]);
  });
  for (const w of wg.values()) {
    const g = D.groups[w.r[R.G]];
    att.push({type: el('span', {class: 'verdict', style: 'background:var(--warn-bg);color:var(--warn)'}, 'WARNING'), g,
      what: s(w.r[R.NAME]), value: w.n > 1 ? w.n + '×' : '', note: s(w.r[R.TEXT]) + (w.n > 1 ? ' (' + w.n + ' occurrences in ' + w.items.size + ' items, first one linked)' : ''),
      h: groupHash(g, w.i)});
  }
  if (!att.length) root.append(el('p', {class: 'hint'}, 'No failed equations, no fatigue usage above 1 and no warnings.'));
  else {
    root.append(el('p', {class: 'hint'}, 'Failed equations (superseded equations of sequential rules are excluded, as in the Word recap), fatigue usage ≥ 1 and calculation warnings. Click a row to open the calculation.'));
    root.append(table(['', 'Item', 'Position', 'Event', 'Rule', 'Equation / quantity', 'Value', 'Detail'],
      att.slice(0, MAX).map(a => el('tr', {class: 'link', onclick: () => go(a.h)}, td(a.type), td(itemName(a.g[0])), td(s(a.g[1])), td(evLabel(a.g)),
        td(s(a.g[G.RULE])), td(a.what), td(a.value, 'num'), td(a.note)))));
  }

  // heatmap
  root.append(el('h2', null, 'Utilisation map'));
  root.append(el('p', {class: 'hint'}, (isSM() ? 'Minimum ' : 'Maximum ') + T().name + ' of each item over all positions and reference events' +
    (HAS_FATIGUE ? ', and maximum cumulative fatigue usage ΣVj over the positions' : '') + '. Click a cell to open the item.'));
  const fText = el('input', {type: 'search', placeholder: 'Filter items', size: 18});
  const fMin = el('input', {type: 'number', step: 'any', min: 0, placeholder: fmt(disp(WARN)), style: 'width:70px',
    title: HAS_FATIGUE ? 'the fatigue usage ΣVj counts as its ' + (isSM() ? 'inverse' : 'value') : null});
  const fSort = el('select', null, el('option', {value: 'worst'}, 'worst first'), el('option', {value: 'name'}, 'assessment order'));
  root.append(el('div', {class: 'toolbar'}, el('label', null, 'Items ', fText), el('label', null, 'Only ' + T().worst + (isSM() ? ' ≤ ' : ' ≥ '), fMin), el('label', null, 'Sort ', fSort),
    el('div', {class: 'legend'}, el('span', {class: 'l-ok'}, below(WARN)), el('span', {class: 'l-warn'}, atLeast(WARN)), el('span', {class: 'l-fail'}, atLeast(1)),
      el('span', {class: 'l-screen'}, 'only failed superseded'), el('span', null, '– not required / not evaluated'))));
  const out = el('div');
  root.append(out);
  // cell values
  const cells = new Map();
  D.equations.forEach(e => {
    const g = D.groups[e[E.G]], col = COLIDX.get(g[G.RULE] + '|' + g[G.EQ]);
    if (!cells.has(g[0])) cells.set(g[0], COLS.map(() => ({eff: null, scr: null, nscr: 0, at: null})));
    const c = cells.get(g[0])[col], r = effective(e);
    if (typeof r === 'number' && (c.eff === null || r > c.eff)) { c.eff = r; c.at = g; }
    if (e[E.SCREEN] && e[E.VERD] === FAILED) { c.nscr++; if (c.scr === null || e[E.RATIO] > c.scr) { c.scr = e[E.RATIO]; if (c.eff === null) c.at = g; } }
  });
  const groupsHead = [], eqHead = [];
  COLS.forEach((c, i) => {
    if (i === 0 || COLS[i - 1].rule !== c.rule) groupsHead.push(el('th', {class: 'grp', colspan: 1, title: s(c.set)}, s(c.rule)));
    else groupsHead[groupsHead.length - 1].colSpan++;
    eqHead.push(el('th', {class: 'eq', title: s(c.set)}, s(c.eq)));
  });
  if (HAS_FATIGUE) { groupsHead.push(el('th', {class: 'grp', rowspan: 2}, 'Fatigue', el('br'), 'ΣVj')); }
  function render() {
    // threshold on the ratio (a margin ≤ x is a ratio ≥ 1/x)
    const q = fText.value.trim().toLowerCase(), mn = fMin.value === '' ? null : disp(Number(fMin.value));
    let items = [...ITEMS.values()].filter(it => it.id >= 0 || cells.has(it.id));
    if (q) items = items.filter(it => itemName(it.id).toLowerCase().includes(q));
    if (mn !== null) items = items.filter(it => typeof it.max === 'number' && it.max >= mn);
    items.sort(fSort.value === 'worst' ? (a, b) => (b.max ?? -1) - (a.max ?? -1) || a.order - b.order : (a, b) => a.order - b.order);
    const rows = items.map(it => {
      const cs = cells.get(it.id) || COLS.map(() => ({eff: null, scr: null}));
      const tds = cs.map((c, i) => {
        const h = c.at ? groupHash(c.at) : itemHash(it.id);
        const title = itemName(it.id) + ' – ' + s(COLS[i].rule) + ' ' + s(COLS[i].eq);
        if (c.eff === null && c.scr === null) return el('td', {class: 'cell na', title: title + ': not required / not evaluated', onclick: () => go(itemHash(it.id))}, '–');
        if (c.eff === null) return el('td', {class: 'cell screen', title: title + ': only failed superseded checks, ' + T().worst + ' ' + ratioTxt(c.scr), onclick: () => go(h)}, ratioTxt(c.scr, 2));
        const extra = c.nscr ? ' (' + c.nscr + ' failures superseded, ' + T().worst + ' ' + ratioTxt(c.scr) + ')' : '';
        return el('td', {class: 'cell ' + level(c.eff), title: title + ': ' + T().worst + ' ' + ratioTxt(c.eff) + ' at ' + s(c.at[1]) + ' ' + evLabel(c.at) + extra, onclick: () => go(h)},
          ratioTxt(c.eff, 2) + (c.nscr ? '*' : ''));
      });
      if (HAS_FATIGUE) {
        const u = it.useMax;
        tds.push(u === null ? el('td', {class: 'cell na'}, '–') :
          el('td', {class: 'cell ' + level(u), title: 'max ΣVj over positions', onclick: () => go(itemHash(it.id))}, u < 0.01 && u > 0 ? u.toExponential(1) : u.toFixed(2)));
      }
      return el('tr', null, el('td', {class: 'item'}, link(itemName(it.id), itemHash(it.id)), it.warnings ? el('span', {class: 'warn', title: it.warnings + ' warnings'}, ' ⚠') : null), tds);
    });
    const t = el('table', {class: 'heat'}, el('thead', null, el('tr', null, el('th', {rowspan: 2}, 'Item (' + items.length + ')'), groupsHead), el('tr', null, eqHead)), el('tbody', null, rows));
    out.replaceChildren(el('div', {class: 'scroll'}, t), COLS.length ? el('p', {class: 'hint'}, '* some checks of this equation failed but were superseded by the governing equations of the sequential rule.') : null);
  }
  const r = debounce(render, 150);
  fText.addEventListener('input', r); fMin.addEventListener('input', r); fSort.addEventListener('change', render);
  render();
}

// recap of each item by damage type, as the word recap: worst result of each damage
// type over positions and reference events (failed superseded equations excluded)
function buildRecap(root) {
  const recap = new Map();
  const cell = (item, d) => {
    if (!recap.has(item)) recap.set(item, new Map());
    const r = recap.get(item);
    if (!r.has(d)) r.set(d, {failed: 0, n: 0, max: null, at: null, screening: 0});
    return r.get(d);
  };
  D.equations.forEach(e => {
    if (e[E.VERD] === null) return;
    const g = D.groups[e[E.G]], c = cell(g[0], damageOf(g));
    c.n++;
    if (e[E.SCREEN] && e[E.VERD] === FAILED) { c.screening++; return; }
    if (e[E.VERD] === FAILED) c.failed++;
    const r = e[E.RATIO];
    if (typeof r === 'number' && (c.max === null || r > c.max)) { c.max = r; c.at = g; }
  });
  for (const it of ITEMS.values()) for (const [pos, u] of it.usage) {
    const c = cell(it.id, FATIGUE);
    c.n++;
    if (u >= 1) c.failed++;
    if (c.max === null || u > c.max) { c.max = u; c.pos = pos; }
  }
  const items = [...ITEMS.values()].filter(it => recap.has(it.id));
  const nFailed = d => items.filter(it => (recap.get(it.id).get(d) || {}).failed).length;
  const nAssessed = d => items.filter(it => recap.get(it.id).has(d)).length;

  root.append(el('h2', null, 'Recap by damage type'));
  root.append(el('p', {class: 'hint'}, 'For each item, the verdict of each damage type over all positions and reference events, with the ' +
    (isSM() ? 'lowest ' : 'highest ') + T().name + ' (cumulative usage \u03a3Vj for fatigue) and where it occurs. As in the Word recap, a failed equation of a sequential rule ' +
    'superseded by the governing ones does not fail the item. Click a cell to open the driving calculation.'));
  const fText = el('input', {type: 'search', placeholder: 'Filter items', size: 18});
  const fFail = el('input', {type: 'checkbox'});
  const fSort = el('select', null, el('option', {value: 'order'}, 'assessment order'), el('option', {value: 'failed'}, 'failed first'));
  root.append(el('div', {class: 'toolbar'}, el('label', null, 'Items ', fText), el('label', null, fFail, 'only failed items'), el('label', null, 'Sort ', fSort)));
  const out = el('div');
  root.append(out);
  const status = it => DAMAGES.some(d => (recap.get(it.id).get(d) || {}).failed);
  function recapCell(it, d) {
    const c = recap.get(it.id).get(d);
    if (!c) return el('td', {class: 'na'}, 'not assessed');
    const fatigue = d === FATIGUE;
    const h = fatigue || !c.at ? itemHash(it.id) : groupHash(c.at);
    const where = fatigue ? s(c.pos) : c.at ? [s(c.at[1]), evLabel(c.at), s(c.at[G.EQ])].filter(Boolean).join(' \u00b7 ') : '';
    const chip = c.failed ? el('span', {class: 'verdict failed'}, 'FAILED') : c.max === null ? el('span', {class: 'verdict notreq'}, 'not required') : el('span', {class: 'verdict ok'}, 'OK');
    const value = c.max === null ? null : el('b', {class: level(c.max)}, fatigue ? '\u03a3Vj ' + usageTxt(c.max) : ratioTxt(c.max));
    const notes = [];
    if (c.failed > 1 && !fatigue) notes.push(c.failed + ' failed equations');
    if (c.failed > 1 && fatigue) notes.push(c.failed + ' positions');
    if (c.screening) notes.push(c.screening + ' superseded');
    return el('td', {class: 'recap link', onclick: () => go(h), title: 'open the driving calculation'},
      el('div', {class: 'recap-top'}, chip, value), where ? el('div', {class: 'sub'}, where) : null,
      notes.length ? el('div', {class: 'sub'}, notes.join(', ')) : null);
  }
  function render() {
    const q = fText.value.trim().toLowerCase();
    let rows = items.filter(it => (!q || itemName(it.id).toLowerCase().includes(q)) && (!fFail.checked || status(it)));
    if (fSort.value === 'failed') rows = [...rows].sort((a, b) => status(b) - status(a) || (b.max ?? -1) - (a.max ?? -1) || a.order - b.order);
    const head = [el('th', null, 'Item (' + rows.length + ')'), el('th', null, 'Verdict'),
      ...DAMAGES.map(d => el('th', null, d, el('div', {class: 'sub'}, nAssessed(d) ? nFailed(d) + ' of ' + nAssessed(d) + ' failed' : 'not assessed')))];
    out.replaceChildren(table(head, rows.map(it => el('tr', null,
      el('td', {class: 'item'}, link(itemName(it.id), itemHash(it.id)), it.warnings ? el('span', {class: 'warn', title: it.warnings + ' calculation warnings'}, ' \u26a0') : null),
      td(status(it) ? el('span', {class: 'verdict failed'}, 'FAILED') : el('span', {class: 'verdict ok'}, 'OK')),
      ...DAMAGES.map(d => recapCell(it, d)))), {class: 'recap'}));
  }
  const r = debounce(render, 150);
  fText.addEventListener('input', r);
  fFail.addEventListener('change', render);
  fSort.addEventListener('change', render);
  render();
}

// ---------- explore ----------
function buildExplore(v) {
  const root = v.node;
  const side = el('aside', {id: 'side'}), panel = el('div', {id: 'panel'});
  const browse = el('div'), detail = el('div');
  panel.append(browse, detail);
  root.append(side, panel);
  if (HAS_GEOMETRY) root.append(el('aside', {id: 'locator'}, view3d()));
  const fText = el('input', {type: 'search', placeholder: 'Filter items'});
  const fSort = el('select', null, el('option', {value: 'name'}, 'assessment order'), el('option', {value: 'worst'}, 'worst first'));
  const list = el('div');
  side.append(fText, el('div', {class: 'sortby'}, 'Sort ', fSort), list);
  let current = null;
  const order = () => {
    const items = [...ITEMS.values()];
    return fSort.value === 'worst' ? items.sort((a, b) => (b.max ?? -1) - (a.max ?? -1) || a.order - b.order) : items;
  };
  let ordered = order();
  function renderList() {
    const q = fText.value.trim().toLowerCase();
    ordered = order();
    list.replaceChildren(...ordered.filter(it => !q || itemName(it.id).toLowerCase().includes(q)).map(it =>
      el('a', {href: itemHash(it.id), class: it.id === current ? 'sel' : null, 'data-id': it.id},
        el('span', null, itemName(it.id), it.warnings ? el('span', {class: 'warn', title: it.warnings + ' warnings'}, ' ⚠') : null), badge(it.eqMax, it.useMax))));
  }
  // the item filter applies to the list and to the table
  const browser = buildBrowse(browse, () => fText.value.trim().toLowerCase());
  fText.addEventListener('input', debounce(() => { renderList(); if (!browse.hidden) browser.refresh(); }, 150));
  fSort.addEventListener('change', renderList);
  renderList();
  function select(id) {
    current = id;
    list.querySelectorAll('a').forEach(a => a.classList.toggle('sel', Number(a.dataset.id) === id));
    const a = list.querySelector('a.sel');
    if (a) a.scrollIntoView({block: 'nearest'});
  }
  v.state.show = r => {
    const it = r.view === 'item' ? ITEMS.get(dec(r.args[0])) : null;
    const ev = r.view === 'event' ? EV.get(r.args.slice(0, 4).map(dec).join('|')) : null;
    browse.hidden = Boolean(it || ev);
    detail.hidden = !browse.hidden;
    panel.scrollTop = 0;
    if (it) { select(it.id); renderItem(detail, it, ordered); }
    else if (ev) { select(ev.ids[0]); renderEvent(detail, ev, r.q); }
    else { select(null); browser.apply(r.q); }
  };
}
function prevNext(list, i, hash, label) {
  const b = (j, t) => el('button', {type: 'button', disabled: j < 0 || j >= list.length, title: j >= 0 && j < list.length ? label(list[j]) : null,
    onclick: () => go(hash(list[j]))}, t);
  return el('span', null, b(i - 1, '← prev'), ' ', b(i + 1, 'next →'));
}
function eventInputs(ev) {
  const out = {};
  for (const i of ev.rows) {
    const r = D.rows[i], g = D.groups[r[R.G]];
    if (r[R.KIND] === KIND_INPUT && g[G.RULE] < 0) out[s(r[R.NAME])] = r;
  }
  return out;
}
const INPUT_COLS = ['T', 'dpa', 'service level', 'loading category', 'loads'];
function renderItem(panel, it, ordered) {
  const idx = ordered.indexOf(it);
  panel.replaceChildren(el('div', {class: 'crumbs'}, link('All items', '#/explore'), el('span', {class: 'sep'}, '›'),
    el('h3', null, itemName(it.id)), badge(it.eqMax, it.useMax), it.failed ? el('span', {class: 'verdict failed'}, 'FAILED') : null,
    el('span', {class: 'spacer'}), prevNext(ordered, idx, x => itemHash(x.id), x => itemName(x.id))));
  if (it.warnings) panel.append(el('div', {class: 'warnbox'}, it.warnings + ' calculation warning(s) in this item: see the events marked ⚠.'));
  for (const [pos, evs] of it.positions) {
    const imm = evs.filter(ev => !isFatigue(ev.ids[3])), fat = evs.filter(ev => isFatigue(ev.ids[3]));
    panel.append(el('h2', null, s(pos) || 'Results'));
    if (imm.length) {
      const cols = COLS.map((_, i) => i).filter(i => imm.some(ev => ev.eqs.some(e => COLIDX.get(D.groups[e[0]][G.RULE] + '|' + D.groups[e[0]][G.EQ]) === i)));
      const inCols = INPUT_COLS.filter(n => imm.some(ev => eventInputs(ev)[n]));
      const head = [el('th', null, 'Event'), ...inCols.map(n => el('th', null, n === 'T' ? 'T [°C]' : n)),
        ...cols.map(i => el('th', {class: 'eq', title: s(COLS[i].set)}, s(COLS[i].rule), el('br'), el('span', {class: 'sub'}, s(COLS[i].eq)))), el('th', null, T().Worst)];
      panel.append(table(head, imm.map(ev => {
        const ins = eventInputs(ev);
        const byCol = new Map(ev.eqs.map(e => [COLIDX.get(D.groups[e[0]][G.RULE] + '|' + D.groups[e[0]][G.EQ]), e]));
        return el('tr', null, el('td', null, link(evLabel(ev.ids), evHash(ev.ids)), ev.warnings ? el('span', {class: 'warn', title: 'warnings'}, ' ⚠') : null),
          inCols.map(n => td(ins[n] ? displayValue(ins[n])[0] : '', ins[n] && ins[n][R.VAL] !== null ? 'num' : null)),
          cols.map(i => {
            const e = byCol.get(i);
            if (!e) return td('', 'na');
            const g = D.groups[e[0]], sc = e[E.SCREEN] && e[E.VERD] === FAILED;
            return el('td', {class: 'num link ' + (invalid(e) ? 'fail' : typeof e[E.RATIO] === 'number' && !sc ? level(e[E.RATIO]) : 'na'), style: 'cursor:pointer',
              title: verdictText(e[E.VERD], e[E.SCREEN]) + ': ' + (invalid(e) ? 'invalidated' : mpa(e[E.APP]) + ' / ' + mpa(e[E.ALW]) + ' MPa'), onclick: () => go(groupHash(g))},
            e[E.VERD] === NOT_REQUIRED ? 'n.r.' : invalid(e) ? 'inv.' : ratioTxt(e[E.RATIO]) + (sc ? ' s' : ''));
          }), ratioCell(ev.max));
      }), {class: 'grid'}));
    }
    if (fat.length) {
      const u = it.usage.get(pos);
      panel.append(el('h3', null, 'Fatigue ', el('span', {class: 'sub'}, 'cumulative usage ΣVj = '), el('span', {class: typeof u === 'number' ? level(u) : ''}, fmt(u))));
      panel.append(table(['Event', 'n cycles', 'N allowable', 'Vj'], fat.map(ev => {
        const f = ev.fat || [];
        return el('tr', {class: 'link', onclick: () => go(evHash(ev.ids))}, td(evLabel(ev.ids)), td(fmt(f[4]), 'num'), td(fmt(f[5]), 'num'), td(fmt(f[6]), 'num'));
      })));
    }
  }
  panel.append(el('p', {class: 'hint'}, 'n.r. = assessment not required (no limit); inv. = rule invalidated (counted as failed, see the warnings); s = failed equation superseded by the governing equations of the sequential rule.'));
}
function valuesTable(rows, focusRow) {
  return table(['Kind', 'Name', 'Value', 'Unit', 'Inputs', 'Source', 'Note'], rows.map(i => {
    const r = D.rows[i], [val, unit] = displayValue(r);
    return el('tr', {class: 'k-' + s(r[R.KIND]) + (i === focusRow ? ' hl' : ''), 'data-row': i}, td(s(r[R.KIND])), td(s(r[R.NAME])), td(val, 'num'), td(unit),
      td(fmtInputs(r[R.INPUTS])), td(s(r[R.SRC])), td(s(r[R.NOTE])));
  }));
}
// the quantity of the rule block whose value matches an equation term (stress or
// allowable), searching the kinds in order of preference
function matchQuantity(rows, kinds, valuePa) {
  if (typeof valuePa !== 'number') return null;
  for (const kind of kinds) for (const i of rows) {
    const r = D.rows[i];
    if (s(r[R.KIND]) !== kind || r[R.VAL] === null) continue;
    const v = s(r[R.UNIT]) === 'MPa' ? r[R.VAL] * 1e6 : r[R.VAL];
    if (Math.abs(v - valuePa) <= 1e-5 * Math.max(Math.abs(valuePa), 1e-9)) return r;
  }
  return null;
}
// label of an equation term: the quantity declared by the rule (source of the
// applied/allowable result) with its formula; traces without the declaration fall
// back to the value of the rule block matching the term
function term(eqRows, resultName, scopes, kinds, valuePa) {
  const res = eqRows.map(i => D.rows[i]).find(r => s(r[R.KIND]) === 'result' && s(r[R.NAME]) === resultName);
  let row = null, name = '';
  if (res && res[R.SRC] >= 0) {
    name = s(res[R.SRC]);
    for (const rows of scopes) {
      const i = rows.find(i => D.rows[i][R.NAME] === res[R.SRC] && s(D.rows[i][R.KIND]) !== 'result');
      if (i !== undefined) { row = D.rows[i]; break; }
    }
  } else {
    row = matchQuantity(scopes[0], kinds, valuePa);
    name = row ? s(row[R.NAME]) : '';
  }
  return name + (row && row[R.NOTE] >= 0 ? ' = ' + s(row[R.NOTE]) : '');
}
function renderEvent(panel, ev, q) {
  const it = ITEMS.get(ev.ids[0]);
  const i = it.events.indexOf(ev);
  const focusRule = q.get('rule'), focusEq = q.get('eq'), focusRow = q.has('row') ? Number(q.get('row')) : null;
  panel.replaceChildren(el('div', {class: 'crumbs'}, link('All items', '#/explore'), el('span', {class: 'sep'}, '›'), link(itemName(it.id), itemHash(it.id)),
    el('span', {class: 'sep'}, '›'), el('span', null, s(ev.ids[1])), el('span', {class: 'sep'}, '›'), el('h3', null, evLabel(ev.ids)), badge(ev.eqMax, ev.fat ? ev.fat[6] : null, 'Vj'),
    el('span', {class: 'spacer'}), prevNext(it.events, i, x => evHash(x.ids), x => s(x.ids[1]) + ' ' + evLabel(x.ids))));
  // split rows: event inputs, rule blocks, event-level calculation (fatigue)
  const inputs = [], general = [], blocks = new Map();
  for (const ri of ev.rows) {
    const r = D.rows[ri], g = D.groups[r[R.G]];
    if (g[G.SET] < 0 && g[G.RULE] < 0) { (r[R.KIND] === KIND_INPUT ? inputs : general).push(ri); continue; }
    const k = g[G.SET] + '|' + g[G.RULE];
    if (!blocks.has(k)) blocks.set(k, {set: g[G.SET], rule: g[G.RULE], values: [], eqs: new Map()});
    const b = blocks.get(k);
    if (g[G.EQ] < 0) { b.values.push(ri); continue; }
    if (!b.eqs.has(g[G.EQ])) b.eqs.set(g[G.EQ], {rows: [], res: null});
    b.eqs.get(g[G.EQ]).rows.push(ri);
  }
  ev.eqs.forEach(e => { const g = D.groups[e[0]]; const b = blocks.get(g[G.SET] + '|' + g[G.RULE]); if (b && b.eqs.has(g[G.EQ])) b.eqs.get(g[G.EQ]).res = e; });
  const warnings = ev.rows.filter(ri => D.rows[ri][R.KIND] === KIND_WARNING);
  if (warnings.length) panel.append(el('div', {class: 'warnbox'}, el('b', null, 'Warnings'), warnings.map(ri => el('div', null, s(D.rows[ri][R.NAME]) + ': ' + s(D.rows[ri][R.TEXT])))));
  if (inputs.length) {
    panel.append(el('div', {class: 'card' + (inputs.includes(focusRow) ? ' hl' : '')}, el('div', {class: 'card-head'}, el('h3', null, 'Reference event inputs')),
      el('div', {class: 'kv'}, inputs.map(ri => {
        const r = D.rows[ri], [val, unit] = displayValue(r);
        return el('span', {class: ri === focusRow ? 'warn' : null}, el('b', null, s(r[R.NAME])), val + (unit ? ' ' + unit : ''));
      }))));
  }
  let target = null;
  if (general.length) {
    const head = el('div', {class: 'card-head'}, el('h3', null, isFatigue(ev.ids[3]) ? 'Fatigue calculation' : 'Calculation'));
    if (ev.fat) head.append(el('span', null, 'Vj = n / N = ', fmt(ev.fat[4]), ' / ', fmt(ev.fat[5]), ' = ', el('b', null, fmt(ev.fat[6]))));
    const card = el('div', {class: 'card' + (general.includes(focusRow) ? ' hl' : '')}, head, valuesTable(general, focusRow));
    if (general.includes(focusRow)) target = card;
    panel.append(card);
  }
  for (const b of blocks.values()) {
    const isFocus = focusRule !== null && s(b.rule) === focusRule && !focusEq;
    const eqFocus = focusRule !== null && s(b.rule) === focusRule;
    const all = [...b.values]; b.eqs.forEach(x => all.push(...x.rows));
    const hasRow = focusRow !== null && all.includes(focusRow);
    let worst = null;
    b.eqs.forEach(x => { if (x.res) worst = higher(worst, effective(x.res)); });
    const card = el('div', {class: 'card' + (isFocus || hasRow || (eqFocus && focusEq) ? ' hl' : '')},
      el('div', {class: 'card-head'}, el('h3', null, s(b.rule) || s(b.set)), b.rule >= 0 ? el('span', {class: 'sub'}, s(b.set)) : null, badge(worst)));
    if (b.eqs.size) {
      card.append(table(['Equation', 'Applied', 'Applied [MPa]', '', 'Allowable [MPa]', 'Allowable', T().col, 'Verdict'], [...b.eqs].map(([eq, x]) => {
        const e = x.res, hl = eqFocus && s(eq) === focusEq;
        const notes = x.rows.map(ri => D.rows[ri]).filter(r => s(r[R.KIND]) === 'branch');
        if (!e) return el('tr', {class: hl ? 'hl' : null}, td(s(eq)), el('td', {colspan: 7, class: 'na'}, notes.map(r => s(r[R.TEXT])).join('; ') || 'not evaluated'));
        const app = term(x.rows, 'applied', [b.values, general], ['stress', 'value'], e[E.APP]);
        const alw = term(x.rows, 'allowable', [b.values], ['allowable', 'material'], e[E.ALW]);
        return el('tr', {class: hl ? 'hl' : null}, td(s(eq)), td(app, 'formula'), td(mpa(e[E.APP]), 'num'),
          td(e[E.ALW] === null ? '' : e[E.VERD] === FAILED ? '>' : '<', 'na'), td(mpa(e[E.ALW]), 'num'), td(alw, 'formula'),
          ratioCell(e[E.RATIO]), td(verdictChip(e[E.VERD], e[E.SCREEN])));
      }), {class: 'calc'}));
    }
    if (b.values.length) {
      const d = el('details', {class: 'values', open: true}, el('summary', null, 'Intermediate values (' + b.values.length + ')'), valuesTable(b.values, focusRow));
      card.append(d);
    }
    if (hasRow && !b.values.includes(focusRow)) card.append(valuesTable([focusRow], focusRow));
    if ((isFocus || hasRow || (eqFocus && focusEq)) && !target) target = card;
    panel.append(card);
  }
  if (target) setTimeout(() => {
    const row = focusRow !== null && target.querySelector('tr.hl');
    (row || target).scrollIntoView({block: row ? 'center' : 'start'});
  }, 0);
}

// ---------- explore table ----------
// shown in the explore panel when no item is open: one filterable table over the
// equation results or over every recorded value; the filters are kept in the url
function buildBrowse(root, itemQuery) {
  const groupText = D.groups.map(g => g.map((x, i) => (i === 0 ? itemName(x) : s(x))).join(' ').toLowerCase());
  const gcols = [['Item', g => itemName(g[0])], ['Position', g => s(g[1])], ['Event', g => evLabel(g)],
    ['Rule', g => s(g[G.RULE])], ['Equation', g => s(g[G.EQ])]];
  const col = (h, get, o) => Object.assign({h, get}, o);
  const fVerd = el('select', null, ['', 'FAILED', 'OK', 'Assessment not required', 'superseded'].map(o => el('option', {value: o}, o || 'All')));
  const fMin = el('input', {type: 'number', step: 'any', placeholder: 'e.g. ' + fmt(disp(WARN)), style: 'width:80px'});
  // exact ratio threshold set by a link, until the field is edited (the margin shown
  // in the field is rounded)
  let minRatio = null;
  const minThreshold = () => (minRatio !== null ? minRatio : fMin.value === '' ? null : disp(Number(fMin.value)));
  const fKind = el('select', null, el('option', {value: ''}, 'All'),
    [...new Set(D.rows.map(r => r[R.KIND]))].filter(k => k >= 0).map(k => el('option', {value: s(k)}, s(k))));
  const modes = {
    equations: {
      // worst first: highest ratio, lowest margin
      label: 'Equation results', all: D.equations, group: e => D.groups[e[E.G]], sort: [7, isSM() ? 1 : -1], hay: null,
      text: e => groupText[e[E.G]] + ' ' + verdictText(e[E.VERD], e[E.SCREEN]).toLowerCase(),
      keep: () => {
        // threshold on the ratio (a margin ≤ x is a ratio ≥ 1/x)
        const vd = fVerd.value, mn = minThreshold();
        return e => (!vd || verdictText(e[E.VERD], e[E.SCREEN]) === vd) && (mn === null || (typeof e[E.RATIO] === 'number' && e[E.RATIO] >= mn));
      },
      hash: e => groupHash(D.groups[e[E.G]]), rowClass: () => '',
      cols: [...gcols.map(([h, f]) => col(h, e => f(D.groups[e[E.G]]))),
        col('Applied [MPa]', e => e[E.APP], {num: true, cell: e => td(mpa(e[E.APP]), 'num'), csv: e => (e[E.APP] === null ? '' : e[E.APP] / 1e6)}),
        col('Allowable [MPa]', e => e[E.ALW], {num: true, cell: e => td(mpa(e[E.ALW]), 'num'), csv: e => (e[E.ALW] === null ? 'No Limit' : e[E.ALW] / 1e6)}),
        col(T().col, e => disp(e[E.RATIO]), {num: true, cell: e => ratioCell(e[E.RATIO]), first: isSM() ? 1 : -1,
          csv: e => { const v = disp(e[E.RATIO]); return v === Infinity ? 'inf' : v; }}),
        col('Verdict', e => verdictText(e[E.VERD], e[E.SCREEN]), {cell: e => td(verdictChip(e[E.VERD], e[E.SCREEN]))})],
      controls: [el('label', null, 'Verdict ', fVerd), el('label', null, (isSM() ? 'Max ' : 'Min ') + T().col.toLowerCase() + ' ', fMin)],
      hint: 'equation results',
    },
    values: {
      label: 'All values', all: D.rows.map((_, i) => i), group: i => D.groups[D.rows[i][R.G]], sort: [null, 1], hay: null,
      text: i => {
        const r = D.rows[i];
        return [groupText[r[R.G]], s(r[R.NAME]), displayValue(r).join(' '), fmtInputs(r[R.INPUTS]), s(r[R.SRC]), s(r[R.NOTE])].join(' ').toLowerCase();
      },
      keep: () => {
        const kind = fKind.value === '' ? null : sid(fKind.value);
        return i => kind === null || D.rows[i][R.KIND] === kind;
      },
      hash: i => groupHash(D.groups[D.rows[i][R.G]], i), rowClass: i => ' k-' + s(D.rows[i][R.KIND]),
      cols: [...gcols.map(([h, f]) => col(h, i => f(D.groups[D.rows[i][R.G]]))),
        col('Kind', i => s(D.rows[i][R.KIND])), col('Name', i => s(D.rows[i][R.NAME])),
        col('Value', i => displayValue(D.rows[i])[0], {cell: i => td(displayValue(D.rows[i])[0], 'num')}),
        col('Unit', i => displayValue(D.rows[i])[1]), col('Inputs', i => fmtInputs(D.rows[i][R.INPUTS])), col('Note', i => s(D.rows[i][R.NOTE]))],
      controls: [el('label', null, 'Kind ', fKind)],
      hint: 'recorded values',
    },
  };
  let mode = 'equations', res = [];
  const select = (label, lvl) => {
    const x = el('select', null, el('option', {value: ''}, 'All'),
      [...new Set(D.groups.map(g => g[lvl]))].filter(o => o >= 0).map(o => s(o)).sort(natural).map(o => el('option', {value: o}, o)));
    return [el('label', null, label + ' ', x), x];
  };
  const fText = el('input', {type: 'search', size: 30, placeholder: 'e.g. Sm "Path 12" LS4'});
  const [lPos, fPos] = select('Position', G.POS), [lEv, fEv] = select('Event', G.EV), [lRule, fRule] = select('Rule', G.RULE), [lEq, fEq] = select('Equation', G.EQ);
  const levels = [[G.POS, fPos], [G.EV, fEv], [G.RULE, fRule], [G.EQ, fEq]];
  const modeButtons = Object.entries(modes).map(([k, m]) => el('button', {type: 'button', 'data-mode': k, onclick: () => setMode(k)}, m.label));
  const exp = el('button', {type: 'button'}, 'Export CSV');
  const extra = el('span', {class: 'toolbar'});
  const out = el('div');
  root.className = 'browse';
  root.append(el('div', {class: 'toolbar'}, el('span', {class: 'seg'}, modeButtons), el('label', null, 'Search ', fText), lPos, lEv, lRule, lEq, extra, exp),
    el('p', {class: 'hint'}, 'All words must match (use quotes for exact phrases); the item filter on the left also applies. ' +
      'Click a column header to sort, a row to open it in its calculation.'), out);
  function setMode(k) {
    if (!modes[k]) k = 'equations';
    mode = k;
    [sortCol, sortDir] = modes[k].sort;
    modeButtons.forEach(b => b.classList.toggle('active', b.dataset.mode === k));
    extra.replaceChildren(...modes[k].controls);
    filter();
  }
  let sortCol = null, sortDir = 1;
  function filter() {
    const m = modes[mode];
    const terms = [...fText.value.toLowerCase().matchAll(/"([^"]+)"|(\S+)/g)].map(x => x[1] || x[2]);
    const iq = itemQuery();
    const items = iq ? new Set([...ITEMS.keys()].filter(id => itemName(id).toLowerCase().includes(iq))) : null;
    const lv = levels.filter(([, x]) => x.value).map(([l, x]) => [l, sid(x.value)]);
    const keep = m.keep();
    if (terms.length && !m.hay) m.hay = m.all.map(m.text);
    res = [];
    m.all.forEach((x, n) => {
      const g = m.group(x);
      if ((items && !items.has(g[0])) || lv.some(([l, v]) => g[l] !== v) || !keep(x)) return;
      if (terms.length && !terms.every(t => m.hay[n].includes(t))) return;
      res.push(x);
    });
    if (sortCol !== null) {
      const c = m.cols[sortCol];
      // missing numbers last in both directions (a margin column sorts ascending)
      const num = (x, y) => (x === null || y === null ? (x === null) - (y === null) : sortDir * (x - y) || 0);
      res.sort((a, b) => (c.num ? num(c.get(a) ?? null, c.get(b) ?? null) : sortDir * natural(c.get(a), c.get(b))));
    }
    // keep the filters in the url without adding history entries (may be refused on file://)
    try {
      history.replaceState(null, '', '#/explore' + qs({mode: mode === 'equations' ? null : mode, q: fText.value, pos: fPos.value, ev: fEv.value,
        rule: fRule.value, eq: fEq.value, verdict: fVerd.value, min: minRatio !== null ? minRatio : fMin.value === '' ? '' : fmt(minThreshold()), kind: fKind.value}));
    } catch (e) { /* ignore */ }
    const head = m.cols.map((c, i) => el('th', {class: 'sortable' + (i === sortCol ? (sortDir > 0 ? ' asc' : ' desc') : ''),
      onclick: () => { if (sortCol === i) sortDir = -sortDir; else { sortCol = i; sortDir = c.first || (c.num ? -1 : 1); } filter(); }}, c.h));
    out.replaceChildren(
      el('p', {class: 'hint'}, res.length + ' ' + m.hint + (res.length > MAX ? ', showing the first ' + MAX + ' (export to get all)' : '') + '.'),
      table(head, res.slice(0, MAX).map(x => el('tr', {class: 'link' + m.rowClass(x), onclick: () => go(m.hash(x))},
        m.cols.map(c => (c.cell ? c.cell(x) : td(c.get(x), c.num ? 'num' : null)))))));
  }
  const f = debounce(filter, 250);
  fMin.addEventListener('input', () => { minRatio = null; });
  [fText, fMin].forEach(x => x.addEventListener('input', f));
  [fPos, fEv, fRule, fEq, fVerd, fKind].forEach(x => x.addEventListener('change', filter));
  exp.addEventListener('click', () => {
    const m = modes[mode];
    download((D.title || 'trace') + '_' + mode + '.csv', csv([m.cols.map(c => c.h)].concat(res.map(x => m.cols.map(c => (c.csv ? c.csv(x) : c.get(x)))))));
  });
  const KEYS = ['mode', 'q', 'pos', 'ev', 'rule', 'eq', 'verdict', 'min', 'kind'];
  return {
    refresh: filter,
    apply(q) {
      // links (summary, back navigation) set all the filters; a plain #/explore keeps them
      if (KEYS.some(k => q.has(k))) {
        fText.value = q.get('q') || ''; fPos.value = q.get('pos') || ''; fEv.value = q.get('ev') || '';
        fRule.value = q.get('rule') || ''; fEq.value = q.get('eq') || ''; fVerd.value = q.get('verdict') || '';
        // the url threshold is on the ratio, the field shows it in the current mode
        minRatio = q.get('min') ? Number(q.get('min')) : null;
        fMin.value = minRatio !== null ? fmt(disp(minRatio)) : ''; fKind.value = q.get('kind') || '';
        setMode(q.get('mode') || 'equations');
      } else if (!modeButtons.some(b => b.classList.contains('active'))) setMode(mode);
      else filter();
    },
  };
}

route();
})();
