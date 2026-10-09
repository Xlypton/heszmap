import type { Status } from './effective';
import type { Citation, Regulation, TextRule } from './types';

/** Why a source is in the set: how it relates to the value the user tapped. */
export type Role = 'override' | 'defines' | 'table' | 'meaning' | 'variant' | 'national' | 'mention' | 'reference' | 'web' | 'cited';

/** One place that defines, changes or mentions a value: a spot in a regulation PDF, or a web page. */
export interface Source {
  role: Role;
  /** The PDF location (regulation id + quote). */
  cite?: Citation;
  /** A whole regulation without a location (opened from the list of regulations). */
  reg?: string;
  /** A web page that cannot be shown inline (e.g. njt.hu forbids framing). */
  url?: string;
  title?: string;
  /** What this source says the value is. */
  value?: string;
  /** Condition, or why the source belongs here. */
  note?: string;
  /** Whether a conditional source applies at the tapped plot. */
  status?: Status;
  /** The paragraph's text, when the extracted rules have it. */
  text?: string;
}

/** Every source behind one value on the card, opened side by side. */
export interface SourceSet {
  title: string;
  /** The value the card shows as applicable here. */
  value?: string;
  sources: Source[];
}

export const ROLE_LABEL: Record<Role, string> = {
  override: 'Felülírja – itt ez érvényes',
  defines: 'Előírja',
  table: 'Táblázat',
  meaning: 'Értelmezés',
  variant: 'Feltételes eltérés',
  national: 'Országos előírás (TÉKA)',
  mention: 'Említi',
  reference: 'Hivatkozott bekezdés',
  web: 'Jogszabálytár',
  cited: 'Hivatkozott hely',
};

const ROLE_ORDER: Role[] = ['cited', 'override', 'defines', 'table', 'meaning', 'variant', 'national', 'mention', 'reference', 'web'];

export interface Library {
  regs: Record<string, Regulation>;
  /** The extracted paragraphs of a regulation, if any. */
  paragraphs(regId: string): TextRule[] | undefined;
}

/** "XX. kerület – KÉSZ", "TÉKA": short enough for a pane header. */
export function shortName(regId: string, reg?: Regulation): string {
  if (regId === 'teka') return 'TÉKA';
  const kind = /-tkr$/.test(regId) ? 'TKR' : /-hesz$/.test(regId) ? 'HÉSZ' : /-kesz-m\d+$/.test(regId) ? 'KÉSZ melléklet' : /-kesz$/.test(regId) ? 'KÉSZ' : '';
  const place = reg?.title.split(' – ')[0].replace(/ kerület .*$/, ' ker.') ?? regId;
  return kind ? `${place} ${kind}` : place;
}

/** Deep link to the paragraph on njt.hu ("15/A. § (2)" -> #SZ15A@BE2); only for its HTML pages. */
export function njtUrl(reg: Regulation | undefined, para?: string): string | undefined {
  if (!reg?.officialUrl.includes('njt.jog.gov.hu/jogszabaly/')) return undefined;
  const m = para?.match(/^(\d+)(?:\/([A-Z]))?\.\s*§(?:\s*\((\d+)\))?/);
  if (!m) return reg.officialUrl;
  return `${reg.officialUrl}#SZ${m[1]}${m[2] ?? ''}${m[3] ? `@BE${m[3]}` : ''}`;
}

// One pane per paragraph: a paragraph cited for two things in the same set is shown once.
const key = (s: Source) => s.cite ? `${s.cite.reg}|${s.cite.para}` : s.url ?? s.reg ?? '';

/** "N. § (m)" and "(m) bekezdés" references inside a paragraph's text, skipping those that point
 *  into another law. `own` is the paragraph's own id, for references within its section. */
