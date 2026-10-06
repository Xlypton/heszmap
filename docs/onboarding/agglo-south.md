# Onboarding batch: agglo-south (Budapest agglomeration, south sector)

Settlements checked against the 2005 Budapest agglomeration list (81 settlements). Szigetcsép,
Szigetszentmárton, Áporka and Bugyi are not on it and were dropped. 14 settlements remain
(Ócsa was listed twice). Settlement ids 2401–2414, in order of population.

Regulations found on njt.jog.gov.hu (search "építési szabályzat", Pest county filter, then the
decree's annexes with `njt.py annexes`). Plan formats from `plan_probe.py` on every annex.

## Triage (2026-10-04)

| id | key | Pop. | Regulation in force (njt id) | Zone limits | Plan on njt | Plan format |
|---|---|---|---|---|---|---|
| 2401 | szigetszentmiklos | ~41k | HÉSZ 1/2012. (II. 1.) `2012-1-SP-5Y429`, consolidated 2026-03-28 | 1. melléklet: separate A4 PDF (13 pages, text layer), tables per zone family | 2. melléklet, 49 sheets 800×550 mm, M=1:4000 | vector, **text drawn as curves** (zone codes red, in ovals) |
| 2402 | gyal | ~24k | HÉSZ 17/2014. (XII. 1.) `2014-17-SP-5Y329`, consolidated 2026-04-01 | in the text, as **prose lists per zone** ("a.) … telek legkisebb területe (m²): 1000 …"), no tables | 1. melléklet, 29 sheets A3 (one 46 MB PDF, "egyben 2026 március") | scan, colour |
| 2403 | dunaharaszti | ~22k | HÉSZ 3/2017. (III. 1.) `2017-3-SP-5Y311`, consolidated 2026-05-30 | in the text, tables with "építési övezet jele" (10 tables) | one PDF, 16 pages: SZT-1 sheets A2, M=1:4000 | vector with text layer (codes red text) |
| 2404 | szigethalom | ~18k | HÉSZ 19/2018. (XII. 12.) `2018-19-SP-5Y426`, consolidated 2024-12-23 | 2.–9. melléklet: separate A4 PDFs with text layer, one per zone family | 1. melléklet, one sheet 910×1600 mm | vector with text layer |
| 2405 | szazhalombatta | ~16k | HÉSZ 18/2015. (XII. 4.) `2015-18-SP-5Y418`, consolidated 2025-10-02 | in the text, one small table per zone with the code as header ("Vt – 2 \| Bm \| Beép[%] …"); 84 tables | **no**: only amendment snippets (M1: 16 A4 pages of sheet excerpts SZT/2019); the full plan sheets are not on njt | scan excerpts |
| 2406 | tokol | ~10k | HÉSZ 15/2010. (IX. 28.) `2010-15-SP-5Y456`, consolidated 2024-11-29; plus 17/2002. (IX. 17.) `2002-17-SP-5Y456` (Dunai Repülőgépgyár area) | in the text, 18 tables with "Építési övezet jele" | 6 annexes: belterület SZT A0 (2023), 1:4000 strip (2023), külterület, airport area (T-11), T-10 mód. | vector; belterület and 1:4000 strip with text layer; külterület and T-11 without text |
| 2407 | ocsa | ~9.5k | HÉSZ 4/2017. (IV. 27.) `2017-4-SP-5Y380`, consolidated 2021-03-26 (later amendments 2023–2026 exist) | in the text, 18 tables with "Építési övezet jele" | **no**: "2. melléklet Szabályozási tervlapok" has no file on njt | – |
| 2408 | halasztelek | ~9.5k | HÉSZ 3/2020. (II. 27.) `2020-3-SP-5Y331`, consolidated 2026-03-13 | not in the text as tables (only a few prose limits); probably on the plan's zone boxes | 1. melléklet SZ-1, one sheet A0 | vector, **no text layer** |
| 2409 | dunavarsany | ~8k | HÉSZ 12/2016. (VI. 10.) `2016-12-SP-5Y314`, consolidated 2025-11-15 | 1. melléklet: separate A4 PDF ("táblázatok", 6 pages) | 2. melléklet, 22 sheets A3 | scan |
| 2410 | taksony | ~6.6k | HÉSZ 14/2022. (VII. 8.) `2022-14-SP-5Y440`, consolidated 2026-05-29 | 3. melléklet: separate A4 PDF (7 pages, text layer) | 1. melléklet belterület SZT, M=1:4000 (one image page), 2. melléklet külterület (scan A1) | image (raster inside a PDF) |
| 2411 | alsonemedi | ~5.5k | HÉSZ 3/2019. (III. 1.) `2019-3-SP-5Y278`, consolidated 2020-12-15 | the text says the parameters are in "1. számú melléklet", but annex 1 is the SZ-1 plan; no table in the text | 3 sheets: SZ-1 külterület 1:10000, SZ-2 belterület 1:4000, SZ-3 north economic area 1:4000 ("kicsi" versions) | image tiles in PDF, no text |
| 2412 | felsopakony | ~3.9k | HÉSZ 11/2021. (XI. 17.) `2021-11-SP-5Y319`, consolidated 2024-04-03 | not in the text as tables; 3.–6. melléklet are A4 lists; probably on the plan | SZ-1 (külterület) and SZ-2 (belterület), A1 | vector with text layer and legend |
| 2413 | delegyhaza | ~3.8k | HÉSZ 12/2025. (VIII. 22.) `2025-12-SP-5Y306`, consolidated 2026-09-18 (replaces 16/2005) | 3. melléklet: separate PDF "paramétertábla" (6 A4 pages) | 1. melléklet SZT 1420×1682 mm, 2. melléklet overlay (scan) | vector with text layer and full legend |
| 2414 | majoshaza | ~1.5k | HÉSZ 10/2015. (IV. 30.) `2015-10-SP-5Y362`, consolidated 2026-09-26 | 1. melléklet: separate A4 PDF ("táblázatok", 3 pages) | 2. melléklet, 14 sheets A3 (102 MB) | scan |

Notes:
- Dunavarsány also lists 16/2013. (IX. 11.) `2013-16-SP-5Y314` as in force (docx annexes); 12/2016 is the
  current HÉSZ with the plan.
- Tököl's 17/2002 regulation covers only the former aircraft-factory area (separate plan sheet).

## Blockers found in triage (tool support)

- **Zone tables in a separate annex PDF** (Szigetszentmiklós, Szigethalom, Dunavarsány, Taksony, Délegyháza,
  Majosháza): `ingest-kesz.mjs` reads only tables in the njt HTML text.
- **Prose zone limits** (Gyál) and **per-zone mini tables** (Százhalombatta): need new parser layouts.
- **Limits only on the plan** (Halásztelek, Felsőpakony, probably Alsónémedi): no citable text table.
- **Plan not on njt** (Ócsa, Százhalombatta): zone table only.

## Status

(updated as work proceeds; see below)
