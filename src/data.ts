import booleanPointInPolygon from '@turf/boolean-point-in-polygon';
import type { FeatureCollection, MultiPolygon, Point, Polygon } from 'geojson';
import type { LookupResult, Regulations, ZoneGuess, ZoneType } from './types';

type Areas<P> = FeatureCollection<Polygon | MultiPolygon, P>;
export type ZoneLabels = FeatureCollection<Point, { code: string; reg: string }>;

export interface Data {
  districts: Areas<{ id: number; name: string }>;
  regs: Regulations;
  zoneTypes: Record<string, Record<string, ZoneType>>;
  zoneLabels: Record<string, ZoneLabels>;
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
  await Promise.all(Object.entries(regs.regulations).flatMap(([id, r]) => [
    r.zoneTypes && getJson<Record<string, ZoneType>>(r.zoneTypes).then((z) => (zoneTypes[id] = z)),
    r.zoneLabels && getJson<ZoneLabels>(r.zoneLabels).then((z) => (zoneLabels[id] = z)),
  ]));
  return { districts, regs, zoneTypes, zoneLabels };
}

function distanceM([lng1, lat1]: number[], [lng2, lat2]: number[]): number {
  const kx = 111_320 * Math.cos((lat1 * Math.PI) / 180);
  return Math.hypot((lng2 - lng1) * kx, (lat2 - lat1) * 110_540);
}

export function lookup(data: Data, lngLat: [number, number], label?: string): LookupResult {
  const district = data.districts.features.find((f) => booleanPointInPolygon(lngLat, f))?.properties;
  const regId = district ? data.regs.districts[district.id]?.regulations[0] : undefined;

  const guesses: ZoneGuess[] = [];
  for (const f of regId ? data.zoneLabels[regId]?.features ?? [] : []) {
    const d = distanceM(lngLat, f.geometry.coordinates);
    if (d > MAX_GUESS_DISTANCE_M) continue;
    const seen = guesses.find((g) => g.code === f.properties.code);
    if (!seen) guesses.push({ code: f.properties.code, distanceM: d });
    else seen.distanceM = Math.min(seen.distanceM, d);
  }
  guesses.sort((a, b) => a.distanceM - b.distanceM);

  return {
    lngLat,
    label,
    district,
    regId,
    regulation: regId ? data.regs.regulations[regId] : undefined,
    guesses: guesses.slice(0, 4),
  };
}
