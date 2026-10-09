import { conditionText, evaluate, heightMeaning, heightValue, overridesFor, STATUS_TEXT, type Applied, type Effective, type Override, type StreetContext } from './effective';
import type { Source, SourceSet } from './sources';
import type { Citation, LookupResult, Param, ParamKey, ProtectedHit, Regulation, Rule, Teka, TextRule, Tkr, TkrRule, ZoneType } from './types';

const STATUS_LABEL: Record<string, string> = {
  none: 'nincs adat',
  linked: 'szabályzat feldolgozva',
  digitized: 'övezetek ellenőrizve',
};

const PARAMS: { key: ParamKey; label: string; unit: string }[] = [
  { key: 'buildingMode', label: 'Beépítési mód', unit: '' },
  { key: 'maxCoveragePct', label: 'Max. beépítettség', unit: '%' },
  { key: 'minGreenPct', label: 'Min. zöldfelület', unit: '%' },
  { key: 'minPlotM2', label: 'Min. telekterület', unit: ' m²' },
  { key: 'minPlotWidthM', label: 'Min. telekszélesség / -mélység', unit: ' m' },
  { key: 'minBuildablePlotM2', label: 'Beépíthető legkisebb telekterület', unit: ' m²' },
  { key: 'minBuildablePlotWidthM', label: 'Beépíthető legkisebb telekszélesség', unit: ' m' },
  { key: 'maxHeightResidentialM', label: 'Max. épületmagasság lakóépületnél', unit: ' m' },
  { key: 'maxFar', label: 'Max. szintterületi mutató', unit: '' },
  { key: 'maxFarParking', label: 'Szintterületi mutató – parkolás', unit: '' },
  { key: 'maxUndergroundPct', label: 'Max. terepszint alatti beépítés', unit: '%' },
];

export interface CardExtras {
  tkr?: { regId: string; reg: Regulation; data: Tkr };
  teka?: { reg: Regulation; data: Teka };
  effective?: Effective;
  /** Nearest named street at the point (from the basemap), for "parallel street" conditions. */
  near?: StreetContext[];
}

export interface CardHandlers {
  /** A citation alone, or every source of the value it belongs to (`set`), with `cite` selected. */
  openCitation(cite: Citation | undefined, set?: SourceSet): void;
  openRegulation(reg: Regulation): void;
}

/** What a [data-cite] button opens. */
interface Ref {
  cite?: Citation;
  set?: SourceSet;
}

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function show(p: Param, unit: string): string {
  // Keep the regulation's own wording ("kialakult", footnote stars); add the unit only to plain numbers.
  return p.num !== null && /^[\d\s,.]+\**$/.test(p.text) ? `${esc(p.text)}${unit}` : esc(p.text);
}

function cite(c: Citation | undefined, cites: Ref[], set?: SourceSet): number {
  cites.push({ cite: c, set });
  return cites.length - 1;
}

const PARAM_LABEL: Record<string, string> = {
  setbacks: 'Elő-, oldal-, hátsókert', units: 'Rendeltetési egységek száma', buildings: 'Épületek száma, mérete',
};

/** A ↗ link; inside a value's cell it opens all the value's sources (`set`) with this one selected. */
function citeLink(c: Citation, cites: Ref[], label = c.para, set?: SourceSet): string {
  return `<button class="link" data-cite="${cite(c, cites, set)}" title="${esc(c.quote)}">${esc(label)} ↗</button>`;
}

/** Everything the card knows about a zone at the tapped point, for gathering a value's sources. */
interface Ctx {
  code: string;
  eff?: Effective;
  at: [number, number];
  near?: StreetContext[];
  rules: Rule[];
  teka?: Teka;
  cites: Ref[];
}

/** TÉKA paragraphs that change a local limit regardless of the local plan (TÉKA 136. § (2)). */
const NATIONAL: Record<string, [string, string][]> = {
  maxCoveragePct: [['8. § (9)', 'Természetes anyagú tartószerkezetű lakóépületnél a megengedett beépítettség 1,2-szerese.'],
    ['8. § (10)', 'Utólagos külső hőszigetelés nem számít bele.'], ['4. § (5)', 'Egyedi eltérés: legfeljebb +5 százalékpont.']],
  maxUndergroundPct: [['47. § (8)', 'Gépjármű-lift az előkertben nem számít bele.'], ['4. § (5)', 'Egyedi eltérés: legfeljebb +5 százalékpont.']],
  maxFar: [['8. § (10)', 'Utólagos külső hőszigetelés nem számít bele.'], ['4. § (5)', 'Egyedi eltérés: legfeljebb +20%, de legfeljebb 0,2 m²/m².']],
  minGreenPct: [['51. §', 'Az automata visszaváltó berendezés helye zöldfelületnek számít.'], ['4. § (5)', 'Egyedi eltérés: legfeljebb −5 százalékpont.']],
  height: [['4. § (5)', 'Egyedi eltérés: a beépítési magasságtól legfeljebb 1,00 m.']],
};

/** The table column a paragraph's flag refers to (rules-*.json "flags"). */
const FLAG: Record<string, string> = { height: 'maxHeightM', minHeight: 'minHeightM' };

