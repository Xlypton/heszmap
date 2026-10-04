import booleanPointInPolygon from '@turf/boolean-point-in-polygon';
import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson';
import type { LookupResult, Regulations, ZoneType } from './types';

type Areas<P> = FeatureCollection<Polygon | MultiPolygon, P>;

export interface Data {
  districts: Areas<{ id: number; name: string }>;
  zones: Areas<{ code: string; regulation: string }>;
  zoneTypes: Record<string, ZoneType>;
  regs: Regulations;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${path}`);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

export async function loadData(): Promise<Data> {
  const [districts, zones, zoneTypes, regs] = await Promise.all([
    getJson<Data['districts']>('districts.geojson'),
    getJson<Data['zones']>('zones.geojson'),
    getJson<Record<string, ZoneType>>('zone-types.json'),
    getJson<Regulations>('regulations.json'),
  ]);
  return { districts, zones, zoneTypes, regs };
}

export function lookup(data: Data, lngLat: [number, number], label?: string): LookupResult {
  const district = data.districts.features.find((f) => booleanPointInPolygon(lngLat, f))?.properties;
  const zone = data.zones.features.find((f) => booleanPointInPolygon(lngLat, f))?.properties;
  const districtRegulations = district
    ? (data.regs.districts[district.id]?.regulations ?? []).map((id) => ({ id, reg: data.regs.regulations[id] }))
    : [];
  return {
    lngLat,
    label,
    district,
    zoneCode: zone?.code,
    zone: zone ? data.zoneTypes[zone.code] : undefined,
    regulation: zone ? data.regs.regulations[zone.regulation] : undefined,
    districtRegulations,
  };
}
