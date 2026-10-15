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
| XI Újbuda | 11 partial KÉSZ, together the whole district: 30/2016 `2016-30`, 11/2017 `2017-11`, 8/2017 `2017-8`, 16/2018 `2018-16`, 25/2018 `2018-25`, 26/2018 `2018-26`, 43/2018 `2018-43`, 30/2020 `2020-30`, 1/2021 `2021-1`, 36/2021 `2021-36`, 41/2023 `2023-41` (all `-SP-5Y260`) | each by bounding streets | mostly in annex PDFs (2. melléklet); only 2017-8 has tables in text | vector PDFs with text layers (zone codes readable), 1–9 files each | **done**: all 11 area KÉSZ (KÉSZ 1, 2, 3, 5, 7, 8, 9, 25/2018., Sasad Liget 8/2017., Lágymányosi-öböl 30/2016., Tóváros 41/2023.) |
| XII Hegyvidék | KVSZ 14/2005. (VIII. 10.) `2005-14-SP-5Y261` (rest of district) + KÉSZ 1/2018 `2018-1`, 23/2018 `2018-23`, 26/2020 Észak-Hegyvidék `2020-26`, 18/2021 Alkotás u. `2021-18`, 35/2021 Kissvábhegy `2021-35`, 36/2021 Dél-Hegyvidék `2021-36` | KVSZ for what the KÉSZ do not cover | in text (all) | KVSZ: **no plan on njt** (only a small image); KÉSZ: A3 multi-page PDFs (37–78 p.), vector without text, or single vector sheets | not started; KVSZ plan not on njt |
| IX Ferencváros | KÉSZ 20/2026. (VII. 16.) `2026-20` (Vámház krt–Üllői út–Déli körvasút, replaces Belső-/Középső-Ferencváros, Malmok, Vágóhíd u. KÉSZ), KÉSZ 22/2017 UNIX `2017-22`, 1/2019 Kvassay `2019-1` (both live), + 10 older KSZT/KÉSZ 2002–2012 (`2002-15`, `2002-19`, `2002-21`, `2003-34`, `2003-37`, `2003-41`, `2004-38`, `2005-17`, `2010-20`, `2012-20`; all `-SP-5Y258`) | partial; Külső-Ferencváros residential areas (e.g. Gloriett-like blocks) need checking | in text for the KÉSZ; old KSZT partly none | 2026 KÉSZ: 8 PNG sheets + overview; old KSZT: small A4/A3 scans (poor) | **partial**: 20/2026. KÉSZ done (7/8 sheets), Kvassay and UNIX KÉSZ done; older KSZT not |

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

### XI. Újbuda, KÉSZ 1 (11/2017.) — done, 2 of 11 area KÉSZ (2026-10-13)

- Text: 11/2017. (V. 3.) KÉSZ for Ferencváros–Kelenföld vasútvonal – Budaörsi út – Kőérberki út – Egér út –
  Andor utca – Galvani út – Duna (Kelenföld, Albertfalva north, Lágymányos south), `public/docs/xi1-kesz.pdf`
  (njt, `2017-11-SP-5Y260`). Key `xi1`.