const OTEK: Source = {
  role: 'web', url: 'https://njt.jog.gov.hu/jogszabaly/1997-253-20-22', title: 'OTÉK – 253/1997. (XII. 20.) Korm. rendelet',
  note: 'A magassági fogalmak (épületmagasság, párkánymagasság) meghatározása az OTÉK 1. mellékletében. Hogy melyik időállapotát kell alkalmazni, a TÉKA 136. § (1) mondja meg; a jogszabálytárban az időállapot a lap tetején választható.',
};

/** Sources every cell of a value shares: TÉKA counterparts and paragraphs flagged as setting it. */
function baseSources(param: string, ctx: Ctx): Source[] {
  const out: Source[] = [];
  const flag = FLAG[param] ?? param;
  for (const r of ctx.rules.filter((r) => r.flags.includes(flag))) out.push({ role: 'mention', cite: r.cite, text: r.text, note: r.note ?? undefined });
  const teka = [...(ctx.teka?.rules ?? []), ...(ctx.teka?.basis ?? [])];
  for (const [id, note] of NATIONAL[param] ?? []) {
    const r = teka.find((x) => x.id === id);
    if (r) out.push({ role: 'national', cite: r.cite, text: r.text, note });
  }
  return out;
}

function overrideSource(a: Applied<Override>, value: string, table: boolean): Source {
  const cond = conditionText(a.override.condition);
  const role = a.status === 'yes' && (table || !a.override.condition) ? (table ? 'override' : 'defines') : 'variant';
  return { role, cite: a.override.cite, value, status: a.override.condition ? a.status : undefined,
    note: [cond, a.override.note].filter(Boolean).join(' · ') || undefined };
}

/** "⧉ 5 forrás": opens all of a value's sources side by side. */
function setLink(set: SourceSet, ctx: Ctx): string {
  const n = new Set(set.sources.map((s) => s.cite ? `${s.cite.reg}|${s.cite.para}` : s.url)).size;
  return n > 1 ? `<button class="srcs" data-cite="${cite(undefined, ctx.cites, set)}" title="Az összes forrás egymás mellett">⧉ ${n} forrás</button>` : '';
}

/** A conditional value that may or may not apply at this plot. */
function variant(text: string, a: Applied<Override>, cites: Ref[], set?: SourceSet): string {
  const cond = conditionText(a.override.condition);
  return `<li class="variant st-${a.status}">${cond ? `<span class="cond">${esc(cond)}:</span> ` : ''}<b>${esc(text)}</b>
    ${a.override.note ? `<span class="muted">(${esc(a.override.note)})</span>` : ''} ${citeLink(a.override.cite, cites, undefined, set)}
    ${a.override.condition ? `<span class="status">${STATUS_TEXT[a.status]}</span>` : ''}</li>`;
}

/** Effective value: what applies here (paragraph overrides first), the table value as background. */
function effCell(label: string, main: string, source: string, variants: string[], set: SourceSet, ctx: Ctx, overridden = false): string {
  return `<div class="param${overridden ? ' overridden' : ''}"><dt>${label}${setLink(set, ctx)}</dt><dd>${main}</dd>
    <span class="src">${source}</span>${variants.length ? `<ul class="variants">${variants.join('')}</ul>` : ''}</div>`;
}

function tableCell(label: string, p: Param, unit: string, key: string, ctx: Ctx): string {
  const { cites } = ctx;
  const applied = overridesFor(ctx.eff, ctx.code, key, ctx.at, ctx.near);
  const here = applied.filter((a) => a.status === 'yes' && a.override.value);
  const other = applied.filter((a) => a.status !== 'yes' || !a.override.value);
  const plain = p.num !== null && /^[\d\s,.]+\**$/.test(p.text) ? `${p.text}${unit}` : p.text;
  const set: SourceSet = { title: label, value: here.length ? here.map((a) => a.override.value!).join('; ') : plain, sources: [
    ...applied.map((a) => overrideSource(a, a.override.value ?? '', true)),
    ...(p.cite ? [{ role: 'table' as const, cite: p.cite, value: plain }] : []),
    ...baseSources(key, ctx),
  ] };
  const tableSrc = p.cite ? `táblázat: ${show(p, unit)} · ${citeLink(p.cite, cites, undefined, set)}` : `táblázat: ${show(p, unit)}`;
  if (here.length) {
    const main = here.map((a) => esc(a.override.value!)).join('; ');
    return effCell(label, main, `${here.map((a) => citeLink(a.override.cite, cites, undefined, set)).join(' ')} · ${tableSrc}`,
      other.map((a) => variant(a.override.value ?? '', a, cites, set)), set, ctx, true);
  }
  return effCell(label, show(p, unit), p.cite ? citeLink(p.cite, cites, undefined, set) : '<span class="nocite">nincs hivatkozás</span>',
    other.map((a) => variant(a.override.value ?? '', a, cites, set)), set, ctx);
}

