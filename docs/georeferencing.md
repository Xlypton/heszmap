# How a plan PDF gets onto the OSM map

The zoning plan (szabályozási terv) is published as a PDF annex of the regulation on njt.jog.gov.hu.
The PDF has no coordinates in it. Georeferencing works out, for every plan sheet, a function
**sheet pixel → map position**, by finding where the things drawn on the plan (street names,
streets, buildings) match the same things in OpenStreetMap. Everything the app shows on the map
from a plan uses that function:
- the plan image tiles;
- the zone labels;
- the zone areas;
- the plots.

```
PDF annex ──plan_sheets.py──► sheet images (+ text with pixel positions: PDF text layer or OCR)
                                     │
OSM (OpenFreeMap vector tiles) ──osm_ref.py──► buildings, roads, named streets
                                     │
                              plan_georef.py  ──(image plans)──►  plan_fit.py
                                     │
                  fit per sheet: scripts/plans/<key>.json
                                     │
         ┌───────────────────────────┼──────────────────────────────┐
   map tiles                  zone labels                 zones / plots
public/tiles/<key>/   public/data/zone-labels-<key>.geojson   plan_zones.py, plan_parcels.py
```

`scripts/pipeline.py <key>` runs the steps in order:

| Step | What it does | Script |
|---|---|---|
| sheets | PDF annex → sheet images, plus the text layer for vector pages | `plan_sheets.py` |
| ocr | text recognition on scanned sheets with no text layer | `plan_ocr.py` |
| labels | targeted re-read of the zone codes | `plan_zone_labels.py` |
| georef | fit each sheet to OSM, cut tiles, place zone labels | `plan_georef.py` (+ `plan_fit.py`) |
| zones | zone areas | `plan_zones.py` |
| parcels | plots | `plan_parcels.py` |

You can resume a run with `--from` or run one step with `--only`. Everything specific to a
municipality is in `districts/<key>.json`; `scripts/district.py` fills in the defaults.

## 1. Sheets: from the PDF to images (`plan_sheets.py`)

The annex is downloaded from njt (`njt.py`). Each PDF page then becomes one sheet image, handled
according to what kind of page it is (`plan_probe.py` decides by the size of the page's content
stream):

- **Scanned page:** the page is one big embedded image. That image is extracted byte for byte,
  without re-encoding (Budapest XX).
- **Vector page (CAD export):** the page is rendered at `plan.dpi`. The PDF's own text (street
  names, zone codes, plot numbers) is read with its exact position and rotation, so no OCR is
  needed. It is written in the same JSON format the OCR produces, so later steps cannot tell
  the two apart.
  - Pages rotated inside the PDF are handled.
  - Fonts without a Unicode map are decoded (`plan.font_fix`; Budapest I printed "XWFD" for
    "utca").
  - Text printed 30 times over itself to look bold is kept once.
- **Image annex** (`.png`/`.jpg`, Csobánka): the image is the sheet.
- **Raster strips** (`plan.rasterize_dpi`, Budapest II and VIII): a page made of many image strips
  is rendered as one image.

`plan.pages` picks the map pages and leaves out legend and title pages.

## 2. Text with positions (`plan_ocr.py`)

Scanned sheets have no text layer. RapidOCR is run on 1600 px tiles that overlap by 250 px.
Labels found twice in an overlap are merged, keeping the more confident reading. Every label has
its text, its confidence and its rotated box in sheet pixels. The street names among these labels
are the first anchor of the georeferencing.

## 3. The reference: OSM from the basemap's own tiles (`osm_ref.py`)

All reference geometry comes from the OpenFreeMap vector tiles at zoom 14. These are the same
tiles the app draws its basemap from, so the plan is aligned to exactly what the user sees under
it.

| Function | Returns | Layer |
|---|---|---|
| `fetch(bbox)` | building outlines and road centre lines | `building`, `transportation` |
| `named_roads(bbox)` | every OSM way of each named street, keyed by name | `transportation_name` |

