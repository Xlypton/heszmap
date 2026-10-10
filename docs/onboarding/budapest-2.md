# Onboarding batch budapest-2: Budapest IX–XVI (triage, 2026-10-04)

Sources: njt.jog.gov.hu search (municipal decrees in force; njt ids end in `5Y<issuer>`: IX 258 … XVI 265,
Főváros 4191), each decree's consolidated text (all lazily loaded blocks fetched, see below) and its annex
files, probed with `plan_probe.py`.

City-wide, applies everywhere alongside the district rules: **FRSZ**, Budapest főváros rendezési szabályzata,
3/2026. (II. 12.) Főv. Kgy. rendelet (`2026-3-SP-5Y4191`, in force from 2026-02-14; replaces 5/2015. (II. 16.),
which older district texts still cite). Duna-parti építési szabályzatok (DÉSZ, Főv. Kgy.) cover the Danube
banks and are excluded from the district KÉSZ: IX → 50/2018. (XII. 10.) (`2018-50-SP-5Y4191`, V/IX/XXI),
XI → 21/2024. (V. 8.) (`2024-21-SP-5Y4191`, I/II/XI), XIII → 36/2018. (X. 30.) (`2018-36-SP-5Y4191`).
XIV: the Városliget is under the Főv. Kgy. Városligeti építési szabályzat (VÉSZ), not the district KÉSZ.

**njt pitfall (fixed in `ingest-kesz.mjs`):** long decrees arrive with part of their text not loaded; njt's
page script fetches each block from `/ajax/njtGetBlock.json` on scroll. Without loading them the XIII KÉSZ
stops at § 73 and has no annexes; X misses 2. melléklet tables 9–36. `ingest-kesz.mjs` now loads every block.

| Dist. | Regulation(s) in force (njt id) | Coverage | Zone limits table | Plan on njt | Status |
|---|---|---|---|---|---|
| X Kőbánya | KÉSZ 16/2020. (XI. 26.) `2020-16-SP-5Y259` (+ two 2003/2006 partial KÉSZ still listed as in force, last changed 2006/2016, superseded in practice) | whole district | in text, 2. melléklet (36 tables) | 13 PNG sheets (`/picture/`, 200/300 dpi, 1:2000), + 4 védelmi sheets | **done** (11/13 sheets) |
| XIII | KÉSZ 14/2021. (VI. 29.) `2021-14-SP-5Y262` | whole district except DÉSZ area | in text, 3. melléklet (≈20 tables) | 12 colour raster PDFs (one JPEG, 10807×8091 px, 300 dpi, 1:2000), sheet grid rotated | **done** (11/12 sheets; heights on a separate map) |
| XIV Zugló | Zugló építési szabályzata 11/2021. (III. 26.) `2021-11-SP-5Y263` | whole district except VÉSZ | in text, 3. melléklet | one 38-page PDF (39 MB), vector with a text layer (zone codes readable), raster basemap | **done** (19/19 sheets) |
| XV | KÉSZ 17/2018. (VI. 26.) `2018-17-SP-5Y264` | whole district | **annex PDF** (2. melléklet), not in text | 1. melléklet: one 202 MB PDF, 20 sheets 1:2000 | **done**, plan for 10/20 sheets |
| XVI | KÉSZ 21/2018. (VII. 6.) `2018-21-SP-5Y265` | whole district | **annex PDF** (2. melléklet), not in text | 1. melléklet: 23-page PDF (51 MB), raster pages, no text layer | **done**, plan for 17/22 sheets |
| XI Újbuda | 11 partial KÉSZ, together the whole district: 30/2016 `2016-30`, 11/2017 `2017-11`, 8/2017 `2017-8`, 16/2018 `2018-16`, 25/2018 `2018-25`, 26/2018 `2018-26`, 43/2018 `2018-43`, 30/2020 `2020-30`, 1/2021 `2021-1`, 36/2021 `2021-36`, 41/2023 `2023-41` (all `-SP-5Y260`) | each by bounding streets | mostly in annex PDFs (2. melléklet); only 2017-8 has tables in text | vector PDFs with text layers (zone codes readable), 1–9 files each | **partial**: KÉSZ 2 (30/2020.) done; 10 more |
| XII Hegyvidék | KVSZ 14/2005. (VIII. 10.) `2005-14-SP-5Y261` (rest of district) + KÉSZ 1/2018 `2018-1`, 23/2018 `2018-23`, 26/2020 Észak-Hegyvidék `2020-26`, 18/2021 Alkotás u. `2021-18`, 35/2021 Kissvábhegy `2021-35`, 36/2021 Dél-Hegyvidék `2021-36` | KVSZ for what the KÉSZ do not cover | in text (all) | KVSZ: **no plan on njt** (only a small image); KÉSZ: A3 multi-page PDFs (37–78 p.), vector without text, or single vector sheets | not started; KVSZ plan not on njt |
| IX Ferencváros | KÉSZ 20/2026. (VII. 16.) `2026-20` (Vámház krt–Üllői út–Déli körvasút, replaces Belső-/Középső-Ferencváros, Malmok, Vágóhíd u. KÉSZ), KÉSZ 22/2017 UNIX `2017-22`, 1/2019 Kvassay `2019-1`, + 10 older KSZT/KÉSZ 2002–2012 (`2002-15`, `2002-19`, `2002-21`, `2003-34`, `2003-37`, `2003-41`, `2004-38`, `2005-17`, `2010-20`, `2012-20`; all `-SP-5Y258`) | partial; Külső-Ferencváros residential areas (e.g. Gloriett-like blocks) need checking | in text for the KÉSZ; old KSZT partly none | 2026 KÉSZ: 8 PNG sheets + overview; old KSZT: small A4/A3 scans (poor) | **partial**: 20/2026. KÉSZ done (7/8 sheets); older KSZT not |

