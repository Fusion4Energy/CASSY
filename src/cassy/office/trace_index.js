(function () {
'use strict';
// display mode toggle of the index page, shared with the component pages (see
// trace_report.js): the worst equation ratio of each component is shown as usage
// factor (applied/allowable) or as safety margin (allowable/applied). The colours
// follow the ratio, the fatigue usage ΣVj stays a usage factor
const MODES = {uf: {label: 'Usage factor', head: 'Max ratio'}, sm: {label: 'Safety margin', head: 'Min margin'}};
let mode = 'uf';
try { if (localStorage.getItem('cassy.mode') === 'sm') mode = 'sm'; } catch (e) { /* ignore */ }
function ratioTxt(r) {
  const v = mode === 'sm' ? (r > 0 ? 1 / r : Infinity) : r;
  if (v === Infinity) return '∞';
  return v > 0 && (v < 1e-3 || v >= 1e4) ? v.toExponential(1) : v.toFixed(3);
}
const seg = document.createElement('span');
seg.className = 'seg mode';
const buttons = Object.entries(MODES).map(([k, m]) => {
  const b = document.createElement('button');
  b.type = 'button'; b.textContent = m.label; b.dataset.mode = k;
  b.onclick = () => {
    mode = k;
    try { localStorage.setItem('cassy.mode', k); } catch (e) { /* ignore */ }
    show();
  };
  seg.append(b);
  return b;
});
document.querySelector('header').append(seg);
function show() {
  buttons.forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  document.getElementById('worst').textContent = MODES[mode].head;
  document.querySelectorAll('td[data-ratio]').forEach(td => { td.textContent = ratioTxt(Number(td.dataset.ratio)); });
}
show();

// excel export of each table (see trace_xlsx.js): the ratios at full precision in the
// display mode, the numeric cells as numbers, '–' as empty
function cellValue(td) {
  if (td.dataset.ratio !== undefined) {
    const r = Number(td.dataset.ratio);
    return mode === 'sm' ? (r > 0 ? 1 / r : Infinity) : r;
  }
  const t = td.textContent.trim();
  if (t === '' || t === '–') return null;
  return /^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t) ? Number(t) : t;
}
document.querySelectorAll('table.grid').forEach((table, i) => {
  const box = table.closest('.scroll') || table;
  const prev = box.previousElementSibling;
  const name = prev && prev.tagName === 'H2' ? prev.textContent : 'Components';
  const rows = () => [...table.rows].map(tr => [...tr.cells].map(c => (c.tagName === 'TH' ? c.textContent.trim() : cellValue(c))));
  const b = window.cassyXlsx.button('assessment_' + name.toLowerCase(), () => [{name, rows: rows()}]);
  if (prev && prev.tagName === 'H2') prev.append(b);
  else { const bar = document.createElement('div'); bar.className = 'toolbar'; bar.append(b); box.before(bar); }
});
})();
