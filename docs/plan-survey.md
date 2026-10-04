# Zoning plans across Hungary: survey (2026-10-04)

How general can the plan pipeline be? A random sample of municipalities' building regulations
(HÉSZ) from the Nemzeti Jogszabálytár, plus the XX. kerület KÉSZ already processed.

## Source

`scripts/njt.py search "helyi építési szabályzat"` returns **1,690** decrees in force with that
phrase in the title, **1,316** of them base regulations (not amendments). Budapest districts call
theirs "kerületi építési szabályzat" (separate search). Annexes (plans) are linked from each decree's
consolidated text as PDFs under `/document/…`.

Sample (random, seed 2026, plus Budapest IV.): Döbrönte, Makkoshotyka, Somogyszob, Söréd, Csorvás,
Jászszentandrás, Üröm, Vértestolna, Tanakajd, Ősi, Pécsdevecser, Győrsövényház, Újpest.

- 11 of 13 had their annexes as PDFs on njt (39 files downloaded).
- Üröm's annexes are not PDF.
- Újpest (IV.) has no annexes on njt; its plans live on the district's site.

## What the plans are

`scripts/plan_probe.py` on every annex. Of the map-sized annexes (A3 and larger):

| Format | Count | Towns |
|---|---|---|
| Vector PDF with a real text layer | 11 | Döbrönte, Győrsövényház, Ősi, Pécsdevecser (Kiskassa), Tanakajd |
| Vector PDF, text drawn as curves | 4 | Jászszentandrás, Pécsdevecser (2000), Somogyszob |
| Scan, colour | 0 in sample | XX. kerület (Budapest) |
| Scan, black and white | 2 | Vértestolna |

The smaller annexes are text: definitions, zone tables, lists. Some of these are scanned A4 pages
(Makkoshotyka, Csorvás).

Conventions differ a lot between plans:
- **Zone codes:** red text (Döbrönte), blue text in circles (Győrsövényház), blue boxes (Ősi), blue
  bold text (XX).
- **Zone boundary:** red dots, red dash-dot, magenta, or black dash-dot on a B/W scan.
- **Streets:** yellow fill (XX), beige hatch (Döbrönte), or no fill, with existing street edges being
  just plot lines (Győrsövényház).
- One plan can draw the same element in several styles: an existing (blue) and a planned (red)
  regulation line; a land-use boundary and a zone boundary.

## What the pipeline can read

**Legend (vector + text).** `plan_vector.py` finds the standard legend entries in the PDF text and
reads the symbol's drawing style. This worked on every vector plan with a text layer:
- zone boundary ("Övezethatár", "eltérő övezetek határa", "eltérő területfelhasználás határa");
- regulation line(s);
- plot lines ("telekhatár", plus the base map's own line style, learned from the strokes around the
  printed plot numbers);
- inner-area and administrative boundaries;
- street areas.

Fixes needed along the way:
- multi-column legends: the symbol window stops at the previous column's label;
- symbol frames of any colour;
- CAD "fills" that are really hatches of thin strokes.

**Legend (scan).** OCR finds the legend entries even on a black-and-white scan, at any rotation
(Vértestolna: "Építési övezet határa", "Szabályozási vonal (telekhatáron)", "Telekhatár meglévő").
On a B/W scan the symbols differ only by line pattern (dash-dot vs dashed), which colour rules cannot
separate.

**Zone codes.**
- Vector + text: exact, from the text layer, checked against the codes the regulation's own text
  uses (Győrsövényház: 134 code labels, 8 codes; Pécsdevecser: 129; Ősi: 85).
- Text as curves: needs OCR of a render, as for scans.

**Plots.** Vector + text: 150 to 1,850 plots per sheet, traced from the plot lines.

**Zones (plots merged up to zone boundaries / regulation lines, labelled by codes).** Not yet
reliable:

| Plan | Zones holding codes | One code | Conflicting |
|---|---|---|---|
| Győrsövényház SZ-1 | 11 | 9 | 2 |
| Pécsdevecser–Kiskassa | 6 | 4 | 2 |
| Ősi SZT-2 | 7 | 4 | 3 |
| Döbrönte SZT-B1 | 1 | 0 | 1 (everything merged) |

The remaining failure is always the same one. Somewhere a zone edge is not drawn as a boundary,
because the zone ends at:
- an existing street edge drawn only as a plot line;
- the inner-area line;
- a water body.

Through that gap, neighbouring blocks connect. XX. kerület avoids this because its streets are a
separate yellow layer. Plans without a street layer need the street to be found another way: from
OSM roads, or from the street parcels' own codes ("KÖ", "Köu").

## Conclusion

1. **One pipeline, configured per municipality, is the right shape.** Everything except the drawing
   conventions is the same everywhere:
   - fetching from njt;
   - georeferencing to OSM;
   - zone cells and plots;
   - cross-checks with the text and OSM;
   - the app.

   `districts/<key>.json` holds what differs.
2. **Vector plans with text (the majority in the sample) can be read without OCR.** The legend gives
   the styles automatically. Reading geometry from the PDF is exact, which scans can never be.
3. **Fully automatic zones are not there yet.** A plan needs a short review step: check the
   legend-derived styles, and fix the leaks the report points at (zones with conflicting codes).
   The cross-checks (code list, text blocks, OSM) make every leak visible, so nothing wrong passes
   silently.
4. **B/W scans** need line-pattern recognition or manual styling. In this sample they are the old
   plans (2005–2006).

Next steps:
- use OSM roads as the street layer in `plan_vector.py`;
- georeference vector plans the same way as scans (street names from the text layer);
- a review page that shows a plan's legend styles and conflicting zones for correction.
