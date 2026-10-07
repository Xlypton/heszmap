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
  csobanka: {
    reg: 'csobanka-hesz',
    district: 1001, // Csobánka (settlement ids from 1001, see scripts/fetch_districts.py)
    tables: true,
    njtId: '2016-10-SP-5Y298',
    title: 'Csobánka – Helyi Építési Szabályzat',
    decree: '10/2016. (XI. 25.) önkormányzati rendelet',
    // The zone tables are spread over the text (1.–17. táblázat), each introduced by a sentence
    // ("A kertvárosias lakóterületek építési övezeteit, … az 1. táblázat tartalmazza:") instead of a
    // heading ending in the zone code; the table caption names the row.
    layout: 'intro',
    // Where the table's introduction does not name the zone type.
    names: { Zkk: 'Közkert (Zkk)' },
    // On the plan, without a table: only the text applies. [name, quote where the text defines it]
    extraZones: {
      'KÖu-1': ['Országos mellékutak övezete (KÖu-1)', 'a Szabályozási Terven a Köu-1 jellel megkülönböztetett terület a 1109 jelű és a 1111 jelű országos mellékút területe'],
      'KÖu-2': ['Települési gyűjtőút övezete (KÖu-2)', 'gyűjtőúti szerepet tölt be a szabályozási Terven a KÖu-2 jellel jelölt Béke út'],
      'V-1': ['Vízgazdálkodási üzemi terület (V-1)', 'V-1 jelű vízgazdálkodási üzemi területek'],
      'V-2': ['Vízfolyások, árkok medre és parti sávja (V-2)', 'V-2 jelű vízfolyások, árkok medre és parti sávja'],
      'V-3': ['Állóvizek medre és parti sávja (V-3)', 'V-3 jelű állóvizek medre és parti sávja'],
    },
    annexes: [
      { title: '1. melléklet – Szabályozási terv, belterület (M=1:3000)', path: '/document/97/97ecLL_10-277785.png' },
      { title: '2. melléklet – Szabályozási terv, külterület (M=1:7000)', path: '/document/de/dec5LL_10-277786.png' },
    ],
  },
};

const NJT = 'https://njt.jog.gov.hu';
const squash = (s) => s.normalize('NFC').replace(/\s+/g, '');

const key = process.argv[2];
// A municipality's ingest settings live in its own config (districts/<key>.json, "ingest": same
// shape as a SOURCES entry, plus "reg" for each regulation key), so municipalities can be added in
// parallel without editing this file. A key like "csobanka" or "csobanka/tkr" picks one entry.
function fromConfig(k) {
  const [file, sub] = k.split('/');
  let cfg;
  try { cfg = JSON.parse(readFileSync(new URL(`../districts/${file}.json`, import.meta.url), 'utf8')); } catch { return undefined; }
  const ing = cfg.ingest;
  if (!ing) return undefined;
  return Array.isArray(ing) ? ing.find((e) => (e.name ?? e.reg) === sub || (!sub && ing.indexOf(e) === 0)) : ing;
}
const src = SOURCES[key] ?? fromConfig(key);
if (!src) throw new Error(`Unknown source "${key}". Known: ${Object.keys(SOURCES).join(', ')}, or districts/<key>.json with "ingest"`);

const url = `${NJT}/jogszabaly/${src.njtId}`;
const res = await fetch(url, { headers: { 'user-agent': 'heszmap/0.1 (+https://github.com/xlypton/heszmap)' } });
if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
let html = await res.text();
const retrievedAt = new Date().toISOString().slice(0, 10);

// Long decrees come with part of the text not yet loaded: njt's page script fetches each block from
// /ajax/njtGetBlock.json when it scrolls into view (placeholder <div class="pH borderStart" data-show-order=…>).
// Fetch every block here and put it where the page script would (before the block's border div, which
// is then removed), so the PDF and the tables hold the whole text. No placeholders: nothing changes.
const blocks = [];
for (const m of html.matchAll(/<div id="([^"]+)" class="pH borderStart" data-show-order="(\d+)"(?: data-last-show-order="(\d+)")?/g)) {
  const req = { start: Number(m[2]), ...(m[3] ? { last: Number(m[3]) } : {}) };
  const r = await fetch(`${NJT}/ajax/njtGetBlock.json`, {
    method: 'POST', body: JSON.stringify({ documentId: src.njtId, data: [req] }),
    headers: { 'content-type': 'application/json; charset=utf-8', 'x-requested-with': 'XMLHttpRequest' },
  });
  if (!r.ok) throw new Error(`njtGetBlock ${m[1]}: HTTP ${r.status}`);
  blocks.push({ id: m[1], content: await r.text() });
}

