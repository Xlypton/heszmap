export type CoverageStatus = 'none' | 'linked' | 'demo' | 'digitized';

/** Points at an exact place in a regulation PDF. */
export interface Citation {
  reg: string;
  page: number;
  para: string;
  quote: string;
}

export interface Param<T> {
  value: T | null;
  cite?: Citation;
}

export interface ZoneType {
  name: string;
  category: string;
  cite?: Citation;
  buildingMode: Param<string>;
  maxCoveragePct: Param<number>;
  maxFar: Param<number>;
  maxHeightM: Param<number>;
  minGreenPct: Param<number>;
  minPlotM2: Param<number>;
}

export interface Regulation {
  title: string;
  decree: string | null;
  /** Local mirror of the official PDF (relative to the site root). */
  pdf: string | null;
  officialUrl: string;
  effectiveFrom?: string | null;
  retrievedAt?: string;
  sha256?: string;
  status: CoverageStatus;
}

export interface Regulations {
  city: Regulation;
  regulations: Record<string, Regulation>;
  districts: Record<string, { status: CoverageStatus; regulations: string[] }>;
}

export interface LookupResult {
  lngLat: [number, number];
  label?: string;
  district?: { id: number; name: string };
  zoneCode?: string;
  zone?: ZoneType;
  regulation?: Regulation;
  districtRegulations: { id: string; reg: Regulation }[];
}