/** Heights shown as párkánymagasság / épületmagasság / legmagasabb pont, never as "beépítési magasság". */
function heightCells(z: ZoneType, modeText: string, ctx: Ctx): string[] {
  const { code, eff, at, near, cites } = ctx;
  const hm = heightMeaning(eff, modeText);
  const maxT = z.maxHeightM?.text && !['---', '-'].includes(z.maxHeightM.text) ? z.maxHeightM.text : undefined;
  const minT = z.minHeightM?.text && !['---', '-'].includes(z.minHeightM.text) ? z.minHeightM.text : undefined;
  // Each height gets its own set; the table value, its meaning (15. §), TÉKA and OTÉK are shared.
  const shared = (p: Param | undefined, t: string | undefined, param: string): Source[] => [
    ...(p?.cite && t ? [{ role: 'table' as const, cite: p.cite, value: `${t} m` }] : []),
    ...hm.entries.map((m) => ({ role: 'meaning' as const, cite: m.cite, note: m.text })),
    ...baseSources(param, ctx),
    OTEK,
  ];
  const mkSet = (title: string, p: Param | undefined, t: string | undefined, param: string): SourceSet => ({ title, sources: shared(p, t, param) });
  const meaningLinks = (set: SourceSet) => hm.entries.map((m) => citeLink(m.cite, cites, undefined, set)).join(' ');
  const tableNote = (t: string | undefined, set: SourceSet, p?: Param) =>
    t ? `táblázat: beépítési magasság ${esc(t)} m${p?.cite ? ` ${citeLink(p.cite, cites, undefined, set)}` : ''} · értelmezés: ${meaningLinks(set)}${hm.open ? ' (a beépítési módtól függ)' : ''}` : '';

  type Row = { label: string; main?: string; src: string; variants: string[]; overridden: boolean; set: SourceSet };
  // A table that gives the épületmagasság itself needs no interpretation.
  const direct = z.heightIs === 'épületmagasság' && !hm.entries.length;
  const sets = {
    cornice: mkSet('Max. párkánymagasság', z.maxHeightM, maxT, 'height'),
    building: mkSet('Max. épületmagasság', z.maxHeightM, maxT, 'height'),
    peak: mkSet('Legmagasabb pont', undefined, undefined, 'height'),
  };
  const directSrc = z.maxHeightM?.cite ? citeLink(z.maxHeightM.cite, cites, undefined, sets.building) : '';
  const rows: Record<'cornice' | 'building' | 'peak', Row> = {
    cornice: { label: 'Max. párkánymagasság', main: hm.cornice && maxT ? `${esc(maxT)} m` : undefined, src: tableNote(maxT, sets.cornice, z.maxHeightM),
      variants: [], overridden: false, set: sets.cornice },
    building: { label: 'Max. épületmagasság', main: (hm.building || direct) && maxT ? `${esc(maxT)} m` : undefined,
      src: direct ? directSrc : tableNote(maxT, sets.building, z.maxHeightM), variants: [], overridden: false, set: sets.building },
    peak: { label: 'Legmagasabb pont', main: undefined, src: '', variants: [], overridden: false, set: sets.peak },
  };
  if (hm.open && maxT && !direct) {
    rows.cornice.label += ' (zártsorú, oldalhatáron álló, ikres)';
    rows.building.label += ' (szabadonálló)';
  }
  for (const a of overridesFor(eff, code, 'height', at, near)) {
    const o = a.override;
    for (const k of ['cornice', 'building', 'peak'] as const) {
      const spec = o[k];
      if (!spec) continue;
      const value = heightValue(spec, maxT, o.delta);
      rows[k].set.sources.push(overrideSource(a, value, true));
      if (a.status === 'yes') {
        rows[k].main = esc(value);
        const note = o.note && (k === 'cornice' || !o.cornice) ? ` · ${esc(o.note)}` : '';
        rows[k].src = `${citeLink(o.cite, cites, undefined, rows[k].set)}${note}${rows[k].src ? ` · ${rows[k].src}` : ''}`;
        rows[k].overridden = true;
      } else {
        rows[k].variants.push(variant(value, a, cites, rows[k].set));
      }
    }
  }
  const out = (['cornice', 'building', 'peak'] as const)
    .filter((k) => rows[k].main || rows[k].variants.length)
    .map((k) => {
      const r = rows[k];
      r.set.value = r.main ? r.main.replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n))) : undefined;
      return effCell(r.label, r.main ?? '–', r.main ? r.src || meaningLinks(r.set) : 'csak az alábbi esetben', r.variants, r.set, ctx, r.overridden);
    });

  // Minimum height: the table's minimum follows the same meaning; paragraphs may set a minimum building height.
  const minRows: string[] = [];
  const minOv = overridesFor(eff, code, 'minHeight', at, near);
  const minHere = minOv.find((a) => a.status === 'yes');
  const minLabel = hm.building && !hm.cornice ? 'Min. épületmagasság' : 'Min. párkánymagasság';
  const minSet = mkSet(minHere ? 'Min. épületmagasság' : minLabel, z.minHeightM, minT, 'minHeight');
  minSet.sources.push(...minOv.map((a) => overrideSource(a, heightValue(a.override.building!, minT), true)));
  if (minHere) {
    minSet.value = heightValue(minHere.override.building!, minT);
    minRows.push(effCell('Min. épületmagasság', esc(minSet.value),
      `${citeLink(minHere.override.cite, cites, undefined, minSet)} · ${esc(conditionText(minHere.override.condition))}${minT ? ` · ${tableNote(minT, minSet, z.minHeightM)}` : ''}.`,
      minOv.filter((a) => a !== minHere).map((a) => variant(heightValue(a.override.building!, minT), a, cites, minSet)), minSet, ctx, true));
  } else if (minT || minOv.length) {
    minSet.value = minT ? `${minT} m` : undefined;
    minRows.push(effCell(minLabel, minT ? `${esc(minT)} m` : '–', tableNote(minT, minSet, z.minHeightM),
      minOv.map((a) => variant(heightValue(a.override.building!, minT), a, cites, minSet)), minSet, ctx));
  }
  return [...out, ...minRows];
}

