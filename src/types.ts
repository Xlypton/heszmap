export type CoverageStatus = 'none' | 'linked' | 'digitized';

/** Points at an exact place in a regulation PDF. The quote is the anchor; the page is a hint. */
export interface Citation {
  reg: string;
  page: number;
  para: string;
  quote: string;
}

/** A value as printed in the regulation ("6,0*", "kialakult", "---"), plus its number when it has one. */
export interface Param {
  text: string;
  num: number | null;
  cite?: Citation;
}

export const PARAM_KEYS = [
  'minPlotM2', 'buildingMode', 'maxCoveragePct', 'minHeightM', 'maxHeightM',
  'minGreenPct', 'maxUndergroundPct', 'maxFar', 'maxFarParking',
  // Columns some municipalities' tables add (Csobánka).
  'minPlotWidthM', 'minBuildablePlotM2', 'minBuildablePlotWidthM', 'maxHeightResidentialM',
] as const;
export type ParamKey = (typeof PARAM_KEYS)[number];

export type ZoneType = {
  name: string;
  category: string | null;
  cite?: Citation;
  /** On the plan, but without a row in the limits table: only rules apply. */
  noTable?: boolean;
  /** The height column is the OTÉK "épületmagasság" itself, not a "beépítési magasság" whose meaning
   *  depends on the building mode. */
  heightIs?: 'épületmagasság';
  /** The table's footnotes, explaining starred values. */
  notes?: { text: string; cite: Citation }[];
} & Partial<Record<ParamKey, Param>>;

export type RuleKind = 'zone' | 'category' | 'mode' | 'general' | 'public';

/** One paragraph (bekezdés) of the regulation and the zones it applies to. */
export interface Rule {
  id: string;
  section: string;
  chapter: string;
  text: string;
  kind: RuleKind;
  zones: string[] | '*';
  /** Applies only where the plan marks something or on named streets/parcels. */
  conditional: boolean;
  /** Table values (or setbacks, unit counts) the paragraph sets or changes. */
  flags: string[];
  note?: string | null;
  cite: Citation;
}

export interface PlanOverlay {
  tiles: string;
  bounds: [number, number, number, number];
  minzoom: number;
  maxzoom: number;
  /** The regulation's own area, when it covers only part of the district (several KÉSZ in one district). */
  area?: number[][][];
}

export interface Regulation {
  title: string;
  decree: string | null;
  /** Local copy of the regulation text as PDF (relative to the site root). */
  pdf: string | null;
  officialUrl: string;
  effectiveFrom?: string | null;
  retrievedAt?: string;
  sha256?: string;
  status: CoverageStatus;
  zoneTypes?: string;
  zoneLabels?: string;
  rules?: string;
  /** Parcels traced from the zoning plan, in grid chunks loaded around a tap. */
  parcels?: { dir: string; cell: [number, number] };
  /** Zone cells traced from the zoning plan (scripts/plan_zones.py), chunked like the parcels. */
  zoneAreas?: { dir: string; cell: [number, number] };
  /** Effective limits: what the body text does to the table (overrides, height meaning). */
  effective?: string;
  /** TKR: character-area rules, and protected buildings/streets. */
  tkr?: string;
  protected?: string;
  /** National rules that apply regardless of the local plan (TÉKA 136. § (2)). */
  mandatoryRules?: string;
  plan?: PlanOverlay;
  annexes?: { title: string; url: string }[];
}

export interface Regulations {
  city: Regulation;
  regulations: Record<string, Regulation>;
  districts: Record<string, { status: CoverageStatus; regulations: string[] }>;
}

export interface ZoneGuess {
  code: string;
  distanceM: number;
}

export interface LookupResult {
  lngLat: [number, number];
  label?: string;
  district?: { id: number; name: string };
  regId?: string;
  regulation?: Regulation;
  /** Nearest zone labels on the zoning plan, closest first, one per code. */
  guesses: ZoneGuess[];
  /** District-protected buildings, street sections or areas at this point (TKR 2. melléklet). */
  protectedHits: ProtectedHit[];
  /** False when the search only found the street: the pin is not on the plot. */
  exact: boolean;
  /** The plot under the point, traced from the zoning plan. */
  parcel?: Parcel;
  /** The zone cell under the point. */
  zone?: ZoneCell;
}

/** "plan": the plan's own zone boundaries enclose this area and it holds one zone code.
 *  "estimated": the boundary is not closed on the plan; the code is that of the nearest label
 *  reachable without crossing a zone boundary or a street. */
export type ZoneStatus = 'plan' | 'estimated';

export interface ZoneCell {
  code: string;
  status: ZoneStatus;
  street: boolean;
  /** A MultiPolygon when a zone continues across the seam between plan sheets in pieces. */
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
}

export interface Parcel {
  hrsz: string | null;
  areaM2: number;
  /** Disagreements with OpenStreetMap: "road" (an OSM street runs through it); "nohrsz" (no
   *  parcel number read inside). */
  check: string[];
  /** Zones the plot lies in, by share of its area. */
  zones: { code: string; status: ZoneStatus; share: number }[];
  geometry: { type: 'Polygon'; coordinates: number[][][] };
}

/** A paragraph from a regulation that is not scoped by KÉSZ zones. */
export interface TextRule {
  id: string;
  section: string;
  chapter?: string;
  text: string;
  cite: Citation;
}

export interface TkrRule extends TextRule {
  scope: 'area' | 'all-areas' | 'protected' | 'device' | 'procedure';
  areas?: string[];
  protection?: 'TSZ' | 'VU' | 'egyedi';
}

export interface Tkr {
  areas: Record<string, string>;
  zoneArea: [string, string][];
  rules: TkrRule[];
}

export interface Teka {
  basis: TextRule[];
  rules: TextRule[];
}

export interface ProtectedHit {
  kind: 'egyedi' | 'VU' | 'TSZ';
  name: string;
  ref: string;
  hrsz?: string;
  distanceM: number;
}
