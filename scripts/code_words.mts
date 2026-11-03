// Which table codes the zone card can say in plain Hungarian (src/codes.ts), and which it still shows bare.
//
//   node --experimental-strip-types scripts/code_words.mts            every area
//   node --experimental-strip-types scripts/code_words.mts xiii pecs  some areas
//
// For each area: building modes the card shows only as a code, zones whose table gives no name and whose
// category the card cannot name, and codes inside other values that have no meaning yet. An area with
// nothing to report says so. When something is listed, find the code in that regulation's table legend
// (or definitions) and add it to src/codes.ts for that area; never guess a meaning from another plan.
import { readdirSync, readFileSync } from 'node:fs';
import { categoryName, modeWords, nameIsCode, valueWords } from '../src/codes.ts';

const dir = new URL('../public/data/', import.meta.url);
const VALUE_KEYS = ['minPlotM2', 'maxCoveragePct', 'minHeightM', 'maxHeightM', 'minGreenPct', 'maxUndergroundPct', 'maxFar',
  'maxFarParking', 'minPlotWidthM', 'minBuildablePlotM2', 'minBuildablePlotWidthM', 'maxHeightResidentialM', 'maxCorniceM', 'minCorniceM'];
const EMPTY = /^[-–‐—]*$/;
const WORDS = /[a-záéíóöőúüű]{4,}/;
const shape = (t: string) => t.replace(/\d+(?:[ ,.]\d+)*/g, 'N');

const want = process.argv.slice(2);
const files = readdirSync(dir).filter((f) => f.startsWith('zone-types-') && f.endsWith('.json'))
  .filter((f) => !want.length || want.includes(f.slice(11, -5))).sort();
let open = 0;
for (const f of files) {
  const area = f.slice(11, -5);
  const zones: Record<string, any> = JSON.parse(readFileSync(new URL(f, dir), 'utf8'));
  const modes = new Map<string, number>();
  const values = new Map<string, number>();
  const unnamed: string[] = [];
  let read = 0, reading = 0;
  for (const [code, z] of Object.entries(zones)) {
    const bm: string | undefined = z.buildingMode?.text;
    if (bm !== undefined && !EMPTY.test(bm.trim())) {
      const m = modeWords(area, bm);
      if (m) { read++; if (m.reading) reading++; }
      else if (WORDS.test(bm)) read++; // printed in words already
      else modes.set(bm, (modes.get(bm) ?? 0) + 1);
    }
    for (const k of VALUE_KEYS) {
      const t: string | undefined = z[k]?.text;
      if (!t || !/[A-Za-zÁ-ű§”]/.test(t) || WORDS.test(t)) continue;
      const v = valueWords(area, t);
      if (!v.main && !v.notes.length) values.set(shape(t), (values.get(shape(t)) ?? 0) + 1);
    }
    if (nameIsCode(z.name) && !(z.category && !nameIsCode(z.category)) && !categoryName(area, code)) unnamed.push(code);
  }
  const n = modes.size + values.size + unnamed.length;
  open += modes.size + unnamed.length;
  console.log(`== ${area}: ${read} building modes readable in words${reading ? ` (${reading} by our reading of an undefined code)` : ''}`
    + (n ? '' : '; nothing left as a bare code'));
  for (const [t, c] of modes) console.log(`   building mode shown as printed: "${t}" (${c} zones)`);
  if (unnamed.length) console.log(`   no name and no category for ${unnamed.length} zones: ${unnamed.slice(0, 8).join(', ')}${unnamed.length > 8 ? ', …' : ''}`);
  for (const [t, c] of [...values].sort((a, b) => b[1] - a[1]).slice(0, 12)) console.log(`   code in a value without a meaning: "${t}" (${c})`);
  if (values.size > 12) console.log(`   … and ${values.size - 12} more value shapes`);
}
console.log(`\n${open} building-mode codes or unnamed zones left bare in ${files.length} areas.`);
