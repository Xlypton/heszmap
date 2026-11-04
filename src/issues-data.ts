/** The known data problems (public/data/issues.json, written by scripts/build_issues.py). */
export type IssueStatus = 'open' | 'worked-around' | 'fixed';
export type Severity = 'wrong-answer' | 'missing' | 'uncertain' | 'info';

export interface Issue {
  id: string;
  area: string;
  kind: string;
  severity: Severity;
  scope: 'item' | 'area';
  note: string;
  status: IssueStatus;
  why?: string;
  source?: { reg: string; page?: number; para?: string };
  found_by?: string;
  first_seen: string;
  last_seen: string;
  fixed_at?: string;
  subject_zone?: string;
  subject_plot?: string;
  at?: [number, number];
  all_at?: [number, number][];
  places?: number;
  codes?: string[];
  fix?: string;
}

export interface IssueFile {
  generated: string;
  counts: Record<IssueStatus, number>;
  areas: Record<string, { name: string; reg: string }>;
  issues: Issue[];
}

export const KIND_LABEL: Record<string, string> = {
  'source-typo': 'Elírás a rendeletben',
  'variant-tables': 'Több táblázat egy övezetre',
  'crossed-boundary': 'Övezet átlépi a határvonalat',
  'guessed-zone': 'Becsült övezetek',
  'no-boundary-lines': 'Nincs határvonal a terven',
  'code-not-on-plan': 'Jel nem található a terven',
  'missing-citation': 'Hiányzó hivatkozás',
  'implausible-value': 'Gyanús érték a táblázatban',
  'text-vs-map': 'A szöveg és a térkép eltér',
  'text-not-read': 'A szöveg övezet-hivatkozásai nincsenek feldolgozva',
  'plan-misaligned': 'A terv nem illeszkedik a telkekhez',
  'plan-outdated': 'Elavult terv',
  'unreviewed-plots': 'Átnézetlen bizonytalan telkek',
  'plots-without-zone': 'Telkek övezet nélkül',
  'plots-missing': 'Hiányos telekadatok',
  'missing-height': 'Hiányzó építménymagasság',
  'no-table': 'Övezetek táblázatsor nélkül',
  'table-highlight': 'Rossz táblázatsor van kiemelve',
  'area-gap': 'Nem értelmezhető ellenőrzés',
};
export const SEVERITY_LABEL: Record<Severity, string> = {
  'wrong-answer': 'Téves adatot mutathat',
  missing: 'Hiányzó adat',
  uncertain: 'Bizonytalan',
  info: 'Tájékoztató',
};
export const STATUS_LABEL: Record<IssueStatus, string> = { open: 'Nyitott', 'worked-around': 'Megkerülve', fixed: 'Javítva' };

let cache: Promise<IssueFile | undefined> | undefined;
export function loadIssues(): Promise<IssueFile | undefined> {
  cache ??= fetch(`${import.meta.env.BASE_URL}data/issues.json`).then((r) => (r.ok ? (r.json() as Promise<IssueFile>) : undefined)).catch(() => undefined);
  return cache;
}

function metres(a: [number, number], b: [number, number]): number {
  const k = Math.PI / 180;
  const dx = (a[0] - b[0]) * k * Math.cos(a[1] * k);
  return Math.hypot(dx, (a[1] - b[1]) * k) * 6371000;
}

export function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
}

/** Open problems that can make the card wrong or incomplete at this spot: same zone, same plot, or a crossing near the tap. */
export function issuesForCard(f: IssueFile, regId: string | undefined, zone: string | undefined, hrsz: string | undefined, at: [number, number]): { here: Issue[]; areaKey?: string; areaOpen: number } {
  const areaKey = Object.keys(f.areas).find((k) => f.areas[k].reg === regId);
  if (!areaKey) return { here: [], areaOpen: 0 };
  const mine = f.issues.filter((i) => i.area === areaKey && i.status === 'open');
  const here = mine.filter((i) =>
    (i.severity === 'wrong-answer' || i.severity === 'missing') && (
      (zone && i.subject_zone === zone) ||
      (hrsz && i.subject_plot === hrsz) ||
      (i.kind === 'crossed-boundary' && (i.all_at ?? []).some((p) => metres(p, at) < 150))));
  return { here, areaKey, areaOpen: mine.length };
}

/** A pre-filled GitHub issue: reports need no backend yet. */
export function reportUrl(i: Issue | undefined, extra = ''): string {
  const title = i ? `Adatprobléma: ${i.area} – ${KIND_LABEL[i.kind] ?? i.kind}` : 'Adatprobléma bejelentése';
  const body = [
    i ? `Probléma: \`${i.id}\`` : '',
    i ? i.note : '',
    extra,
    '',
    'Mit látsz másképp? (írd ide, ha tudod, melyik oldalon / melyik sorban):',
  ].filter((x) => x !== '').join('\n');
  return `https://github.com/Xlypton/heszmap/issues/new?labels=data-issue&title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}
