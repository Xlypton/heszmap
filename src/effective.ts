import booleanPointInPolygon from '@turf/boolean-point-in-polygon';
import type { Citation, ZoneType } from './types';

/** Where in the district a paragraph's value applies. */
export type Condition =
  | { type: 'along' | 'not-along' | 'parallel' | 'not-parallel'; street: string }
  | { type: 'block'; block: string }
  | { type: 'manual'; text: string };

export interface Override {
  zones: string[];
  param: string;
  value?: string;
  /** Heights: explicit párkánymagasság / épületmagasság / legmagasabb pont ("table", "+3,0 m" or "9,0 m"). */
  cornice?: string;
  building?: string;
  peak?: string;
  delta?: number;
  note?: string;
  condition: Condition | null;
  cite: Citation;
}

export interface Effective {
  heightMeaning: { mode: string; meaning: string; text: string; para: string; cite: Citation }[];
  overrides: Override[];
  streets: Record<string, number[][][]>;
  blocks: Record<string, number[][]>;
}

/** Nearest named street at the point, from the basemap. */
export interface StreetContext {
  name: string;
  bearing: number;
  distanceM: number;
}

export type Status = 'yes' | 'no' | 'unknown';

// A plot row along a street: the street's centre line is within this distance.
const ALONG_M = 45;
const PARALLEL_DEG = 20;
const OWN_STREET_M = 35;

function toM([lng, lat]: number[], ref: number[]): [number, number] {
  return [(lng - ref[0]) * 111_320 * Math.cos((ref[1] * Math.PI) / 180), (lat - ref[1]) * 110_540];
}

/** Distance (m) from p to the polylines, and the bearing (0–180°) of the nearest segment. */
export function nearestOnLines(p: number[], lines: number[][][]): { d: number; bearing: number } {
  let best = { d: Infinity, bearing: 0 };
  for (const ln of lines) {
    for (let i = 1; i < ln.length; i++) {
      const [ax, ay] = toM(ln[i - 1], p), [bx, by] = toM(ln[i], p);
      const dx = bx - ax, dy = by - ay;
      const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy || 1)));
      const d = Math.hypot(ax + dx * t, ay + dy * t);
      if (d < best.d) best = { d, bearing: ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 180 };
    }
  }
  return best;
}

function angleDiff(a: number, b: number): number {
  const d = Math.abs(a - b) % 180;
  return Math.min(d, 180 - d);
}

export function evaluate(c: Condition | null, p: [number, number], eff: Effective, near: StreetContext[] = []): Status {
  if (!c) return 'yes';
  if (c.type === 'manual') return 'unknown';
  if (c.type === 'block') {
    const ring = eff.blocks[c.block];
    return ring ? (booleanPointInPolygon(p, { type: 'Polygon', coordinates: [ring] }) ? 'yes' : 'no') : 'unknown';
  }
  const lines = eff.streets[c.street];
  if (!lines) return 'unknown';
  const ref = nearestOnLines(p, lines);
  const along = ref.d <= ALONG_M;
  // The plot's own street: the nearest named street other than the reference street.
  const own = near.find((n) => n.name !== c.street && n.distanceM <= OWN_STREET_M);
  const onParallel = !!own && angleDiff(own.bearing, ref.bearing) <= PARALLEL_DEG;
  // A plot between the reference street and a parallel street fronts both: say so instead of guessing.
  if (along && onParallel) return 'unknown';
  if (c.type === 'along') return along ? 'yes' : 'no';
  if (c.type === 'not-along') return along ? 'no' : 'yes';
  const parallel: Status = along ? 'no' : own ? (onParallel ? 'yes' : 'no') : 'unknown';
  if (c.type === 'parallel') return parallel;
  return parallel === 'unknown' ? 'unknown' : parallel === 'yes' ? 'no' : 'yes';
}

/** "Határ út" -> "Határ úttal", "Klapka utca" -> "Klapka utcával". */
function withStreet(s: string): string {
  if (s.endsWith(' út')) return `${s}tal`;
  if (s.endsWith(' utca')) return `${s.slice(0, -1)}ával`;
  return `${s}-val`;
}

export function conditionText(c: Condition | null): string {
  if (!c) return '';
  switch (c.type) {
    case 'along': return `${c.street} menti teleksoron`;
    case 'not-along': return `nem ${c.street} menti telken`;
    case 'parallel': return `${withStreet(c.street)} párhuzamos utcák teleksorán`;
    case 'not-parallel': return `nem ${withStreet(c.street)} párhuzamos utcában`;
    case 'block': return `a(z) ${c.block} által határolt területen`;
    case 'manual': return c.text;
  }
}

export const STATUS_TEXT: Record<Status, string> = {
  yes: 'itt érvényes (a térkép alapján)',
  no: 'itt valószínűleg nem érvényes',
  unknown: 'ellenőrizd: a térkép alapján nem egyértelmű (pl. két utcára néző telek)',
};

export interface Applied<T> {
  override: T;
  status: Status;
}

export function overridesFor(eff: Effective | undefined, code: string, param: string, p: [number, number], near?: StreetContext[]): Applied<Override>[] {
  return (eff?.overrides ?? [])
    .filter((o) => o.param === param && o.zones.includes(code))
    .map((o) => ({ override: o, status: evaluate(o.condition, p, eff!, near) }));
}

/** Which heights the table's "beépítési magasság" means for this building mode (15. §). */
export function heightMeaning(eff: Effective | undefined, modeText: string) {
  const open = ['---', '-', ''].includes(modeText.trim());
  const entries = (eff?.heightMeaning ?? []).filter((m) => open || modeText.includes(m.mode));
  return {
    entries,
    cornice: entries.some((m) => m.meaning.includes('párkánymagasság')),
    building: entries.some((m) => m.meaning === 'épületmagasság'),
    open,
  };
}

/** "9,0 m" | "table" | "+3,0 m" -> display text, given the table value. */
export function heightValue(spec: string, table: string | undefined, delta?: number): string {
  if (spec === 'table') return table ? `${table} m` : 'a táblázat szerinti';
  if (spec.startsWith('+') && table) {
    const n = Number(table.replace(',', '.').replace(/\*+$/, ''));
    if (!Number.isNaN(n) && delta !== undefined) return `${(n + delta).toLocaleString('hu-HU')} m`;
  }
  return spec;
}

export type { ZoneType };
