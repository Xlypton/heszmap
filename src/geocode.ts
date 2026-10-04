// Nominatim usage policy: max 1 req/s and no search-as-you-type, so we only geocode on submit.
const BUDAPEST_VIEWBOX: [number, number, number, number] = [18.92, 47.34, 19.34, 47.62];

export interface GeocodeHit {
  lngLat: [number, number];
  label: string;
  /** False when only the street (not the house number) was found. */
  exact: boolean;
}

/** viewbox: [west, south, east, north] of the covered areas (Budapest when not given). */
export async function geocode(query: string, viewbox = BUDAPEST_VIEWBOX): Promise<GeocodeHit | null> {
  const params = new URLSearchParams({
    q: query,
    format: 'json',
    limit: '1',
    countrycodes: 'hu',
    viewbox: [viewbox[0], viewbox[3], viewbox[2], viewbox[1]].map((v) => v.toFixed(4)).join(','),
    bounded: '1',
    'accept-language': 'hu',
  });
  const res = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
  if (!res.ok) throw new Error(`Geocoding failed: ${res.status}`);
  const [hit] = await res.json();
  if (!hit) return null;
  const exact = !['road', 'street', 'suburb', 'quarter', 'neighbourhood', 'city_district'].includes(hit.addresstype);
  return { lngLat: [Number(hit.lon), Number(hit.lat)], label: hit.display_name, exact };
}
