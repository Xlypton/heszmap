import { conditionText, heightMeaning, heightValue, overridesFor, STATUS_TEXT, type Applied, type Effective, type Override, type StreetContext } from './effective';
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
  openCitation(cite: Citation): void;
  openRegulation(reg: Regulation): void;
}

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function show(p: Param, unit: string): string {
  // Keep the regulation's own wording ("kialakult", footnote stars); add the unit only to plain numbers.
  return p.num !== null && /^[\d\s,]+\**$/.test(p.text) ? `${esc(p.text)}${unit}` : esc(p.text);
}

function cite(c: Citation, cites: Citation[]): number {
  cites.push(c);
  return cites.length - 1;
}

const PARAM_LABEL: Record<string, string> = {
  setbacks: 'Elő-, oldal-, hátsókert', units: 'Rendeltetési egységek száma', buildings: 'Épületek száma, mérete',
};

function citeLink(c: Citation, cites: Citation[], label = c.para): string {
  return `<button class="link" data-cite="${cite(c, cites)}" title="${esc(c.quote)}">${esc(label)} ↗</button>`;
}

/** A conditional value that may or may not apply at this plot. */
function variant(text: string, a: Applied<Override>, cites: Citation[]): string {
  const cond = conditionText(a.override.condition);
  return `<li class="variant st-${a.status}">${cond ? `<span class="cond">${esc(cond)}:</span> ` : ''}<b>${esc(text)}</b>
    ${a.override.note ? `<span class="muted">(${esc(a.override.note)})</span>` : ''} ${citeLink(a.override.cite, cites)}
    ${a.override.condition ? `<span class="status">${STATUS_TEXT[a.status]}</span>` : ''}</li>`;
}

/** Effective value: what applies here (paragraph overrides first), the table value as background. */
function effCell(label: string, main: string, source: string, variants: string[], cites: Citation[], overridden = false): string {
  return `<div class="param${overridden ? ' overridden' : ''}"><dt>${label}</dt><dd>${main}</dd>
    <span class="src">${source}</span>${variants.length ? `<ul class="variants">${variants.join('')}</ul>` : ''}</div>`;
}

function tableCell(label: string, p: Param, unit: string, key: string, code: string, eff: Effective | undefined,
  at: [number, number], near: StreetContext[] | undefined, cites: Citation[]): string {
  const applied = overridesFor(eff, code, key, at, near);
  const here = applied.filter((a) => a.status === 'yes' && a.override.value);
  const other = applied.filter((a) => a.status !== 'yes' || !a.override.value);
  const tableSrc = p.cite ? `táblázat: ${show(p, unit)} · ${citeLink(p.cite, cites)}` : `táblázat: ${show(p, unit)}`;
  if (here.length) {
    const main = here.map((a) => esc(a.override.value!)).join('; ');
    return effCell(label, main, `${here.map((a) => citeLink(a.override.cite, cites)).join(' ')} · ${tableSrc}`,
      other.map((a) => variant(a.override.value ?? '', a, cites)), cites, true);
  }
  return effCell(label, show(p, unit), p.cite ? citeLink(p.cite, cites) : '<span class="nocite">nincs hivatkozás</span>',
    other.map((a) => variant(a.override.value ?? '', a, cites)), cites);
}