`named_roads` matters because Nominatim's search returns only some ways of a street; fits based
on that partial geometry ended up 100 m or more off. Tiles are cached in `scripts/.cache/`.

All fitting is done in **local metres** (`plan_georef.Local`): an equirectangular projection
around the settlement's centre, accurate to well under a metre across a district. Coordinates are
converted to longitude and latitude only at the end.

## 4. Fitting a sheet

There are two routes, chosen by `plan.kind` in the config.

### Route A: scanned plans of unknown scale (`plan_georef.py`; Budapest XX)

A scan is not a clean similarity of the map: paper and scanner distort it a little, and the scale
is unknown. So the model is a **2-D polynomial** from pixels to metres (`PolyModel`): order 1 is
affine, and orders 2–3 absorb the scan's bending.

1. **Coarse fit from street names** (`fit_sheet`).
   - Every OCR line that parses as a street ("Ady Endre utca", with OCR fixes like "utoa" → "utca")
     is looked up in OSM by name, via Nominatim, inside the district's box. Six or more matched
     labels are needed.
   - The fit starts from street centroids: the mean label position of each street against the
     mean point of that street in OSM gives a first affine.
   - Then **ICP** (iterative closest point): each label is moved to the nearest point of *its own*
     street. The correspondence is by name, so a label cannot snap to the wrong street. The affine
     is re-solved by least squares.
   - Labels further than 3 × the median residual (at least 8 m) are dropped as outliers.
   - It repeats until stable. The script prints the residual (median and 90th percentile, in m)
     and the scale in metres per pixel.
2. **Fine fit on road crossings** (`refine`).
   - A single long street only pins the plan across its direction. Crossings pin both axes.
   - From the OSM roads, every point where two roads crossing at more than 50° meet is found
     (`road_intersections`), at most one per 8 m cell.
   - The plan's streets are the yellow street-fill bands (the `street` style). A distance
     transform of that mask is deepest along each band's centre line.
   - For each crossing (`match_intersections`), the road points within 30 m are shifted by every
     offset up to ±20 px. The shift that puts them deepest inside the yellow bands wins.
   - A match is skipped when the score is flat, sits at the edge of the search window, or has a
     second peak above 85 % of the best one. Ambiguous crossings vote for nothing.
   - The polynomial is re-fitted on the matched crossings at order 1, then 2, then 3, with
     outliers dropped at each stage (residual > 3 × median, at least 1 m). The offset statistics
     are printed before and after.

### Route B: plans at a known scale (`plan_fit.py`, `plan.kind: "image"`)

This covers CAD exports, as rendered vector pages or as images: Csobánka and Budapest I, II, V,
VI and VIII. Such a sheet is an exact similarity of the national grid (EOV). Only four numbers
are unknown: the position (2), a small rotation (EOV grid north is not true north) and a small
scale correction. The scale is known from the printed scale and the dpi:
`metres per pixel = plan.scales[i] × 0.0254 / dpi`.

1. **Match street names to OSM streets** (`match_labels`).
   - The settlement's named OSM streets come from `named_roads`, plus a buffer around the
     boundary (`plan.street_buffer_deg`) for streets on the edge.
   - Names are compared without accents. "Hanfland" matches "Hanfland körút" by its base name. A
     misread suffix is stripped. OCR slips are accepted only when one street is clearly the
     closest (similarity ≥ 0.86 and 0.06 ahead of the runner-up).
2. **Hough voting** (`vote`). No starting guess is needed, and a wrong match cannot pull the
   result.
   - Rotations and scale factors are tried on a small grid. The ranges default to ±1.5° and
     0.97–1.03, and can be widened with `plan.rotation_search_deg` and `plan.scale_search`.
   - For each rotation and scale, every label votes for all the translations that would put it
     within 14 m of its street, on a 4 m grid.
   - Correct matches pile their votes on one cell; wrong matches scatter theirs. The strongest
     peak gives rotation, scale and position.
