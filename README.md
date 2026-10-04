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

```sh
# 1. Regulation text -> PDF + every zone's limits with citations (each quote verified against the PDF)
NODE_USE_ENV_PROXY=1 node scripts/ingest-kesz.mjs xx

# 2. OCR the scanned zoning plan sheets (annex 2.a), one JSON per sheet
pip install rapidocr-onnxruntime pillow numpy
python3 scripts/plan_ocr.py sheet0.jpg ocr0.json

# 3. Georeference the sheets from their street-name labels (fit to OSM streets),
#    cut map tiles, and geolocate the zone labels
python3 scripts/plan_georef.py xx sheet0.jpg:ocr0.json sheet1.jpg:ocr1.json
```

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
