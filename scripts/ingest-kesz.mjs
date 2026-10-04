// Ingest a building regulation from the Nemzeti Jogszabálytár (njt.jog.gov.hu):
//   1. fetch the consolidated (egységes szerkezetű) text,
//   2. render it unchanged to a PDF with a source/version header (NJT's own "PDF" button is a browser print too),
//   3. parse the zone tables of the "Építési övezetek és övezetek szabályozási határértékei" annex,
//   4. verify that every citation quote is found in the PDF, and record its page.
//
// Usage: node scripts/ingest-kesz.mjs xx
// Needs Playwright + Chromium. Behind an HTTP proxy run with NODE_USE_ENV_PROXY=1.
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { getDocument } from 'pdfjs-dist/legacy/build/pdf.mjs';

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(`${execSync('npm root -g').toString().trim()}/playwright`); }

const SOURCES = {
  teka: {
    reg: 'teka',
    district: null, // national: applies everywhere, alongside the local regulations
    njtId: '2024-280-20-22',
    title: 'TÉKA – Településrendezési és építési követelmények alapszabályzata',
    decree: '280/2024. (IX. 30.) Korm. rendelet',
    tables: false,
    annexes: [],
  },
  'xx-tkr': {
    reg: 'xx-tkr',
    district: 20,
    njtId: '2019-17-SP-5Y269',
    title: 'XX. kerület Pesterzsébet – Településképi rendelet',
    decree: '17/2019. (V.21.) önkormányzati rendelet',
    tables: false,
    annexes: [
      { title: 'TKR 1. melléklet – Településképi szempontból meghatározó területek, védett értékek (térkép)', path: '/document/d0/d0bcLL_EJR_77050956-1_mell_klet.pdf' },
      { title: 'Településképi Arculati Kézikönyv (TAK, 2017, ajánlások)', url: 'https://pesterzsebet.hu/wp-content/uploads/hivatalban-intezheto-ugyek-osztalyok-szerint/foepiteszi-iroda/1500965552_Telep%C3%BCl%C3%A9sk%C3%A9pi_Arculati_K%C3%A9zik%C3%B6nyv_elfogadott.pdf' },
    ],
  },
  xx: {
    reg: 'xx-kesz',
    district: 20,
    tables: true,
    njtId: '2015-26-SP-5Y269',
    title: 'XX. kerület Pesterzsébet – Kerületi Építési Szabályzat',
    decree: '26/2015. (X. 21.) önkormányzati rendelet',
    // Zones that appear on the plan but have no row in the limits table (rules only).
    extraZones: {
      'KÖu-1': 'Gyorsforgalmi utak területe (KÖu‐1)',
      'KÖu-2': 'I. rendű főutak területe (KÖu‐2)',
      'KÖu-4': 'Településszerkezeti jelentőségű gyűjtőutak területe (KÖu‐4)',
      'Kt-Kk': 'Kerületi jelentőségű közutak területe (Kt‐Kk)',
      'Kt-Kgy': 'Önálló gyalogos utak területe (Kt‐Kgy)',
      'Ek-3': 'Védelmi elsődleges rendeltetésű közjóléti erdőterület (Ek‐3)',
      'Ev-Ve': 'Védelmi erdőterület (Ev-Ve)',
      'Vf': 'Folyóvizek medre és partja (Vf)',
      'Vá': 'Állóvizek medre és partja (Vá)',
    },
    annexes: [
      { title: '2.a melléklet – Szabályozási terv, szabályozási elemek', path: '/document/eb/ebaaLL_EJR_115271848-2a_mell_klet.pdf' },
      { title: '2.b melléklet – Védelem, korlátozás, kötelezettség', path: '/document/0b/0bdbLL_EJR_105863361-2_b_mell_klet.pdf' },
    ],
  },
};

const NJT = 'https://njt.jog.gov.hu';
const squash = (s) => s.normalize('NFC').replace(/\s+/g, '');

const key = process.argv[2];
const src = SOURCES[key];
if (!src) throw new Error(`Unknown source "${key}". Known: ${Object.keys(SOURCES).join(', ')}`);

const url = `${NJT}/jogszabaly/${src.njtId}`;
const res = await fetch(url, { headers: { 'user-agent': 'heszmap/0.1 (+https://github.com/xlypton/heszmap)' } });
if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
const html = await res.text();
const retrievedAt = new Date().toISOString().slice(0, 10);

const browser = await playwright.chromium.launch();
const page = await browser.newPage();
await page.setContent(html, { waitUntil: 'domcontentloaded' });

