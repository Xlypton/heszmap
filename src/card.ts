import type { Citation, LookupResult, Param, ParamKey, Regulation, ZoneType } from './types';

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

function cell(label: string, p: Param, unit: string, cites: Citation[]): string {
  const value = `<dd>${show(p, unit)}</dd>`;
  if (!p.cite) return `<div class="param"><dt>${label}</dt>${value}<span class="nocite">nincs hivatkozás</span></div>`;
  cites.push(p.cite);
  return `<button class="param cited" data-cite="${cites.length - 1}" title="${esc(p.cite.quote)}">
      <dt>${label}</dt>${value}<span class="para">${esc(p.cite.para)} ↗</span></button>`;
}

function zoneBlock(code: string, z: ZoneType, cites: Citation[]): string {
  let head = `<div class="zone-code">${esc(code)}</div><div class="zone-name">${esc(z.name)}</div>`;
  if (z.cite) {
    cites.push(z.cite);
    head = `<button class="zone cited" data-cite="${cites.length - 1}">${head}<span class="para">${esc(z.cite.para)} ↗</span></button>`;
  } else {
    head = `<div class="zone">${head}</div>`;
  }
  const cells = PARAMS.filter(({ key }) => z[key] && z[key]!.text && z[key]!.text !== '---' && z[key]!.text !== '-')
    .map(({ key, label, unit }) => cell(label, z[key]!, unit, cites));
  return `${head}
    <dl class="params">${cells.join('')}</dl>
    <p class="muted small">Kattints egy értékre: megnyílik a rendelet, kiemelve a forrás sorát. A * jelölés lábjegyzetre utal (pl. OTÉK-eltérés).</p>
    <div class="calc">
      <label for="plot">Telekterület (m²)</label>
      <input id="plot" type="number" min="0" step="1" placeholder="pl. 720" />
      <div id="calc-out"></div>
    </div>`;
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
  h: CardHandlers,
): void {
  const [lng, lat] = r.lngLat;
  const where = r.label ? esc(r.label) : `${lat.toFixed(5)}, ${lng.toFixed(5)}`;

  if (!r.district) {
    el.innerHTML = `<p class="where">${where}</p><p class="hint">Ez a pont Budapesten kívül esik.</p>`;
    return;
  }

  const status = r.regulation?.status ?? 'none';
  const regs: Regulation[] = [city, ...(r.regulation ? [r.regulation] : [])];
  const annexes = (r.regulation?.annexes ?? [])
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
    <p class="district">${esc(r.district.name)} <span class="badge st-${status}">${STATUS_LABEL[status]}</span></p>
    ${zonePicker}
    <h3>Vonatkozó szabályzatok</h3>
    <ul class="regs">${regs.map((reg, i) => regItem(i, reg)).join('')}${annexes}</ul>`;

  el.querySelectorAll<HTMLElement>('[data-reg]').forEach((b) =>
    b.addEventListener('click', () => h.openRegulation(regs[Number(b.dataset.reg)])),
  );
  if (!zoneTypes) return;

  const select = el.querySelector<HTMLSelectElement>('#zone-select')!;
  const zoneEl = el.querySelector<HTMLElement>('#zone')!;
  const renderZone = () => {
    const code = select.value;
    const z = code ? zoneTypes[code] : undefined;
    if (!z) { zoneEl.innerHTML = ''; return; }
    const cites: Citation[] = [];
    zoneEl.innerHTML = zoneBlock(code, z, cites);
    zoneEl.querySelectorAll<HTMLElement>('[data-cite]').forEach((b) =>
      b.addEventListener('click', () => h.openCitation(cites[Number(b.dataset.cite)])),
    );
    const input = zoneEl.querySelector<HTMLInputElement>('#plot')!;
    const out = zoneEl.querySelector<HTMLElement>('#calc-out')!;
    input.addEventListener('input', () => (out.innerHTML = renderCalc(z, Number(input.value))));
  };
  select.addEventListener('change', renderZone);
  el.querySelectorAll<HTMLElement>('[data-code]').forEach((b) =>
    b.addEventListener('click', () => { select.value = b.dataset.code!; renderZone(); }),
  );
  renderZone();
}
