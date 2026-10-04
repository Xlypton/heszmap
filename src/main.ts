import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './style.css';
import { renderCard } from './card';
import { loadData, lookup, rulesFor, type Data } from './data';
import { nearestOnLines, type StreetContext } from './effective';
import { geocode } from './geocode';
import { PdfViewer } from './pdfviewer';
import { BottomSheet } from './sheet';

const STATUS_COLORS = ['match', ['get', 'status'],
  'linked', '#f2c14e',
  'digitized', '#3fa34d',
  /* none */ '#9aa0a6'] as maplibregl.ExpressionSpecification;

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/liberty',
  center: [19.1, 47.44],
  zoom: 12,
  hash: true,
});
map.addControl(new maplibregl.NavigationControl(), 'top-right');

const card = document.getElementById('card')!;
const marker = new maplibregl.Marker({ color: '#d33' });
const viewer = new PdfViewer(document.getElementById('viewer')!);
const planToggle = document.getElementById('plan-toggle') as HTMLInputElement;
const planOpacity = document.getElementById('plan-opacity') as HTMLInputElement;
const panel = document.getElementById('panel')!;
const mobile = window.matchMedia('(max-width: 720px)');

// On phones the panel is a bottom sheet over a full-screen map.
const sheet = new BottomSheet(panel, document.getElementById('sheet-top')!);
const setSheet = (open: boolean) => sheet.set(open ? 'half' : 'peek');
const mapPadding = () => ({ top: 0, bottom: mobile.matches ? window.innerHeight * 0.55 : 0, left: 0, right: 0 });

const tappable: string[] = [];

