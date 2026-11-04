import './issues.css';
import { esc, KIND_LABEL, loadIssues, reportUrl, SEVERITY_LABEL, STATUS_LABEL, type Issue, type IssueFile, type Severity } from './issues-data';

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const PAGE = 80;
const SEV_ORDER: Record<Severity, number> = { 'wrong-answer': 0, missing: 1, uncertain: 2, info: 3 };

let file: IssueFile;
let shown = PAGE;
let matches: Issue[] = [];

function params(): URLSearchParams { return new URLSearchParams(location.search); }

function setFilters(): void {
  const q = params();
  $<HTMLSelectElement>('f-status').value = q.get('status') ?? 'open';
  $<HTMLSelectElement>('f-area').value = q.get('area') ?? '';
  $<HTMLSelectElement>('f-kind').value = q.get('kind') ?? '';
  $<HTMLInputElement>('f-wrong').checked = q.get('wrong') === '1';
  $<HTMLInputElement>('f-q').value = q.get('q') ?? '';
}

function saveFilters(): void {
  const q = new URLSearchParams();
  const v = (id: string) => $<HTMLInputElement | HTMLSelectElement>(id).value;
  if (v('f-status') !== 'open') q.set('status', v('f-status'));
  if (v('f-area')) q.set('area', v('f-area'));
  if (v('f-kind')) q.set('kind', v('f-kind'));
  if ($<HTMLInputElement>('f-wrong').checked) q.set('wrong', '1');
  if (v('f-q').trim()) q.set('q', v('f-q').trim());
  const id = params().get('id');
  if (id) q.set('id', id);
  history.replaceState(null, '', q.size ? `?${q}` : location.pathname);
}

function mapLink(i: Issue): string {
  const at = i.at;
  return at ? `./?goto=${at[0]},${at[1]}` : '';
}

function row(i: Issue, open: boolean): string {
  const a = file.areas[i.area];
  const src = i.source?.reg ? `<a href="./?reg=${encodeURIComponent(i.source.reg)}">A rendelet megnyitása${i.source.para ? ` (${esc(i.source.para)})` : ''}${i.source.page ? `, ${i.source.page}. oldal` : ''}</a>` : '';
  const places = i.all_at && i.all_at.length > 1
    ? `<p class="small muted">${i.places} hely, a legsúlyosabb: ${i.at![1].toFixed(5)}, ${i.at![0].toFixed(5)}</p>` : '';
  return `<details class="issue sev-${i.severity}" data-id="${esc(i.id)}"${open ? ' open' : ''}>
    <summary>
      <span class="area">${esc(i.area.toUpperCase())}</span>
      <span class="what">${esc(i.note)}<small>${esc(KIND_LABEL[i.kind] ?? i.kind)} · ${esc(SEVERITY_LABEL[i.severity])}${i.scope === 'area' ? ' · egész terület' : ''}</small></span>
      <span class="pill st-${i.status}">${STATUS_LABEL[i.status]}</span>
    </summary>
    <div class="detail">
      <p class="small muted">${esc(a?.name ?? i.area)} · felismerte: ${esc(i.found_by ?? '?')} · először látva: ${esc(i.first_seen)}${i.fixed_at ? ` · javítva: ${esc(i.fixed_at)}` : ''}</p>
      ${i.why ? `<p><b>${i.status === 'fixed' ? 'Javítás' : 'Miért nem kezeljük'}:</b> ${esc(i.why)}${i.fix ? ` <code>${esc(i.fix)}</code>` : ''}</p>` : ''}
      ${places}
      ${i.codes ? `<p class="small codes">${i.codes.map((c) => `<code>${esc(c)}</code>`).join(' ')}</p>` : ''}
      <p class="actions">
        ${src ? `<span>${src}</span>` : ''}
        ${mapLink(i) ? `<a href="${mapLink(i)}">Megnézem a térképen</a>` : ''}
        <a href="${reportUrl(i)}" target="_blank" rel="noopener">Hibát látok / pontosítanék</a>
        <a href="?id=${encodeURIComponent(i.id)}" class="perma">Hivatkozás erre</a>
      </p>
    </div>
  </details>`;
}

