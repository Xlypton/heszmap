import type maplibregl from 'maplibre-gl';

// Optional overlays from external map services, served through the tile proxy in worker/index.js.
// LICENSING IS NOT CLEARED for any of them (docs/data-sources.md): prototype use only.

interface Overlay {
  id: string;
  label: string;
  path: string; // /x/<source>/<variant>
  attribution: string;
  /** Imagery goes under the zoning plans; line work and plans go above them. */
  under?: boolean;
  bounds?: [number, number, number, number];
  minzoom?: number;
  maxzoom?: number;
  opacity?: number;
}

const BUDAPEST: [number, number, number, number] = [18.92, 47.34, 19.34, 47.62];
const LECHNER = '© Lechner Tudásközpont';
const BPK = '© Budapest Közút Zrt.';

const OVERLAYS: Overlay[] = [
  { id: 'oeny-plots', label: 'Telekhatárok, hrsz (földhivatali térkép)', path: 'oeny/plots',
    attribution: `Földhivatali térkép: ${LECHNER} (OÉNY, nem közhiteles)`, minzoom: 15, maxzoom: 20 },
  { id: 'oeny-buildings', label: 'Épületek (földhivatali térkép)', path: 'oeny/buildings',
    attribution: `Földhivatali térkép: ${LECHNER} (OÉNY, nem közhiteles)`, minzoom: 15, maxzoom: 20, opacity: 0.6 },
  { id: 'bp-orto', label: 'Légifotó 2024 (Budapest)', path: 'bp/orto', attribution: `Légifotó 2024: ${BPK}`,
    under: true, bounds: BUDAPEST, minzoom: 10, maxzoom: 21 },
  { id: 'lechner-orto', label: 'Légifotó 2015 (országos)', path: 'lechner/2015', attribution: `Ortofotó 2015: ${LECHNER}`,
    under: true, minzoom: 12, maxzoom: 19 },
  { id: 'bp-frsz', label: 'FRSZ, fővárosi rendezési szabályzat', path: 'bp/frsz', attribution: `FRSZ: ${BPK}`,
    bounds: BUDAPEST, minzoom: 12, maxzoom: 19, opacity: 0.8 },
  { id: 'bp-tszt', label: 'TSZT, településszerkezeti terv (Budapest)', path: 'bp/tszt', attribution: `TSZT: ${BPK}`,
    bounds: BUDAPEST, minzoom: 12, maxzoom: 19, opacity: 0.7 },
  { id: 'bp-vi', label: 'VI. kerület KÉSZ (vektoros)', path: 'bp/vi', attribution: `VI. kerület KÉSZ: ${BPK}`,
    bounds: [19.05, 47.495, 19.09, 47.52], minzoom: 14, maxzoom: 20 },
];

const STORE = 'heszmap.overlays';

function saved(): string[] {
  try {
    return JSON.parse(localStorage.getItem(STORE) ?? '[]') as string[];
  } catch {
    return [];
  }
}

function save(ids: string[]): void {
  try {
    localStorage.setItem(STORE, JSON.stringify(ids));
  } catch {
    // Private mode or blocked storage: the choice just isn't remembered.
  }
}

/** Adds every overlay (hidden unless chosen before) and a checkbox per overlay into `container`.
 * `underId` is the lowest app layer (imagery goes below it), `overId` the layer line work goes below. */
export function addOverlays(map: maplibregl.Map, container: HTMLElement, underId: string, overId: string): void {
  const on = new Set(saved());
  for (const o of OVERLAYS) {
    map.addSource(o.id, {
      type: 'raster',
      tiles: [`${location.origin}/x/${o.path}/{z}/{x}/{y}`],
      tileSize: 256,
      bounds: o.bounds,
      minzoom: o.minzoom,
      maxzoom: o.maxzoom,
      attribution: o.attribution,
    });
    map.addLayer({ id: o.id, type: 'raster', source: o.id, minzoom: o.minzoom,
      layout: { visibility: on.has(o.id) ? 'visible' : 'none' },
      paint: { 'raster-opacity': o.opacity ?? 1 } }, o.under ? underId : overId);

    const label = document.createElement('label');
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = on.has(o.id);
    box.addEventListener('change', () => {
      map.setLayoutProperty(o.id, 'visibility', box.checked ? 'visible' : 'none');
      if (box.checked) on.add(o.id); else on.delete(o.id);
      save([...on]);
    });
    label.append(box, ` ${o.label}`);
    container.append(label);
  }
}
