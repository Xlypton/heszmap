// Zone limits tables published as a PDF annex (not as HTML tables in the njt text): Budapest I. and
// II. kerület print "Építési övezetek … szabályozási határértékei" as a separate PDF.
//   1. download the annex from njt.jog.gov.hu and publish it unchanged (public/docs/<reg>.pdf),
//   2. read its tables from the PDF text layer: the column-letter row ("A B C …") gives the columns,
//      every zone code left of column A starts a row,
//   3. cite every row by a run of consecutive text items of that row, so the quote is by construction
//      in the PDF's text (and re-verified the way the viewer searches it).
// Config: districts/<key>.json "zoneTablePdf" (see districts/i.json). Run scripts/ingest-kesz.mjs
// first (regulation text + registry entry); this adds the annex as a regulation of its own (so the
// viewer opens it at the cited row) and points the main regulation's "zoneTypes" at the table.
//
//   node scripts/ingest-pdf-zones.mjs i
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { getDocument, Util } from 'pdfjs-dist/legacy/build/pdf.mjs';

const NJT = 'https://njt.jog.gov.hu';
const key = process.argv[2];
const cfg = JSON.parse(readFileSync(new URL(`../districts/${key}.json`, import.meta.url), 'utf8'));
const t = cfg.zoneTablePdf;
if (!t) throw new Error(`districts/${key}.json has no "zoneTablePdf"`);
const mainReg = cfg.regulation.reg;
const url = t.url ?? `${NJT}${t.path}`;

const cache = `scripts/.cache/${key}/annex`;
mkdirSync(cache, { recursive: true });
const local = `${cache}/${url.split('/').pop()}`;
if (!existsSync(local)) {
  const r = await fetch(url, { headers: { 'user-agent': 'heszmap/0.1 (+https://github.com/xlypton/heszmap)' } });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  writeFileSync(local, Buffer.from(await r.arrayBuffer()));
}
const bytes = readFileSync(local);
const pdfPath = `public/docs/${t.reg}.pdf`;
writeFileSync(pdfPath, bytes); // the official file, unchanged

const squash = (s) => s.normalize('NFC').replace(/\s+/g, '');
const dash = (s) => s.replace(/[‐‑–]/g, '-');
const codeRe = new RegExp(t.codeRe ?? '^[A-ZÁÉÍÓÖŐÚÜŰ][A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{0,4}(?:[-/_][A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9]+)+$', 'u');
// The column letters as printed left to right; "letterOrder" when a table prints them out of order
// (Budapest XV.: "A B C D F G H I E J …").
const letters = t.letterOrder ?? 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

const num = (s) => {
  let v = s.replace(/\s/g, '');
  if (t.decimal === '.') v = v.replace(/^(\d+)\.(\d+)$/, '$1,$2');
  v = v.replace(/^(\d{1,3})((?:\.\d{3})+)$/, (_, a, b) => a + b.replace(/\./g, ''));
  const m = v.replace(',', '.').match(/^(\d+(?:\.\d+)?)$/);
  return m ? Number(m[1]) : null;
};

