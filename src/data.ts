import booleanPointInPolygon from '@turf/boolean-point-in-polygon';
import type { Feature, FeatureCollection, Geometry, MultiPolygon, Point, Polygon } from 'geojson';
import type { Effective } from './effective';
import type { LookupResult, Parcel, ProtectedHit, Regulations, Rule, Teka, Tkr, ZoneCell, ZoneGuess, ZoneType } from './types';

type Areas<P> = FeatureCollection<Polygon | MultiPolygon, P>;
export type ZoneLabels = FeatureCollection<Point, { code: string; reg: string }>;

export interface Data {
  districts: Areas<{ id: number; name: string }>;
  regs: Regulations;
  zoneTypes: Record<string, Record<string, ZoneType>>;
  zoneLabels: Record<string, ZoneLabels>;
  rules: Record<string, Rule[]>;
  tkr: Record<string, Tkr>;
  protected: Record<string, FeatureCollection<Geometry, {
    kind: ProtectedHit['kind']; name: string; ref: string; hrsz?: string;
    approx?: boolean; street?: string; number?: string;
  }>>;
  teka?: Teka;
  effective: Record<string, Effective>;
}

const MAX_GUESS_DISTANCE_M = 250;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${path}`);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

export async function loadData(): Promise<Data> {
  const [districts, regs] = await Promise.all([
    getJson<Data['districts']>('districts.geojson'),
    getJson<Regulations>('regulations.json'),
  ]);
  const zoneTypes: Data['zoneTypes'] = {};
  const zoneLabels: Data['zoneLabels'] = {};
  const rules: Data['rules'] = {};
  const tkr: Data['tkr'] = {};
  const prot: Data['protected'] = {};
  let teka: Teka | undefined;
  const effective: Data['effective'] = {};
  await Promise.all(Object.entries(regs.regulations).flatMap(([id, r]) => [
    r.zoneTypes && getJson<Record<string, ZoneType>>(r.zoneTypes).then((z) => (zoneTypes[id] = z)),
    r.zoneLabels && getJson<ZoneLabels>(r.zoneLabels).then((z) => (zoneLabels[id] = z)),
    r.rules && getJson<Rule[]>(r.rules).then((x) => (rules[id] = x)),
    r.tkr && getJson<Tkr>(r.tkr).then((x) => (tkr[id] = x)),
    r.protected && getJson<Data['protected'][string]>(r.protected).then((x) => (prot[id] = x)),
    r.mandatoryRules && getJson<Teka>(r.mandatoryRules).then((x) => (teka = x)),
    r.effective && getJson<Effective>(r.effective).then((x) => (effective[id] = x)),
  ]));
  return { districts, regs, zoneTypes, zoneLabels, rules, tkr, protected: prot, teka, effective };
}

function distanceM([lng1, lat1]: number[], [lng2, lat2]: number[]): number {
  const kx = 111_320 * Math.cos((lat1 * Math.PI) / 180);
  return Math.hypot((lng2 - lng1) * kx, (lat2 - lat1) * 110_540);
}

function distanceToSegmentM(p: number[], a: number[], b: number[]): number {
  const kx = 111_320 * Math.cos((p[1] * Math.PI) / 180), ky = 110_540;
  const ax = (a[0] - p[0]) * kx, ay = (a[1] - p[1]) * ky, bx = (b[0] - p[0]) * kx, by = (b[1] - p[1]) * ky;
  const dx = bx - ax, dy = by - ay;
  const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(ax + dx * t, ay + dy * t);
}

// A protected building is a geocoded address point; a protected street section covers the plots on
// both sides of it; a protected structure is an area.
const BUILDING_RADIUS_M = 25;
const STREET_BUFFER_M = 35;

const norm = (s: string) => s.toLowerCase().normalize('NFC').replace(/[.\s]/g, '');

/** "60, Bartók Béla út, Szentimreváros, …" (Nominatim) -> street + house number. */
function parseAddress(label: string | undefined): { street: string; number: string } | null {
  const m = label?.match(/^(\d+[a-z]?(?:\/[a-z])?), ([^,]+)/i);
  return m ? { street: m[2], number: m[1] } : null;
}

/** What the user typed: "Albert utca 7, XX. kerület" -> street + house number. */
function parseQuery(q: string | undefined): { street: string; number: string } | null {
  const m = q?.split(',')[0].trim().match(/^(.+?)\s+(\d+[a-z]?(?:\/[a-z])?)\.?$/i);
  return m ? { street: m[1], number: m[2] } : null;
}

function protectedAt(fc: Data['protected'][string] | undefined, p: [number, number], label?: string, query?: string): ProtectedHit[] {
  const hits: ProtectedHit[] = [];
  const addr = parseAddress(label) ?? parseQuery(query);
  for (const f of (fc?.features ?? []) as Feature<Geometry, Data['protected'][string]['features'][number]['properties']>[]) {
    const g = f.geometry;
    let d = Infinity;
    const sameAddress = !!addr && !!f.properties.street && norm(f.properties.street) === norm(addr.street) &&
      norm(f.properties.number ?? '') === norm(addr.number);
    if (sameAddress) d = 0;
    else if (f.properties.approx) continue;
    else if (g.type === 'Point') d = distanceM(p, g.coordinates);
    else if (g.type === 'MultiLineString') for (const ln of g.coordinates) for (let i = 1; i < ln.length; i++) d = Math.min(d, distanceToSegmentM(p, ln[i - 1], ln[i]));
    else if (g.type === 'Polygon' || g.type === 'MultiPolygon') d = booleanPointInPolygon(p, g) ? 0 : Infinity;
    const limit = f.properties.kind === 'egyedi' ? BUILDING_RADIUS_M : f.properties.kind === 'VU' ? STREET_BUFFER_M : 0;
    if (d <= limit && !hits.some((h) => h.ref === f.properties.ref)) hits.push({ ...f.properties, distanceM: d });
  }
  return hits.sort((a, b) => a.distanceM - b.distanceM);
}

export function lookup(data: Data, lngLat: [number, number], label?: string, query?: string, exact = true): LookupResult {
  const district = data.districts.features.find((f) => booleanPointInPolygon(lngLat, f))?.properties;
  const regIds = district ? data.regs.districts[district.id]?.regulations ?? [] : [];
  // A district can have several regulations, each for its own area (plan.area): the one covering the point.
  const withTypes = regIds.filter((id) => data.zoneTypes[id]);
  const areaOf = (id: string) => data.regs.regulations[id]?.plan?.area;
  const regId = withTypes.find((id) => areaOf(id) && booleanPointInPolygon(lngLat, { type: 'Polygon', coordinates: areaOf(id)! }))
    ?? withTypes.find((id) => !areaOf(id)) ?? withTypes[0] ?? regIds[0];

  const guesses: ZoneGuess[] = [];
  for (const f of regId ? data.zoneLabels[regId]?.features ?? [] : []) {
    const d = distanceM(lngLat, f.geometry.coordinates);
    if (d > MAX_GUESS_DISTANCE_M) continue;
    const seen = guesses.find((g) => g.code === f.properties.code);
    if (!seen) guesses.push({ code: f.properties.code, distanceM: d });
    else seen.distanceM = Math.min(seen.distanceM, d);
  }
  guesses.sort((a, b) => a.distanceM - b.distanceM);
  const protectedHits = district
    ? (data.regs.districts[district.id]?.regulations ?? []).flatMap((id) => protectedAt(data.protected[id], lngLat, label, query))
    : [];

  return {
    lngLat,
    label,
    district,
    regId,
    regulation: regId ? data.regs.regulations[regId] : undefined,
    guesses: guesses.slice(0, 4),
    protectedHits,
    exact,
  };
}

export function rulesFor(all: Rule[] | undefined, code: string): Rule[] {
  return (all ?? []).filter((r) => r.zones === '*' || r.zones.includes(code));
}

const parcelCells = new Map<string, Promise<FeatureCollection<Polygon, any>>>();

/** The parcel under a point: the smallest traced plot that contains it (chunks are fetched on demand). */
/** The features of a grid chunk ({dir}/{ix}_{iy}.json) under p that contain it. */
async function chunkHits(cfg: { dir: string; cell: [number, number] }, p: [number, number]): Promise<Feature<Polygon, any>[]> {
  const key = `${cfg.dir}/${Math.floor(p[0] / cfg.cell[0])}_${Math.floor(p[1] / cfg.cell[1])}`;
  if (!parcelCells.has(key)) {
    parcelCells.set(key, fetch(`${import.meta.env.BASE_URL}data/${key}.json`)
      .then((r) => (r.ok ? r.json() : { type: 'FeatureCollection', features: [] })));
  }
  const fc = await parcelCells.get(key)!;
  return fc.features.filter((f: Feature<Polygon>) => booleanPointInPolygon(p, f));
}

export async function parcelAt(data: Data, regId: string | undefined, p: [number, number]): Promise<Parcel | undefined> {
  const cfg = regId ? data.regs.regulations[regId]?.parcels : undefined;
  if (!cfg) return undefined;
  const hits = await chunkHits(cfg, p);
  hits.sort((a, b) => a.properties.areaM2 - b.properties.areaM2);
  const f = hits[0];
  return f ? {
    hrsz: f.properties.hrsz, areaM2: f.properties.areaM2, geometry: f.geometry,
    check: f.properties.check ?? [], zones: f.properties.zones ?? [],
  } : undefined;
}

/** The cell of zone `code` nearest to p (the plot's zone, when the tap fell into a neighbouring cell). */
export async function zoneNear(data: Data, regId: string | undefined, p: [number, number], code: string): Promise<ZoneCell | undefined> {
  const cfg = regId ? data.regs.regulations[regId]?.zoneAreas : undefined;
  if (!cfg) return undefined;
  await chunkHits(cfg, p);
  const key = `${cfg.dir}/${Math.floor(p[0] / cfg.cell[0])}_${Math.floor(p[1] / cfg.cell[1])}`;
  const fc = await parcelCells.get(key)!;
  let best: Feature<Polygon, any> | undefined, bestD = Infinity;
  for (const f of fc.features as Feature<Polygon, any>[]) {
    if (f.properties.code !== code || f.properties.street) continue;
    const g = f.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon;
    const rings = g.type === 'MultiPolygon' ? g.coordinates.map((poly) => poly[0]) : [g.coordinates[0]];
    const d = booleanPointInPolygon(p, f) ? 0 : Math.min(...rings.flat().map((c) => distanceM(p, c)));
    if (d < bestD) [best, bestD] = [f, d];
  }
  return best && bestD < 150
    ? { code, status: best.properties.status, street: false, geometry: best.geometry }
    : undefined;
}

export async function zoneAt(data: Data, regId: string | undefined, p: [number, number]): Promise<ZoneCell | undefined> {
  const cfg = regId ? data.regs.regulations[regId]?.zoneAreas : undefined;
  if (!cfg) return undefined;
  const hits = await chunkHits(cfg, p);
  // Cells meet with a small overlap: prefer one the plan itself closes, then the smaller.
  hits.sort((a, b) => Number(a.properties.status !== 'plan') - Number(b.properties.status !== 'plan'));
  const f = hits[0];
  return f ? { code: f.properties.code, status: f.properties.status, street: f.properties.street, geometry: f.geometry } : undefined;
}