- Zone limits: 1c. melléklet PDF (`xi1-kesz-m1c.pdf`), read by `scripts/pdf_zone_rows.py` (columns from each
  table's unit row; config `zoneTablePdf.layouts`), every row's quote verified by `ingest-pdf-zones.mjs`:
  **146 rows + 7 zones cited from the text** (KÖu-XI-2/3/4, KÖ-kt-XI, Tk-XI, Vf-XI, Zkk-XI-01).
- Plan: 1a. melléklet, one vector sheet at 1:4000, rendered at 200 dpi. Georeference: 775/837 street names
  on their OSM street (median 2.1 m); OSM buildings on the plan's grey outlines median 1.46 m.
- Area (`plan.clip`): the plan's own red dashed boundary line, drawn at 50% opacity, so its colour is
  "red over any grey" (`district.py` rule `over_grey`); dash-sized blobs kept (`area_line_blob`), gaps under
  other symbols closed (`area_line_gap_m`) and one hand wall at the Danube/Galvani út corner. Overlay
  checked against the dashed line on the whole sheet.
- Zone labels: 440 (149 codes, all in the zone table). Tiles: `public/pmtiles/xi1/` (z13–17, 494 tiles).
- The app picks KÉSZ 1 or KÉSZ 2 by area (`plan.area` may now hold several rings, one per piece).

### XI. Újbuda, KÉSZ 9 (16/2018.) — done, 3 of 11 area KÉSZ (2026-10-13)

- Text: 16/2018. (VI. 6.) KÉSZ for Galvani út – Andor utca – Solt utca – Kondorosi út – Sáfrány utca –
  vasútvonal – kerülethatár (Albertfalva, Kelenvölgy side to the Danube), `public/docs/xi9-kesz.pdf`
  (njt, `2018-16-SP-5Y260`, consolidated 2025.12.15.). Key `xi9`. Same annex set and drawing style as KÉSZ 1.
- Zone limits: 1c. melléklet PDF, `pdf_zone_rows.py`: **92 rows + 6 zones cited from the text** (KÖu-XI-2/3/4,
  KÖ-kt-XI, Vf-XI, Zkk-XI-01). Some tables print no unit over the plot-area column; those layouts place it by
  its header text (`layouts` value `{"fields", "headers"}`). "K/500"-style cells (kialakult / new plots) are
  kept as text with no number.
- Plan: 1a. melléklet, one vector A1 sheet at 1:4000, 200 dpi. Georeference: 434/470 street names on their
  OSM street (median 1.6 m); buildings median 1.33 m. Area traced from the red dashed boundary as for KÉSZ 1
  (thin spurs along the two Danube bridges included).
- Zone labels: 185 (94 codes, all in the zone table). Tiles: `public/pmtiles/xi9/` (z13–17, 240 tiles).

### XI. Újbuda, KÉSZ 8 (1/2021.) — done, 4 of 11 area KÉSZ (2026-10-13)

- Text: 1/2021. (I. 29.) KÉSZ for kerülethatár – vasútvonal – Sáfrány utca – Kondorosi út – Solt utca – Andor
  utca – Egér út – Balatoni út – villamosvonal (Kelenvölgy, Péterhegy, Madárhegy side; garden-city area),
  `public/docs/xi8-kesz.pdf` (njt, `2021-1-SP-5Y260`). Key `xi8`. Different planner (Korényi) from KÉSZ 1/9.
- Zone limits: 2. melléklet, one page, 15 rows transcribed into `zoneTablePdf.rows` from the PDF text, quotes
  verified; the PDF carries invisible text ("IKRIK RiIIKR") inside one row, dropped by the new
  `zoneTablePdf.ignoreText` before matching. The table has szmá/szmp only (no total): szmá is mapped to the
  FAR. Concession values like "20 (25)x" keep the base number; the (x)/(xx) footnotes are row notes.
  KÖu-XI-2/3 cited from § 26; KÖu-XI-4, KÖk-XI and KÖ-kt-XI are printed on the plan but have no rule in this
  decree, so they stay unknown.
- Plan: 1. melléklet page 1 (KÉSZ-1A; page 2, KÉSZ-1B, is a constraints map), A1 at 1:4000, 200 dpi, frame
  stops before the legend. Georeference: 484/509 street names (median 1.4 m), buildings median 1.42 m.
- Area: no distinct boundary line, so the part covered by zone hatching (`area_colour`, a colour rule at full
  size), closed over streets; two motorway corridors drawn outside were cut off by hand (`area_walls_px`,
  now also in this mode). The north edge near Kelenföld station may include some railway land.
- Zone labels: 140. Tiles: `public/pmtiles/xi8/` (z13–17, 291 tiles).

### XI. Újbuda, KÉSZ 5 (43/2018.) — done, 5 of 11 area KÉSZ (2026-10-13)

- Text: 43/2018. (XII. 4.) KÉSZ for Budaörsi út – Budaörs határa – XII. kerület – Gazdagréti út – Rétköz utca –
  Gazdagréti út – Budaörsi út (Őrmező, Gazdagrét west, Madárhegy), `public/docs/xi5-kesz.pdf` (njt,
  `2018-43-SP-5Y260`; plan updated 2026. június). Key `xi5`. Same planner as KÉSZ 8.
- Zone limits: 2. melléklet (2 pages), read by the new `scripts/pdf_zone_seq.py` (one cell per text line,
  `zoneTablePdf.seqFields`; joins "15" + ",0"; footnotes (x)…(xxxx), [ ] and Z attached to rows whose cells
  carry the mark): **31 rows + 3 zones from the text** (KÖu-XI-2/3 § 41, Kb-Ez-XI-01 § 46). KÖu-XI-4 has no
  rule in this decree. "kialakult" cells have no number.
- Plan: 1. melléklet page 1 (KÉSZ-1A-3000), 1300×820 mm at 1:3000, 200 dpi, frame stops before the legend.
  Georeference: 429/454 street names (median 1.8 m); buildings median 2.2 m.
- Area: the part drawn in black linework (`area_colour` max 70 grey; the base map outside is lighter),
  closed 90 m, land south of Budaörsi út cut off by hand (`area_cut_px`, new).
- Zone labels: 126. Tiles: `public/pmtiles/xi5/` (z13–17).

### XI. Újbuda, Tóváros KÉSZ (41/2023.) — done, 6 of 11 area KÉSZ (2026-10-13)

- Text: 41/2023. (XII. 19.) KÉSZ for Balatoni út – MÁV vasútvonal – Partfutó utca – villamosvonal (Tóváros,
  by Repülőtéri út), `public/docs/xi-tovaros-kesz.pdf` (njt, `2023-41-SP-5Y260`). Key `xi-tovaros`.
- Zone limits: 2. melléklet, `pdf_zone_seq.py` (now also joins an exception value on its own line,
  "12,0" + "(7,5)", and attaches the "( ) … eltéréssel alkalmazható" note): **7 rows + Vf-XI** from § 27.
  Codes use a slash (Lk-2-XI/1).
- Plan: one vector sheet 928×610 mm at 1:2000, 200 dpi, frame stops before the legend. Only 27 street
  labels, 25 on their street (median 1.3 m); buildings median 1.47 m after the building fit; checked on
  Kékperje utca / Kanalasgém utca.
- Area: the coloured part of the plan, closed 20 m; it includes the railway strips the plan colours.
- Zone labels: 25. Tiles: `public/pmtiles/xi-tovaros/`.

Fix (same day): `plan_georef.py` now clears `public/tiles/<key>/` before rendering. Before, a re-run after
setting `plan.clip` left the earlier unclipped tiles in place and `pack_tiles.py --from-tiles` packed them,
so KÉSZ 1, 8 and 9 showed plan tiles outside their areas; all three were repacked (after packing, run
`registry.py export <key>` before `build`, or the archive size in regulations.json goes stale).

### XI. Újbuda, KÉSZ 7 (36/2021.) — done, 7 of 11 area KÉSZ (2026-10-13)

- Text: 36/2021. (XI. 23.) KÉSZ for Repülőtéri út – Kőérberki út – Egér út – Balatoni út – villamosvonal –
  kerülethatár – Kamaraerdei út – Budaörs határa (Kamaraerdő, Tóváros surroundings), `public/docs/xi7-kesz.pdf`
  (njt, `2021-36-SP-5Y260`). Key `xi7`.
- Zone limits: 2. melléklet, 11 rows transcribed (Ek/Má/Mk rows have no szmp column; "1, de legfeljebb
  500 m2"; K-Rek-XI/1 coverage "5" carries footnote 1, the OTÉK exemption, kept as a row note), quotes
  verified; + Zkp-XI, Ev-XI, Vf-XI, KÖk-XI from the text headings. Codes printed on the plan but not in this
  table: Ek-XI/3, Mk-XI/3 (unknown), Lk-2-XI/2–3 (Tóváros KÉSZ, shown for information).
- Plan: 1. melléklet, two vector sheets at 1:2000 (`scales` per sheet), 200 dpi. Building outlines are
  light grey (195–228). Street names: sheet 1 71/82 (median 1.9 m), sheet 2 only 6/9 (median 1.5 m; the
  building fit then moved it 7.8 m). Checked at Susulyka utca / Kamaraerdei út: on the streets.
- Area: inside the blue dashed "tervezési terület határa" (`area_line` blue, dash blobs, gaps up to 80 m),
  seeds per sheet (`plan_area.py` now skips a seed outside a sheet); the land north of Repülőtéri út
  (KÉSZ 25/2018) cut off by hand (`area_cut_px`, now also in line mode). Tóváros is a hole.
- Zone labels: 50. Tiles: `public/pmtiles/xi7/`.

### XI. Újbuda, KÉSZ 3 (26/2018.) — done, 8 of 11 area KÉSZ (2026-10-13)

- Text: 26/2018. (VII. 3.) KÉSZ 3 for Gazdagréti út – Rétköz utca – Háromszék utca – Sasadi út – Budaörsi út – kerülethatár,
  `public/docs/xi3-kesz.pdf` (njt, `2018-26-SP-5Y260`). Key `xi3`.
- Zone limits: 2. melléklet read with `pdf_zone_seq.py` (32 rows; `minCellSize` 7.5 drops footnote
  superscripts from the values but keeps them in the quote; footnote 1, "( )" and "K - kialakult" as row
  notes), quotes verified; + KÖu-XI-02/03, KÖu-XI-03/Üa, Zkp-XI/1–2, Ek-XI, Ev-XI, Tk-XI from the text.
  The plan prints "KÖu-XI-03-Üa" with a dash, so that one label is not matched.
- Plan: 1. melléklet, two vector sheets at 1:2000, 200 dpi; street names drawn in a shifted font,
  decoded with `font_fix` copied from districts/i.json. Fit: sheet 1 100/107 labels (median 1.7 m),
  sheet 2 165/173 (median 1.6 m). Checked at Márton Áron tér / Talaj utca: on the streets.
- Area: inside the dark blue dashed "tervezési terület határa", same rule as KÉSZ 7, gaps up to 40 m, one
  seed per sheet; legends lie outside it. Zone labels: 181. Tiles: `public/pmtiles/xi3/`.

### XI. Újbuda, KÉSZ 25/2018. — done, 9 of 11 area KÉSZ (2026-10-15)

- Text: 25/2018. (VII. 3.) KÉSZ for Budaörsi út – Kőérberki út – Repülőtéri út – Budaörs határa,
  `public/docs/xi25-kesz.pdf` (njt, `2018-25-SP-5Y260`). Key `xi25`.
- Zone limits: 2. melléklet PDF (`zoneTablePdf`, 8 rows) + 7 zones from § 17 (KÖu-XI-02/03/04, Ev-XI,
  Ek-XI, Vf-XI, Kb-Ez-XI) as `extraZones`.
- Plan: two vector sheets at 1:2000 with a text layer but almost no street names as text (parked on
  2026-10-13 for that). Placed by plot numbers (`hrsz_fit`) and the plot-outline fit against the BTP plots
  (`styles.building_line` max 175: the plot lines, not the light grey buildings): median 0.42 / 0.52 m.
  The pages are stored rotated (`/Rotate 270`): a text-layer export must apply the page's rotation
  matrix; the raster OCR (`pipeline --only ocr`) was used, plus the zone codes from the text layer.
- Area: the blue dashed boundary has long gaps and the blue cycle-route circles look like it, so
  `plan_area.py` leaked; traced by hand on both sheets (`plan_area_trace.py` now takes
  `{"<sheet>": [[x, y], ...]}`), roads included, cut by the district boundary. 2.04 km², overlaps
  KÉSZ 1, 5 and 7 by under 2% along the shared roads.
- Plots: 239, 179 with a zone. Zone labels: 68. Tiles: `public/pmtiles/xi25/`.

### XI. Újbuda, Sasad Liget KÉSZ (8/2017.) — done, 10 of 11 area KÉSZ (2026-10-15)

- Text: 8/2017. (III. 28.) KÉSZ for Budaörsi út – Gazdagréti út – Rétköz utca – Háromszék utca – Sasadi út,
  `public/docs/xi-sasad-kesz.pdf` (njt, `2017-8-SP-5Y260`). Key `xi-sasad`.
- Zone limits: 2. melléklet .docx, `docx_zone_rows.py` with two new options: `docxCodeCol` 0 (no row
  number column) and `docxCategoryRows` (category rows inside the table): 8 rows, + Zkp-XI-Kk-01 (§ 22).
- Plan: one PDF of two vector A3 sheets, `/Rotate 270`, shifted-font text layer (`font_fix` as Budapest I.).
  Drawn at **1:3000** and turned **37.7°** (estimated from the plot numbers first): `scales` 3000,
  `rotation_search_deg` [35, 40.5]. Street names: 53/56 and 65/67 on their street (median 0.9 m), then the
  building fit (`building_line` 150–200): buildings median 1.0 / 1.1 m. The plot-outline fit made it worse
  here (plot lines too faint at 200 dpi), so it is off.
- Area: the blue dashed boundary leaked in `plan_area.py`; traced by hand on both sheets, overlaps with
  KÉSZ 3 and 5 split by the nearer zone label (2–3% left along shared roads). 0.71 km².
- Plots: 515, 439 with a zone. Zone labels: 60. Tiles: `public/pmtiles/xi-sasad/`.

### XI. Újbuda, Lágymányosi-öböl KÉSZ (30/2016.) — done, 11 of 11 area KÉSZ (2026-10-15)

- Text: 30/2016. (XII. 19.) KÉSZ for the Lágymányosi-öböl and its surroundings (as amended by 26/2017.),
  `public/docs/xi-lagymanyos-kesz.pdf` (njt, `2016-30-SP-5Y260`). Key `xi-lagymanyos`.
- Zone limits: 1.c melléklet, an old `.doc` (egységes): converted to .docx with LibreOffice for
  `docx_zone_rows.py` (`docxCodeCol` 0, new `docxCategoryFromLimits`), and `ingest-pdf-zones.mjs` now
  publishes a `.doc` as its PDF rendering like a `.docx`. 21 rows; + KÖu-XI-3, KÖ-kt-XI-01/02/03 from
  §§ 23–24 and Vf-XI (printed on the plan, no rule in the text, so no citation).
- Plan: the only zone plan on njt (1.a, egységes) is a 200 dpi A4 scan, page `/Rotate 270`
  (`rasterize_dpi` 200, `rotate_deg` 90). No street names or plot numbers are readable, so it was placed
  with the new `scripts/plan_chamfer_fit.py`: one block corner picked by hand against the BTP plots and
  0.86 m/px, then a chamfer fit of the sheet's dark and red lines onto the BTP plot outlines (median
  1.2 m, rotation −0.3°). Checked at Bíró László József körút and Budafoki út: on the plan's lines.
  Zone codes: 35 labels placed by hand (`"pass": "hand: …"`), the scan is too coarse for OCR.
- Area: traced by hand (zoned land, the öböl and the KÖu-XI-3 road; the unzoned plots west of the
  ID-06/07/08 strip left out), overlaps with KÉSZ 1 and 2 split by the nearer label. 0.56 km².
- Plots: 72, 63 with a zone. Tiles: `public/pmtiles/xi-lagymanyos/`. With this, all 11 XI area KÉSZ are in.

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

- **XI. Újbuda, the other three area KÉSZ** (largest district of the batch) — not done: eleven area KÉSZ that together cover the district,
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
  2026-10-15: the two newest are live, `districts/ix-kvassay.json` (1/2019., Kvassay út; 45 plots, 0.40 km²)
  and `districts/ix-unix.json` (22/2017., UNIX telephely; 58 plots, 0.86 km²). Zone tables: Kvassay 6 zones,
  UNIX 7 (one table per zone, `ingest.verticalTables`), plus the road, railway and forest zones from the
  text (`extraZones`). Both plans draw plot lines in blue, so the outline fit only places them with
  `styles.building_line` set to blue (Kvassay 0.54 m, UNIX 0.27 m median from the BTP plot lines; with the
  default dark-line style they were 4.4 and 11 m off). Zone codes: a 2x OCR pass plus a few hand-placed
  labels (`"pass": "hand: ..."` in the OCR file) for lettering on hatches or rotated. Areas traced with
  `plan_area_trace.py` along the plans' boundary lines. The other ten KSZT/KÉSZ are still not onboarded.
- **XIII. / IX. / XI. Danube banks** — under the Főv. Kgy. Duna-parti építési szabályzatok (DÉSZ),
  city-level, not onboarded.