3. **Label ICP** (`refine_labels`). The labels that agree with the peak are moved to the nearest
   point of their street, and the similarity is solved by least squares. The tolerance tightens
   each round to 3 × the median, but not below 6 m.
4. **Building refinement** (chamfer matching). Building outlines are about the most precise thing
   on both maps.
   - OSM building outlines, sampled every 0.5–1 m, are projected onto the sheet.
   - The plan's building lines (the `building_line` style, dark lines by default) are turned into
     a distance map.
   - The similarity is optimised so the outlines fall on the plan's lines, using a robust loss
     with each point's distance capped at 3 m.
   - The result is accepted only when it is clearly better (median at least 5 % smaller) and
     moves the plan less than 25 m.
5. **Independent checks**:
   - the road-crossing fit of Route A, run on the plan's street bands; its difference from the
     final fit is reported;
   - the street-name residual, recomputed under the final fit.
6. **Acceptance.** A sheet is refused when either check exceeds 10 m. `plan.max_building_median_m`
   sets a stricter bar on the building check (3 m in Budapest II and VIII).

Special cases, each switched on in the config:

- **`register_to: [null, 0]`.** An overview sheet with few names is matched to a detail sheet
  that is already fitted.
  - Edge images are matched by template matching, then refined to a fraction of a pixel with ECC
    (`register_to_sheet`).
  - The overview sheet then inherits the detail sheet's fit. Csobánka's 1:7000 sheet is placed
    on its 1:3000 sheet this way.
- **`register_to: [{key, sheet, crop, style}]`.** The same, across two regulations drawn on one
  base map.
  - Budapest VI.'s second KÉSZ is placed by finding a cropped piece of its blue plot lines in the
    first plan's sheet, by normalised cross-correlation.
- **`grid_fallback`.** A sheet with too few street names (forest, a railway yard) is placed in
  one of the eight positions next to a fitted sheet of the same series. Sheets of a series abut
  along their frames.
  - The position is kept only if the buildings fit clearly: median under 3 m, and every
    alternative position at least 1.5 × worse.
- **`skip_unfit`.** A sheet that fails every check is left out, with the reason recorded. No tiles
  or labels come from it. This is why Budapest II and VIII have some sheets missing.
- **`blank` and `frames`.** These mark the legend, title block and inset maps, so they are neither
  tiled nor read as zone labels.

### Route C: vector PDFs read as geometry (`plan_vector.py` + `plan_roadmatch.py`; review page)

This route is experimental and used only for the review bundles of the village sample plans.

- **Street-name similarity fit** (`fit_similarity`).
  - The page's y axis runs down while the map's runs north, so the page is flipped first.
  - The similarity is solved with Umeyama's method, and ICP is restarted from 24 rotations × 5
    scales, because a label only fixes a position *somewhere along* its street.
  - A median residual under 8 m is accepted as is. Győrsövényház fits to 1.1 m.
- **Road-network matching** (`plan_roadmatch.py`), for plans that name too few streets.
  - The plan's linework becomes a "corridor map". A road centre line placed correctly runs
    1.5–14 m from the plot lines on both sides and never across them.
  - All shifts are scored at once by FFT cross-correlation, for a sweep of scales around the
    printed "M=1:xxxx" and rotations of ±8°. The best result is then polished with a Powell
    optimiser.
  - **It is still unreliable:** on Győrsövényház it picks about 3× the true scale. It is not used
    for anything shown in the app.

## 5. What a fit is and where it is stored

Every route ends with a `PolyModel` per sheet. A known-scale similarity is stored as an order-1
`PolyModel`, so all later steps read every plan the same way. It holds the polynomial order and
coefficients, plus the centre and scale the pixel coordinates are normalised with.

- It is saved in `scripts/plans/<key>.json`, together with the `Local` origin. Each sheet's fit
  is written as soon as it exists, since fitting is the slow part.
- `--reuse-fit` re-renders tiles and labels from the saved fit without fitting again.
- `PolyModel.inverse()` fits the map → pixel direction on a 60 × 60 grid, two orders higher, and
  asserts it is exact to half a pixel.
