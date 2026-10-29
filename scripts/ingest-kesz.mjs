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
//   codeCols     2: the code is split over the two columns under "jele" (XXII.: "LN-T" | "/1")
const opts = { layout: src.layout ?? 'heading', codePattern: src.codePattern ?? null, keepSup: !!src.keepSup, notesAfter: !!src.notesAfter,
  headerFromTop: !!src.headerFromTop, fieldRules: src.fieldRules ?? [], codeCols: src.codeCols ?? 1, cornerPairs: !!src.cornerPairs, flatTables: src.flatTables ?? null, verticalTables: !!src.verticalTables };
const extracted = await page.evaluate(({ layout, codePattern, keepSup, notesAfter, headerFromTop, fieldRules, codeCols, cornerPairs, flatTables, verticalTables }) => {
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
    // A párkánymagasság column is its own limit, next to (or instead of) the épületmagasság (IX., XII.).
    if (l.includes('párkány')) return l.includes('legkisebb') ? 'minCorniceM' : 'maxCorniceM';
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
  // verticalTables (IX. 22/2017. UNIX): one table per zone, the code in the last cell of the first row
  // ("Az építési övezet jele | Vi-2/IX-U"), then one row per limit: its label across the first cells, the
  // value with its unit in the last ("legnagyobb | beépítési mértéke: | 35 %").
  const vfield = (l) => {
    for (const [re, f] of fieldRules) if (new RegExp(re, 'u').test(l)) return f;
    if (l.includes('beépítési módja')) return 'buildingMode';
    if (l.includes('legkisebb') && l.includes('területe')) return 'minPlotM2';
    if (l.includes('szélessége')) return 'minPlotWidthM';
    if (l.includes('szint alatti')) return 'maxUndergroundPct';
    if (l.includes('beépítési mértéke')) return 'maxCoveragePct';
    if (l.includes('zöldfelület')) return 'minGreenPct';
    if (l.includes('szmp')) return 'maxFarParking';
    if (l.includes('szmá')) return 'maxFar';
    if (l.includes('maximális') && l.includes('épületmagass')) return 'maxHeightM';
    if (l.includes('minimális') && l.includes('párkány')) return 'minHeightM';
    return null;
  };
  for (const table of verticalTables ? root.querySelectorAll('table') : []) {
    const rows = [...table.rows];
    const first = rows[0] ? [...rows[0].cells] : [];
    const code = first.length ? text(first.at(-1), false) : '';
    if (!/jele/i.test(text(rows[0], false)) || !isCode(code)) continue;
    const z = { code, caption: null, notes: [], heightIsBuilding: true, category: null, categoryQuote: null, quote: text(rows[0], false), values: {} };
    for (const tr of rows.slice(1)) {
      const cells = [...tr.cells];
      const label = cells.slice(0, -1).map((c) => text(c, false)).join(' ').toLowerCase();
      if (label.includes('megnevezése')) { z.category = cells.slice(1).map((c) => text(c, false)).filter(Boolean).join(', '); continue; }
      const f = vfield(label);
      const v = marked(cells.at(-1)).replace(/\s*(m2\/\s*m2|m2|%|m)$/, '').trim();
      if (f && v && !(f in z.values)) z.values[f] = v;
    }
    zones.push(z);
    table.dataset.vertical = '1';
  }
  for (const table of root.querySelectorAll('table')) {
    if (table.dataset.vertical) continue;
    const g = grid(table);
    // The header row is the one naming the code column ("Építési övezet jele"); rows above it (column
    // letters) and columns left of it (row numbers) are the table's own numbering.
    const isCodeHead = (x) => x && /jele$/i.test(text(x.cell, false));
    const head = g.findIndex((row) => row.some(isCodeHead));
    if (head < 0) continue;
    let codeCol = g[head].findIndex(isCodeHead);
    // A "jele" header spanning two columns whose rows put the code in the second one, the row number
    // spanning the first (XIII. Vi-3, Gksz tables): read the code from the column the rows use.
    if (codeCols === 1) {
      const span = g[head].map((x, c) => (x && x.cell === g[head][codeCol].cell ? c : -1)).filter((c) => c >= 0);
      // The row number may also sit under "jele" (IV. Újpest: "1. | Lk-1/IV-5/1"): prefer the column holding a code.
      const codeText = (row, c) => text(row[c].cell, false).replace(/[‐‑–]/g, '-').replace(/\s+/g, '');
      const used = (row) => span.find((c) => row[c]?.origin && isCode(codeText(row, c)) && /\p{L}/u.test(codeText(row, c)))
        ?? span.find((c) => row[c]?.origin && text(row[c].cell, false));
      const r = g.findIndex((row, i) => i > head && used(row) !== undefined);
      if (r >= 0) codeCol = used(g[r]);
    }
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
      // An earlier table ending in a unit ("(%)") is not a heading (XIII.).
      // "2. táblázat: Kisvárosias, jellemzően szabadonálló jellegű lakóterület Lk-2" (IV. Újpest) also heads its table.
      const tableTitle = /^(?:\d+\.\s*)?táblázat:\s*(.+)$/;
      while (prev && (prev.matches('table') || prev.querySelector('table') || !(/\(\S+\)\s*$/.test(text(prev, false)) || tableTitle.test(text(prev, false))))) prev = prev.previousElementSibling;
      if (prev) {
        // "6. Kertvárosias … (Lke‐1) Kertvárosias … (Lke‐1)": drop the numbering and the repeated title.
        const t0 = text(prev, false), tt = t0.match(tableTitle);
        const title = tt ? tt[1].replace(/\s+(\p{Lu}[\p{L}\d]*-[\p{L}\d-]*)$/u, ' ($1)') : t0.replace(/^\d+(?:\.\s*|\s+)/, '').replace(/^(.+?\))\s*\1$/, '$1');
        category = { title, quote: text(prev, true) };
      }
    }

    // Sub-header rows ("Legkisebb | Legnagyobb", "Általános | Parkolásra", units) sit under the
    // rowspanned "jele" cell, so the first data row is the first one that starts a new non-empty cell
    // in the code column.
    // codeCols (XXII.): the "jele" header spans the code's two cells ("LN-T" | "/1"), joined into one code.
    const codeSpan = codeCols > 1 ? g[head].filter((x) => x && x.cell === g[head][codeCol].cell).length : 1;
    const firstData = g.findIndex((row, r) => r > head && row[codeCol]?.origin && text(row[codeCol].cell, false));
    if (firstData < 0) continue;
    const labels = g[head].map((_, c) => g.slice(headerFromTop ? 0 : head, firstData).map((row) => (row[c] ? text(row[c].cell, false) : '')).join(' '));
    // Keep the first column per field: trailing empty sub-columns would otherwise overwrite values.
    const fields = labels.map((l, c) => (c < codeCol ? null : field(l))).map((f, c, all) => (all.indexOf(f) === c ? f : null));
    // cornerPairs (IV. Újpest): each limit has a "K" (közbenső telek) and an "S" (saroktelek) column; the
    // K value is the field's, the S value is added to it when it differs.
    const cornerOf = {};
    if (cornerPairs) labels.forEach((l, c) => {
      const m = l.match(/^(.*\S)\s+K\**$/);
      if (m && fields[c] === undefined) return;
      if (m && labels[c + 1]?.match(/^(.*\S)\s+S\**$/)?.[1] === m[1]) cornerOf[c] = c + 1;
    });
    tables.push({ caption, category: category?.title, columns: labels.map((l, c) => [l, fields[c]]) });
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
        const sup = el.firstElementChild?.nodeName === 'SUP' && !el.firstElementChild.classList.contains('fnSup') && t.startsWith(el.firstElementChild.textContent.trim())
          && !/^\d+$/.test(el.firstElementChild.textContent.trim()); // not an njt footnote number ("11Hatályon kívül helyezve …")
        if (/^„-” jelölés/.test(t)) continue; // the table's own legend line before its notes (XIX. Wekerletelep)
        if (!sup && !/^[*ⁿ]/.test(t)) break;
        notes.push(t);
      }
    }

    for (const row of g.slice(firstData)) {
      const cells = row.map((x) => x?.cell);
      if (!cells[codeCol]) continue;
      const codeCells = [...new Set(cells.slice(codeCol, codeCol + codeSpan))].filter(Boolean);
      const code = codeCells.map((c) => text(c, false)).join('').replace(/[‐‑–]/g, '-').replace(/\s+/g, '');
      // "jele" at the end only: "Kiemelt jelentőségű … (Vt-H)" is a category row, not a header (XIX).
      if (!code || /jele$/i.test(code)) continue;
      // With codePattern, a row is a footnote/legend row if its code is not a code, or if one wide cell
      // follows it ("KH/L | lakóépület esetén csak …").
      const others = new Set(cells.slice(codeCol + codeSpan).filter((c) => c && !codeCells.includes(c)));
      const rest = others.size;
      // A code with one cell spanning every limit column ("Ln-T/IV-2/K | kialakult", IV. Újpest): that word is every limit.
      const wide = rest === 1 && [...others][0];
      if (codePattern && isCode(code) && wide && /^kialakult$/i.test(text(wide, false))) {
        const z = { code, caption, notes, heightIsBuilding: false, category: category?.title ?? null, categoryQuote: category?.quote ?? null, quote: text(cells[codeCol].parentElement, true), values: {} };
        fields.forEach((f, c) => { if (f && f !== 'code' && cells[c] === wide) z.values[f] = text(wide, false); });
        zones.push(z);
        continue;
      }
      if (!isCode(code) || (codePattern && rest <= 2)) {
        // A row naming a category inside the table, its one cell spanning the row ("6 | Nagyvárosias, …
        // lakóterület (Ln-2)", "2 | Vt-V"), heads the rows below it.
        const t = text(cells[codeCol], false);
        if (codePattern && rest === 0 && (/\([^)]+\)\s*\**$/.test(t) || isCode(code))) category = { title: t.replace(/^\d+\.?\s+(?=\D)/, ''), quote: text(cells[codeCol].parentElement, true) };
        else notes.push(text(cells[codeCol].parentElement, true));
        continue;
      }
      const heightLabel = labels[fields.indexOf('maxHeightM')] ?? '';
      const z = { code, caption, notes, heightIsBuilding: /épület[- ]?magasság/i.test(heightLabel), category: category?.title ?? null, categoryQuote: category?.quote ?? null, quote: text(cells[codeCol].parentElement, true), values: {} };
      fields.forEach((f, c) => { if (f && f !== 'code' && cells[c]) z.values[f] = keepSup ? marked(cells[c]) : text(cells[c], false); });
      // A height's column header as printed ("Beépítési magasság (m) (épület=É párkány=P)"): the card names
      // the limit in the regulation's own words.
      z.labels = Object.fromEntries(fields.map((f, c) => [f, labels[c]]).filter(([f]) => /Height|Cornice/.test(f ?? '')));
      for (const [k, sc] of Object.entries(cornerOf)) {
        const f = fields[k];
        const kv = cells[k] && text(cells[k], false), sv = cells[sc] && cells[sc] !== cells[k] && text(cells[sc], false);
        if (f && f !== 'code' && sv && sv !== kv) z.values[f] = `${kv || '-'} (saroktelek: ${sv})`;
      }
      // One row for several codes ("Vt-M-XIX/1<br>Vt-M-XIX/1*", XIX): the same limits for each.
      // A code broken after its "/" ("K-Hon/<br>ÉK-1", XII. 26/2020) is one code.
      const several = codePattern ? text(cells[codeCol], false).replace(/[‐‑–]/g, '-').replace(/([/-]) +/g, '$1').split(' ') : [];
      if (several.length > 1 && several.every(isCode)) for (const c of several) zones.push({ ...z, code: c });
      else zones.push(z);
    }
  }
  // flatTables (IV. Újpest 12/2018., 5/2018.): njt prints some zone tables as one run of text, not a
  // <table> ("Vt-M A B C … Építési övezet jele … 1. Vt-M/IV-4/1 zártsorú (Z) 3000 30 80 100 4,0 2,0
  // É=12,5 É=30,0 15 2. …"). flatTables is the field of each number after the building mode, in order.
  if (flatTables) {
    for (const el of root.querySelectorAll('.szelet, .mellekletPont')) {
      const t = text(el, false);
      if (!/Építési övezet jele/.test(t) || el.querySelector('table')) continue;
      // The title is the block before (12/2018.: "5. Mellékközpont területe") or the run's own first
      // paragraph (5/2018.: "2. táblázat: Kisvárosias, …" then "Lk-2" and the header).
      const own = el.matches('.mellekletPont') && el.querySelector('p');
      let head = own || el.previousElementSibling;
      while (head && !own && !text(head, false)) head = head.previousElementSibling;
      const sb = own ? el.querySelectorAll('p')[1]?.querySelector('b') : el.querySelector('b');
      const short = sb ? text(sb, false) : '';
      const ht = head ? text(head, false).replace(/^\d+\.\s*/, '').replace(/^táblázat:\s*/, '') : null;
      const category = ht ? { title: short ? `${ht} (${short})` : ht, quote: text(head, true) } : null;
      // Cells run together where njt drops the space ("… 25" + "3. Gksz-2/IV-5/3" = "253. Gksz…"): the
      // rows are numbered 1, 2, 3 …, so split before each next number.
      let body = ` ${t}`;
      for (let k = 1; k < 100; k++) {
        const r = new RegExp(`(\\S)(${k}\\.\\s+\\S+\\/IV-\\d)`);
        const spaced = new RegExp(`\\s${k}\\.\\s+\\S+\\/IV-\\d`).test(body);
        if (spaced) continue;
        if (!r.test(body)) break;
        body = body.replace(r, '$1 $2');
      }
      body = body.slice(body.search(/\s1\.\s+\S+\/IV-\d/));
      const rows = [...body.matchAll(/(\d+)\.\s+(\S+\/IV-\d+(?:\/\S+)?)\s+(.*?)(?=\s+\d+\.\s+\S+\/IV-\d|\s+KA=|$)/g)];
      for (const [, n, code, rest] of rows) {
        if (!isCode(code)) continue;
        const m = rest.match(/^((?:\p{L}+\s+\([A-ZÁÉ]+\)\s*)+)(.*)$/u);
        if (!m) continue;
        // The last row runs on into the next heading ("… 25 BEÉPÍTÉSRE NEM SZÁNT TERÜLETEK"): limits only.
        const all = m[2].trim().split(/\s+/);
        const stop = all.findIndex((w) => !/^(?:[ÉP]=)?[\d,.-]+\**$/.test(w));
        const nums = stop < 0 ? all : all.slice(0, stop);
        const glued = stop >= 0 && all[stop].match(/^((?:[ÉP]=)?[\d,]+)\p{Lu}{3}/u); // "25BEÉPÍTÉSRE"
        if (glued) nums.push(glued[1]);
        const quote = `${n}. ${code} ${m[1].trim()} ${nums.join(' ')}`;
        const z = { code, caption: null, notes: [], heightIsBuilding: /É=/.test(rest), category: category?.title ?? null, categoryQuote: category?.quote ?? null, quote: quote.trim(), values: { buildingMode: m[1].trim() } };
        flatTables.forEach((f, i) => { if (nums[i] !== undefined) z.values[f] = i === flatTables.length - 1 ? nums.slice(i).join(' ') : nums[i]; });
        zones.push(z);
      }
      tables.push({ caption: null, category: category?.title, columns: flatTables.map((f) => [f, f]) });
    }
  }
  return { effectiveFrom, zones, tables, body: root.innerHTML };
}, opts);