function addLayers(data: Data): void {
  const districts = {
    ...data.districts,
    features: data.districts.features.map((f) => ({
      ...f,
      properties: { ...f.properties, status: data.regs.districts[f.properties.id]?.status ?? 'none' },
    })),
  };
  map.addSource('districts', { type: 'geojson', data: districts });
  map.addLayer({ id: 'districts-fill', type: 'fill', source: 'districts',
    paint: { 'fill-color': STATUS_COLORS, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 11, 0.25, 14, 0.04] } });

  const planLayers: string[] = [];
  const labelLayers: string[] = [];
  for (const [id, reg] of Object.entries(data.regs.regulations)) {
    if (reg.plan) {
      map.addSource(`plan-${id}`, {
        type: 'raster',
        // Plain concatenation: URL() would percent-encode the {z}/{x}/{y} placeholders.
        tiles: [`${location.origin}${import.meta.env.BASE_URL}${reg.plan.tiles}`],
        tileSize: 256,
        bounds: reg.plan.bounds,
        minzoom: reg.plan.minzoom,
        maxzoom: reg.plan.maxzoom,
        attribution: `Szabályozási terv: ${reg.title}`,
      });
      map.addLayer({ id: `plan-${id}`, type: 'raster', source: `plan-${id}`, paint: { 'raster-opacity': 0.85 } });
      planLayers.push(`plan-${id}`);
    }
    const labels = data.zoneLabels[id];
    if (labels) {
      map.addSource(`labels-${id}`, { type: 'geojson', data: labels });
      map.addLayer({ id: `labels-${id}`, type: 'circle', source: `labels-${id}`, minzoom: 14,
        paint: { 'circle-radius': 3, 'circle-color': '#1f4fd1', 'circle-stroke-color': '#fff', 'circle-stroke-width': 1 } });
      map.addLayer({ id: `labels-${id}-text`, type: 'symbol', source: `labels-${id}`, minzoom: 15,
        layout: { 'text-field': ['get', 'code'], 'text-font': ['Noto Sans Regular'], 'text-size': 12, 'text-offset': [0, 1] },
        paint: { 'text-color': '#1f4fd1', 'text-halo-color': '#fff', 'text-halo-width': 1.5 } });
      labelLayers.push(`labels-${id}`, `labels-${id}-text`);
    }
  }

  // Street names and house numbers drawn above the zoning plan, so the scan stays readable in context.
  const NAME = ['coalesce', ['get', 'name:hu'], ['get', 'name']] as maplibregl.ExpressionSpecification;
  map.addLayer({ id: 'ov-street-names', type: 'symbol', source: 'openmaptiles', 'source-layer': 'transportation_name', minzoom: 13,
    layout: { 'symbol-placement': 'line', 'text-field': NAME, 'text-font': ['Noto Sans Regular'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 13, 10, 18, 14], 'text-max-angle': 30 },
    paint: { 'text-color': '#1d1f21', 'text-halo-color': '#ffffff', 'text-halo-width': 2 } });
  map.addLayer({ id: 'ov-housenumbers', type: 'symbol', source: 'openmaptiles', 'source-layer': 'housenumber', minzoom: 17,
    layout: { 'text-field': ['get', 'housenumber'], 'text-font': ['Noto Sans Regular'], 'text-size': 11 },
    paint: { 'text-color': '#444', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 } });

  // District-protected values (TKR 2. melléklet): areas, street sections, buildings. Tappable.
  for (const [id, fc] of Object.entries(data.protected)) {
    map.addSource(`protected-${id}`, { type: 'geojson', data: fc });
    map.addLayer({ id: `protected-area-${id}`, type: 'line', source: `protected-${id}`, minzoom: 13,
      filter: ['==', ['get', 'kind'], 'TSZ'],
      paint: { 'line-color': '#d9480f', 'line-width': 2.5, 'line-dasharray': [1, 1] } });
    map.addLayer({ id: `protected-street-${id}`, type: 'line', source: `protected-${id}`, minzoom: 13,
      filter: ['all', ['==', ['get', 'kind'], 'VU'], ['in', ['geometry-type'], ['literal', ['LineString', 'MultiLineString']]]],
      paint: { 'line-color': '#d9480f', 'line-width': ['interpolate', ['linear'], ['zoom'], 13, 3, 18, 12], 'line-opacity': 0.45 } });
    map.addLayer({ id: `protected-point-${id}`, type: 'circle', source: `protected-${id}`, minzoom: 13,
      filter: ['all', ['==', ['geometry-type'], 'Point'], ['!=', ['get', 'approx'], true]],
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 4, 18, 9], 'circle-color': '#d9480f',
        'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } });
    map.addLayer({ id: `protected-label-${id}`, type: 'symbol', source: `protected-${id}`, minzoom: 16,
      filter: ['all', ['==', ['geometry-type'], 'Point'], ['!=', ['get', 'approx'], true]],
      layout: { 'text-field': '★ védett', 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-offset': [0, 1.3] },
      paint: { 'text-color': '#d9480f', 'text-halo-color': '#fff', 'text-halo-width': 1.5 } });
    tappable.push(`protected-point-${id}`, `protected-street-${id}`);
  }

  map.addLayer({ id: 'districts-line', type: 'line', source: 'districts',
    paint: { 'line-color': '#555', 'line-width': 1.2 } });
  map.addLayer({ id: 'districts-label', type: 'symbol', source: 'districts', maxzoom: 13,
    layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 12 },
    paint: { 'text-color': '#333', 'text-halo-color': '#fff', 'text-halo-width': 1.5 } });

  // The plan prints the zone codes itself; show our label points only when the plan is off.
  const syncPlan = () => {
    planLayers.forEach((l) => {
      map.setLayoutProperty(l, 'visibility', planToggle.checked ? 'visible' : 'none');
      map.setPaintProperty(l, 'raster-opacity', Number(planOpacity.value) / 100);
    });
    labelLayers.forEach((l) => map.setLayoutProperty(l, 'visibility', planToggle.checked ? 'none' : 'visible'));
  };
  planToggle.addEventListener('change', syncPlan);
  planOpacity.addEventListener('input', syncPlan);
  syncPlan();
}

