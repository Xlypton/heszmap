import type { Citation, LookupResult, Param, Regulation, ZoneType } from './types';

const STATUS_LABEL: Record<string, string> = {
  none: 'nincs adat',
  linked: 'szabályzat linkelve',
  demo: 'DEMO adat – nem valós',
  digitized: 'digitalizált',
};

export interface CardHandlers {
  openCitation(cite: Citation): void;
  openRegulation(id: string): void;
}

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function fmt(v: number | string | null, unit: string): string {
  if (v === null) return '–';
  return typeof v === 'number' ? `${v.toLocaleString('hu-HU')}${unit}` : esc(v);
}

// Citations are kept in a per-render array and referenced by index from the markup.
function cell(label: string, p: Param<number | string>, unit: string, cites: Citation[]): string {
  const value = `<dd>${fmt(p.value, unit)}</dd>`;
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
  return `${head}
    <dl class="params">
      ${cell('Beépítési mód', z.buildingMode, '', cites)}
      ${cell('Max. beépítettség', z.maxCoveragePct, '%', cites)}
      ${cell('Max. szintterületi mutató', z.maxFar, '', cites)}
      ${cell('Max. épületmagasság', z.maxHeightM, ' m', cites)}
      ${cell('Min. zöldfelület', z.minGreenPct, '%', cites)}
      ${cell('Min. telekméret', z.minPlotM2, ' m²', cites)}
    </dl>
    <p class="muted small">Kattints egy értékre a forrás megnyitásához.</p>
    <div class="calc">
      <label>Telekterület (m²) <input id="plot" type="number" min="0" step="1" placeholder="pl. 800" /></label>
      <div id="calc-out"></div>
    </div>`;
}

function renderCalc(z: ZoneType, area: number): string {
  if (!area) return '';
  const cov = z.maxCoveragePct.value, far = z.maxFar.value, green = z.minGreenPct.value, minPlot = z.minPlotM2.value;
  const rows: string[] = [];
  if (cov !== null) rows.push(`Max. beépíthető: <b>${Math.floor((area * cov) / 100)} m²</b>`);
  if (far !== null) rows.push(`Max. bruttó szintterület: <b>${Math.floor(area * far)} m²</b>`);
  if (green !== null) rows.push(`Min. zöldfelület: <b>${Math.ceil((area * green) / 100)} m²</b>`);
  if (minPlot !== null && area < minPlot) rows.push(`<span class="warn">A telek kisebb a minimális telekméretnél (${minPlot} m²).</span>`);
  return rows.map((r) => `<div>${r}</div>`).join('');
}

function regItem(id: string, r: Regulation): string {
  const decree = r.decree ? ` <span class="muted">(${esc(r.decree)})</span>` : '';
  const icon = r.pdf ? '📄' : '↗';
  return `<li><button class="link" data-reg="${esc(id)}">${icon} ${esc(r.title)}</button>${decree}</li>`;
}

export function renderCard(el: HTMLElement, r: LookupResult, city: Regulation, h: CardHandlers): void {
  const [lng, lat] = r.lngLat;
  const where = r.label ? esc(r.label) : `${lat.toFixed(5)}, ${lng.toFixed(5)}`;

  if (!r.district) {
    el.innerHTML = `<p class="where">${where}</p><p class="hint">Ez a pont Budapesten kívül esik.</p>`;
    return;
  }

  const cites: Citation[] = [];
  const status = r.regulation?.status ?? (r.districtRegulations.length ? 'linked' : 'none');
  const districtRegs = r.districtRegulations.length
    ? r.districtRegulations.map(({ id, reg }) => regItem(id, reg)).join('')
    : '';

  el.innerHTML = `
    <p class="where">${where}</p>
    <p class="district">${esc(r.district.name)} <span class="badge st-${status}">${STATUS_LABEL[status]}</span></p>
    ${r.zone && r.zoneCode ? zoneBlock(r.zoneCode, r.zone, cites) : '<p class="hint">Erre a pontra még nincs digitalizált övezet.</p>'}
    <h3>Vonatkozó szabályzatok</h3>
    <ul class="regs">${regItem('city', city)}${districtRegs}</ul>
    ${r.districtRegulations.length ? '' : '<p class="muted small">Ehhez a kerülethez még nincs kerületi szabályzat feltöltve.</p>'}`;

  el.querySelectorAll<HTMLElement>('[data-cite]').forEach((b) =>
    b.addEventListener('click', () => h.openCitation(cites[Number(b.dataset.cite)])),
  );
  el.querySelectorAll<HTMLElement>('[data-reg]').forEach((b) =>
    b.addEventListener('click', () => h.openRegulation(b.dataset.reg!)),
  );

  const zone = r.zone;
  const input = el.querySelector<HTMLInputElement>('#plot');
  const out = el.querySelector<HTMLElement>('#calc-out');
  if (zone && input && out) {
    input.addEventListener('input', () => (out.innerHTML = renderCalc(zone, Number(input.value))));
  }
}
