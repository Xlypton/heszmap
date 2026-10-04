// Dev tool: generates a clearly-labelled DEMO regulation PDF plus zone-types.json whose
// every value carries a citation (paragraph + page + exact quote) into that PDF.
// Usage: node scripts/make-demo-doc.mjs   (needs Playwright with Chromium installed)
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(`${execSync('npm root -g').toString().trim()}/playwright`); }

const REG = 'demo-xi';
const num = (v) => v.toLocaleString('hu-HU');

const zones = [
  { code: 'Vi1', name: 'Intézményi terület – nagyvárosias', category: 'vegyes', buildingMode: 'zártsorú', maxCoveragePct: 65, maxFar: 3, maxHeightM: 23, minGreenPct: 15, minPlotM2: 500 },
  { code: 'L1', name: 'Nagyvárosias lakóterület – zártsorú', category: 'lakó', buildingMode: 'zártsorú', maxCoveragePct: 60, maxFar: 2.5, maxHeightM: 20, minGreenPct: 20, minPlotM2: 400 },
  { code: 'L3', name: 'Kertvárosias lakóterület', category: 'lakó', buildingMode: 'oldalhatáron álló', maxCoveragePct: 30, maxFar: 0.6, maxHeightM: 7.5, minGreenPct: 50, minPlotM2: 700 },
  { code: 'Z-KP', name: 'Közpark', category: 'zöld', buildingMode: 'szabadonálló', maxCoveragePct: 2, maxFar: 0.02, maxHeightM: 4.5, minGreenPct: 70, minPlotM2: null },
];

const sentences = {
  buildingMode: (z) => `A beépítési mód: ${z.buildingMode}.`,
  maxCoveragePct: (z) => `A legnagyobb beépítettség mértéke: ${num(z.maxCoveragePct)}%.`,
  maxFar: (z) => `A legnagyobb szintterületi mutató: ${num(z.maxFar)}.`,
  maxHeightM: (z) => `A legnagyobb épületmagasság: ${num(z.maxHeightM)} m.`,
  minGreenPct: (z) => `A legkisebb zöldfelületi arány: ${num(z.minGreenPct)}%.`,
  minPlotM2: (z) => (z.minPlotM2 === null ? null : `A kialakítható legkisebb telekterület: ${num(z.minPlotM2)} m2.`),
};

const zoneTypes = {};
let html = `<!doctype html><meta charset="utf-8"><style>
  body { font-family: 'DejaVu Serif', serif; font-size: 12pt; line-height: 1.5; margin: 0; }
  .page { page-break-after: always; padding: 0 8mm; }
  .banner { border: 2px solid #b00; color: #b00; padding: 6px 10px; font-weight: bold; }
  h1 { font-size: 16pt; } h2 { font-size: 13pt; margin-top: 18pt; }
</style>
<div class="page">
  <p class="banner">DEMO DOKUMENTUM – NEM VALÓS JOGSZABÁLY. A HÉSZ térkép prototípus teszteléséhez készült.</p>
  <h1>Budapest Főváros XI. kerület – DEMO kerületi építési szabályzat</h1>
  <h2>1. § Általános rendelkezések</h2>
  <p>(1) E rendelet hatálya a szabályozási terven lehatárolt területre terjed ki.</p>
  <p>(2) Az építési övezetek határértékeit a 10–13. § tartalmazza.</p>
</div>`;

zones.forEach((z, i) => {
  const para = 10 + i;
  const page = 2 + i;
  const t = { name: z.name, category: z.category, cite: { reg: REG, page, para: `${para}. §`, quote: `${z.code} jelű építési övezet` } };
  let n = 0;
  let body = '';
  for (const [key, fn] of Object.entries(sentences)) {
    const quote = fn(z);
    if (quote === null) { t[key] = { value: null }; continue; }
    n += 1;
    body += `<p>(${n}) ${quote}</p>`;
    t[key] = { value: z[key], cite: { reg: REG, page, para: `${para}. § (${n})`, quote } };
  }
  zoneTypes[z.code] = t;
  html += `<div class="page"><h2>${para}. § ${z.code} jelű építési övezet – ${z.name}</h2>${body}</div>`;
});

const browser = await playwright.chromium.launch();
const pg = await browser.newPage();
await pg.setContent(html);
await pg.pdf({ path: 'public/docs/demo-xi-kesz.pdf', format: 'A4', margin: { top: '20mm', bottom: '20mm' } });
await browser.close();

writeFileSync('public/data/zone-types.json', JSON.stringify(zoneTypes, null, 2) + '\n');
console.log('wrote public/docs/demo-xi-kesz.pdf and public/data/zone-types.json');
