import type { Citation, LookupResult, Param, ParamKey, ProtectedHit, Regulation, Rule, Teka, TextRule, Tkr, TkrRule, ZoneType } from './types';

const STATUS_LABEL: Record<string, string> = {
  none: 'nincs adat',
  linked: 'szabályzat feldolgozva',
  digitized: 'övezetek ellenőrizve',
};

const PARAMS: { key: ParamKey; label: string; unit: string }[] = [
  { key: 'buildingMode', label: 'Beépítési mód', unit: '' },
  { key: 'maxCoveragePct', label: 'Max. beépítettség', unit: '%' },
  { key: 'maxHeightM', label: 'Max. beépítési magasság', unit: ' m' },
  { key: 'minHeightM', label: 'Min. beépítési magasság', unit: ' m' },
  { key: 'minGreenPct', label: 'Min. zöldfelület', unit: '%' },
  { key: 'minPlotM2', label: 'Min. telekterület', unit: ' m²' },
  { key: 'maxFar', label: 'Max. szintterületi mutató', unit: '' },
  { key: 'maxFarParking', label: 'Szintterületi mutató – parkolás', unit: '' },
  { key: 'maxUndergroundPct', label: 'Max. terepszint alatti beépítés', unit: '%' },
];

export interface CardExtras {
  tkr?: { regId: string; reg: Regulation; data: Tkr };
  teka?: { reg: Regulation; data: Teka };
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

function cell(label: string, p: Param, unit: string, cites: Citation[], modifiers: Rule[]): string {
  const value = `<dd>${show(p, unit)}</dd>`;
  const mods = modifiers.length
    ? `<span class="mod">⚠ eltérő előírás: ${modifiers.map((r) => `<button class="link" data-cite="${cite(r.cite, cites)}">${esc(r.id)}</button>`).join(', ')}</span>`
    : '';
  if (!p.cite) return `<div class="param"><dt>${label}</dt>${value}<span class="nocite">nincs hivatkozás</span>${mods}</div>`;
  return `<div class="param"><button class="cited" data-cite="${cite(p.cite, cites)}" title="${esc(p.cite.quote)}">
      <dt>${label}</dt>${value}<span class="para">${esc(p.cite.para)} ↗</span></button>${mods}</div>`;
}

const FLAG_FOR: Partial<Record<ParamKey, string[]>> = {
  maxHeightM: ['maxHeightM'], minHeightM: ['minHeightM', 'maxHeightM'], maxCoveragePct: ['maxCoveragePct'],
  minGreenPct: ['minGreenPct'], maxFar: ['maxFar'], maxFarParking: ['maxFar'], minPlotM2: ['minPlotM2'],
};

function modifiersOf(key: ParamKey, rules: Rule[]): Rule[] {
  const flags = FLAG_FOR[key] ?? [];
  return rules.filter((r) => r.kind !== 'general' && r.kind !== 'public' &&
    (r.flags.includes('kialakult') || r.flags.some((f) => flags.includes(f))));
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

function zoneBlock(code: string, z: ZoneType, cites: Citation[], rules: Rule[]): string {
  let head = `<div class="zone-code">${esc(code)}</div><div class="zone-name">${esc(z.name)}</div>`;
  if (z.cite) {
    cites.push(z.cite);
    head = `<button class="zone cited" data-cite="${cites.length - 1}">${head}<span class="para">${esc(z.cite.para)} ↗</span></button>`;
  } else {
    head = `<div class="zone">${head}</div>`;
  }
  const cells = PARAMS.filter(({ key }) => z[key] && z[key]!.text && z[key]!.text !== '---' && z[key]!.text !== '-')
    .map(({ key, label, unit }) => cell(label, z[key]!, unit, cites, modifiersOf(key, rules)));
  const table = z.noTable
    ? '<p class="hint">Ennek az övezetnek nincs sora a határérték-táblázatban: az előírásait lent találod.</p>'
    : `<dl class="params">${cells.join('')}</dl>
    <p class="muted small">Kattints egy értékre: megnyílik a rendelet, kiemelve a forrás sorát. A * lábjegyzetre utal (pl. OTÉK-eltérés).
    A ⚠ jelölt értéket egy bekezdés felülírja vagy pontosítja.</p>
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
    zoneEl.innerHTML = zoneBlock(code, z, cites, rules(code));
    zoneEl.querySelectorAll<HTMLElement>('[data-cite]').forEach((b) =>
      b.addEventListener('click', () => h.openCitation(cites[Number(b.dataset.cite)])),
    );
    const input = zoneEl.querySelector<HTMLInputElement>('#plot');
    const out = zoneEl.querySelector<HTMLElement>('#calc-out');
    if (input && out) input.addEventListener('input', () => (out.innerHTML = renderCalc(z, Number(input.value))));
  };
  select.addEventListener('change', renderZone);
  el.querySelectorAll<HTMLElement>('[data-code]').forEach((b) =>
    b.addEventListener('click', () => { select.value = b.dataset.code!; renderZone(); }),
  );
  renderZone();
}