// Everything below runs on the official DOM.
const extracted = await page.evaluate(() => {
  const root = document.getElementById('jogszab');
  if (!root) throw new Error('#jogszab (law body) not found');
  root.querySelectorAll('.changeVersionParent, script, button').forEach((el) => el.remove());
  const effectiveFrom = root.querySelector('.hataly')?.textContent?.trim() ?? null;

  const text = (el, withSup) => {
    const c = el.cloneNode(true);
    if (!withSup) c.querySelectorAll('sup').forEach((s) => s.remove());
    // Header words are often separated only by <br>.
    c.querySelectorAll('br').forEach((br) => br.replaceWith(' '));
    return c.textContent.replace(/\s+/g, ' ').trim();
  };

  // Expand a table into a grid so colspan/rowspan headers line up with data cells.
  const grid = (table) => {
    const out = [];
    [...table.rows].forEach((tr, r) => {
      out[r] ??= [];
      let c = 0;
      for (const cell of tr.cells) {
        while (out[r][c]) c++;
        for (let dr = 0; dr < (cell.rowSpan || 1); dr++) {
          for (let dc = 0; dc < (cell.colSpan || 1); dc++) {
            (out[r + dr] ??= [])[c + dc] = { cell, origin: dr === 0 && dc === 0 };
          }
        }
        c += cell.colSpan || 1;
      }
    });
    return out;
  };

  const field = (label) => {
    // Undo soft hyphenation such as "Legki-sebb".
    const l = label.toLowerCase().replace(/(\p{L})-(\p{Ll})/gu, '$1$2');
    if (l.includes('jele')) return 'code';
    if (l.includes('telek')) return 'minPlotM2';
    if (l.includes('beépítési mód')) return 'buildingMode';
    if (l.includes('terepszint alatti')) return 'maxUndergroundPct';
    if (l.includes('beépítettség') || l.includes('beépítés megengedett')) return 'maxCoveragePct';
    if (l.includes('magasság')) return l.includes('legkisebb') ? 'minHeightM' : 'maxHeightM';
    if (l.includes('zöldfelület')) return 'minGreenPct';
    if (l.includes('szintterület')) return l.includes('parkol') && !l.includes('általános/parkolás') ? 'maxFarParking' : 'maxFar';
    return null;
  };

  const zones = [];
  let category = null;
  for (const table of root.querySelectorAll('table')) {
    const g = grid(table);
    const head = g[0]?.map((x) => text(x.cell, false)) ?? [];
    if (!head.some((h) => /jele$/i.test(h))) continue;

    // The category heading ("6. Kertvárosias, intenzív beépítésű lakóterület (Lke‐1)") is the closest
    // preceding text block.
    let prev = table.closest('.TABLE') ?? table;
    while (prev && !/\(\S+\)\s*$/.test(text(prev, false))) prev = prev.previousElementSibling;
    if (prev) {
      // "6. Kertvárosias … (Lke‐1) Kertvárosias … (Lke‐1)": drop the numbering and the repeated title.
      const title = text(prev, false).replace(/^\d+\.\s*/, '').replace(/^(.+?\))\s*\1$/, '$1');
      category = { title, quote: text(prev, true) };
    }

    // Sub-header rows ("Legkisebb | Legnagyobb", "Általános | Parkolásra") sit under the rowspanned
    // "jele" cell, so the first data row is the first one that starts a new cell in column 0.
    const firstData = g.findIndex((row, r) => r > 0 && row[0]?.origin);
    if (firstData < 0) continue;
    const labels = g[0].map((_, c) => g.slice(0, firstData).map((row) => text(row[c].cell, false)).join(' '));
    // Keep the first column per field: trailing empty sub-columns would otherwise overwrite values.
    const fields = labels.map(field).map((f, c, all) => (all.indexOf(f) === c ? f : null));

    for (const row of g.slice(firstData)) {
      const cells = row.map((x) => x.cell);
      const code = text(cells[0], false).replace(/[‐‑–]/g, '-').replace(/\s+/g, '');
      if (!code || /jele/i.test(code)) continue;
      const z = { code, category: category?.title ?? null, categoryQuote: category?.quote ?? null, quote: text(cells[0].parentElement, true), values: {} };
      fields.forEach((f, c) => { if (f && f !== 'code') z.values[f] = text(cells[c], false); });
      zones.push(z);
    }
  }
  return { effectiveFrom, zones, body: root.innerHTML };
});

const header = `
  <div class="src">
    <b>${src.title}</b><br>
    ${src.decree} – egységes szerkezetben, hatályos: ${extracted.effectiveFrom ?? 'ismeretlen'}<br>
    Forrás: Nemzeti Jogszabálytár, ${url} · letöltve: ${retrievedAt}<br>
    A szöveg változtatás nélkül, a Nemzeti Jogszabálytár egységes szerkezetű szövegéből készült.
  </div>`;
