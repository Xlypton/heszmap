# HÉSZ térkép

Map for architects: search an address in Budapest and see which local building regulation
(HÉSZ / KÉSZ) zone applies, with the key limits. Every value cites its paragraph and opens
the regulation PDF at that exact place, highlighted.

> Prototype. Processed so far: **XX. kerület (Pesterzsébet)**, KÉSZ 26/2015. (X. 21.), consolidated text in force from 2026-04-03.
> Zone at an address is *estimated* from the nearest zone label on the official plan; always check the plan layer.

## Run

```sh
npm install
npm run dev        # http://localhost:5173
npm run build      # static site in dist/
```

## Deploy (Cloudflare Workers Builds)

The `heszmap` Worker is connected to this repo. On push Cloudflare runs `npm run build`, then
`npx wrangler deploy`, which serves `dist/` as static assets (see `wrangler.jsonc`).

## Data pipeline (per district)

Each municipality has a config, `districts/<key>.json`: its regulation (njt id), its plan annexes,
and how its plan draws each element (`styles`: colour rules for plot lines, zone codes, zone
boundaries, regulation lines and streets; see `scripts/district.py`). Defaults follow the most common
convention, so a district only lists what differs.

```sh
# Regulation text -> PDF + every zone's limits with citations (each quote verified against the PDF)
NODE_USE_ENV_PROXY=1 node scripts/ingest-kesz.mjs xx
python3 scripts/extract_rules.py xx && python3 scripts/extract_effective.py xx

# Plan: annex PDFs -> sheets -> OCR (scans only) -> zone codes -> georeference + tiles -> zones -> plots
pip install rapidocr-onnxruntime pillow numpy scipy opencv-python-headless shapely pymupdf
python3 scripts/pipeline.py xx            # all steps
python3 scripts/pipeline.py xx --from zones
```

| Step | Script | |
|---|---|---|
| sheets | `plan_sheets.py` | Scanned page: embedded image as is. Vector page: rendered, and its text layer exported as the OCR result |
| ocr | `plan_ocr.py` | RapidOCR on scanned sheets |
| labels | `plan_zone_labels.py` | Re-reads every zone code in the zone-code style, snapped to the regulation's code list |
| georef | `plan_georef.py` | Fits sheets to OSM streets (labels, then road intersections); cuts tiles |
| zones | `plan_zones.py` | Zone cells: labels spread up to boundaries/regulation lines/streets; text cross-check |
| parcels | `plan_parcels.py` | Plots from plot lines, their zone(s), OSM checks |

Other municipalities: `scripts/njt.py search "helyi építési szabályzat"` lists every decree in force
(njt.jog.gov.hu), `njt.py annexes <id>` its annex PDFs; `plan_probe.py` says whether a plan is a scan
or vector and whether its legend is readable; `plan_vector.py` reads a vector plan directly (legend
styles → boundaries → plots → zones). See `docs/plan-survey.md` for a survey of plans across the country.

| File | What |
|---|---|
| `public/data/districts.geojson` | 23 district boundaries from OSM (`npm run fetch:districts`) |
| `public/data/regulations.json` | Per regulation: PDF copy, official URL, version date, sha256, annex links, plan tiles; per-district coverage |
| `public/data/zone-types-xx.json` | Zone limits as printed (`text`), parsed (`num`), and cited (`cite: { reg, page, para, quote }`) |
| `public/data/zone-labels-xx.geojson` | Zone code labels read from the plan, as points |
| `public/docs/xx-kesz.pdf` | The consolidated regulation text rendered unchanged from njt.jog.gov.hu, with source header |
| `public/tiles/xx/` | Georeferenced zoning plan tiles |

A citation's `quote` is the anchor and `page` only a hint: if a newer version moves the text, the viewer
searches the whole document, and warns when the quote is gone.
