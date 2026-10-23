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
})();