- Route B also writes a report per sheet, `scripts/plans/<key>-fit-<i>.json`. Here is the one for
  Csobánka sheet 0:

```json
{"labelsMatched": 31, "labelsOnStreet": 29, "labelResidualMedianM": 1.69,
 "buildingMedianM_initial": 1.88, "buildingFitShiftM": 3.46, "buildingMedianM": 1.72,
 "rotationDeg": 0.0459, "scaleFactor": 0.99552, "streetBandFitDiffMedianM": 1.96}
```

## 6. Using the fit

**Map tiles** (`render_tiles`):

1. For every web-map tile (z13 to `plan.maxzoom`, 17 for new municipalities) that touches the
   district polygon, the tile's three corners are converted to metres and then, with the inverse
   model, to sheet pixels.
2. Those three points define an affine transform, exact to a fraction of a pixel within one 256 px
   tile even when the model is cubic.
3. Only the tile's footprint is cropped from the sheet before resampling, which makes rendering
   about 300× faster.
4. Zoomed out, the source is averaged first, so fine hatching does not alias into moiré.
5. Where sheets overlap, all of them are laid down, and then their non-white ink is laid on top.
   White paper margins never cover the neighbouring sheet's drawing. With
   `overlap: "first-wins"`, a detail sheet covers the overview under it instead.
6. Pixels outside the district (or outside the regulation's own area, `plan.clip`) are
   transparent. Tiles are saved as WebP in `public/tiles/<key>/{z}/{x}/{y}.webp`.

**Zone labels.** Each zone code found on a sheet (from OCR, the text layer, or the targeted
re-read) is placed through the model. Codes outside the district are dropped, and the rest are
written to `public/data/zone-labels-<key>.geojson`.

**Zone areas and plots.** `plan_zones.py` and `plan_parcels.py` trace areas and plots in sheet
pixels and convert their outlines with the same model.

**regulations.json.** The regulation's `plan` entry gets:
- the tile URL template;
- the bounds;
- the zoom range;
- for a regulation covering part of a district, its `area` polygon, which the app uses to pick the
  regulation for a tapped point.

**In the app** (`src/main.ts`), the tiles are a MapLibre raster layer over the OpenFreeMap
basemap. The opacity slider fades between the plan and the basemap, so you can check the
alignment yourself.

## 7. How accurate it is, and how that is measured

Each fit is measured against things it was not (only) fitted on:
- **street-name residual:** the distance from each label to its own OSM street;
- **building median:** the distance from OSM building outlines to the plan's building lines;
- **street-band check:** the difference between the crossing-based fit and the final fit;
- **visual check:** tiles overlaid on the basemap.

Typical results:
- **Csobánka:** about 1.5–2 m.
- **Budapest I, II, V, VI, VIII:** building median 0.9–2.9 m per sheet, street names about
  1.0–1.6 m.

These figures also include OSM's own error, which is often around 1 m.

## 8. Known weaknesses

- Route A still looks up street geometry through Nominatim, which can return only some ways of a
  street. Routes B and C use the complete geometry from the vector tiles. Switching Route A over
  is a small change, not yet done because XX already fits well.
- Plans with almost no street names rely on `grid_fallback` (needs a fitted neighbour sheet) or
  are left out. Road-network matching, meant to solve this, does not yet find the right scale.
- The printed scale is not always the true one: Budapest II sheet 1 fits at about 1:1778 and the
  VIII scans at 1:2120–1:2190 against a printed 1:2000. The scale search must be wide enough
  (`plan.scale_search`).
- One similarity per sheet assumes the sheet is undistorted. That holds for CAD exports but not
  for scans of paper, which is why scans go through Route A's polynomial.

## Running it

```bash
python3 scripts/pipeline.py <key>                 # everything
python3 scripts/pipeline.py <key> --only georef   # refit (or re-render with a saved fit)
python3 scripts/registry.py export <key>          # write the municipality's registry fragment
```
