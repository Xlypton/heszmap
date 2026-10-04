// Nominatim usage policy: max 1 req/s and no search-as-you-type, so we only geocode on submit.
const BUDAPEST_VIEWBOX = '18.92,47.62,19.34,47.34';

export interface GeocodeHit {
  lngLat: [number, number];
  label: string;
  /** False when only the street (not the house number) was found. */
  exact: boolean;
}

export async function geocode(query: string): Promise<GeocodeHit | null> {
  const params = new URLSearchParams({
    q: query,
    format: 'json',
    limit: '1',
    countrycodes: 'hu',
    viewbox: BUDAPEST_VIEWBOX,
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