/** Values the table has no column for: setbacks, unit counts, number of buildings. */
function extraRows(ctx: Ctx): string {
  const blocks = Object.entries(PARAM_LABEL).map(([param, label]) => {
    const applied = overridesFor(ctx.eff, ctx.code, param, ctx.at, ctx.near);
    if (!applied.length) return '';
    const set: SourceSet = { title: label, sources: [...applied.map((a) => overrideSource(a, a.override.value ?? '', false)), ...baseSources(param, ctx)] };
    return `<div class="extra"><dt>${label}${setLink(set, ctx)}</dt><ul class="variants">${applied.map((a) => variant(a.override.value ?? '', a, ctx.cites, set)).join('')}</ul></div>`;
  }).join('');
  return blocks ? `<h3>További előírt értékek</h3><div class="extras">${blocks}</div>` : '';
}

const GROUPS: { title: string; open: boolean; pick: (r: Rule) => boolean }[] = [
  { title: 'Az övezet saját előírásai', open: true, pick: (r) => !r.conditional && r.kind === 'zone' },
  { title: 'A területfelhasználási egység előírásai', open: true, pick: (r) => !r.conditional && r.kind === 'category' },
  { title: 'A beépítési módhoz kötött előírások', open: true, pick: (r) => !r.conditional && r.kind === 'mode' },
  { title: 'Feltételes: csak ha a szabályozási terv jelöli, vagy adott utcákra, telkekre', open: false, pick: (r) => r.conditional },
  { title: 'Általános előírások', open: false, pick: (r) => !r.conditional && (r.kind === 'general' || r.kind === 'public') },
];

/** A paragraph opened with the paragraphs its text refers to. */
function ruleSet(r: TextRule): SourceSet {
  return { title: r.id, sources: [{ role: 'cited', cite: r.cite, text: r.text }] };
}

function textRules(rules: TextRule[], cites: Ref[]): string {
  return `<ul>${rules.map((r) => `
    <li class="rule">
      <button class="rule-id" data-cite="${cite(r.cite, cites, ruleSet(r))}">${esc(r.id)} ↗</button>
      <p>${esc(r.text.replace(/^\d+(?:\/[A-Z])?\.\s*§\s*/, ''))}</p>
    </li>`).join('')}</ul>`;
}

function details(title: string, body: string, count: number, open = false): string {
  return count ? `<details class="rules" ${open ? 'open' : ''}><summary>${title} <span class="count">${count}</span></summary>${body}</details>` : '';
}

const PROTECTION_LABEL: Record<ProtectedHit['kind'], string> = {
  egyedi: 'Kerületi egyedi védelem alatt álló építmény',
  VU: 'Kerületi védelem alatt álló utcaszakasz',
  TSZ: 'Kerületi védelem alatt álló településszerkezet',
};

function areaFor(tkr: Tkr, code: string | undefined): string | undefined {
  return code ? tkr.zoneArea.find(([rx]) => new RegExp(`^(?:${rx})$`).test(code))?.[1] : undefined;
}