function references(text: string, own: string): string[] {
  const out: string[] = [];
  // Drop the paragraph's own leading "24. § (1)" / "(2)".
  const body = text.replace(/^\s*(?:\d+(?:\/[A-Z])?\.\s*§\s*)?(?:\(\d+\))?/, '');
  for (const m of body.matchAll(/(\d+(?:\/[A-Z])?)\.\s*§[\p{L}-]*(?:\s*\((\d+)\))?/gu)) {
    const before = body.slice(Math.max(0, m.index - 45), m.index);
    // "a 314/2012. (XI. 8.) Korm. rendelet 5. §", "az Étv. 2. §": another law's paragraph.
    if (/(?<!e )(rendelet|törvény|Korm\.|Étv\.|OTÉK|TÉKA)\S*\s*$/.test(before)) continue;
    out.push(m[2] ? `${m[1]}. § (${m[2]})` : `${m[1]}. §`);
  }
  const section = own.match(/^(\d+(?:\/[A-Z])?)\.\s*§/)?.[1];
  if (section) {
    // "(2) bekezdés", "(4), (5) és (6) bekezdés", "(4)–(6) bekezdés"
    for (const m of body.matchAll(/(?<!§\s*)((?:\(\d+\)(?:\s*[,–-]\s*|\s+(?:és|vagy)\s+|,\s*(?:és|vagy)\s+)?)+)\s*bekezdés/g)) {
      const nums = [...m[1].matchAll(/\((\d+)\)/g)].map((x) => Number(x[1]));
      const range = /\)\s*[–-]\s*\(/.test(m[1]) && nums.length === 2;
      const all = range ? Array.from({ length: Math.min(nums[1] - nums[0] + 1, 6) }, (_, k) => nums[0] + k) : nums;
      for (const n of all) out.push(`${section}. § (${n})`);
    }
  }
  return [...new Set(out)];
}

function findParagraph(rules: TextRule[] | undefined, para: string): TextRule | undefined {
  if (!rules) return undefined;
  // "24. §" may be stored as "24. § (1)": the first paragraph of the section stands for it.
  return rules.find((r) => r.id === para) ?? (para.includes('(') ? undefined : rules.find((r) => r.id.startsWith(`${para} (`)));
}

const MAX_REFERENCES = 4;

/** Fill in paragraph texts, add the paragraphs the sources refer to, drop duplicates, sort by role. */
export function expand(set: SourceSet, lib: Library): SourceSet {
  const seen = new Set<string>();
  const sources: Source[] = [];
  const rank = (s: Source) => ROLE_ORDER.indexOf(s.role);
  // The strongest role wins when a paragraph comes up twice (e.g. an override that is also flagged).
  for (const s of [...set.sources].sort((a, b) => rank(a) - rank(b))) {
    if (seen.has(key(s))) continue;
    seen.add(key(s));
    const text = s.text ?? (s.cite ? findParagraph(lib.paragraphs(s.cite.reg), s.cite.para)?.text : undefined);
    sources.push({ ...s, text });
  }
  const refs: Source[] = [];
  for (const s of sources) {
    if (!s.cite || !s.text || s.role === 'reference') continue;
    const rules = lib.paragraphs(s.cite.reg);
    for (const para of references(s.text, s.cite.para)) {
      if (refs.length >= MAX_REFERENCES) break;
      const r = findParagraph(rules, para);
      if (!r || r.id === s.cite.para) continue;
      const ref: Source = { role: 'reference', cite: r.cite, text: r.text };
      if (seen.has(key(ref))) continue;
      seen.add(key(ref));
      refs.push(ref);
    }
  }
  return { ...set, sources: [...sources, ...refs].sort((a, b) => rank(a) - rank(b)) };
}

/** A one-line reading of the set: what applies, what it overrides, what else to look at. */
export function summary(set: SourceSet): string {
  const by = (r: Role) => set.sources.filter((s) => s.role === r);
  const para = (s: Source) => s.cite?.para ?? s.title ?? '';
  const parts: string[] = [];
  const over = by('override'), table = by('table');
  if (over.length && table.length) {
    parts.push(`A táblázat értékét (${table[0].value ?? '–'}) itt a(z) ${over.map(para).join(', ')} felülírja.`);
  } else if (over.length) {
    parts.push(`Itt a(z) ${over.map(para).join(', ')} szerinti érték érvényes.`);
  }
  if (by('meaning').length) parts.push(`A táblázat értékének jelentését a(z) ${by('meaning').map(para).join(', ')} adja meg.`);
  const variants = by('variant');
  if (variants.length) {
    const here = variants.filter((v) => v.status === 'yes').length, unknown = variants.filter((v) => v.status === 'unknown').length;
    parts.push(`${variants.length} feltételes eltérés${here ? `, ebből ${here} itt érvényes` : ''}${unknown ? `, ${unknown} nem egyértelmű` : ''}.`);
  }
  if (by('national').length) parts.push(`${by('national').length} országos (TÉKA) előírás módosíthatja vagy kiegészíti.`);
  if (by('mention').length) parts.push(`${by('mention').length} további bekezdés említi.`);
  if (by('reference').length) parts.push(`${by('reference').length} hivatkozott bekezdés.`);
  return parts.join(' ');
}
