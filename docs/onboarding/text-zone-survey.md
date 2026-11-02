# Zone boundaries described in the regulation text: survey (2026-11-02)

Question (Peti, 2026-11-02): some regulations describe an area in words, as streets that bound it or
as a list of plot numbers (hrsz). Can that text make the zone assignment more accurate, as a
cross-check on the zones read from the plan, or as a fallback where no boundary line was read?

## What was searched

All 78 regulation PDFs in `public/docs` (51 areas, base texts and amendments), as text
(`pdftotext -layout`), split into paragraphs and points. A paragraph was kept when it has

- a chain of two or more streets, plot numbers, district borders or watercourses before
  "által határolt", "között(i)", "által közrezárt/bezárt" (a street-described area), or
- a plot number ("hrsz", "helyrajzi szám").

Each kept paragraph was matched against the area's zone codes (`public/data/zone-types-<key>.json`)
and against scope wording ("hatálya ... terjed ki"). About 120 were then read by hand.

## Classes and counts

| Class | What it says | Paragraphs | Areas | Usable for zones? |
|---|---|---|---|---|
| **A** zone extent by streets | "the zone X is the area bounded by streets ..." | **~3** | 3 | too few to build on |
| **B1** rule for a street-bounded part of a zone | "in zone X, inside the area bounded by S1 – S2 – S3, the minimum plot is 800 m²" | 52 | 21 | weak: describes a part of a zone, not its edges |
| **B2** rule for named plots in a zone | "in zone X, on plot 7221 ..." / "zone X: plots 38028/1, 38028/2" | 74 mentions (prototype); 47 kept by the strict reader | 15 (10 kept) | **yes**: each one says plot N lies in zone X |
| **C** scope of the KÉSZ or of its sub-areas | "the rule applies to the area bounded by ..." | 41 | 17 | plan coverage only (VIII's 10 negyed, XXI ~12 sub-areas, each KÉSZ's own scope) |
| no zone code | traffic conditions ("between X and Y a lane must ..."), building rules for a street-bounded block | ~290 | 47 | no |

The three type A sentences:

- XXI: "A Vi-1/Sz-3 jelű építési övezet a Kossuth Lajos utca – Ady Endre út - (209922) hrsz-ú
  közterület – Védgát utca – tervezett Köu-2 övezetű főút – Corvin út által határolt ... területek
  övezete" (it also runs to a planned road that is not on OpenStreetMap).
- XIII: "A Zkp-Kk-2 közkert övezet a felső rakpart menti, a Révész utca és a Szent István körút
  közötti közparkokat összekötő közkertek területe".
- X: the Kőbánya sub-area list (1. melléklet) bounds areas by streets and plot edges
  ("42804/6 hrsz.-ú telek északi határa ..."), which is type C, plus one "az Ek/1 övezet déli határa".

Per area (paragraphs, by class):

| Area | A | B1 | B2 (kept) | C |
|---|---|---|---|---|
| I | | | 12 | |
| II | | 10 | 11 | |
| IX | | | 2 | |
| IX Kvassay | | | 3 | |
| VI | | | 2 | 1 |
| VI-2 | | | | 1 |
| VIII | | 3 | | 11 |
| X | 1 | 11 | | (sub-area list) |
| XI KÉSZ 8 | | | 10 | 1 |
| xii-dh, xii-kvh | | 1 each | | 0 and 1 |
| xii-ek | | | | 2 |
| XIII | 1 | 3 | | |
| XIV | | | 1 | 1 |
| XV | | 1 | (7 in prototype, all streets or unmapped plots) | |
| XVI | | 8 | 2 | |
| XVII | | 1 | 3 | |
| XVIII | | 3 | | 1 |
| XIX | | 2 | | 1 |
| XIX Wekerle | | | | 1 |
| XX | | 2 | | |
| XXI | 1 | 1 | 1 | 12 |
| xxii, xxii-bf, xxii-nt | | | | 1–2 each |
| XXIII | | 1 | | |
| IV (all 9 KÉSZ), Csobánka, Győr, Pécs | | (Pécs 4) | | IV-6, IV-10, Győr 2 |

Győr and Pécs were missed by this first pass: the branch it ran on had no zone tables for them,
and the run reported "51 areas" without listing the two that returned nothing. Since then
`text_zone_check.py` prints NOTHING FOUND / SKIPPED per area and Z8 warns until
`acceptance.text_refs` explains it (onboarding step 1b in acceptance.md).