export function tkrBlock(tkr: Tkr, reg: Regulation, hits: ProtectedHit[], area: string | undefined, estimated: boolean, cites: Ref[]): string {
  const prot = hits.map((h) => `<div class="protected"><b>${PROTECTION_LABEL[h.kind]}</b>: ${esc(h.name)}${h.hrsz ? ` (hrsz ${esc(h.hrsz)})` : ''}
      <span class="muted small">· TKR ${esc(h.ref)}${h.kind !== 'TSZ' ? ` · ${Math.round(h.distanceM)} m` : ''}</span></div>`).join('');
  const protRules = tkr.rules.filter((r) => r.scope === 'protected' && hits.some((h) => h.kind === r.protection));
  const pick = (f: (r: TkrRule) => boolean) => tkr.rules.filter(f);
  const areaRules = area ? pick((r) => r.scope === 'area' && !!r.areas?.includes(area)) : [];
  const allAreas = pick((r) => r.scope === 'all-areas');
  const devices = pick((r) => r.scope === 'device');
  const procedure = pick((r) => r.scope === 'procedure');
  const map = reg.annexes?.[0];
  return `<h3>Településkép (TKR)</h3>
    <p class="muted small">${esc(reg.decree ?? '')}${reg.effectiveFrom ? ` · hatályos: ${esc(reg.effectiveFrom)}` : ''}</p>
    ${prot || '<p class="muted small">Nem találtunk itt kerületi védett építményt, utcaszakaszt vagy védett településszerkezetet (TKR 2. melléklet). A védett épületeket cím alapján helyeztük el, ezért a pontosság néhány méter.</p>'}
    ${details('Védelemre vonatkozó előírások', textRules(protRules, cites), protRules.length, true)}
    <div class="picker">
      <label for="tkr-area">Településképi karakterterület</label>
      <select id="tkr-area">
        <option value="">– válassz –</option>
        ${Object.entries(tkr.areas).map(([k, v]) => `<option value="${k}" ${k === area ? 'selected' : ''}>${esc(v)}</option>`).join('')}
      </select>
      <p class="muted small">${estimated ? 'Becslés a KÉSZ-övezet alapján. ' : ''}A pontos lehatárolás a TKR 1. mellékletének térképén van${map ? `: <a href="${esc(map.url)}" target="_blank" rel="noopener">térkép megnyitása ↗</a>` : ''}.</p>
    </div>
    ${details('A karakterterület előírásai', textRules(areaRules, cites), areaRules.length, true)}
    ${details('Minden karakterterületen', textRules(allAreas, cites), allAreas.length)}
    ${details('Cégtábla, klíma, hőszivattyú, napelem, kémény, közmű', textRules(devices, cites), devices.length)}
    ${details('Eljárás: konzultáció, véleményezés, bejelentés', textRules(procedure, cites), procedure.length)}`;
}

export function tekaBlock(teka: Teka, reg: Regulation, cites: Ref[], local?: Regulation): string {
  const chapters = new Map<string, TextRule[]>();
  for (const r of teka.rules) chapters.set(r.chapter ?? '', [...(chapters.get(r.chapter ?? '') ?? []), r]);
  const basis = teka.basis.map((b) => `<button class="link" data-cite="${cite(b.cite, cites, ruleSet(b))}">${esc(b.id)}</button>`).join(', ');
  return `<h3>TÉKA – országos előírások</h3>
    <p class="small">${esc(reg.decree ?? '')}${reg.effectiveFrom ? ` · hatályos: ${esc(reg.effectiveFrom)}` : ''}.
    A helyi szabályzat${local?.decree ? ` (${esc(local.decree)})` : ''} a 314/2012. Korm. rendelet szerint készült, ezért a TÉKA 136. § (1) b) szerint az OTÉK 2021. július 15-i állapotú II–III. fejezetével együtt kell alkalmazni.
    A TÉKA 136. § (2) szerint viszont az alábbi rendelkezések minden 2025. június 30. után indult eljárásban kötelezők, és a helyi szabályzat ezekkel ellentétes előírásai nem alkalmazhatók (${basis}).</p>
    ${[...chapters].map(([ch, rs]) => details(esc(ch), textRules(rs, cites), rs.length)).join('')}`;
}

function rulesBlock(rules: Rule[], cites: Ref[]): string {
  if (!rules.length) return '';
  const groups = GROUPS.map((g) => {
    const items = rules.filter(g.pick);
    if (!items.length) return '';
    const li = items.map((r) => `
      <li class="rule${r.flags.length ? ' flagged' : ''}">
        <button class="rule-id" data-cite="${cite(r.cite, cites, ruleSet(r))}">${esc(r.id)} ↗</button>
        <p>${esc(r.text.replace(/^\d+(?:\/[A-Z])?\.\s*§\s*/, ''))}</p>
        ${r.note ? `<p class="rule-note">${esc(r.note)}</p>` : ''}
      </li>`).join('');
    return `<details class="rules" ${g.open ? 'open' : ''}><summary>${g.title} <span class="count">${items.length}</span></summary><ul>${li}</ul></details>`;
  }).join('');
  return `<h3>Minden vonatkozó előírás</h3>
    <p class="muted small">A rendelet összes bekezdése, ami erre az övezetre vonatkozik. A ↗ megnyitja a bekezdést a rendeletben.
    A sárga szegélyű bekezdések határértéket, telekméretet vagy rendeltetési egységszámot írnak elő.</p>${groups}`;
}