const browser = await playwright.chromium.launch();
const page = await browser.newPage();
await page.setContent(html, { waitUntil: 'domcontentloaded' });
if (blocks.length) {
  const left = await page.evaluate((blocks) => {
    for (const b of blocks) {
      const border = document.getElementById(b.id);
      if (!border) throw new Error(`njt text block ${b.id} not found`);
      border.insertAdjacentHTML('beforebegin', b.content);
      border.remove();
    }
    return document.querySelectorAll('#jogszab div.pH.borderStart').length;
  }, blocks);
  if (left) throw new Error(`${left} njt text blocks still not loaded`);
  console.log(`loaded ${blocks.length} lazily loaded text block(s) from njt`);
}

// Everything below runs on the official DOM.
// Optional, per municipality (all off by default):
//   codePattern  regex a zone code must match; other rows of a limits table (footnotes printed as table
//                rows: "* BP/1701/… OTÉK eltérési engedély alapján") become notes of that table
//   keepSup      keep superscript markers in values ("15,0ᵖ" = párkánymagasság): such a value has no number
//   notesAfter   footnotes right after a table ("ᵖ párkánymagasság", "* …") explain its marked values
//   tableAnnex   the annex holding the tables, for citations (default "1. melléklet")
//   headerFromTop a column's label is its whole header (all rows above the data), not only the rows from
//                the "jele" row down (XIII: "a telek megengedett legnagyobb | beépítettsége | terepszint felett")
//   fieldRules   [[regex, field or null], ...] tried on a column label before the built-in mapping
const opts = { layout: src.layout ?? 'heading', codePattern: src.codePattern ?? null, keepSup: !!src.keepSup, notesAfter: !!src.notesAfter,
  headerFromTop: !!src.headerFromTop, fieldRules: src.fieldRules ?? [] };