Pécs (re-run): the zone rules sit under a heading ("6. a Vi-28XY(BD) jelű építési övezet sajátos
előírásai:") with the plots in its a), b) points; the reader now carries the heading's code into its
points. 11 statements: 5 agree, 5 not on the map, 1 disagrees (17485/1: text Vt-60XX(B), map
Lk-60YX(B), not yet checked on the plan). The same change found 12 more in XVII (all agree) and 2 in
XIX. Pécs codes carry a sub-area suffix ((B), (BD), (ÚP) ...) that the text defines by streets
("Az Újpatacs, Platán köz – Kislőtér utca közötti terület (ÚP)"): a possible later check that every
zone with a suffix lies inside its described sub-area.

## Győr: numbered zones (added 2026-11-02, after Peti asked)

The GYÉSZ plan prints a 5-digit **zone number** above every coded label (`00492` over
`Lke06/I/30/50-/075/02-20/32/`), and the text keys its zone-specific rules by that number: the
103. § table has 687 rows such as "00492 Az övezet területén belül lévő 3562 hrsz.-ú ingatlanon ...".
4,084 zone numbers are on the plan's text layer (`scripts/plans/gyor-ocr-*.json`). The reader places
each number with the sheet fits, takes the code label printed with it (within 25 m), and turns a row
that names a plot into "plot N has that code".

First run (Győr data of 2026-11-02): 44 statements, 30 agree, 10 plots not on the map or unzoned,
4 disagree:

| Plot | Text (zone number, its code) | Map | On the plan |
|---|---|---|---|
| 42540 | 01722 "A temető övezetben ..." Kte01/S/05/80-/070/02-//150 | Lf05/O/30/40-/048/02-//004 | at the corner of the cemetery zone 01722, next to 01721: **likely map wrong** |
| 27523/2 | 01948 Lf05/O/30/40-/070/02-18/40/ | Lf05/O/30/40-/070/02-14//006 | west of the street, in the 01948/01949 block; the map took the code from across the street: **likely map wrong** |
| 8473 | 01054 Lk15/Z/40/40-/105/04-//K | Lk15/Z/40/40-/075/03-//K | not checked yet (same zone kind, other height) |
| 2855/4 | 00354 (label read: KÖu00//10/5-030-0020) | Gipe03/S/30/50-/070/-//010 | not checked yet: the code nearest the number may be a road label |

Győr zone data is owned by the onboarding work (PR #14); these stay warnings until it is reviewed.
The zone numbers would also let the 687 per-zone rules of the 103. § table reach the right zone
areas on the card (not done).

## Decision

The street-geometry fallback (type A to street polygons to plots) is not worth building: about three
sentences in 78 regulations, and the 13 plans with no red dots read have none. Hungarian KÉSZ texts
leave zone extents to the plan drawing; street-bounded sentences mostly add a rule to part of a zone.

Built instead (warning only): type B2 as check **Z8** (`scripts/text_zone_check.py`, see
`acceptance.md`). It needs no street matching: the plot number finds the plot directly.

First run, on the zones of PR #13 (47 statements, 10 areas): 34 agree, 10 name a plot that is not on
the map or has no zone (merged plots, street plots), 3 disagree:

| Plot | Text | Map | On the plan | Outcome |
|---|---|---|---|---|
| II 14955 | Ln-2/Z-7 | Zkp-Kk/1 | inside the Ln-2/Z-7 block south of Ln-2/Z-8 | **map wrong**: review answer added (`"why": "text"`), applied on the next II rebuild |
| II 59155/11 | Má-1 | Ek-1 | Má-1 fill, Má-1 labels all round | **map wrong**: review answer added |
| IX Kvassay 38038/3 | KÖk-1/IX-K | KÖk-2/IX-K | inside the red dotted KÖk-2 loop | text contradicts its own plan: `acceptance.text_zones_ok` |

The prototype also flagged XI KÉSZ 8 44147 (text Lke-2-XI-02, map Lke-2-XI-INT-02); the plan is not
clear there (the plot sits on a short red dotted segment) and the strict reader no longer keeps that
sentence.

## Possible next steps

- C as a coverage check: compare each KÉSZ's own scope sentence with its plan area (`plan.clip`).
- Read Győr/Pécs-style codes with parentheses.
- B1 as a soft hint for review crops: show the quote when a plot inside the described part has
  another code.