function zoneBlock(code: string, z: ZoneType, cites: Ref[], rules: Rule[], at: [number, number], extras: CardExtras): string {
  const eff = extras.effective, near = extras.near;
  const ctx: Ctx = { code, eff, at, near, rules, teka: extras.teka?.data, cites };
  let head = `<div class="zone-code">${esc(code)}</div><div class="zone-name">${esc(z.name)}</div>`;
  if (z.cite) {
    // The zone's definition, with its own paragraphs alongside.
    const own = rules.filter((r) => r.kind === 'zone' && !r.conditional).slice(0, 6);
    const set: SourceSet = { title: `${code} – ${z.name}`, sources: [{ role: 'cited', cite: z.cite },
      ...own.map((r) => ({ role: 'mention' as const, cite: r.cite, text: r.text, note: 'az övezet saját előírása' }))] };
    head = `<button class="zone cited" data-cite="${cite(z.cite, cites, set)}">${head}<span class="para">${esc(z.cite.para)} ↗</span></button>`;
  } else {
    head = `<div class="zone">${head}</div>`;
  }
  // The building mode can itself depend on the location (e.g. Vi-2/L-Z1 on Határ út-parallel streets).
  // Only location-dependent mode rules change how the height is read; explanatory ones (26. § (1)) do not.
  const modeHere = overridesFor(eff, code, 'buildingMode', at, near)
    .find((a) => a.status === 'yes' && a.override.value && a.override.condition);
  const modeText = modeHere?.override.value ?? z.buildingMode?.text ?? '';
  const all = overridesFor(eff, code, 'all', at, near).map((a) =>
    `<p class="kialakult">⚠ ${esc(a.override.value ?? '')} ${citeLink(a.override.cite, cites)}</p>`).join('');
  const cells = [
    ...PARAMS.filter(({ key }) => z[key] && z[key]!.text && z[key]!.text !== '---' && z[key]!.text !== '-')
      .map(({ key, label, unit }) => tableCell(label, z[key]!, unit, key, ctx)),
  ];
  cells.splice(2, 0, ...heightCells(z, modeText, ctx));
  const table = z.noTable
    ? '<p class="hint">Ennek az övezetnek nincs sora a határérték-táblázatban: az előírásait lent találod.</p>'
    : `${all}<dl class="params">${cells.join('')}</dl>
    ${(z.notes ?? []).map((n) => `<p class="small">${esc(n.text)} ${citeLink(n.cite, cites)}</p>`).join('')}
    <p class="muted small">${eff
      ? 'Az értékek a rendelet szövegével együtt értelmezve: ha egy bekezdés eltér a táblázattól, az itt alkalmazandó érték látszik, alatta a táblázat értéke.'
      : 'Az értékek a rendelet táblázatából valók. A szöveg további előírásokat és kivételeket adhat (pl. elő-, oldal- és hátsókert): ezeket itt még nem dolgoztuk fel, nézd meg a rendeletben.'} ${z.heightIs === 'épületmagasság' ? 'A táblázat magassága az épületmagasság (OTÉK szerint).' : 'A „beépítési magasság” a beépítési módtól függően párkánymagasság vagy épületmagasság (15. §).'}
    A feltételes értékeknél a térkép alapján jelezzük, érvényes-e ezen a telken. A * lábjegyzetre utal (pl. OTÉK-eltérés).</p>
    ${extraRows(ctx)}
    <div class="calc">
      <label for="plot">Telekterület (m²)</label>
      <input id="plot" type="number" min="0" step="1" placeholder="pl. 720" />
      <div id="calc-out"></div>
    </div>`;
  return `${head}${table}${rulesBlock(rules, cites)}`;
}

function renderCalc(z: ZoneType, area: number): string {
  if (!area) return '';
  const n = (k: ParamKey) => z[k]?.num ?? null;
  const rows: string[] = [];
  const cov = n('maxCoveragePct'), far = n('maxFar'), green = n('minGreenPct'), minPlot = n('minPlotM2');
  if (cov !== null) rows.push(`Max. beépíthető alapterület: <b>${Math.floor((area * cov) / 100)} m²</b>`);
  if (far !== null) rows.push(`Max. bruttó szintterület: <b>${Math.floor(area * far)} m²</b>`);
  if (green !== null) rows.push(`Min. zöldfelület: <b>${Math.ceil((area * green) / 100)} m²</b>`);
  if (minPlot !== null && area < minPlot) rows.push(`<span class="warn">Kisebb, mint a kialakítható legkisebb telek (${minPlot} m²) – meglévő telekre külön szabályok vonatkozhatnak.</span>`);
  return rows.map((r) => `<div>${r}</div>`).join('');
}

function regItem(i: number, r: Regulation): string {
  const decree = r.decree ? `<span class="muted small">${esc(r.decree)}${r.effectiveFrom ? ` · hatályos: ${esc(r.effectiveFrom)}` : ''}</span>` : '';
  return `<li><button class="link" data-reg="${i}">${r.pdf ? '📄' : '↗'} ${esc(r.title)}</button>${decree}</li>`;
}

const PARCEL_CHECK: Record<string, string> = {
  road: 'Az OpenStreetMap szerint utca halad át ezen a területen: lehet, hogy (részben) közterület.',
  'outline-wrong': 'A tervvel összevetve ez a körvonal nem pontos telekhatár: a valódi határt a „Szabályozási terv” rétegen nézd meg.',
};

function parcelChecks(check: string[]): string {
  const items = check.filter((c) => PARCEL_CHECK[c]).map((c) => `<span class="warn small block">⚠ ${PARCEL_CHECK[c]}</span>`);
  return items.join('');
}

/** Which zone applies here, and on what evidence: the plan's zone cell, the plot's share of each
 *  zone, and the KÉSZ text naming the zone for a street-bounded block that contains the point. */