/** Named streets near the point (closest first, one per name) from the loaded basemap tiles. */
function nearbyStreets(p: [number, number]): StreetContext[] {
  const best = new Map<string, StreetContext>();
  for (const f of map.querySourceFeatures('openmaptiles', { sourceLayer: 'transportation_name' })) {
    const name = (f.properties['name:hu'] ?? f.properties.name) as string | undefined;
    const g = f.geometry;
    if (!name || (g.type !== 'LineString' && g.type !== 'MultiLineString')) continue;
    const { d, bearing } = nearestOnLines(p, g.type === 'LineString' ? [g.coordinates] : g.coordinates);
    if (d < 80 && d < (best.get(name)?.distanceM ?? Infinity)) best.set(name, { name, bearing, distanceM: d });
  }
  return [...best.values()].sort((a, b) => a.distanceM - b.distanceM);
}

function show(data: Data, lngLat: [number, number], label?: string, query?: string, exact = true): void {
  marker.setLngLat(lngLat).addTo(map);
  setSheet(true);
  panel.scrollTop = 0;
  const result = lookup(data, lngLat, label, query, exact);
  const regRules = result.regId ? data.rules[result.regId] : undefined;
  const districtRegs = result.district ? data.regs.districts[result.district.id]?.regulations ?? [] : [];
  const tkrId = districtRegs.find((id) => data.tkr[id]);
  const extras = {
    tkr: tkrId ? { regId: tkrId, reg: data.regs.regulations[tkrId], data: data.tkr[tkrId] } : undefined,
    teka: data.teka && result.district ? { reg: data.regs.regulations.teka, data: data.teka } : undefined,
    effective: result.regId ? data.effective[result.regId] : undefined,
    near: nearbyStreets(lngLat),
  };
  renderCard(card, result, data.regs.city, result.regId ? data.zoneTypes[result.regId] : undefined, (code) => rulesFor(regRules, code), extras, {
    openCitation: (cite) => void viewer.open(data.regs.regulations[cite.reg], cite),
    openRegulation: (reg) => void viewer.open(reg),
  });
}

async function init(): Promise<void> {
  const [data] = await Promise.all([loadData(), map.once('load')]);
  addLayers(data);

  for (const l of tappable) {
    map.on('mouseenter', l, () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', l, () => (map.getCanvas().style.cursor = ''));
  }
  map.on('click', (e) => {
    // Fingers are imprecise: snap to a protected building within ~14 px of the tap.
    const r = 14;
    const hit = map.queryRenderedFeatures([[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]],
      { layers: tappable.filter((l) => l.startsWith('protected-point')) })[0];
    if (hit?.geometry.type === 'Point') {
      const [lng, lat] = hit.geometry.coordinates as [number, number];
      show(data, [lng, lat], String(hit.properties.name));
      if (mobile.matches) map.easeTo({ center: [lng, lat], padding: mapPadding() });
      return;
    }
    show(data, [e.lngLat.lng, e.lngLat.lat]);
    if (mobile.matches) map.easeTo({ center: e.lngLat, padding: mapPadding() });
  });

  document.getElementById('search')!.addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = (document.getElementById('q') as HTMLInputElement).value.trim();
    if (!q) return;
    card.innerHTML = '<p class="hint">Keresés…</p>';
    try {
      const hit = await geocode(q);
      if (!hit) {
        card.innerHTML = '<p class="hint">Nincs találat Budapesten. Próbáld kerülettel, pl. „Kossuth Lajos utca 20, XX. kerület”.</p>';
        return;
      }
      (document.getElementById('q') as HTMLInputElement).blur();
      map.flyTo({ center: hit.lngLat, zoom: 17, padding: mapPadding() });
      show(data, hit.lngLat, hit.label, q, hit.exact);
    } catch (err) {
      card.innerHTML = `<p class="warn">A keresés nem sikerült (${(err as Error).message}). Próbáld újra, vagy kattints a térképre.</p>`;
    }
  });
}

init().catch((err) => {
  card.innerHTML = `<p class="warn">Az adatok betöltése nem sikerült: ${(err as Error).message}</p>`;
});
