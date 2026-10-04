import './review.css';

/** A drawing style from plan_vector.py: ["stroke", [r,g,b], width] or ["fill", [r,g,b], size]. */
type Style = [string, number[], number];

interface Entry { style: Style; label: string; source: string }
interface Zone {
  id: number;
  codes: Record<string, number>;
  status: 'ok' | 'conflict' | 'unlabelled';
  street: boolean;
  plots: number;
  path: string;
  bbox: [number, number, number, number];
}
interface Review {
  key: string;
  name: string;
  source: string;
  code_labels: number;
  distinct_codes: string[];
  plots: number;
  street_plots: number;
  osm_roads: number;
  georef: { ok: boolean; why?: string; residual_m?: number; labels_used?: number; streets?: number; streets_in_osm?: number };
  /** The zones (the bundle's "zones" list). */
  zones: Zone[];
  image: { src: string; size: [number, number] };
  layers: string[];
  legend: Record<string, Entry[]>;
  candidates: { style: Style; layer: string }[];
}

interface Stats { zones: number; with_codes: number; one_code: number; conflicting: number }

const ELEMENTS: Record<string, string> = {
  zone_boundary: 'Övezethatár',
  regulation_line: 'Szabályozási vonal',
  parcel: 'Telekhatár',
  inner_area: 'Belterület határa',
  admin: 'Közigazgatási határ',
  street: 'Közlekedési terület',
};
const LAYER_NAMES: Record<string, string> = {
  ...ELEMENTS,
  osm_roads: 'OSM utak (utcák)',
  zones: 'Övezetek',
};

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!));
const key = (s: Style) => JSON.stringify(s);
const rgb = (c: number[]) => `rgb(${c.map((v) => Math.round(v * 255)).join(',')})`;

let review: Review;
let zones: Zone[] = [];
let stats: Stats;
let index: { key: string; name: string; zones: Stats; georef: boolean }[] = [];
/** Per element: the styles in effect (enabled) and the ones the reviewer can toggle back on. */
let chosen: Record<string, { style: Style; label: string; on: boolean }[]> = {};

function swatch(s: Style): string {
  if (s[0] === 'fill') return `<span class="sw fill" style="background:${rgb(s[1])}"></span>`;
  const w = Math.max(1, Math.min(6, s[2] * 2));
  return `<span class="sw"><span style="background:${rgb(s[1])};height:${w}px"></span></span>`;
}

function styleText(s: Style): string {
  const c = s[1].map((v) => Math.round(v * 255)).join(', ');
  return s[0] === 'fill' ? `kitöltés (${c})` : `vonal ${s[2].toLocaleString('hu-HU')} pt (${c})`;
}

function storageKey() { return `review:${review.key}`; }

function save() {
  try { localStorage.setItem(storageKey(), JSON.stringify(chosen)); } catch { /* private mode */ }
  renderExport();
}

function initChosen() {
  chosen = {};
  for (const el of Object.keys(ELEMENTS)) {
    chosen[el] = (review.legend[el] ?? []).map((e) => ({ style: e.style, label: e.label, on: true }));
  }
  try {
    const saved = localStorage.getItem(storageKey());
    if (saved) chosen = { ...chosen, ...JSON.parse(saved) };
  } catch { /* ignore */ }
}

function renderSummary() {
  const r = review;
  const g = r.georef;
  $('summary').innerHTML = `
    <dl class="stats">
      <div><dt>Övezeti jelek</dt><dd>${r.code_labels} <span class="muted">(${r.distinct_codes.length} féle)</span></dd></div>
      <div><dt>Telkek</dt><dd>${r.plots.toLocaleString('hu-HU')} <span class="muted">(${r.street_plots} utca)</span></dd></div>
      <div><dt>Övezetek jellel</dt><dd>${stats.with_codes}</dd></div>
      <div><dt>Ebből ütköző</dt><dd class="${stats.conflicting ? 'bad' : 'good'}">${stats.conflicting}</dd></div>
    </dl>
    <p class="small">${g.ok
      ? `Térképre illesztés: ${g.labels_used} utcanév alapján, eltérés medián <b>${g.residual_m} m</b>${(g.residual_m ?? 99) > 10 ? ' <span class="bad">– nem megbízható</span>' : ''}; ${r.osm_roads} OSM út.`
      : `<span class="bad">Térképre illesztés nem sikerült:</span> ${esc(g.why ?? '')}`}</p>
    <p class="small"><a href="${esc(r.source)}" target="_blank" rel="noopener">Forrás PDF ↗</a></p>`;
}