if (process.env.DEBUG_TABLES) for (const t of extracted.tables) console.log(t.caption, t.category, JSON.stringify(t.columns.filter(([l]) => l.trim())));

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
  // Two numbers in one cell ("45 75": general / corner plot) are not one number; "10 000" is.
  if (/\d\s+\d/.test(s) && !/^\d{1,3}(?:[ .]\d{3})+\s*\**$/.test(s.trim())) return null;
  const m = s.replace(/\s/g, '').replace(/^(\d{1,3})((?:\.\d{3})+)(\**)$/, (_, a, b, c) => a + b.replace(/\./g, '') + c)
    .replace(',', '.').match(/^(\d+(?:\.\d+)?)\**$/);
  return m ? Number(m[1]) : null;
};

const missing = [];
const zoneTypes = {};
for (const z of src.tables ? extracted.zones : []) {
  const page = findPage(z.quote);
  if (!page) { missing.push(z.code); if (process.env.DEBUG_TABLES) console.error(z.quote); continue; }
  const cite = { reg: src.reg, page, para: `${z.caption ?? src.tableAnnex ?? '1. melléklet'} – ${z.code} sor`, quote: z.quote };
  // categoryFix [[code regex, title]]: rows whose table has no category row of its own, which would
  // otherwise keep the previous table's (XII. 26/2020: the Zkp/Kk table after Kb-Rek).
  const fix = src.categoryFix?.find(([re]) => new RegExp(re).test(z.code));
  if (fix) Object.assign(z, { category: fix[1], categoryQuote: null });
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
  // footnoteDigits (IV. Újpest): njt prints a footnote mark as a plain digit after the value ("65" + "¹" =
  // "651"); a percentage over 100 whose last digit is such a mark is shown as "65¹".
  const sup = { 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵' };
  const unmark = (f, raw) => (src.footnoteDigits && /Pct$/.test(f)
    ? raw.replace(/\b(\d{1,3})([1-5])\b/g, (m, a, b) => (Number(m) > 100 && Number(a) <= 100 ? a + sup[b] : m)) : raw);
  for (const [f, raw0] of Object.entries(z.values)) {
    const raw = unmark(f, raw0);
    t[f] = { text: raw, num: f === 'buildingMode' ? null : num(raw.replace(/[¹²³⁴⁵]$/, '')), cite,
      ...(z.labels?.[f] ? { label: z.labels[f].replace(/(\p{L})-(\p{Ll})/gu, '$1$2').replace(/\s+/g, ' ').trim() } : {}) };
  }
  if (zoneTypes[z.code]) console.warn(`duplicate zone code ${z.code}, keeping the first`);
  else zoneTypes[z.code] = t;
}
// scannedRows (IV. Újpest 3/2019.): zone tables njt publishes only as images, transcribed by hand from the
// image ({code, table, category, image, values}). The cite is the page of the regulation PDF where the annex
// starts (scannedAnchor) and names the table; the quote is the transcription, checked by eye against the image.
if (src.scannedRows?.length) {
  const page = findPage(src.scannedAnchor);
  if (!page) missing.push(`scannedAnchor ${src.scannedAnchor}`);
  for (const r of src.scannedRows) {
    const quote = `${r.code} ${Object.values(r.values).join(' ')}`;
    const cite = { reg: src.reg, page, para: `${src.tableAnnex ?? '2. melléklet'} ${r.table}. táblázat (${src.scannedLabel ?? 'képként közölve'}) – ${r.code} sor`, quote };
    const t = { name: r.code, category: r.category, cite, heightIs: 'épületmagasság', scanned: r.image };
    // scannedNotes: the table's legend, by mark: footnote digits ("¹"), asterisks or abbreviations used in cells
    // ("Á:", "K"); scannedTableNotes[table] adds to or overrides it for one table (3/2019.: "L" differs by table).
    const legend = { ...src.scannedNotes, ...src.scannedTableNotes?.[r.table] };
    const cells = Object.values(r.values).join(' ');
    const edge = (c) => (/\p{L}/u.test(c) ? '\\p{L}' : c === '*' ? '\\*' : null);
    const esc = (m) => m.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const hit = (m) => {
      const [b, a] = [edge(m[0]), edge(m.at(-1))];
      return new RegExp(`${b ? `(?<!${b})` : ''}${esc(m)}${a ? `(?!${a})` : ''}`, 'u').test(cells);
    };
    const marks = Object.keys(legend).filter(hit);
    if (marks.length) t.notes = marks.map((m) => ({ text: `${m} ${legend[m]}`, cite }));
    for (const [f, raw] of Object.entries(r.values)) t[f] = { text: raw, num: f === 'buildingMode' ? null : num(raw.replace(/[¹²³⁴⁵]$/, '')), cite };
    if (zoneTypes[r.code]) console.warn(`duplicate zone code ${r.code}, keeping the table row`);
    else zoneTypes[r.code] = t;
  }
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
for (const k of ['plan', 'zoneLabels', 'rules', 'tkr', 'protected', 'national', 'effective', 'parcels', 'zoneAreas', 'planBasis']) {
  if (previous?.[k]) regs.regulations[src.reg][k] = previous[k];
}
if (src.district !== null) {
  const d = (regs.districts[src.district] ??= { status: 'linked', regulations: [] });
  if (!d.regulations.includes(src.reg)) d.regulations.push(src.reg);
}
writeFileSync(regsPath, JSON.stringify(regs, null, 2) + '\n');

console.log(`${src.reg}: ${Object.keys(zoneTypes).length} zones, ${doc.numPages} PDF pages, all citations verified`);
writeFileSync(`scripts/.cache/njt-${src.njtId}.html`, html);
