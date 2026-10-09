import type { Data } from './data';

// Parcel-number search: "hrsz 173037", "173037", "Csobánka 156", "0101/23 hrsz Csobánka".
// The index is public/data/hrsz/<regulation id>.json (scripts/hrsz_index.py), loaded on first use.

export interface HrszHit {
  lngLat: [number, number];
  hrsz: string;
  regId: string;
}

const NUMBER = /(?:^|\s)(0?\d{1,6}(?:\/\d{1,4}){0,2})(?=\s|$|,)/;
const indexes = new Map<string, Promise<Record<string, [number, number]>>>();

const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/\bker(ulet)?\b|\bhrsz\b|[.,:]/g, ' ').replace(/\s+/g, ' ').trim();

function index(regId: string): Promise<Record<string, [number, number]>> {
  if (!indexes.has(regId)) {
    indexes.set(regId, fetch(`${import.meta.env.BASE_URL}data/hrsz/${regId}.json`)
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({})));
  }
  return indexes.get(regId)!;
}

/** The parcel number and the districts the query names, or undefined when it is not a parcel search
 * (an address such as "Béke út 10, Csobánka" has words that are neither "hrsz" nor a place name). */
export function parseHrsz(data: Data, query: string): { hrsz: string; districts: number[] } | undefined {
  const m = query.match(NUMBER);
  if (!m) return undefined;
  const rest = norm(query.replace(m[1], ' '));
  const named = data.districts.features.filter((f) => {
    const name = norm(f.properties.name);
    return rest && (name === rest || name.startsWith(rest + ' ') || rest.split(' ').every((w) => name.split(' ').includes(w)));
  });
  if (rest && !named.length && !/hrsz/i.test(query)) return undefined;
  return { hrsz: m[1], districts: named.map((f) => f.properties.id) };
}

/** Looks the number up in the named districts, else in the regulation in view, else everywhere
 * (nearest to the view first: small numbers repeat between towns). */
export async function findHrsz(data: Data, query: string, inView: string | undefined,
  centre: [number, number]): Promise<HrszHit | null | undefined> {
  const q = parseHrsz(data, query);
  if (!q) return undefined;
  const withPlots = Object.keys(data.regs.regulations).filter((id) => data.regs.regulations[id].parcels);
  const named = withPlots.filter((id) => q.districts.some((d) => data.regs.districts[d]?.regulations.includes(id)));
  const order = named.length ? named : [...(inView && withPlots.includes(inView) ? [inView] : []), ...withPlots];
  const hits: HrszHit[] = [];
  for (const regId of order) {
    const at = (await index(regId))[q.hrsz];
    if (at) hits.push({ lngLat: at, hrsz: q.hrsz, regId });
    if (hits.length && regId === inView) break;
  }
  const d = (h: HrszHit) => (h.lngLat[0] - centre[0]) ** 2 + (h.lngLat[1] - centre[1]) ** 2;
  return hits.sort((a, b) => d(a) - d(b))[0] ?? null;
}
