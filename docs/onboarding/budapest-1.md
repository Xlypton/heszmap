# Onboarding batch budapest-1: Budapest I.–VIII. kerület (triage, 2026-10-04)

Sources: njt.jog.gov.hu (issuer ids 250–257 = I.–VIII. kerület; `njt.py search` with the issuer
filter, then each decree's consolidated text and annex list). Population: KSH 2022 census, rounded.

Everywhere the city-wide **FRSZ** (Budapest Főváros Rendezési Szabályzata, 5/2015. (II. 16.) Főv. Kgy.)
and **TSZT** apply as well, and along the Danube the **DÉSZ** (Duna-parti Építési Szabályzat, Főv. Kgy.)
replaces the district regulation in its own area (the district KÉSZ texts say so: I. 1. § (1), II. 1. § (2),
V. 1. § (2)). Those are city-level and not onboarded here.

Note on njt: long decrees are served in parts (placeholder blocks loaded while scrolling); the annex
links are usually in the late blocks. `njt.py` and `ingest-kesz.mjs` now fill those blocks in
(`njt.py html <id>`); before that, II., III. and V. looked as if they had no annexes.

| Dist. | Pop. | Regulation in force (njt id) | Area | Zone limits table | Plan (format) | Status |
|---|---|---|---|---|---|---|
| III. Óbuda-Békásmegyer | 129k | **ÓBÉSZ** 20/2018. (VI. 26.) (`2018-20-SP-5Y252`), hatályos 2025.12.31. | whole district (except DÉSZ / Duna-part KÉSZ areas) | 2. melléklet, **not on njt** | 1. melléklet SZ-M1, 1:2000, 25 sheets, **not on njt** (no annex links at all); not located on obuda.hu yet | blocked: plan + tables only from the district (not found) |
| III. | | Duna-part I. szakasz KÉSZ 6/2019. (II. 8.) (`2019-6-SP-5Y252`) | riverbank strip | 2. melléklet PDF (text) | 1. melléklet: A4 scans | small area; after ÓBÉSZ |
| III. | | Pünkösdfürdő Duna-part KÉSZ 34/2022. (XII. 8.) (`2022-34-SP-5Y252`) | riverbank strip | 2. melléklet (scan with text) | 1. melléklet A4 scan | small area |
| III. | | Római-part Duna-part KÉSZ 30/2024. (XII. 23.) (`2024-30-SP-5Y252`) | riverbank strip | 2. melléklet PDF (text) | 1. melléklet: 2 scanned sheets 683×914 mm | small area |
| III. | | older area KÉSZ 26/2017, 32/2017, 48/2017 (`2017-26/32/48-SP-5Y252`) | small blocks | normaszöveg PDF | in the PDF | still listed in force; check against ÓBÉSZ |
| IV. Újpest | 101k | 10 "városszerkezeti egység" KÉSZ: 1 Dél-Újpest 34/2018 (`2018-34`), 2 Újpesti lakótelep 33/2018 (`2018-33`), 3 Városközpont 18/2018 (`2018-18`), 4 Károlyi városnegyed 12/2018 (`2018-12`), 5 Újpest kertváros 5/2018 (`2018-5`), 6 Északi kertváros 2/2019 (`2019-2`), 7 Megyer kertváros 19/2018 (`2018-19`), 9 Káposztásmegyer lakótelep 3/2019 (`2019-3`), 10 Székesdűlő 8/2019 (`2019-8`); Népsziget 22/2018, Duna-part 23/2018 (all `-SP-5Y253`) | each its unit; unit 8 not found on njt | **HTML tables** in the njt text (13–16 per decree; 9: PNG images) | **not on njt** (annexes there are parking/other maps); as-adopted plans on ujpest.hu/tu_dokumentumok (council papers, may predate amendments) | blocked for now: current plans not on njt; 11 regulations |
| II. | 89k | **KÉSZ** 28/2019. (XI. 27.) (`2019-28-SP-5Y251`), hatályos 2026.07.07. | whole district except 8. melléklet areas (DÉSZ) | 2. melléklet PDF, vector text, 23 pages, column letters A–O | 1. melléklet SZ-M1, 1:2000, 27 sheets 917×770 mm, **raster strips** in PDF (render) | candidate |
| VIII. Józsefváros | 75k | **KÉSZ** 45/2023. (XII. 14.) (`2023-45-SP-5Y257`), hatályos 2026.09.25.; repealed the earlier area KÉSZ (PALOTAKÉSZ, 17/2022 etc.) | whole district | 2. melléklet PDF (mixed: text + scanned pages) | 1. melléklet 1:2000, 29 pages A3, **JPEG raster** 2300–3600 px | candidate (raster, like XX) |
| VII. Erzsébetváros | 54k | Erzsébetváros Építési Szabályzata 25/2018. (XII. 21.) | whole district | in the district's consolidated PDF | in the district's consolidated PDF | **not in njt** (`2018-25-SP-5Y256` → "nem létezik"); erzsebetvaros.hu has a consolidated PDF of 2024-12-12, but 33/2025 amended it since | blocked: no current consolidated text |
| VI. Terézváros | 38k | KÉSZ 23/2019. (XI. 21.) (`2019-23-SP-5Y255`) south/inner part; KÉSZ 35/2020. (VI. 25.) (`2020-35-SP-5Y255`) north part (Váci út – Lehel u. – … – Teréz krt.) | together the whole district | 2. melléklet PDF with text (3 pages each) | 1. melléklet: **one vector sheet with full text layer** each (841×1189 mm; 740×540 mm) | candidate (best plan format) |
| V. Belváros-Lipótváros | 25k | **KÉSZ** 6/2020. (I. 30.) (`2020-6-SP-5Y254`), hatályos 2026.04.01. | whole district except DÉSZ area | in the njt text (1 HTML table) / annexes | 1–4. melléklet: **one scanned sheet** 915×1560 mm | candidate |
| I. Budavár | 23k | **KÉSZ** 29/2022. (XII. 20.) (`2022-29-SP-5Y250`), hatályos 2025.06.06.; repealed 16/2000 (still flagged in force on njt) | whole district except DÉSZ area | 1. melléklet PDF, vector text, 13 pages, column letters A–M | 2. melléklet: 1:2000, legend + 10 **vector sheets with text layer** (A2), yellow streets, red dotted zone boundaries, magenta codes | candidate |

## Order of work

Biggest first, as far as the sources allow: III. and IV. are blocked on plans that njt does not publish
(and VII. on the text itself), so the deep work goes II. → VIII. → VI. → V. → I., with the blocked
districts recorded here. Progress is noted below as each district is done.

## Progress

### VI. Terézváros — done (2026-10-06)

Two regulations, split along Podmaniczky utca (each plan's tiles and labels are clipped to its own
side: `plan.clip`; the app picks the regulation whose `plan.area` holds the tapped point).

| | `vi` — KÉSZ 23/2019. (south, inner Terézváros) | `vi2` — KÉSZ 35/2020. (north, Nyugati) |
|---|---|---|
| Text | `public/docs/vi-kesz.pdf` (njt, hatályos 2025.12.23.) | `public/docs/vi2-kesz.pdf` (njt, hatályos 2025.12.15.) |
| Zone limits | 2. melléklet (official PDF, `vi-kesz-m2.pdf`): 15 rows transcribed in the config (cells hold several cases: Á general / S corner plot / MG garage / F ground floor), every row's quote found in the PDF; + 4 street/square zones cited to the text | 11 rows the same way + 4 street/rail zones cited to the text |
| Plan | one vector A0 sheet, 1:2500, full text layer; 200 dpi | one vector sheet, 1:2500; zone codes drawn as curves, street names only in the inset |
| Georeference | street names from the text layer: 132/135 labels on their OSM street, median 1.2 m; OSM building/plot overlays checked at three corners of the sheet: within ~1 m | no usable street names on the main map: registered to the `vi` sheet by correlating the blue plot lines of the shared base map (translation, peak 0.66 / fine 0.68), so it inherits the `vi` fit |
| Zone labels | 131 (text layer, legend/inset blanked) | 13 (OCR of the red lettering; partial: Vt-V/VI/6, /9, /10, Kt-Fk/VI/3 not read) |
| Zones / plots | not traced | not traced |

### I. Budavár — done (2026-10-06)

- Text: KÉSZ 29/2022. (XII. 20.), `public/docs/i-kesz.pdf` (njt, hatályos 2025.06.06.).
- Zone limits: 1. melléklet is a separate official PDF (`public/docs/i-kesz-m1.pdf`, vector text, column
  letters A–M / A–G): 53 zones read automatically, every row cited by its own text run; the PDF lists 53
  codes, all 53 parsed. "K" = kialakult (no number). Category names from each table's heading.
- Plan: 2. melléklet, 1:2000, legend page + 10 vector sheets (A2, pages rotated 270°: the text layer is
  rotated into the rendered sheet; street names in a subset font are decoded, `plan.font_fix`). 8 sheets
  georeferenced; the two Danube-bank sheets (pages 8 and 11: Döbrentei tér and a sliver by Szent Gellért
  rakpart, 3 zone labels, mostly DÉSZ area) have 1 street name each and are not used.
- Georeference: street names (37–57 per sheet on their OSM street, median 1.0–1.6 m), then OSM building
  outlines on the plan's building lines: median 0.9–2.2 m, 26–58% of outline points within 1 m; overlays
  checked on three sheets (within ~0.5 m).
- Zone labels: 307 (text layer). Zones / plots: not traced.