/** Heights shown as párkánymagasság / épületmagasság / legmagasabb pont, never as "beépítési magasság". */
function heightCells(code: string, z: ZoneType, modeText: string, eff: Effective | undefined, at: [number, number],
  near: StreetContext[] | undefined, cites: Citation[]): string[] {
  const hm = heightMeaning(eff, modeText);
  const maxT = z.maxHeightM?.text && !['---', '-'].includes(z.maxHeightM.text) ? z.maxHeightM.text : undefined;
  const minT = z.minHeightM?.text && !['---', '-'].includes(z.minHeightM.text) ? z.minHeightM.text : undefined;
  const meaningLinks = hm.entries.map((m) => citeLink(m.cite, cites)).join(' ');
  const tableNote = (t: string | undefined, p?: Param) =>
    t ? `táblázat: beépítési magasság ${esc(t)} m${p?.cite ? ` ${citeLink(p.cite, cites)}` : ''} · értelmezés: ${meaningLinks}${hm.open ? ' (a beépítési módtól függ)' : ''}` : '';

  type Row = { label: string; main?: string; src: string; variants: string[]; overridden: boolean };
  const rows: Record<'cornice' | 'building' | 'peak', Row> = {
    cornice: { label: 'Max. párkánymagasság', main: hm.cornice && maxT ? `${esc(maxT)} m` : undefined, src: tableNote(maxT, z.maxHeightM), variants: [], overridden: false },
    building: { label: 'Max. épületmagasság', main: hm.building && maxT ? `${esc(maxT)} m` : undefined, src: tableNote(maxT, z.maxHeightM), variants: [], overridden: false },
    peak: { label: 'Legmagasabb pont', main: undefined, src: '', variants: [], overridden: false },
  };
  if (hm.open && maxT) {
    rows.cornice.label += ' (zártsorú, oldalhatáron álló, ikres)';
    rows.building.label += ' (szabadonálló)';
  }
  for (const a of overridesFor(eff, code, 'height', at, near)) {
    const o = a.override;
    for (const k of ['cornice', 'building', 'peak'] as const) {
      const spec = o[k];
      if (!spec) continue;
      const value = heightValue(spec, maxT, o.delta);
      if (a.status === 'yes') {
        rows[k].main = esc(value);
        const note = o.note && (k === 'cornice' || !o.cornice) ? ` · ${esc(o.note)}` : '';
        rows[k].src = `${citeLink(o.cite, cites)}${note}${rows[k].src ? ` · ${rows[k].src}` : ''}`;
        rows[k].overridden = true;
      } else {
        rows[k].variants.push(variant(value, a, cites));
      }
    }
  }
  const out = (['cornice', 'building', 'peak'] as const)
    .filter((k) => rows[k].main || rows[k].variants.length)
    .map((k) => effCell(rows[k].label, rows[k].main ?? '–', rows[k].main ? rows[k].src || meaningLinks : 'csak az alábbi esetben', rows[k].variants, cites, rows[k].overridden));

  // Minimum height: the table's minimum follows the same meaning; paragraphs may set a minimum building height.
  const minRows: string[] = [];
  const minOv = overridesFor(eff, code, 'minHeight', at, near);
  const minHere = minOv.find((a) => a.status === 'yes');
  const minLabel = hm.building && !hm.cornice ? 'Min. épületmagasság' : 'Min. párkánymagasság';
  if (minHere) {
    minRows.push(effCell('Min. épületmagasság', esc(heightValue(minHere.override.building!, minT)),
      `${citeLink(minHere.override.cite, cites)} · ${esc(conditionText(minHere.override.condition))}${minT ? ` · ${tableNote(minT, z.minHeightM)}` : ''}.`,
      minOv.filter((a) => a !== minHere).map((a) => variant(heightValue(a.override.building!, minT), a, cites)), cites, true));
  } else if (minT || minOv.length) {
    minRows.push(effCell(minLabel, minT ? `${esc(minT)} m` : '–', tableNote(minT, z.minHeightM),
      minOv.map((a) => variant(heightValue(a.override.building!, minT), a, cites)), cites));
  }
  return [...out, ...minRows];
}