function renderLayers() {
  const names = [...review.layers, 'zones'];
  $('layers').innerHTML = names.map((n) => `
    <label><input type="checkbox" data-layer="${n}" ${['zone_boundary', 'regulation_line', 'zones', 'osm_roads'].includes(n) ? 'checked' : ''}>
      ${esc(LAYER_NAMES[n] ?? n)}</label>`).join('');
  $('overlays').innerHTML = review.layers.map((n) =>
    `<img data-layer="${n}" src="review/${review.key}/${n}.png" alt="" draggable="false">`).join('');
  $('layers').querySelectorAll<HTMLInputElement>('input').forEach((cb) => {
    cb.addEventListener('change', applyLayers);
  });
  applyLayers();
}

function applyLayers() {
  $('layers').querySelectorAll<HTMLInputElement>('input').forEach((cb) => {
    const n = cb.dataset.layer!;
    if (n === 'zones') $('zones').style.display = cb.checked ? '' : 'none';
    else {
      const img = $('overlays').querySelector<HTMLElement>(`img[data-layer="${n}"]`);
      if (img) img.hidden = !cb.checked;
    }
  });
}

function renderLegend() {
  const used = new Set(Object.values(chosen).flat().map((e) => key(e.style)));
  $('legend').innerHTML = Object.entries(ELEMENTS).map(([el, title]) => {
    const rows = (chosen[el] ?? []).map((e, i) => `
      <li class="${e.on ? '' : 'off'}">
        <label><input type="checkbox" data-el="${el}" data-i="${i}" ${e.on ? 'checked' : ''}>
          ${swatch(e.style)} <span>${esc(e.label)}<br><span class="muted small">${styleText(e.style)}</span></span></label>
      </li>`).join('');
    const options = review.candidates.filter((c) => !used.has(key(c.style)))
      .map((c) => `<option value="${esc(key(c.style))}" data-layer="${c.layer}">${esc(styleText(c.style))}</option>`).join('');
    return `<div class="element">
      <h3>${esc(title)}</h3>
      <ul>${rows || '<li class="muted small">nincs felismerve</li>'}</ul>
      <div class="add">
        <select data-add="${el}"><option value="">+ stílus hozzáadása…</option>${options}</select>
      </div>
    </div>`;
  }).join('');
  $('legend').querySelectorAll<HTMLInputElement>('input[data-el]').forEach((cb) => cb.addEventListener('change', () => {
    chosen[cb.dataset.el!][Number(cb.dataset.i)].on = cb.checked;
    save();
    renderLegend();
  }));
  $('legend').querySelectorAll<HTMLSelectElement>('select[data-add]').forEach((sel) => {
    // Preview a candidate style on the plan while choosing.
    sel.addEventListener('input', () => {
      const opt = sel.selectedOptions[0];
      if (!opt?.value) return;
      const el = sel.dataset.add!;
      (chosen[el] ??= []).push({ style: JSON.parse(opt.value), label: 'kézzel hozzáadva', on: true });
      save();
      renderLegend();
      showCandidate(null);
    });
    sel.addEventListener('mouseover', (ev) => {
      const opt = ev.target as HTMLOptionElement;
      if (opt.dataset?.layer) showCandidate(opt.dataset.layer);
    });
    sel.addEventListener('change', () => showCandidate(null));
    sel.addEventListener('blur', () => showCandidate(null));
  });
  // Preview on hover over the candidate list does not fire on all browsers (native <select>):
  // also offer explicit preview buttons.
  renderCandidates(used);
}