function zoneEvidence(r: LookupResult, eff: Effective | undefined): { code?: string; html: string } {
  const z = r.zone;
  const pz = (r.parcel?.zones ?? []).filter((x) => x.share >= 0.15);
  const pCodes = [...new Set(pz.map((x) => x.code))];
  // The plot is what gets built on: its majority zone wins over the tapped point's cell.
  const code = pz.length && pz[0].share >= 0.5 ? pz[0].code : z?.code;
  if (!code) return { html: '' };
  const status = (pz.length && pz[0].code === code ? pz[0].status : z?.status) ?? 'estimated';
  const lines: string[] = [];
  lines.push(status === 'plan'
    ? `<b>${esc(code)}</b>: a szabályozási terv övezethatárai (piros pontozott vonal) és az utcák által közrezárt terület felirata – lila folytonos vonallal jelölve a térképen.`
    : `<b>${esc(code)}</b> – becslés: itt a terven nincs zárt övezethatár, ezért a legközelebbi olyan felirat, amelyhez övezethatár és utca keresztezése nélkül el lehet jutni (lila szaggatott vonallal jelölve). Ellenőrizd a „Szabályozási terv” réteggel.`);
  if (z?.street) lines.push('A pont közterületen (utcán) van.');
  if (pCodes.length > 1) {
    lines.push(`<span class="warn">⚠ A telek két övezetbe esik: ${pz.map((x) => `${esc(x.code)} (${Math.round(x.share * 100)}%)`).join(', ')}. Telekrészenként más előírások vonatkozhatnak rá.</span>`);
  }
  // Cross-check with the text: provisions that name zones for a street-bounded block.
  const blocks = new Map<string, string[]>();
  for (const o of eff?.overrides ?? []) {
    if (o.condition?.type === 'block' && evaluate(o.condition, r.lngLat, eff!) === 'yes') {
      blocks.set(o.condition.block, [...new Set([...(blocks.get(o.condition.block) ?? []), ...o.zones])]);
    }
  }
  for (const [block, zones] of blocks) {
    lines.push(zones.includes(code)
      ? `✓ A KÉSZ szövege is ezt az övezetet nevezi meg erre a területre (${esc(block)} által határolt terület).`
      : `<span class="muted">A KÉSZ szövege erre a területre (${esc(block)} által határolt terület) külön előírást ad a(z) ${zones.map(esc).join(', ')} övezet(ek)re; a terv szerint itt ${esc(code)} van, így az nem vonatkozik ide – ha mégis az, ellenőrizd.</span>`);
  }
  return { code, html: `<p class="small zone-evidence">${lines.join('<br>')}</p>` };
}