Order of work (population, then feasibility): XI is the largest but needs per-area regulation choice in
the app and PDF tables, so X and XIII (district-wide, tables in text, plans readable) go first, then XIV.

## Progress

### IX. Ferencváros, inner area (20/2026. KÉSZ) — done (2026-10-10)

- Text: KÉSZ 20/2026. (VII. 16.) for the area Vámház körút – Kálvin tér – Üllői út – Déli körvasút –
  DÉSZ area, `public/docs/ix-kesz.pdf` (njt, hatályos 2026.08.16.). It replaced the Belső-Ferencváros,
  Középső-Ferencváros, Malmok and Vágóhíd utca KÉSZ.
- Zone limits: 4. melléklet, HTML tables on njt: **113 zones** (BF/, KF/, VH/, IT/ prefixes by
  neighbourhood), every row cited by its own text; "K" (kialakult) values have no number. The 3. melléklet
  table of allowed uses (also with a "jele" column) is skipped (no limit columns).
- Area: the KÉSZ covers only part of the district, so its tiles, labels and `plan.area` are clipped to a
  polygon: the IX. boundary cut by the OSM centre lines of Üllői út and the railway lines (`plan.clip`);
  the Danube-bank strip of the DÉSZ is not cut out. Note: outside this area the app still falls back to
  this regulation for the district (src/data.ts picks `withTypes[0]` when no area holds the point); the
  zone guesses there are empty because no labels are near.
- Plan: 1. melléklet, 8 PNG sheets (200 dpi, 1:2000), OCR'd at 200 dpi, fitted and tiled at 150 dpi.
- Georeference: street names (final residual median 1.7–4.7 m), then OSM buildings on the plan's grey
  building outlines: per-sheet median 0.82–2.08 m (median 1.48 m). Overlay checked (Ráday utca – Ferenc
  tér): within ~1–2 m. **7 of 8 sheets** (sheet 5 of the series: no street names read).
- Zone labels: 268 (88 codes, all in the zone table). Zones / plots: not traced.
- Tiles: `public/pmtiles/ix/` (PMTiles, z13–18, 634 tiles, 7 MB).

### X. Kőbánya — done (2026-10-06)