const doc = await getDocument({ data: new Uint8Array(bytes), standardFontDataUrl: 'node_modules/pdfjs-dist/standard_fonts/' }).promise;
const zoneTypes = {};
const report = [];
// Tables too irregular to read automatically (Budapest VI.: no column letters, several values per
// cell for general / corner-plot / underground-garage cases) are transcribed in the config ("rows"):
// each row's quote must be found in the PDF text, so every transcribed value points at its printed row.
const pageTexts = [];
for (let n = 1; n <= doc.numPages; n++) {
  const tc = await (await doc.getPage(n)).getTextContent();
  pageTexts.push(squash(tc.items.map((it) => it.str ?? '').join('')));
}
const findPage = (q) => { const i = pageTexts.findIndex((pt) => pt.includes(squash(q))); return i < 0 ? null : i + 1; };
for (const r of t.rows ?? []) {
  const page = findPage(r.quote);
  if (!page) throw new Error(`${r.code}: quote not in the PDF text: ${r.quote}`);
  const caption = t.caption ?? '1. melléklet';
  const cite = { reg: t.reg, page, para: `${caption} – ${r.code} sor`, quote: r.quote };
  const catPage = r.categoryQuote ? findPage(r.categoryQuote) : null;
  if (r.categoryQuote && !catPage) throw new Error(`${r.code}: category quote not in the PDF text`);
  const z = {
    name: r.category ? `${r.category} (${r.code})` : r.code,
    category: r.category ?? null,
    cite: catPage ? { reg: t.reg, page: catPage, para: caption, quote: r.categoryQuote } : cite,
    ...(r.heightIs ?? t.heightIs ? { heightIs: r.heightIs ?? t.heightIs } : {}),
  };
  if (r.notes) {
    z.notes = r.notes.map((nq) => {
      const np = findPage(nq);
      if (!np) throw new Error(`${r.code}: note not in the PDF text: ${nq}`);
      return { text: nq, cite: { reg: t.reg, page: np, para: `${caption} – jelmagyarázat`, quote: nq } };
    });
  }
  // A value is its printed text, or [text, number] when the cell lists cases (the number is the general one).
  for (const [f, v] of Object.entries(r.values)) {
    const [text, n] = Array.isArray(v) ? v : [v, f === 'buildingMode' ? null : num(v)];
    z[f] = { text, num: n, cite };
  }
  zoneTypes[r.code] = z;
}
let lastHead = null; // the last letter row seen ("continued")
for (let n = 1; n <= (t.rows ? 0 : doc.numPages); n++) {
  const page = await doc.getPage(n);
  const tc = await page.getTextContent();
  // A rotated page (Budapest XV.: landscape tables on /Rotate 90 pages): positions as seen on the
  // displayed page, y up, so rows and the column-letter line are horizontal as on an upright page.
  const vp = page.rotate ? page.getViewport({ scale: 1 }) : null;
  const pos = (tr) => {
    if (!vp || !tr) return [tr?.[4], tr?.[5]];
    const [, , , , x, y] = Util.transform(vp.transform, tr);
    return [x, vp.height - y];
  };
  const all = tc.items.map((it, i) => { const [x, y] = pos(it.transform); return { i, s: it.str ?? '', x, y, w: it.width, h: it.height }; });
  const pageText = squash(all.map((it) => it.s).join(''));
  // Non-empty items; a row number drawn as "1" + "." is one item (the "." is kept for the quote).
  const items = [];
  for (const it of all) {
    if (!it.s.trim()) continue;
    const prev = items[items.length - 1];
    if (it.s.trim() === '.' && prev && /^\d+$/.test(prev.s.trim()) && Math.abs(prev.y - it.y) < 1 && it.x - (prev.x + prev.w) < 1) {
      items[items.length - 1] = { ...prev, s: prev.s.trim() + '.', w: it.x + it.w - prev.x, also: [it.i] };
      continue;
    }
    items.push(it);
  }
  // Column-letter rows: single capital letters A, B, C, … on one line, left to right. A page can hold
  // several tables (of different widths); each row belongs to the nearest letter row above it.
  const singles = items.filter((it) => /^[A-Z]$/.test(it.s.trim()));
  const heads = [];
  for (const a of singles.filter((it) => it.s.trim() === 'A')) {
    const row = singles.filter((it) => Math.abs(it.y - a.y) < 2 && it.x >= a.x - 1).sort((p, q) => p.x - q.x);
    const seq = [];
    for (const it of row) if (it.s.trim() === letters[seq.length]) seq.push(it);
    if (seq.length >= 5 && !heads.some((h) => Math.abs(h.y - a.y) < 2)) heads.push({ y: a.y, letters: seq });
  }
  // "continued": a table that runs on from the previous page without repeating its letter row (Budapest
  // XVI.): the rows above this page's first letter row belong to the previous page's last table, whose
  // columns stand at the same x positions.
  const top = Math.max(...items.map((it) => it.y)) + 10;
  if (t.continued && lastHead && !heads.some((h) => h.y >= Math.max(...items.filter((it) => /^\d+\.$/.test(it.s.trim())).map((it) => it.y), -Infinity))) {
    heads.push({ y: top, letters: lastHead.letters.map((it) => ({ ...it, y: top })) });
  }
  if (!heads.length) continue;
  heads.sort((p, q) => q.y - p.y);
  lastHead = heads[heads.length - 1];
  // The zone codes stand left of column A, or in a lettered column of their own ("codeColumn").
  const codeCol = t.codeColumn ? letters.indexOf(t.codeColumn) : -1;
  const catRe = t.categoryRe ? new RegExp(t.categoryRe, 'u') : null;
  for (const h of heads) {
    const centres = h.letters.map((it) => it.x + it.w / 2);
    h.bounds = centres.map((c, k) => [k ? (centres[k - 1] + c) / 2 : c - (centres[1] - c) / 2,
      k < centres.length - 1 ? (c + centres[k + 1]) / 2 : c + (c - centres[k - 1]) / 2]);
    h.left = h.bounds[Math.max(codeCol, 0)][0];
    // Columns by table width ("columnsByCount": {"7": {...}}), else "columns".
    h.columns = t.columnsByCount?.[h.letters.length] ?? t.columns;
    // Category line: the table's heading ("2. Nagyvárosias, … lakóterület") closest above it, when the
    // config names a pattern.
    // (A heading can be split into items: "2." + "Nagyvárosias, …"; its items on one line are joined.)
    h.cat = null;
    if (catRe) {
      const above = items.filter((it) => it.y > h.y).sort((p, q) => p.y - q.y);
      for (const it of above) {
        const line = above.filter((o) => Math.abs(o.y - it.y) < 1).sort((p, q) => p.x - q.x).map((o) => o.s.trim()).join(' ');
        if (catRe.test(line) && pageText.includes(squash(line))) { h.cat = { s: line }; break; }
      }
    }
  }
  const headOf = (y) => heads.filter((h) => h.y > y + 2).sort((p, q) => p.y - q.y)[0];
  // A row number stands left of its own table's code column.
  const isRowNo = (it) => /^\d+(?:[a-z]?\.[a-z]?\.?|[a-z])$/.test(it.s.trim()) && !!headOf(it.y) && it.x + it.w <= headOf(it.y).left + 1;
  // A code wider than the letter's column half-width can start left of the first column's bound.
  const inCodeCol = (h) => (it) => !isRowNo(it) && (codeCol < 0 ? it.x + it.w <= h.left + 2
    : it.x + it.w / 2 < h.bounds[codeCol][1] && (codeCol === 0 || it.x + it.w / 2 >= h.bounds[codeCol][0]));
  // Rows: the table numbers its rows ("6.", "7.", …) left of the code column; a row reaches halfway to
  // its neighbours (never above its table's letter row). A row is a zone row when its code cell reads
  // as a zone code (a code split into several text items is joined) and its cells hold values, not
  // header words ("területe", "felett").
  const rowNo = items.filter((it) => isRowNo(it) && headOf(it.y)).sort((p, q) => q.y - p.y);
  const lastY = Math.min(...items.map((it) => it.y));
  rowNo.forEach((no, k) => {
    const h = headOf(no.y);
    const { bounds, cat } = h;
    const prevY = k && headOf(rowNo[k - 1].y) === h ? rowNo[k - 1].y : null;
    // The next row only if it is in the same table: else this row ends above the next table's heading.
    const nextY = k < rowNo.length - 1 && headOf(rowNo[k + 1].y) === h ? rowNo[k + 1].y : null;
    const step = nextY !== null ? no.y - nextY : prevY !== null ? prevY - no.y : 2 * Math.max(no.h, 8);
    const top = Math.min(prevY !== null ? (prevY + no.y) / 2 : no.y + step / 2, h.y - 2);
    const bottom = nextY !== null ? (no.y + nextY) / 2 : Math.max(no.y - Math.min(step / 2, 1.5 * Math.max(no.h, 8)), lastY - 1);
    const inRow = items.filter((it) => it.y <= top && it.y > bottom);
    const codeItems = inRow.filter(inCodeCol(h)).sort((p, q) => p.i - q.i); // stream order: a code can wrap
    const code = dash(codeItems.map((it) => it.s.trim()).join(''));
    if (!codeRe.test(code)) { if (process.env.DEBUG_ROWS && code) console.warn(`p${n} row ${no.s}: not a code: ${code}`); return; }
    const cells = {};
    for (const it of inRow) {
      if (it === no || codeItems.includes(it)) continue;
      const cx = it.x + it.w / 2;
      const col = bounds.findIndex(([a, b]) => cx >= a && cx < b);
      if (col < 0) continue;
      (cells[letters[col]] ??= []).push(it);
    }
    // A row holding several sub-rows of values under one code (merged cells) cannot be read safely.
    const lines = (L) => new Set((cells[L] ?? []).map((it) => Math.round(it.y))).size;
    if (Object.keys(cells).filter((L) => lines(L) >= 3).length >= 3) {
      console.warn(`p${n} ${code}: several value lines in one row, skipped`);
      return;
    }
    // Cell text, top to bottom and left to right. Footnote marks (superscripts: much smaller text) are
    // dropped; pieces of one value that touch ("8" "5") are joined without a space.
    const hMed = [...inRow.map((it) => it.h)].sort((p, q) => p - q)[Math.floor(inRow.length / 2)] || 0;
    const cellText = (L) => {
      // (A unit or abbreviation in parentheses, like "(Ém)", is the header's last line, not a value.)
      const its = (cells[L] ?? []).filter((it) => !(it.h < 0.75 * hMed && /^\d+\)?$/.test(it.s.trim())) && !/^\([A-Za-zÉé%]+\)$/.test(it.s.trim()))
        .sort((p, q) => (Math.abs(p.y - q.y) > 2 ? q.y - p.y : p.x - q.x));
      let out = '';
      its.forEach((it, m) => {
        const prev = its[m - 1];
        const touch = prev && Math.abs(prev.y - it.y) <= 2 && it.x - (prev.x + prev.w) < 0.8;
        out += (m && !touch ? ' ' : '') + it.s.trim();
      });
      return out.replace(/\s+/g, ' ').trim();
    };
    // A header row: words in several cells (one cell may say "1. melléklet szerint" in a value row).
    if (Object.keys(cells).filter((L) => /[a-záéíóöőúüű]{4,}/i.test(cellText(L).replace(/kialakult|meglévő/gi, ""))).length >= 3) return;
    // Quote: the run of consecutive text items from the row number on that stays in this row.
    const inSet = new Set(inRow.flatMap((it) => [it.i, ...(it.also ?? [])]));
    let j = no.i;
    while (j + 1 < all.length && (inSet.has(j + 1) || !all[j + 1].s.trim())) j++;
    const quote = all.slice(no.i, j + 1).map((it) => it.s).join(' ').replace(/\s+/g, ' ').trim();
    if (!pageText.includes(squash(quote))) throw new Error(`p${n} ${code}: quote not in page text`);
    if (!squash(quote).includes(squash(codeItems.map((it) => it.s).join('')))) { console.warn(`p${n} ${code}: code not read whole, row skipped (${quote})`); return; }
    const caption = t.caption ?? '1. melléklet';
    const cite = { reg: t.reg, page: n, para: `${caption} – ${code} sor`, quote };
    // Land-use family names from the config ("families": {"Lke": "Kertvárosias lakóterület"}), longest prefix.
    const fam = Object.keys(t.families ?? {}).filter((f) => code === f || code.startsWith(f + '-') || code.startsWith(f + '/'))
      .sort((p, q) => q.length - p.length)[0];
    const catName = cat ? cat.s.trim().replace(/^\d+\.\s*/, '') : fam ? t.families[fam] : null;
    const z = {
      name: catName ? `${catName} (${code})` : code,
      category: catName,
      cite: cat ? { reg: t.reg, page: n, para: caption, quote: cat.s.trim() } : cite,
      ...(t.heightIs ? { heightIs: t.heightIs } : {}),
    };
    const values = {};
    for (const [L, field] of Object.entries(h.columns)) {
      const v = cellText(L);
      if (!v) continue;
      values[L] = v;
      z[field] = { text: v, num: field === 'buildingMode' ? null : num(v), cite };
    }
    report.push([n, code, values]);
    if (zoneTypes[code]) console.warn(`duplicate zone code ${code} (page ${n}), keeping the first`);
    else zoneTypes[code] = z;
  });
}
if (process.env.DEBUG_ROWS) for (const r of report) console.log(JSON.stringify(r));
// On the plan without a row in the table (streets, squares): the text applies. [name, quote where the
// regulation's text (public/docs/<main reg>.pdf, from ingest-kesz.mjs) defines the zone], verified.
let mainPages = null;
for (const [code, extra] of Object.entries(t.extraZones ?? {})) {
  const [name, quote] = Array.isArray(extra) ? extra : [extra, null];
  let cite;
  if (quote) {
    if (!mainPages) {
      const md = await getDocument({ data: new Uint8Array(readFileSync(`public/docs/${mainReg}.pdf`)), verbosity: 0 }).promise;
      mainPages = [];
      for (let n = 1; n <= md.numPages; n++) {
        const tc = await (await md.getPage(n)).getTextContent();
        mainPages.push(squash(tc.items.map((it) => it.str ?? '').join('')));
      }
    }
    const i = mainPages.findIndex((pt) => pt.includes(squash(quote)));
    if (i < 0) throw new Error(`${code}: quote not in ${mainReg}.pdf: ${quote}`);
    cite = { reg: mainReg, page: i + 1, para: 'szöveg', quote };
  }
  zoneTypes[code] ??= { name, category: name, noTable: true, ...(cite ? { cite } : {}) };
}

writeFileSync(`public/data/zone-types-${key}.json`, JSON.stringify(zoneTypes, null, 1) + '\n');
const regsPath = 'public/data/regulations.json';
const regs = JSON.parse(readFileSync(regsPath, 'utf8'));
regs.regulations[t.reg] = {
  title: t.title,
  decree: cfg.regulation.decree,
  status: 'linked',
  pdf: `docs/${t.reg}.pdf`,
  officialUrl: url,
  effectiveFrom: regs.regulations[mainReg]?.effectiveFrom ?? null,
  retrievedAt: new Date().toISOString().slice(0, 10),
  sha256: createHash('sha256').update(bytes).digest('hex'),
  annexes: [],
};
if (!regs.regulations[mainReg]) throw new Error(`${mainReg} not in regulations.json: run scripts/ingest-kesz.mjs ${key} first`);
regs.regulations[mainReg].zoneTypes = `zone-types-${key}.json`;
writeFileSync(regsPath, JSON.stringify(regs, null, 2) + '\n');
console.log(`${t.reg}: ${Object.keys(zoneTypes).length} zones from ${doc.numPages} pages, all row quotes found in the PDF text`);