await page.setContent(`<!doctype html><meta charset="utf-8"><style>
  body { font-family: 'DejaVu Serif', serif; font-size: 10pt; line-height: 1.4; }
  .src { font-family: 'DejaVu Sans', sans-serif; font-size: 8pt; border: 1px solid #999; padding: 6px 8px; margin-bottom: 12px; }
  h1 { font-size: 14pt; } h2 { font-size: 12pt; }
  table { border-collapse: collapse; width: 100%; font-size: 7.5pt; page-break-inside: auto; }
  tr { page-break-inside: avoid; }
  td, th { border: 1px solid #555; padding: 2px 3px; vertical-align: top; }
  .jhId { display: none; }
</style>${header}${extracted.body}`);
const pdfPath = `public/docs/${src.reg}.pdf`;
await page.pdf({ path: pdfPath, format: 'A4', margin: { top: '15mm', bottom: '15mm', left: '12mm', right: '12mm' } });
await browser.close();

// Verify every quote against the PDF text and record the page it is on.
const pdfBytes = readFileSync(pdfPath);
const doc = await getDocument({ data: new Uint8Array(pdfBytes) }).promise;
const pages = [];
for (let n = 1; n <= doc.numPages; n++) {
  const tc = await (await doc.getPage(n)).getTextContent();
  pages.push(squash(tc.items.map((i) => ('str' in i ? i.str : '')).join('')));
}
const findPage = (quote) => {
  const q = squash(quote);
  const i = pages.findIndex((p) => p.includes(q));
  return i < 0 ? null : i + 1;
};

const num = (s) => {
  const m = s.replace(/\s/g, '').replace(',', '.').match(/^(\d+(?:\.\d+)?)\**$/);
  return m ? Number(m[1]) : null;
};

const missing = [];
const zoneTypes = {};
for (const z of src.tables ? extracted.zones : []) {
  const page = findPage(z.quote);
  if (!page) { missing.push(z.code); continue; }
  const cite = { reg: src.reg, page, para: `1. melléklet – ${z.code} sor`, quote: z.quote };
  const catPage = z.categoryQuote && findPage(z.categoryQuote);
  const t = {
    name: z.category ?? z.code,
    category: z.category,
    cite: catPage ? { reg: src.reg, page: catPage, para: '1. melléklet', quote: z.categoryQuote } : cite,
  };
  for (const [f, raw] of Object.entries(z.values)) t[f] = { text: raw, num: f === 'buildingMode' ? null : num(raw), cite };
  if (zoneTypes[z.code]) console.warn(`duplicate zone code ${z.code}, keeping the first`);
  else zoneTypes[z.code] = t;
}
for (const [code, name] of Object.entries(src.extraZones ?? {})) {
  zoneTypes[code] ??= { name, category: name, noTable: true };
}
if (missing.length) {
  console.error(`Citation quotes not found in the PDF for: ${missing.join(', ')}`);
  process.exit(1);
}

if (src.tables) writeFileSync(`public/data/zone-types-${key}.json`, JSON.stringify(zoneTypes, null, 1) + '\n');

const regsPath = 'public/data/regulations.json';
const regs = JSON.parse(readFileSync(regsPath, 'utf8'));
const previous = regs.regulations[src.reg];
regs.regulations[src.reg] = {
  title: src.title,
  decree: src.decree,
  status: 'linked',
  pdf: `docs/${src.reg}.pdf`,
  officialUrl: url,
  effectiveFrom: extracted.effectiveFrom,
  retrievedAt,
  sha256: createHash('sha256').update(pdfBytes).digest('hex'),
  ...(src.tables ? { zoneTypes: `zone-types-${key}.json` } : {}),
  annexes: src.annexes.map((a) => ({ title: a.title, url: a.url ?? `${NJT}${a.path}` })),
};
// Keep fields added by later pipeline steps (plan tiles, labels, rules).
for (const k of ['plan', 'zoneLabels', 'rules', 'tkr', 'protected', 'national']) {
  if (previous?.[k]) regs.regulations[src.reg][k] = previous[k];
}
if (src.district !== null) {
  const d = (regs.districts[src.district] ??= { status: 'linked', regulations: [] });
  if (!d.regulations.includes(src.reg)) d.regulations.push(src.reg);
}
writeFileSync(regsPath, JSON.stringify(regs, null, 2) + '\n');

console.log(`${src.reg}: ${Object.keys(zoneTypes).length} zones, ${doc.numPages} PDF pages, all citations verified`);
writeFileSync(`scripts/.cache/njt-${src.njtId}.html`, html);