- Text: KÉSZ 16/2020. (XI. 26.), `public/docs/x-kesz.pdf` (njt, hatályos 2026.07.10.; one lazily loaded
  block filled in — without it 2. melléklet tables 9–36 are missing).
- Zone limits: 2. melléklet, HTML tables in the njt text: **441 zones**, every row cited by its own text
  (verified in the PDF). Footnote rows inside the tables ("* BP/1701/… OTÉK eltérési engedély alapján") and
  the marks after a table ("ᵖ párkánymagasság") are kept as notes of that table; marked values keep their
  mark ("15,0ᵖ") and carry no number. Height = épületmagasság unless marked ᵖ.
- Plan: 1. melléklet 1.1–1.13, 13 PNG sheets (`/picture/` on njt), 1:2000, 300 dpi (7 sheets) and 200 dpi
  (6 sheets, re-issued 2026-06-19); OCR'd at full size, then resampled to 150 dpi for fitting and tiling
  (`plan.image_max_dpi`; at full size the 13 sheets do not fit in memory together).
- Georeference: street names (6–211 per sheet, median 1.4–2.2 m), then OSM building outlines on the plan's
  grey building/plot lines (`styles.building_line`): per-sheet median 0.81–1.21 m, 43–58% of outline points
  within 1 m; final street-name residual median 1.5–3.1 m. Overlay of OSM buildings on the z17 tiles checked
  (Kőbánya-Újhegy, Sörgyár utca): within ~1 m. **11 of 13 sheets**; sheets 12 and 13 of the series (south-east,
  Újköztemető / Keresztúri út edge) are left out (few street names; scale fit off, buildings median 10.6 m).
- Zone labels: 1180 (387 codes, all in the zone table). Zones / plots: not traced.
- Tiles: `public/pmtiles/x/` (PMTiles, packed on the main branch).

### XIV. Zugló — done (2026-10-07)

- Text: Zugló építési szabályzata 11/2021. (III. 26.), `public/docs/xiv-kesz.pdf` (njt, hatályos
  2025.06.28.). The Városliget (VÉSZ, Főv. Kgy.) is outside its scope.