function renderCandidates(used: Set<string>) {
  let box = document.getElementById('cands');
  if (!box) {
    box = document.createElement('div');
    box.id = 'cands';
    $('legend').after(box);
  }
  const free = review.candidates.filter((c) => !used.has(key(c.style)));
  box.innerHTML = `<details><summary class="small">A terv további gyakori stílusai (${free.length}) – mutasd a térképen</summary>
    <ul class="cands">${free.map((c) => `<li><button class="ghost" data-layer="${c.layer}">${swatch(c.style)} ${esc(styleText(c.style))}</button></li>`).join('')}</ul></details>`;
  box.querySelectorAll<HTMLButtonElement>('button[data-layer]').forEach((b) => {
    b.addEventListener('mouseenter', () => showCandidate(b.dataset.layer!));
    b.addEventListener('mouseleave', () => showCandidate(null));
    b.addEventListener('click', () => showCandidate(b.dataset.layer!, true));
  });
}

let pinnedCand: string | null = null;
function showCandidate(layer: string | null, pin = false) {
  if (pin) pinnedCand = pinnedCand === layer ? null : layer;
  const show = layer ?? pinnedCand;
  let img = document.getElementById('cand-overlay') as HTMLImageElement | null;
  if (!img) {
    img = document.createElement('img');
    img.id = 'cand-overlay';
    img.alt = '';
    img.draggable = false;
    $('overlays').append(img);
  }
  img.hidden = !show;
  if (show) img.src = `review/${review.key}/${show}.png`;
  $('hint').textContent = show ? 'Kiemelve: a kiválasztott stílusú vonalak (magenta)' : '';
}

function renderZones() {
  const [w, h] = review.image.size;
  const svg = $('zones');
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.innerHTML = zones.map((z) => `<path d="${z.path}" class="z ${z.status}${z.street ? ' street' : ''}" data-id="${z.id}"><title>${esc(Object.entries(z.codes).map(([c, n]) => `${c} ×${n}`).join(', ') || 'jel nélkül')} · ${z.plots} telek</title></path>`).join('');
  const list = zones.filter((z) => z.status === 'conflict');
  $('conflicts').innerHTML = list.length
    ? list.map((z) => `<li><button class="link" data-id="${z.id}">${Object.entries(z.codes).map(([c, n]) => `${esc(c)} ×${n}`).join(' · ')}</button> <span class="muted small">${z.plots} telek</span></li>`).join('')
    : '<li class="muted small">Nincs ütközés.</li>';
  $('conflicts').querySelectorAll<HTMLButtonElement>('button').forEach((b) => b.addEventListener('click', () => {
    const z = zones.find((q) => q.id === Number(b.dataset.id))!;
    focusBox(z.bbox);
    svg.querySelectorAll('.focus').forEach((p) => p.classList.remove('focus'));
    svg.querySelector(`[data-id="${z.id}"]`)?.classList.add('focus');
  }));
}

function renderExport() {
  const styles: Record<string, Style[]> = {};
  for (const [el, list] of Object.entries(chosen)) {
    const auto = (review.legend[el] ?? []).map((e) => key(e.style)).sort().join('|');
    const now = list.filter((e) => e.on).map((e) => e.style);
    if (now.map(key).sort().join('|') !== auto) styles[el] = now;
  }
  const json = JSON.stringify({ vector: { styles } }, null, 2);
  $('export').textContent = Object.keys(styles).length ? json : '– nincs változtatás az automatikus felismeréshez képest –';
  $('cfg-path').textContent = `districts/${review.key}.json`;
  $('cfg-cmd').textContent = `python3 scripts/plan_vector.py ${review.key}`;
  const a = $<HTMLAnchorElement>('download');
  a.href = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
  a.download = `${review.key}-review.json`;
}

