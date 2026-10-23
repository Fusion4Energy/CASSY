// 3D location map of the trace report (see trace_report.py and geometry_view.py).
// Shows the model and the items (paths as segments, bolts as points) in the .view3d
// container of the visible page, coloured by their worst result (equation ratio or
// fatigue usage, in the display mode of trace_report.js); the item of the current
// route is highlighted and framed. In the bolts reports the other flanges are shown
// faded, as context (their meshes are registered in window.CASSY_MESHES by the scripts
// of the geometry folder). It follows the route published by trace_report.js
// in window.CASSY, and never runs if three.js cannot be loaded (no internet).
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const C = window.CASSY;
if (C) start();

function start() {
  const G = C.geometry, WARN = C.warnRatio;
  const PALETTE = {ok: '#2e9e55', warn: '#f0a020', fail: '#d0203a', na: '#8a94a3', plain: '#1f5fa8', dim: '#c3c9d1', sel: '#e0119d'};
  const level = r => (typeof r !== 'number' ? 'na' : r >= 1 ? 'fail' : r >= WARN ? 'warn' : 'ok');
  const fmt = r => (typeof r === 'number' ? (r > 0 && r < 1e-3 ? r.toExponential(1) : r.toFixed(3)) : '–');
  // worst result of an item: the equations in the display mode, or the fatigue usage
  // when it is higher (a usage factor in both modes)
  const worst = it => (typeof it.useMax === 'number' && !(typeof it.eqMax === 'number' && it.eqMax >= it.useMax) ?
    'ΣVj ' + fmt(it.useMax) : C.label().worst + ' ' + C.label().col.toLowerCase() + ' ' + (typeof it.eqMax === 'number' ? C.ratioTxt(it.eqMax) : '–'));
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; };

  // ---------- items ----------
  const items = Object.entries(G.items).map(([name, loc]) => {
    const p = loc.p.map(x => new THREE.Vector3(...x));
    const center = p.length > 1 ? p[0].clone().add(p[1]).multiplyScalar(0.5) : p[0].clone();
    const r = C.items.get(name) || {};
    return {name, p, center, axis: loc.axis ? new THREE.Vector3(...loc.axis).normalize() : null,
      length: p.length > 1 ? p[0].distanceTo(p[1]) : 0, max: r.max, eqMax: r.eqMax, useMax: r.useMax};
  });
  const byName = new Map(items.map(it => [it.name, it]));

  // ---------- scene ----------
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#f7f8fa');
  scene.add(new THREE.HemisphereLight('#ffffff', '#8890a0', 2.2));
  const sun = new THREE.DirectionalLight('#ffffff', 1.5);
  scene.add(sun);
  const box = new THREE.Box3();
  items.forEach(it => it.p.forEach(x => box.expandByPoint(x)));

  const modelMat = new THREE.MeshStandardMaterial({color: '#c9d1db', flatShading: true, roughness: 0.8,
    transparent: true, opacity: 0.3, depthWrite: false, side: THREE.DoubleSide});
  const edgeMat = new THREE.LineBasicMaterial({color: '#6b7684', transparent: true, opacity: 0.5});
  let model = null, edges = null;
  function meshGeometry(m) {
    const bytes = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(bytes(m.vertices)), 3));
    geo.setIndex(new THREE.BufferAttribute(new Uint32Array(bytes(m.faces)), 1));
    geo.computeVertexNormals();
    geo.computeBoundingBox();
    return geo;
  }
  if (G.mesh) {
    const geo = meshGeometry(G.mesh);
    box.union(geo.boundingBox);
    model = new THREE.Mesh(geo, modelMat);
    edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), edgeMat);
    scene.add(model, edges);
  }
  // other flanges: geometry only, faded, not part of the framing
  const contextMat = new THREE.MeshStandardMaterial({color: '#dde2e8', flatShading: true, roughness: 0.9,
    transparent: true, opacity: 0.12, depthWrite: false, side: THREE.DoubleSide});
  const contextEdgeMat = new THREE.LineBasicMaterial({color: '#9aa3ae', transparent: true, opacity: 0.18});
  const context = new THREE.Group();
  const missingContext = [];
  for (const c of G.context || []) {
    const m = (window.CASSY_MESHES || {})[c.key];
    if (!m) { missingContext.push(c.name); continue; }
    const geo = meshGeometry(m);
    context.add(new THREE.Mesh(geo, contextMat), new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), contextEdgeMat));
  }
  if (missingContext.length) console.warn('CASSY: geometry of ' + missingContext.join(', ') + ' not found in the geometry folder');
  // blended before the model, so that it stays behind it
  context.renderOrder = -1;
  scene.add(context);
  const size = box.getSize(new THREE.Vector3()).length() || 1;
  const centre = box.getCenter(new THREE.Vector3());

  // markers: tubes for the paths, spheres (or short cylinders along the axis) for
  // the bolts, sized on the model and on the typical path length; plus a point of
  // constant screen size for each item, visible at any zoom
  const lengths = items.map(it => it.length).filter(l => l > 0).sort((a, b) => a - b);
  const typical = lengths.length ? lengths[Math.floor(lengths.length / 2)] : Infinity;
  const radius = Math.min(size * 0.003, typical * 0.12);
  const ballR = Math.min(size * 0.006, typical * 0.25);
  const Y = new THREE.Vector3(0, 1, 0);
  const tube = new THREE.CylinderGeometry(1, 1, 1, 10), ball = new THREE.SphereGeometry(1, 14, 10);
  const markers = new THREE.Group();
  scene.add(markers);
  for (const it of items) {
    it.mat = new THREE.MeshStandardMaterial({roughness: 0.5});
    it.objs = [];
    const add = (geo, pos, scale, dir) => {
      const m = new THREE.Mesh(geo, it.mat);
      m.position.copy(pos); m.scale.copy(scale);
      if (dir) m.quaternion.setFromUnitVectors(Y, dir);
      it.objs.push(m); markers.add(m);
    };
    if (it.p.length > 1 && it.length > 0) {
      add(tube, it.center, new THREE.Vector3(radius, it.length, radius), it.p[1].clone().sub(it.p[0]).normalize());
      it.p.forEach(x => add(ball, x, new THREE.Vector3(1, 1, 1).multiplyScalar(radius * 1.8)));
    } else if (it.axis) {
      add(tube, it.center, new THREE.Vector3(ballR * 0.6, ballR * 5, ballR * 0.6), it.axis);
      add(ball, it.center, new THREE.Vector3(1, 1, 1).multiplyScalar(ballR));
    } else add(ball, it.center, new THREE.Vector3(1, 1, 1).multiplyScalar(ballR));
  }
  const dot = document.createElement('canvas');
  dot.width = dot.height = 32;
  const ctx = dot.getContext('2d');
  ctx.beginPath(); ctx.arc(16, 16, 13, 0, 2 * Math.PI); ctx.fillStyle = '#fff'; ctx.fill();
  ctx.lineWidth = 3; ctx.strokeStyle = '#333'; ctx.stroke();
  const pointsGeo = new THREE.BufferGeometry();
  pointsGeo.setAttribute('position', new THREE.Float32BufferAttribute(items.flatMap(it => it.center.toArray()), 3));
  pointsGeo.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(items.length * 3), 3));
  const points = new THREE.Points(pointsGeo, new THREE.PointsMaterial({size: 9, sizeAttenuation: false, vertexColors: true,
    map: new THREE.CanvasTexture(dot), alphaTest: 0.5, depthTest: false}));
  points.renderOrder = 2;
  scene.add(points);

  // ---------- renderer and controls ----------
  const wrap = el('div', 'v3d');
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  // far enough for the other flanges too
  const all = box.clone().union(new THREE.Box3().setFromObject(context));
  const camera = new THREE.PerspectiveCamera(35, 1, size * 1e-4, Math.max(size, all.getSize(new THREE.Vector3()).length()) * 100);
  camera.up.set(0, 0, 1);  // FEM models are usually z-up
  const controls = new OrbitControls(camera, renderer.domElement);
  const labels = el('div', 'v3d-labels'), tip = el('div', 'v3d-tip'), bar = el('div', 'v3d-bar');
  const help = el('div', 'v3d-help', 'drag: rotate · right drag: pan · wheel: zoom · click a marker: open the item');
  tip.hidden = true;
  wrap.append(renderer.domElement, labels, tip, bar, help);

  // ---------- toolbar ----------
  // names shown by default when they are few enough to stay readable
  const state = {model: 'x-ray', colours: 'ratio', labels: items.length <= 30, context: true, selected: null};
  const button = (text, title, onclick) => { const b = el('button', null, text); b.type = 'button'; b.title = title; b.onclick = onclick; bar.append(b); return b; };
  button('Fit all', 'Show the whole model', () => frame(null));
  const bModel = button('', 'Model display', () => { state.model = {'x-ray': 'solid', solid: 'hidden', hidden: 'x-ray'}[state.model]; style(); });
  const bCol = button('', 'Marker colours', () => { state.colours = state.colours === 'ratio' ? 'plain' : 'ratio'; style(); });
  const bLab = button('', 'Show the names of all the items', () => { state.labels = !state.labels; style(); });
  const bCtx = context.children.length ? button('', 'Geometry of the other flanges of the assessment (context only)',
    () => { state.context = !state.context; style(); }) : null;
  const legend = el('span', 'v3d-legend');
  bar.append(legend);
  function fillLegend() {
    // the thresholds in the display mode, and on the fatigue usage when the margin is shown
    const fat = C.mode === 'sm' && C.hasFatigue, both = (r, txt) => txt(r) + (fat ? ' (ΣVj ' + (txt === C.below ? '< ' : '≥ ') + r + ')' : '');
    legend.title = C.label().col + (fat ? ' (or fatigue usage ΣVj)' : '');
    legend.replaceChildren(...[['ok', both(WARN, C.below)], ['warn', both(WARN, C.atLeast)], ['fail', both(1, C.atLeast)], ['na', 'no result'], ['sel', 'selected']].map(([k, t]) => {
      const s = el('span', null, t); s.style.setProperty('--c', PALETTE[k]); return s;
    }));
  }

  function style() {
    bModel.textContent = 'Model: ' + state.model;
    bCol.textContent = 'Colours: ' + state.colours;
    bLab.textContent = state.labels ? 'Hide labels' : 'Show labels';
    legend.hidden = state.colours !== 'ratio';
    fillLegend();
    if (bCtx) bCtx.textContent = state.context ? 'Hide other flanges' : 'Show other flanges';
    context.visible = state.context;
    if (model) {
      model.visible = edges.visible = state.model !== 'hidden';
      modelMat.transparent = state.model === 'x-ray';
      modelMat.opacity = state.model === 'x-ray' ? 0.3 : 1;
      modelMat.depthWrite = state.model !== 'x-ray';
      modelMat.needsUpdate = true;
    }
    const col = pointsGeo.attributes.color, c = new THREE.Color();
    items.forEach((it, i) => {
      const sel = it === state.selected, dim = state.selected && !sel;
      c.set(sel ? PALETTE.sel : dim ? PALETTE.dim : state.colours === 'ratio' ? PALETTE[level(it.max)] : PALETTE.plain);
      it.mat.color.copy(c);
      it.mat.emissive.copy(c).multiplyScalar(sel ? 0.5 : 0.15);
      // the selected item stays visible behind the model
      it.mat.depthTest = !sel;
      it.objs.forEach(o => { o.renderOrder = sel ? 3 : 0; o.scale.multiplyScalar((sel ? 1.6 : 1) / (o.userData.k || 1)); o.userData.k = sel ? 1.6 : 1; });
      col.setXYZ(i, c.r, c.g, c.b);
    });
    col.needsUpdate = true;
    drawLabels();
    render();
  }

  // ---------- labels and hover ----------
  const screen = v => {
    const p = v.clone().project(camera), r = renderer.domElement;
    return {x: (p.x + 1) / 2 * r.clientWidth, y: (1 - p.y) / 2 * r.clientHeight, front: p.z < 1};
  };
  function drawLabels() {
    const shown = state.labels ? items.slice(0, 400) : state.selected ? [state.selected] : [];
    labels.replaceChildren(...shown.map(it => {
      const p = screen(it.center);
      if (!p.front) return '';
      const l = el('span', it === state.selected ? 'sel' : null, it.name);
      l.style.transform = `translate(${p.x + 8}px, ${p.y - 8}px)`;
      return l;
    }));
  }
  function nearest(ev) {
    const r = renderer.domElement.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
    let best = null, bd = 12 * 12;
    for (const it of items) {
      const p = screen(it.center), d = (p.x - x) ** 2 + (p.y - y) ** 2;
      if (p.front && d < bd) { bd = d; best = it; }
    }
    return {it: best, x, y};
  }
  renderer.domElement.addEventListener('pointermove', ev => {
    const {it, x, y} = nearest(ev);
    tip.hidden = !it;
    renderer.domElement.style.cursor = it ? 'pointer' : '';
    if (!it) return;
    tip.textContent = it.name + ' · ' + worst(it);
    tip.style.transform = `translate(${x + 14}px, ${y + 10}px)`;
  });
  renderer.domElement.addEventListener('pointerleave', () => { tip.hidden = true; });
  let down = null;
  renderer.domElement.addEventListener('pointerdown', ev => { down = [ev.clientX, ev.clientY]; });
  renderer.domElement.addEventListener('pointerup', ev => {
    // a click, not the end of a rotation
    if (!down || Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) > 4) return;
    const {it} = nearest(ev);
    if (it) C.open(it.name);
  });

  // ---------- camera ----------
  let anim = null;
  function frame(it, instant) {
    const target = it ? it.center : centre;
    // keep the context around the item: a fraction of the model, at least a few
    // times the item itself
    const r = it ? Math.max(size * 0.08, it.length * 4, ballR * 20) : size / 2;
    const dir = camera.position.clone().sub(controls.target);
    if (dir.lengthSq() === 0) dir.set(1, -1.2, 0.8);
    const dist = r / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2));
    const to = target.clone().add(dir.normalize().multiplyScalar(dist));
    if (instant) { camera.position.copy(to); controls.target.copy(target); controls.update(); render(); return; }
    const from = [camera.position.clone(), controls.target.clone()], t0 = performance.now();
    anim = () => {
      const t = Math.min(1, (performance.now() - t0) / 450), k = t * t * (3 - 2 * t);
      camera.position.lerpVectors(from[0], to, k);
      controls.target.lerpVectors(from[1], target, k);
      controls.update();
      if (t >= 1) anim = null;
    };
    loop();
  }
  let pending = false;
  function render() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      sun.position.copy(camera.position);
      renderer.render(scene, camera);
      drawLabels();
    });
  }
  function loop() {
    if (anim) { anim(); render(); requestAnimationFrame(loop); }
  }
  controls.addEventListener('change', render);
  renderer.domElement.addEventListener('webglcontextrestored', render);
  const resize = new ResizeObserver(() => {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    render();
  });
  resize.observe(wrap);

  // ---------- route ----------
  let first = true;
  function follow(route) {
    // a single viewer, moved to the container of the visible page
    const host = document.querySelector('main section:not([hidden]) .view3d');
    if (!host) return;
    if (wrap.parentNode !== host) host.replaceChildren(wrap);
    state.selected = route.item ? byName.get(route.item) || null : null;
    host.classList.toggle('missing', Boolean(route.item && !state.selected));
    host.dataset.missing = route.item && !state.selected ? 'No location given for ' + route.item : '';
    style();
    frame(state.selected, first);
    first = false;
  }
  document.addEventListener('cassy:route', ev => follow(ev.detail));
  document.addEventListener('cassy:mode', style);
  if (C.route.view) follow(C.route);
}