/** Values the table has no column for: setbacks, unit counts, number of buildings. */
function extraRows(code: string, eff: Effective | undefined, at: [number, number], near: StreetContext[] | undefined, cites: Citation[]): string {
  const blocks = Object.entries(PARAM_LABEL).map(([param, label]) => {
    const applied = overridesFor(eff, code, param, at, near);
    if (!applied.length) return '';
    return `<div class="extra"><dt>${label}</dt><ul class="variants">${applied.map((a) => variant(a.override.value ?? '', a, cites)).join('')}</ul></div>`;
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

function textRules(rules: TextRule[], cites: Citation[]): string {
  return `<ul>${rules.map((r) => `
    <li class="rule">
      <button class="rule-id" data-cite="${cite(r.cite, cites)}">${esc(r.id)} ↗</button>
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

export function tkrBlock(tkr: Tkr, reg: Regulation, hits: ProtectedHit[], area: string | undefined, estimated: boolean, cites: Citation[]): string {
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

export function tekaBlock(teka: Teka, reg: Regulation, cites: Citation[]): string {
  const chapters = new Map<string, TextRule[]>();
  for (const r of teka.rules) chapters.set(r.chapter ?? '', [...(chapters.get(r.chapter ?? '') ?? []), r]);
  const basis = teka.basis.map((b) => `<button class="link" data-cite="${cite(b.cite, cites)}">${esc(b.id)}</button>`).join(', ');
  return `<h3>TÉKA – országos előírások</h3>
    <p class="small">${esc(reg.decree ?? '')}${reg.effectiveFrom ? ` · hatályos: ${esc(reg.effectiveFrom)}` : ''}.
    A kerületi szabályzat 2015-ös, ezért a TÉKA 136. § (1) b) szerint az OTÉK 2021. július 15-i állapotú II–III. fejezetével együtt kell alkalmazni.
    A TÉKA 136. § (2) szerint viszont az alábbi rendelkezések minden 2025. június 30. után indult eljárásban kötelezők, és a kerületi szabályzat ezekkel ellentétes előírásai nem alkalmazhatók (${basis}).</p>
    ${[...chapters].map(([ch, rs]) => details(esc(ch), textRules(rs, cites), rs.length)).join('')}`;
}

function rulesBlock(rules: Rule[], cites: Citation[]): string {
  if (!rules.length) return '';
  const groups = GROUPS.map((g) => {
    const items = rules.filter(g.pick);
    if (!items.length) return '';
    const li = items.map((r) => `
      <li class="rule${r.flags.length ? ' flagged' : ''}">
        <button class="rule-id" data-cite="${cite(r.cite, cites)}">${esc(r.id)} ↗</button>
        <p>${esc(r.text.replace(/^\d+(?:\/[A-Z])?\.\s*§\s*/, ''))}</p>
        ${r.note ? `<p class="rule-note">${esc(r.note)}</p>` : ''}
      </li>`).join('');
    return `<details class="rules" ${g.open ? 'open' : ''}><summary>${g.title} <span class="count">${items.length}</span></summary><ul>${li}</ul></details>`;
  }).join('');
  return `<h3>Minden vonatkozó előírás</h3>
    <p class="muted small">A rendelet összes bekezdése, ami erre az övezetre vonatkozik. A ↗ megnyitja a bekezdést a rendeletben.
    A sárga szegélyű bekezdések határértéket, telekméretet vagy rendeltetési egységszámot írnak elő.</p>${groups}`;
}

function zoneBlock(code: string, z: ZoneType, cites: Citation[], rules: Rule[], at: [number, number], extras: CardExtras): string {
  const eff = extras.effective, near = extras.near;
  let head = `<div class="zone-code">${esc(code)}</div><div class="zone-name">${esc(z.name)}</div>`;
  if (z.cite) {
    cites.push(z.cite);
    head = `<button class="zone cited" data-cite="${cites.length - 1}">${head}<span class="para">${esc(z.cite.para)} ↗</span></button>`;
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
      .map(({ key, label, unit }) => tableCell(label, z[key]!, unit, key, code, eff, at, near, cites)),
  ];
  cells.splice(2, 0, ...heightCells(code, z, modeText, eff, at, near, cites));
  const table = z.noTable
    ? '<p class="hint">Ennek az övezetnek nincs sora a határérték-táblázatban: az előírásait lent találod.</p>'
    : `${all}<dl class="params">${cells.join('')}</dl>
    <p class="muted small">Az értékek a rendelet szövegével együtt értelmezve: ha egy bekezdés eltér a táblázattól, az itt alkalmazandó érték látszik,
    alatta a táblázat értéke. A „beépítési magasság” a beépítési módtól függően párkánymagasság vagy épületmagasság (15. §).
    A feltételes értékeknél a térkép alapján jelezzük, érvényes-e ezen a telken. A * lábjegyzetre utal (pl. OTÉK-eltérés).</p>
    ${extraRows(code, eff, at, near, cites)}
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
    el.innerHTML = `<p class="where">${where}</p><p class="hint">Ez a pont Budapesten kívül esik.</p>`;
    return;
  }

  const status = r.regulation?.status ?? 'none';
  const regs: Regulation[] = [city, ...(r.regulation ? [r.regulation] : []), ...(extras.tkr ? [extras.tkr.reg] : []),
    ...(extras.teka ? [extras.teka.reg] : [])];
  const annexes = [...(r.regulation?.annexes ?? []), ...(extras.tkr?.reg.annexes ?? [])]
    .map((a) => `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">↗ ${esc(a.title)}</a></li>`).join('');

  const codes = zoneTypes ? Object.keys(zoneTypes).sort((a, b) => a.localeCompare(b, 'hu')) : [];
  const guess = r.guesses[0]?.code;
  const zonePicker = zoneTypes
    ? `<div class="picker">
        <label for="zone-select">Övezet</label>
        <select id="zone-select">
          <option value="">– válassz a szabályozási terv alapján –</option>
          ${codes.map((c) => `<option ${c === guess ? 'selected' : ''}>${esc(c)}</option>`).join('')}
        </select>
        ${r.guesses.length
          ? `<p class="muted small">A szabályozási terv legközelebbi övezetfeliratai:
              ${r.guesses.map((g) => `<button class="chip" data-code="${esc(g.code)}">${esc(g.code)} · ${Math.round(g.distanceM)} m</button>`).join(' ')}
              <br>Ez becslés a terv feliratai alapján: ellenőrizd a térképen a „Szabályozási terv” réteggel.</p>`
          : '<p class="muted small">Nincs övezetfelirat a közelben. Kapcsold be a „Szabályozási terv” réteget, és válaszd ki az övezetet.</p>'}
      </div>
      <div id="zone"></div>`
    : '<p class="hint">Ehhez a kerülethez még nincs feldolgozott övezeti adat.</p>';

  el.innerHTML = `
    <p class="where">${where}</p>
    ${r.parcel ? `<p class="parcel">Telek${r.parcel.hrsz ? `: <b>hrsz ${esc(r.parcel.hrsz)}</b>` : ''} · kb. <b>${r.parcel.areaM2.toLocaleString('hu-HU')} m²</b>
      <span class="muted small">(a szabályozási tervről kirajzolva, narancs színnel jelölve a térképen – ellenőrizd, hogy ez a telek-e)</span></p>`
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

  const bindCites = (root: HTMLElement, cites: Citation[]) =>
    root.querySelectorAll<HTMLElement>('[data-cite]').forEach((b) =>
      b.addEventListener('click', () => h.openCitation(cites[Number(b.dataset.cite)])));

  const tkrEl = el.querySelector<HTMLElement>('#tkr')!;
  const renderTkr = (code: string | undefined, chosen?: string) => {
    if (!extras.tkr) return;
    const estimate = areaFor(extras.tkr.data, code);
    const cites: Citation[] = [];
    tkrEl.innerHTML = tkrBlock(extras.tkr.data, extras.tkr.reg, r.protectedHits, chosen ?? estimate, !chosen && !!estimate, cites);
    bindCites(tkrEl, cites);
    tkrEl.querySelector<HTMLSelectElement>('#tkr-area')!.addEventListener('change', (e) =>
      renderTkr(code, (e.target as HTMLSelectElement).value || undefined));
  };
  if (extras.teka) {
    const tekaEl = el.querySelector<HTMLElement>('#teka')!;
    const cites: Citation[] = [];
    tekaEl.innerHTML = tekaBlock(extras.teka.data, extras.teka.reg, cites);
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
    const cites: Citation[] = [];
    zoneEl.innerHTML = zoneBlock(code, z, cites, rules(code), r.lngLat, extras);
    zoneEl.querySelectorAll<HTMLElement>('[data-cite]').forEach((b) =>
      b.addEventListener('click', () => h.openCitation(cites[Number(b.dataset.cite)])),
    );
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