function apply(): void {
  const st = $<HTMLSelectElement>('f-status').value;
  const area = $<HTMLSelectElement>('f-area').value;
  const kind = $<HTMLSelectElement>('f-kind').value;
  const wrong = $<HTMLInputElement>('f-wrong').checked;
  const q = $<HTMLInputElement>('f-q').value.trim().toLowerCase();
  const id = params().get('id');
  matches = file.issues.filter((i) =>
    (id ? i.id === id : (!st || i.status === st) && (!area || i.area === area) && (!kind || i.kind === kind)
      && (!wrong || i.severity === 'wrong-answer')
      && (!q || `${i.note} ${i.subject_zone ?? ''} ${i.subject_plot ?? ''} ${i.area} ${i.why ?? ''}`.toLowerCase().includes(q))));
  matches.sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity] || a.area.localeCompare(b.area) || a.kind.localeCompare(b.kind));
  const single = matches.length === 1 && !!id;
  $('count').textContent = id ? 'Egy probléma.' : `${matches.length.toLocaleString('hu-HU')} találat`;
  $('list').innerHTML = matches.slice(0, shown).map((i) => row(i, single)).join('') || '<p class="muted">Nincs találat.</p>';
  $<HTMLButtonElement>('more').hidden = matches.length <= shown;
  saveFilters();
}

function grid(): void {
  const kinds = [...new Set(file.issues.map((i) => i.kind))].sort();
  const open = file.issues.filter((i) => i.status === 'open');
  const head = `<tr><th>Terület</th>${kinds.map((k) => `<th title="${esc(KIND_LABEL[k] ?? k)}">${esc(k)}</th>`).join('')}</tr>`;
  const body = Object.keys(file.areas).map((a) => {
    const cells = kinds.map((k) => {
      const l = open.filter((i) => i.area === a && i.kind === k);
      if (!l.length) return '<td></td>';
      const bad = l.some((i) => i.severity === 'wrong-answer');
      return `<td class="${bad ? 'bad' : 'soft'}"><a href="?area=${encodeURIComponent(a)}&kind=${encodeURIComponent(k)}">${l.length}</a></td>`;
    }).join('');
    return `<tr><th><a href="?area=${encodeURIComponent(a)}">${esc(a)}</a></th>${cells}</tr>`;
  }).join('');
  $('grid').innerHTML = head + body;
}

async function init(): Promise<void> {
  const f = await loadIssues();
  if (!f) { $('list').innerHTML = '<p class="warn">Az adatok betöltése nem sikerült.</p>'; return; }
  file = f;
  const c = f.counts;
  const wrong = f.issues.filter((i) => i.status === 'open' && i.severity === 'wrong-answer').length;
  $('kpis').innerHTML = [[c.open, 'nyitott'], [wrong, 'téves adatot mutathat'], [c['worked-around'], 'megkerülve'], [c.fixed, 'javítva']]
    .map(([n, l]) => `<div class="kpi"><b>${(n as number).toLocaleString('hu-HU')}</b><span>${l}</span></div>`).join('')
    + `<div class="kpi"><span>frissítve: ${esc(f.generated)}</span></div>`;
  $('f-area').innerHTML = '<option value="">Mind</option>' + Object.entries(f.areas).map(([k, a]) => `<option value="${esc(k)}">${esc(k)} – ${esc(a.name)}</option>`).join('');
  const kinds = [...new Set(f.issues.map((i) => i.kind))].sort();
  $('f-kind').innerHTML = '<option value="">Mind</option>' + kinds.map((k) => `<option value="${esc(k)}">${esc(KIND_LABEL[k] ?? k)}</option>`).join('');
  $<HTMLAnchorElement>('report').href = reportUrl(undefined);
  setFilters();
  grid();
  for (const id of ['f-status', 'f-area', 'f-kind', 'f-wrong']) $(id).addEventListener('change', () => { shown = PAGE; history.replaceState(null, '', location.pathname); apply(); });
  $('f-q').addEventListener('input', () => { shown = PAGE; apply(); });
  $('more').addEventListener('click', () => { shown += PAGE; apply(); });
  apply();
}

void init();
