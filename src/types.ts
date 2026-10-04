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
] as const;
export type ParamKey = (typeof PARAM_KEYS)[number];

export type ZoneType = {
  name: string;
  category: string | null;
  cite?: Citation;
  /** On the plan, but without a row in the limits table: only rules apply. */
  noTable?: boolean;
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
