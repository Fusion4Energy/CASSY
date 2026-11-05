(function () {
'use strict';
// excel export of the summary tables, shared by the index and the component pages.
// SheetJS is loaded from its CDN at the first export (the rest of the report works
// offline); the integrity hash pins the exact file
const SHEETJS = {
  src: 'https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.mini.min.js',
  integrity: 'sha384-NG/W3xvO3ynQEcDQYIOcZTXRtwUs83cLv1FIl9PuqWPDuNhsMRF6wutlNLFwlb71',
};
let loading = null;
function load() {
  if (window.XLSX) return Promise.resolve(window.XLSX);
  if (!loading) loading = new Promise((resolve, reject) => {
    const sc = document.createElement('script');
    sc.src = SHEETJS.src; sc.integrity = SHEETJS.integrity; sc.crossOrigin = 'anonymous';
    sc.onload = () => resolve(window.XLSX);
    sc.onerror = () => { loading = null; sc.remove(); reject(new Error('the excel export needs internet access to load the SheetJS library')); };
    document.head.append(sc);
  });
  return loading;
}
const safe = n => String(n).replace(/[^\w\-.]+/g, '_').replace(/^_+|_+$/g, '') || 'trace';
// empty for the missing values, infinite margins as text
const clean = v => (v === null || v === undefined || Number.isNaN(v) ? null : v === Infinity ? '∞' : v);

// sheets: [{name, rows: [[...]], header: header rows (default 1), merges: [[r0, c0, r1, c1]]}]
async function save(file, sheets) {
  const X = await load();
  const wb = X.utils.book_new();
  for (const sh of sheets) {
    const rows = sh.rows.map(r => r.map(clean));
    const ws = X.utils.aoa_to_sheet(rows);
    const n = Math.max(1, ...rows.map(r => r.length)), header = sh.header || 1;
    if (sh.merges) ws['!merges'] = sh.merges.map(([r0, c0, r1, c1]) => ({s: {r: r0, c: c0}, e: {r: r1, c: c1}}));
    ws['!cols'] = [...Array(n).keys()].map(c => ({wch: Math.min(50, Math.max(8, ...rows.map(r => String(r[c] ?? '').length + 2)))}));
    if (rows.length > header) ws['!autofilter'] = {ref: X.utils.encode_range({r: header - 1, c: 0}, {r: rows.length - 1, c: n - 1})};
    // sheet names: at most 31 characters, none of []:*?/\
    X.utils.book_append_sheet(wb, ws, sh.name.replace(/[[\]:*?/\\]/g, ' ').slice(0, 31));
  }
  X.writeFile(wb, safe(file) + '.xlsx');
}

// button exporting the sheets returned by getSheets() when clicked
function button(file, getSheets, title) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'xlsx'; b.textContent = 'Excel';
  b.title = (title || 'Export this table to excel') + ' (needs internet access)';
  b.onclick = async () => {
    b.disabled = true; b.textContent = 'Exporting…';
    try { await save(file, getSheets()); } catch (e) { alert('Excel export failed: ' + e.message); }
    b.disabled = false; b.textContent = 'Excel';
  };
  return b;
}
window.cassyXlsx = {save, button};
})();