const extracted = await page.evaluate(({ layout, codePattern, keepSup, notesAfter, headerFromTop, fieldRules }) => {
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
  // A value with its superscript markers, without njt's own footnote numbers (sup.fnSup).
  const marked = (el) => {
    const c = el.cloneNode(true);
    c.querySelectorAll('sup.fnSup').forEach((s) => s.remove());
    return c.textContent.replace(/\s+/g, ' ').trim();
  };
  const isCode = codePattern ? (s) => new RegExp(codePattern, 'u').test(s) : () => true;

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
    for (const [re, f] of fieldRules) if (new RegExp(re, 'u').test(l)) return f;
    if (l.includes('jele')) return 'code';
    // Columns some plans add (Csobánka): plot width/depth, the smallest plot that may be built on, and
    // a separate height limit for dwellings.
    if (l.includes('beépíthető legkisebb telek terület')) return 'minBuildablePlotM2';
    if (l.includes('beépíthető legkisebb telekszélesség')) return 'minBuildablePlotWidthM';
    if (l.includes('kialakítható legkisebb telekszélesség')) return 'minPlotWidthM';
    if (l.includes('lakó épület esetén') && l.includes('magasság')) return 'maxHeightResidentialM';
    if (l.includes('telek')) return 'minPlotM2';
    if (l.includes('beépítési mód')) return 'buildingMode';
    if (l.includes('terepszint alatti')) return 'maxUndergroundPct';
    if (l.includes('beépítettség') || l.includes('beépítés megengedett')) return 'maxCoveragePct';
    if (l.includes('magasság')) return l.includes('legkisebb') ? 'minHeightM' : 'maxHeightM';
    if (l.includes('zöldfelület')) return 'minGreenPct';
    if (l.includes('szintterület')) return l.includes('parkol') && !l.includes('általános/parkolás') ? 'maxFarParking' : 'maxFar';
    return null;
  };

  // The non-empty blocks before a table, closest first.
  const before = function* (table) {
    for (let el = (table.closest('.tablazat') ?? table).previousElementSibling; el; el = el.previousElementSibling) {
      if (text(el, false)) yield el;
    }
  };

  const zones = [];
  const tables = []; // header -> field mapping per table, printed with DEBUG_TABLES=1
  let category = null;
  for (const table of root.querySelectorAll('table')) {
    const g = grid(table);
    // The header row is the one naming the code column ("Építési övezet jele"); rows above it (column
    // letters) and columns left of it (row numbers) are the table's own numbering.
    const isCodeHead = (x) => x && /jele$/i.test(text(x.cell, false));
    const head = g.findIndex((row) => row.some(isCodeHead));
    if (head < 0) continue;
    const codeCol = g[head].findIndex(isCodeHead);
    let caption = null;

    if (layout === 'intro') {
      // "1. A kertvárosias lakóterületek építési övezeteit, azok … paramétereit az 1. táblázat tartalmazza:"
      for (const el of before(table)) {
        const t = text(el, false);
        if (!caption && /^\d+\. táblázat$/.test(t)) { caption = t; continue; }
        if (/táblázat tartalmazza/.test(t)) {
          const m = t.match(/^(?:\(?\d+\)?\.?\s*)?(?:Az?\s+)?(.+?)(?:\s+építési)?\s+övezet(?:e|ei)?t?\b/);
          const title = m ? m[1].replace(/^\p{Ll}/u, (c) => c.toUpperCase()) : t;
          category = { title, quote: text(el, true) };
          break;
        }
      }
    } else {
      // The category heading ("6. Kertvárosias, intenzív beépítésű lakóterület (Lke‐1)") is the closest
      // preceding text block.
      let prev = table.closest('.TABLE') ?? table;
      while (prev && !/\(\S+\)\s*$/.test(text(prev, false))) prev = prev.previousElementSibling;
      if (prev) {
        // "6. Kertvárosias … (Lke‐1) Kertvárosias … (Lke‐1)": drop the numbering and the repeated title.
        const title = text(prev, false).replace(/^\d+\.\s*/, '').replace(/^(.+?\))\s*\1$/, '$1');
        category = { title, quote: text(prev, true) };
      }
    }

    // Sub-header rows ("Legkisebb | Legnagyobb", "Általános | Parkolásra", units) sit under the
    // rowspanned "jele" cell, so the first data row is the first one that starts a new non-empty cell
    // in the code column.
    const firstData = g.findIndex((row, r) => r > head && row[codeCol]?.origin && text(row[codeCol].cell, false));
    if (firstData < 0) continue;
    const labels = g[head].map((_, c) => g.slice(headerFromTop ? 0 : head, firstData).map((row) => (row[c] ? text(row[c].cell, false) : '')).join(' '));
    // Keep the first column per field: trailing empty sub-columns would otherwise overwrite values.
    const fields = labels.map((l, c) => (c < codeCol ? null : field(l))).map((f, c, all) => (all.indexOf(f) === c ? f : null));
    tables.push({ caption, columns: labels.map((l, c) => [l, fields[c]]) });
    // With codePattern: a table with a code column but no limits column (IX.: the table of uses allowed
    // per zone) is not a limits table.
    if (codePattern && !fields.some((f) => f && f !== 'code')) continue;

    // Footnotes right after the table ("*kivéve hitéleti épület esetén, …") explain starred values.
    const notes = [];
    if (layout === 'intro') {
      for (let el = (table.closest('.tablazat') ?? table).nextElementSibling; el; el = el.nextElementSibling) {
        const t = text(el, false);
        if (!t) continue;
        if (!t.startsWith('*')) break;
        notes.push(text(el, true));
      }
    } else if (notesAfter) {
      for (let el = (table.closest('.tablazat, .mellekletPont, .pslice') ?? table).nextElementSibling; el; el = el.nextElementSibling) {
        const t = text(el, true);
        if (!t) continue;
        const sup = el.firstElementChild?.nodeName === 'SUP' && !el.firstElementChild.classList.contains('fnSup') && t.startsWith(el.firstElementChild.textContent.trim());
        if (!sup && !/^[*ⁿ]/.test(t)) break;
        notes.push(t);
      }
    }

    for (const row of g.slice(firstData)) {
      const cells = row.map((x) => x?.cell);
      if (!cells[codeCol]) continue;
      const code = text(cells[codeCol], false).replace(/[‐‑–]/g, '-').replace(/\s+/g, '');
      if (!code || /jele/i.test(code)) continue;
      // With codePattern, a row is a footnote/legend row if its code is not a code, or if one wide cell
      // follows it ("KH/L | lakóépület esetén csak …").
      const others = new Set(cells.slice(codeCol + 1).filter((c) => c && c !== cells[codeCol]));
      const rest = others.size;
      if (!isCode(code) || (codePattern && rest <= 2)) {
        // A row naming a category inside the table, its one cell spanning the row ("6 | Nagyvárosias, …
        // lakóterület (Ln-2)", "2 | Vt-V"), heads the rows below it.
        const t = text(cells[codeCol], false);
        if (codePattern && rest === 0 && (/\([^)]+\)\s*\**$/.test(t) || isCode(code))) category = { title: t, quote: text(cells[codeCol].parentElement, true) };
        else notes.push(text(cells[codeCol].parentElement, true));
        continue;
      }
      const heightLabel = labels[fields.indexOf('maxHeightM')] ?? '';
      const z = { code, caption, notes, heightIsBuilding: /épület[- ]?magasság/i.test(heightLabel), category: category?.title ?? null, categoryQuote: category?.quote ?? null, quote: text(cells[codeCol].parentElement, true), values: {} };
      fields.forEach((f, c) => { if (f && f !== 'code' && cells[c]) z.values[f] = keepSup ? marked(cells[c]) : text(cells[c], false); });
      zones.push(z);
    }
  }
  return { effectiveFrom, zones, tables, body: root.innerHTML };
}, opts);

