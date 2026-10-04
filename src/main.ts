import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './style.css';
import { renderCard } from './card';
import { loadData, lookup, type Data } from './data';
import { geocode } from './geocode';
import { PdfViewer } from './pdfviewer';

const STATUS_COLORS = ['match', ['get', 'status'],
  'linked', '#f2c14e',
  'demo', '#b58cf2',
  'digitized', '#3fa34d',
  /* none */ '#9aa0a6'] as maplibregl.ExpressionSpecification;

const ZONE_COLORS = ['match', ['get', 'category'],
  'lakó', '#e8846b',
  'vegyes', '#c46bd1',
  'zöld', '#5bb36b',
  'gazdasági', '#6b8fe8',
  /* other */ '#bbbbbb'] as maplibregl.ExpressionSpecification;

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/positron',
  center: [19.06, 47.49],
  zoom: 11,
});
map.addControl(new maplibregl.NavigationControl(), 'top-right');

const card = document.getElementById('card')!;
const marker = new maplibregl.Marker({ color: '#d33' });
const viewer = new PdfViewer(document.getElementById('viewer')!);

function addLayers(data: Data): void {
  const districts = {
    ...data.districts,
    features: data.districts.features.map((f) => ({
      ...f,
      properties: { ...f.properties, status: data.regs.districts[f.properties.id]?.status ?? 'none' },
    })),
  };
  const zones = {
    ...data.zones,
    features: data.zones.features.map((f) => ({
      ...f,
      properties: { ...f.properties, category: data.zoneTypes[f.properties.code]?.category ?? 'egyéb' },
    })),
  };

  map.addSource('districts', { type: 'geojson', data: districts });
  map.addSource('zones', { type: 'geojson', data: zones });

  map.addLayer({ id: 'districts-fill', type: 'fill', source: 'districts',
    paint: { 'fill-color': STATUS_COLORS, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 11, 0.25, 14, 0.05] } });
  map.addLayer({ id: 'districts-line', type: 'line', source: 'districts',
    paint: { 'line-color': '#555', 'line-width': 1.2 } });
  map.addLayer({ id: 'districts-label', type: 'symbol', source: 'districts', maxzoom: 13,
    layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 12 },
    paint: { 'text-color': '#333', 'text-halo-color': '#fff', 'text-halo-width': 1.5 } });

  map.addLayer({ id: 'zones-fill', type: 'fill', source: 'zones', minzoom: 12,
    paint: { 'fill-color': ZONE_COLORS, 'fill-opacity': 0.45 } });
  map.addLayer({ id: 'zones-line', type: 'line', source: 'zones', minzoom: 12,
    paint: { 'line-color': '#333', 'line-width': 0.8 } });
  map.addLayer({ id: 'zones-label', type: 'symbol', source: 'zones', minzoom: 14,
    layout: { 'text-field': ['get', 'code'], 'text-font': ['Noto Sans Regular'], 'text-size': 13 },
    paint: { 'text-color': '#111', 'text-halo-color': '#fff', 'text-halo-width': 1.5 } });
}

function show(data: Data, lngLat: [number, number], label?: string): void {
  marker.setLngLat(lngLat).addTo(map);
  renderCard(card, lookup(data, lngLat, label), data.regs.city, {
    openCitation: (cite) => void viewer.open(data.regs.regulations[cite.reg], cite),
    openRegulation: (id) => void viewer.open(id === 'city' ? data.regs.city : data.regs.regulations[id]),
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
        card.innerHTML = '<p class="hint">Nincs találat Budapesten.</p>';
        return;
      }
      map.flyTo({ center: hit.lngLat, zoom: 16 });
      show(data, hit.lngLat, hit.label);
    } catch (err) {
      card.innerHTML = `<p class="warn">Hiba a keresésnél: ${(err as Error).message}</p>`;
    }
  });
}

init().catch((err) => {
  card.innerHTML = `<p class="warn">Betöltési hiba: ${(err as Error).message}</p>`;
});