// --- pan & zoom ---------------------------------------------------------------------------------
let scale = 1, tx = 0, ty = 0;
function applyTransform() {
  $('stage').style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
}
function fit() {
  const v = $('view').getBoundingClientRect();
  const [w, h] = review.image.size;
  scale = Math.min(v.width / w, v.height / h);
  tx = (v.width - w * scale) / 2;
  ty = (v.height - h * scale) / 2;
  applyTransform();
}
function focusBox([x0, y0, x1, y1]: number[]) {
  const v = $('view').getBoundingClientRect();
  scale = Math.min(v.width / (x1 - x0 + 200), v.height / (y1 - y0 + 200), 2.5);
  tx = v.width / 2 - ((x0 + x1) / 2) * scale;
  ty = v.height / 2 - ((y0 + y1) / 2) * scale;
  applyTransform();
}
function initPanZoom() {
  const view = $('view');
  const pts = new Map<number, { x: number; y: number }>();
  let last: { x: number; y: number; d: number } | null = null;
  view.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = view.getBoundingClientRect();
    const f = Math.exp(-e.deltaY * 0.0015);
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    tx = mx - (mx - tx) * f;
    ty = my - (my - ty) * f;
    scale *= f;
    applyTransform();
  }, { passive: false });
  view.addEventListener('pointerdown', (e) => {
    view.setPointerCapture(e.pointerId);
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    last = null;
  });
  view.addEventListener('pointermove', (e) => {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const p = [...pts.values()];
    const cx = p.reduce((s, q) => s + q.x, 0) / p.length, cy = p.reduce((s, q) => s + q.y, 0) / p.length;
    const d = p.length > 1 ? Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) : 0;
    if (last) {
      const r = view.getBoundingClientRect();
      if (p.length > 1 && last.d) {
        const f = d / last.d;
        const mx = cx - r.left, my = cy - r.top;
        tx = mx - (mx - tx) * f;
        ty = my - (my - ty) * f;
        scale *= f;
      }
      tx += cx - last.x;
      ty += cy - last.y;
      applyTransform();
    }
    last = { x: cx, y: cy, d };
  });
  const end = (e: PointerEvent) => { pts.delete(e.pointerId); last = null; };
  view.addEventListener('pointerup', end);
  view.addEventListener('pointercancel', end);
  view.addEventListener('dblclick', fit);
}

async function load(k: string) {
  review = await (await fetch(`review/${k}/review.json`)).json();
  zones = review.zones;
  stats = index.find((e) => e.key === k)!.zones;
  const img = $<HTMLImageElement>('plan');
  img.src = `review/${k}/${review.image.src}`;
  const [w, h] = review.image.size;
  $('stage').style.width = `${w}px`;
  $('stage').style.height = `${h}px`;
  initChosen();
  renderSummary();
  renderLayers();
  renderLegend();
  renderZones();
  renderExport();
  fit();
  history.replaceState(null, '', `#${k}`);
}

async function init() {
  index = await (await fetch('review/index.json')).json();
  const sel = $<HTMLSelectElement>('plan-select');
  sel.innerHTML = index.map((e) => `<option value="${e.key}">${esc(e.name)} – ${e.zones?.conflicting ?? '?'} ütközés</option>`).join('');
  sel.addEventListener('change', () => void load(sel.value));
  $('copy').addEventListener('click', () => {
    navigator.clipboard.writeText($('export').textContent ?? '').catch(() => {
      const r = document.createRange();
      r.selectNodeContents($('export'));
      getSelection()?.removeAllRanges();
      getSelection()?.addRange(r);
    });
  });
  $('reset').addEventListener('click', () => {
    try { localStorage.removeItem(storageKey()); } catch { /* ignore */ }
    initChosen();
    renderLegend();
    renderExport();
  });
  initPanZoom();
  window.addEventListener('resize', fit);
  const first = location.hash.slice(1) || index[0]?.key;
  if (first) {
    sel.value = first;
    await load(first);
  }
}

void init();
