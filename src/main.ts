import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './style.css';
import { renderCard } from './card';
import { loadData, lookup, type Data } from './data';
import { geocode } from './geocode';
import { PdfViewer } from './pdfviewer';

const STATUS_COLORS = ['match', ['get', 'status'],
  'linked', '#f2c14e',
  'digitized', '#3fa34d',
  /* none */ '#9aa0a6'] as maplibregl.ExpressionSpecification;

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/positron',
  center: [19.1, 47.44],
  zoom: 12,
});
map.addControl(new maplibregl.NavigationControl(), 'top-right');

const card = document.getElementById('card')!;
const marker = new maplibregl.Marker({ color: '#d33' });
const viewer = new PdfViewer(document.getElementById('viewer')!);
const planToggle = document.getElementById('plan-toggle') as HTMLInputElement;
const planOpacity = document.getElementById('plan-opacity') as HTMLInputElement;

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
  for (const [id, reg] of Object.entries(data.regs.regulations)) {
    if (reg.plan) {
      map.addSource(`plan-${id}`, {
        type: 'raster',
        tiles: [new URL(`${import.meta.env.BASE_URL}${reg.plan.tiles}`, location.href).href],
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
    }
  }

  map.addLayer({ id: 'districts-line', type: 'line', source: 'districts',
    paint: { 'line-color': '#555', 'line-width': 1.2 } });
  map.addLayer({ id: 'districts-label', type: 'symbol', source: 'districts', maxzoom: 13,
    layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 12 },
    paint: { 'text-color': '#333', 'text-halo-color': '#fff', 'text-halo-width': 1.5 } });

  const syncPlan = () => planLayers.forEach((l) => {
    map.setLayoutProperty(l, 'visibility', planToggle.checked ? 'visible' : 'none');
    map.setPaintProperty(l, 'raster-opacity', Number(planOpacity.value) / 100);
  });
  planToggle.addEventListener('change', syncPlan);
  planOpacity.addEventListener('input', syncPlan);
  syncPlan();
}

function show(data: Data, lngLat: [number, number], label?: string): void {
  marker.setLngLat(lngLat).addTo(map);
  const result = lookup(data, lngLat, label);
  renderCard(card, result, data.regs.city, result.regId ? data.zoneTypes[result.regId] : undefined, {
    openCitation: (cite) => void viewer.open(data.regs.regulations[cite.reg], cite),
    openRegulation: (reg) => void viewer.open(reg),
  });
}

async function init(): Promise<void> {
  const [data] = await Promise.all([loadData(), map.once('load')]);
  addLayers(data);

  map.on('click', (e) => show(data, [e.lngLat.lng, e.lngLat.lat]));

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
      map.flyTo({ center: hit.lngLat, zoom: 17 });
      show(data, hit.lngLat, hit.label);
    } catch (err) {
      card.innerHTML = `<p class="warn">A keresés nem sikerült (${(err as Error).message}). Próbáld újra, vagy kattints a térképre.</p>`;
    }
  });
}

init().catch((err) => {
  card.innerHTML = `<p class="warn">Az adatok betöltése nem sikerült: ${(err as Error).message}</p>`;
});
