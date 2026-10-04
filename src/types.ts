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
} & Partial<Record<ParamKey, Param>>;

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
}