export function renderCard(
  el: HTMLElement,
  r: LookupResult,
  city: Regulation,
  zoneTypes: Record<string, ZoneType> | undefined,
  rules: (code: string) => Rule[],
  extras: CardExtras,
  h: CardHandlers,
): void {
  const [lng, lat] = r.lngLat;
  const where = r.label ? esc(r.label) : `${lat.toFixed(5)}, ${lng.toFixed(5)}`;

  if (!r.district) {
    el.innerHTML = `<p class="where">${where}</p><p class="hint">Ez a pont a feldolgozott településeken (Budapest, Csobánka) kívül esik.</p>`;
    return;
  }

  const status = r.regulation?.status ?? 'none';
  // The Budapest-wide regulation applies only in the capital's districts (ids 1–23).
  const inBudapest = r.district.id <= 23;
  const regs: Regulation[] = [...(inBudapest ? [city] : []), ...(r.regulation ? [r.regulation] : []), ...(extras.tkr ? [extras.tkr.reg] : []),
    ...(extras.teka ? [extras.teka.reg] : [])];
  const annexes = [...(r.regulation?.annexes ?? []), ...(extras.tkr?.reg.annexes ?? [])]
    .map((a) => `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">↗ ${esc(a.title)}</a></li>`).join('');

  const codes = zoneTypes ? Object.keys(zoneTypes).sort((a, b) => a.localeCompare(b, 'hu')) : [];
  const ev = zoneEvidence(r, extras.effective);
  const guess = ev.code ?? r.guesses[0]?.code;
  const zonePicker = zoneTypes
    ? `<div class="picker">
        <label for="zone-select">Övezet</label>
        <select id="zone-select">
          <option value="">– válassz a szabályozási terv alapján –</option>
          ${codes.map((c) => `<option ${c === guess ? 'selected' : ''}>${esc(c)}</option>`).join('')}
        </select>
        ${ev.html}
        ${r.guesses.length
          ? `<p class="muted small">${ev.code ? 'További közeli övezetfeliratok' : 'A szabályozási terv legközelebbi övezetfeliratai'}:
              ${r.guesses.map((g) => `<button class="chip" data-code="${esc(g.code)}">${esc(g.code)} · ${Math.round(g.distanceM)} m</button>`).join(' ')}
              ${ev.code ? '' : '<br>Ez becslés a terv feliratai alapján: ellenőrizd a térképen a „Szabályozási terv” réteggel.'}</p>`
          : ev.code ? '' : '<p class="muted small">Nincs övezetfelirat a közelben. Kapcsold be a „Szabályozási terv” réteget, és válaszd ki az övezetet.</p>'}
      </div>
      <div id="zone"></div>`
    : `<p class="hint">Ehhez a ${inBudapest ? 'kerülethez' : 'településhez'} még nincs feldolgozott övezeti adat.</p>`;

  el.innerHTML = `
    <p class="where">${where}</p>
    ${r.parcel ? `<p class="parcel">Telek${r.parcel.hrsz ? `: <b>hrsz ${esc(r.parcel.hrsz)}</b>` : ''} · kb. <b>${r.parcel.areaM2.toLocaleString('hu-HU')} m²</b>
      ${r.parcel.builtM2 !== undefined && r.parcel.areaM2 > 0 && !r.parcel.check.includes('street')
        ? ` · beépítve most kb. <b>${Math.round((100 * r.parcel.builtM2) / r.parcel.areaM2)}%</b> <span class="muted small">(${r.parcel.builtM2.toLocaleString('hu-HU')} m², a földhivatali térkép épületei alapján)</span>`
        : ''}
      <span class="muted small">${r.parcel.source === 'btp'
        ? '(telekhatár: © Budapest Közút Zrt., Budapesti Térinformatikai Portál; narancs színnel jelölve a térképen)'
        : r.parcel.source === 'oeny'
          ? '(telekhatár: földhivatali térkép, © Lechner Tudásközpont, OÉNY, nem közhiteles; narancs színnel jelölve a térképen)'
          : '(a szabályozási tervről kirajzolva, narancs színnel jelölve a térképen – ellenőrizd, hogy ez a telek-e)'}</span>
      ${parcelChecks(r.parcel.check)}</p>`
      : '<p class="muted small">Itt nem találtunk telekhatárt a szabályozási terven (pl. közterület).</p>'}
    ${r.exact ? '' : '<p class="warn small">A házszámot nem találtuk a térképen, ezért a jelölő az utca közepén van. Koppints a telekre a térképen a pontos övezetért.</p>'}
    <p class="district">${esc(r.district.name)} <span class="badge st-${status}">${STATUS_LABEL[status]}</span></p>
    ${zonePicker}
    <div id="tkr"></div>
    <div id="teka"></div>
    <h3>Vonatkozó szabályzatok</h3>
    <ul class="regs">${regs.map((reg, i) => regItem(i, reg)).join('')}${annexes}</ul>`;

  el.querySelectorAll<HTMLElement>('[data-reg]').forEach((b) =>
    b.addEventListener('click', () => h.openRegulation(regs[Number(b.dataset.reg)])),
  );

  const bindCites = (root: HTMLElement, cites: Ref[]) =>
    root.querySelectorAll<HTMLElement>('[data-cite]').forEach((b) =>
      b.addEventListener('click', () => {
        const ref = cites[Number(b.dataset.cite)];
        h.openCitation(ref.cite, ref.set);
      }));

  const tkrEl = el.querySelector<HTMLElement>('#tkr')!;
  const renderTkr = (code: string | undefined, chosen?: string) => {
    if (!extras.tkr) return;
    const estimate = areaFor(extras.tkr.data, code);
    const cites: Ref[] = [];
    tkrEl.innerHTML = tkrBlock(extras.tkr.data, extras.tkr.reg, r.protectedHits, chosen ?? estimate, !chosen && !!estimate, cites);
    bindCites(tkrEl, cites);
    tkrEl.querySelector<HTMLSelectElement>('#tkr-area')!.addEventListener('change', (e) =>
      renderTkr(code, (e.target as HTMLSelectElement).value || undefined));
  };
  if (extras.teka) {
    const tekaEl = el.querySelector<HTMLElement>('#teka')!;
    const cites: Ref[] = [];
    tekaEl.innerHTML = tekaBlock(extras.teka.data, extras.teka.reg, cites, r.regulation);
    bindCites(tekaEl, cites);
  }
  renderTkr(guess);
  if (!zoneTypes) return;

  const select = el.querySelector<HTMLSelectElement>('#zone-select')!;
  const zoneEl = el.querySelector<HTMLElement>('#zone')!;
  const renderZone = () => {
    const code = select.value;
    const z = code ? zoneTypes[code] : undefined;
    renderTkr(code || undefined);
    if (!z) { zoneEl.innerHTML = ''; return; }
    const cites: Ref[] = [];
    zoneEl.innerHTML = zoneBlock(code, z, cites, rules(code), r.lngLat, extras);
    bindCites(zoneEl, cites);
    const input = zoneEl.querySelector<HTMLInputElement>('#plot');
    const out = zoneEl.querySelector<HTMLElement>('#calc-out');
    if (input && out) {
      input.addEventListener('input', () => (out.innerHTML = renderCalc(z, Number(input.value))));
      if (r.parcel) {
        input.value = String(r.parcel.areaM2);
        out.innerHTML = renderCalc(z, r.parcel.areaM2);
      }
    }
  };
  select.addEventListener('change', renderZone);
  el.querySelectorAll<HTMLElement>('[data-code]').forEach((b) =>
    b.addEventListener('click', () => { select.value = b.dataset.code!; renderZone(); }),
  );
  renderZone();
}