- Zone limits: 3. melléklet, one HTML table on njt with category rows inside it ("6 | Nagyvárosias, …
  (Ln-2)"): **193 zones** (Ln, Lk, Lke, Vt-M, Vi, Gksz, Gip-E, K-…, Zkp, Kt-…, KÖu, KÖk), each row cited by its
  own text. The engedményes (bonus) floor-area columns are not mapped (no field for them); the base values are.
- Plan: 1. melléklet, one 38-page PDF; pages 1–19 are the Szabályozási terv sheets (pages 20–38 another map
  series), vector with a full text layer (zone codes and street names read exactly, no OCR), rendered at
  150 dpi; map frame set per sheet (legend column on the right).
- Georeference: street names from the text layer (4–139 per sheet; final residual median 1.1–2.7 m), then
  OSM buildings on the plan's grey building outlines: per-sheet median 0.55–1.38 m (median 0.77 m), 39–73%
  within 1 m. **All 19 sheets.** Overlays checked (Kassai tér / Nagy Lajos király útja; Paskál utca area):
  within ~1 m.
- Zone labels: 2060 (182 codes, all in the zone table). Zones / plots: not traced.
- Tiles: `public/pmtiles/xiv/` (PMTiles, packed on the main branch).

### XI. Újbuda, KÉSZ 2 (30/2020.) — done, 1 of 11 area KÉSZ (2026-10-10)

- Text: 30/2020. (IX. 25.) KÉSZ for Duna – I./XI. határ – Budaörsi út – Ferencváros–Kelenföld vasútvonal
  (Gellérthegy, Lágymányos, Kelenföld north of the railway), `public/docs/xi2-kesz.pdf` (njt). Key `xi2`.
- Zone limits: 2. melléklet PDF (`xi2-kesz-m2.pdf`, 18 pages). Its tables have no column letters, so the
  rows were read by a pattern (zone code + 11 cells in a fixed order: plot area, width, mode, coverage
  above/below ground, height min/max with "ém:"/"pm:", FAR total/general/parking, green) and written into
  the config as `zoneTablePdf.rows`; `ingest-pdf-zones.mjs` then verified every row's quote in the PDF.
  **97 zones**; 5 rows whose cells did not fit the pattern are left out (Lk-2-XI-01, Vt-V-XI-04,
  K-Hon-XI-01/02, Zvp-XI-S-01). Heights given as "pm:" (párkánymagasság) carry no number. The szmá column
  (general share of the FAR) is not mapped.
- Plan: 1a. melléklet, one vector sheet (900×594 mm, 1:4000) with a full text layer, rendered at 200 dpi.
- Georeference: 376/396 street names on their OSM street (median 1.7 m), OSM buildings on the plan's grey
  building outlines median 1.19 m; overlay checked at Móricz Zsigmond körtér: within ~1 m.
- Area (`plan.clip`): traced from the plan's own pink dashed boundary line, the district boundary and the OSM
  railway lines (flood fill from a point inside, then inlets left by same-coloured zone fills closed); 50 of the
  276 codes printed on the sheet lie outside it (the neighbouring KÉSZ areas, shown for information) and are
  dropped. The strip between Budaörsi út and the XII. district boundary is outside (it belongs to another KÉSZ).
- Zone labels: 226 (92 codes, all in the zone table). Tiles: `public/pmtiles/xi2/` (PMTiles, z13–18, 704 tiles).
- Caveat for the app: XI. now has one regulation with an area; outside it the app falls back to this
  regulation for the whole district (same as IX.).

### XIII. kerület — done (2026-10-07)

- Text: KÉSZ 14/2021. (VI. 29.), `public/docs/xiii-kesz.pdf` (njt, hatályos 2026.08.01.; the njt page
  arrives in 7 parts, 6 lazily loaded blocks filled in — without them the text stops at § 73 and has no annexes).
  The Duna-part (DÉSZ, Főv. Kgy. 36/2018.) is outside its scope.
- Zone limits: 3. melléklet, 20 HTML tables on njt with a three-row header: **256 zones**, columns mapped by
  their full header (`headerFromTop` + `fieldRules`), every row cited by its own text. Legend rows inside the
  tables ("KH/L …", "Z - általános zártsorú …") are kept as notes. Cells with several cases ("80 / 100 F”",
  "4,5 / 5,0 S") are kept as printed, without a number. **Heights are not in the table**: the KÉSZ sets them on a
  separate map (4. melléklet SZ-M4, linked), so no height is shown.
- Plan: 1. melléklet SZ-M1, 12 sheets (one 10807×8091 JPEG each, 1:2000), rendered at 200 dpi, OCR'd; zone
  codes re-read from their blue lettering (`plan_zone_labels`, `zone_labels.zlabels`).
- Georeference: street names (9–52 per sheet; final residual median 1.1–4.0 m), then OSM buildings on the
  plan's black building outlines: per-sheet median 1.21–2.53 m (median 2.08 m), 24–43% within 1 m. Overlay
  checked (Róbert Károly körút / Hajdú utca): OSM outlines within ~2–3 m of the plan's buildings — less
  exact than X./XIV.; the plan's base map seems to differ slightly from OSM. **11 of 12 sheets**; sheet 12 of
  the series refused (buildings median 3.6 m).
- Zone labels: 575 (194 codes, all in the zone table); fewer than on the other plans (small blue codes,
  many not read). Zones / plots: not traced.
- Tiles: `public/pmtiles/xiii/` (PMTiles, z13–18, 1586 tiles, 20 MB).

### XV. Rákospalota, Pestújhely, Újpalota — done, plan for half of the district (2026-10-07)

- Text: KÉSZ 17/2018. (VI. 26.), `public/docs/xv-kesz.pdf` (njt, hatályos 2024.01.15.).
- Zone limits: 2. melléklet, a separate official PDF (`public/docs/xv-kesz-m2.pdf`, landscape tables on
  rotated pages, column letters printed out of order "A B C D F G H I E J …"): **257 zones** read with
  `ingest-pdf-zones.mjs` (new options `letterOrder`, rotated pages), every row cited by its own text run.
  Columns: B mode, C/D plot area/width, F/G coverage above/below ground, H/I FAR, E green, J height
  (épületmagasság). Values with conditions ("35 § 50") kept as printed, without a number.
- Plan: 1. melléklet T-SZ, 20 scanned sheets (917×760 mm, one 202 MB PDF), rendered at 200 dpi and OCR'd.
- Georeference: street names, then OSM buildings on the plan's grey building outlines: per-sheet median
  1.06–1.43 m (median 1.34 m), final street-name residual 0.7–1.8 m; overlay checked (Gábor Áron utca /
  Kozák tér): within ~1 m. **10 of 20 sheets.** The streets of Rákospalota run diagonally on the sheets
  and the OCR reads too few of the rotated street names on the other ten (sheets 1, 2, 4, 7, 8, 11, 12, 16,
  17, 20 of the series; 7 had names but its buildings check failed at 5.5 m) → no tiles or labels there. Fix to try: OCR the
  sheets rotated by 45°, or register them to their fitted neighbours by image correlation.
- Zone labels: 1060 (213 codes, all in the zone table). Zones / plots: not traced.
- Tiles: `public/pmtiles/xv/` (PMTiles, z13–18, 2144 tiles, 22 MB).

### XVI. kerület — done, plan for 17 of 22 sheets (2026-10-10)

- Text: KÉSZ 21/2018. (VII. 6.), `public/docs/xvi-kesz.pdf` (njt, hatályos 2026.06.18.).
- Zone limits: 2. melléklet, separate official PDF (`public/docs/xvi-kesz-2m.pdf`): **72 zones** read with
  `ingest-pdf-zones.mjs` (columns A–I: mode, plot area, coverage, underground, épületmagasság, green, FAR
  general/parking); tables that run on over a page break without repeating the column letters are read
  with the new `continued` option. Not read: Lk-2/XVI/ÓM (garbled code cell) and Lke-1/XVI/I.
- Plan: 1. melléklet, 23-page PDF: page 1 is the legend (left out), pages 2–23 the 22 sheets (raster,
  841×594 mm, 1:2000), rendered at 200 dpi and OCR'd; frame below the title strip.
- Georeference: street names (final residual median 0.6–1.7 m), then OSM buildings on the plan's grey
  building outlines: per-sheet median 0.60–0.85 m (median 0.71 m), 56–71% within 1 m. **17 of 22 sheets**;
  sheets 7, 12, 17, 21, 22 of the series have no readable street names and no unambiguous neighbour
  position (mostly the outer, forest and industrial edges).
- Zone labels: 960 (63 codes, all in the zone table). Zones / plots: not traced.
- Tiles: `public/pmtiles/xvi/` (PMTiles, z13–18, 3794 tiles, 33 MB).

### Not onboarded (2026-10-07)

- **XI. Újbuda, the other ten area KÉSZ** (largest district of the batch) — not done: eleven area KÉSZ that together cover the district,
  each with its own vector plan (text layer, zone codes readable) and mostly a PDF zone table (2. melléklet).
  Each needs its own regulation entry, zone table, georeference and an area polygon (`plan.clip`) built
  from its bounding streets so the app picks the right one; about a day of work at the pace above. The
  plan PDFs are vector with text, so no OCR is needed; `ingest-pdf-zones.mjs` should read most tables.
- **XII. Hegyvidék** — not started: the KVSZ 14/2005. (rest of the district) has **no plan on njt**
  (hegyvidek.hu would be the source); the six area KÉSZ have A3 multi-page plans (17–78 pages, vector
  without text) and HTML zone tables on njt.
- **IX. Ferencváros, outside the 20/2026. KÉSZ** — not onboarded: ten older KSZT/KÉSZ (2002–2019) with
  small A4/A3 scanned plans; the app falls back to nothing there (the IX. KÉSZ entry is clipped to its
  own area).
- **XIII. / IX. / XI. Danube banks** — under the Főv. Kgy. Duna-parti építési szabályzatok (DÉSZ),
  city-level, not onboarded.