if (process.env.DEBUG_TABLES) for (const t of extracted.tables) console.log(t.caption, JSON.stringify(t.columns.filter(([l]) => l.trim())));

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
// `from`: the first page to look at (a footnote repeated under several tables belongs to the next one).
const findPage = (quote, from = 1) => {
  const q = squash(quote);
  const i = pages.findIndex((p, n) => n + 1 >= from && p.includes(q));
  return i < 0 ? null : i + 1;
};

const num = (s) => {
  // "30.000" and "40 000" are thousands, "5,0" is a decimal comma.
  const m = s.replace(/\s/g, '').replace(/^(\d{1,3})((?:\.\d{3})+)(\**)$/, (_, a, b, c) => a + b.replace(/\./g, '') + c)
    .replace(',', '.').match(/^(\d+(?:\.\d+)?)\**$/);
  return m ? Number(m[1]) : null;
};

const missing = [];
const zoneTypes = {};
for (const z of src.tables ? extracted.zones : []) {
  const page = findPage(z.quote);
  if (!page) { missing.push(z.code); continue; }
  const cite = { reg: src.reg, page, para: `${z.caption ?? src.tableAnnex ?? '1. melléklet'} – ${z.code} sor`, quote: z.quote };
  const catPage = z.categoryQuote && findPage(z.categoryQuote);
  const t = {
    name: src.layout === 'intro' && z.category ? `${z.category} (${z.code})` : z.category ?? z.code,
    category: z.category,
    cite: catPage ? { reg: src.reg, page: catPage, para: z.caption ?? src.tableAnnex ?? '1. melléklet', quote: z.categoryQuote } : cite,
    // The height column is the OTÉK "épületmagasság" itself (not a "beépítési magasság" to interpret).
    ...(z.heightIsBuilding ? { heightIs: 'épületmagasság' } : {}),
  };
  if (src.names?.[z.code]) t.name = src.names[z.code];
  if (z.notes?.length) {
    t.notes = z.notes.map((n) => {
      let p = findPage(n, page);
      let quote = n;
      // A long footnote row can break across PDF pages: anchor on its longest prefix found on one page.
      for (let words = n.split(' '); !p && words.length > 6; words = words.slice(0, -1)) {
        quote = words.slice(0, -1).join(' ');
        p = findPage(quote, page);
      }
      if (!p) { missing.push(`${z.code} (lábjegyzet)`); if (process.env.DEBUG_TABLES) console.error(n); }
      return { text: n, cite: { reg: src.reg, page: p, para: `${z.caption ?? src.tableAnnex ?? '1. melléklet'} – lábjegyzet`, quote } };
    });
  }
  for (const [f, raw] of Object.entries(z.values)) t[f] = { text: raw, num: f === 'buildingMode' ? null : num(raw), cite };
  if (zoneTypes[z.code]) console.warn(`duplicate zone code ${z.code}, keeping the first`);
  else zoneTypes[z.code] = t;
}
for (const [code, extra] of Object.entries(src.extraZones ?? {})) {
  // [name, quote]: the quote is where the text defines the zone, verified like the table rows.
  const [name, quote] = Array.isArray(extra) ? extra : [extra, null];
  const page = quote && findPage(quote);
  if (quote && !page) { missing.push(code); continue; }
  zoneTypes[code] ??= { name, category: name, noTable: true, ...(page ? { cite: { reg: src.reg, page, para: 'szöveg', quote } } : {}) };
}
if (missing.length) {
  console.error(`Citation quotes not found in the PDF for: ${missing.join(', ')}`);
  process.exit(1);
}

if (src.tables) writeFileSync(`public/data/zone-types-${key.replace('/', '-')}.json`, JSON.stringify(zoneTypes, null, 1) + '\n');

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
  ...(src.tables ? { zoneTypes: `zone-types-${key.replace('/', '-')}.json` } : {}),
  annexes: src.annexes.map((a) => ({ title: a.title, url: a.url ?? `${NJT}${a.path}` })),
};
// Keep fields added by later pipeline steps (plan tiles, labels, rules).
for (const k of ['plan', 'zoneLabels', 'rules', 'tkr', 'protected', 'national', 'effective', 'parcels', 'zoneAreas']) {
  if (previous?.[k]) regs.regulations[src.reg][k] = previous[k];
}
if (src.district !== null) {
  const d = (regs.districts[src.district] ??= { status: 'linked', regulations: [] });
  if (!d.regulations.includes(src.reg)) d.regulations.push(src.reg);
}
writeFileSync(regsPath, JSON.stringify(regs, null, 2) + '\n');

console.log(`${src.reg}: ${Object.keys(zoneTypes).length} zones, ${doc.numPages} PDF pages, all citations verified`);
writeFileSync(`scripts/.cache/njt-${src.njtId}.html`, html);
