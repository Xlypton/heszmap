# HÉSZ térkép

Map for architects: search an address in Budapest and see which local building regulation
(HÉSZ / KÉSZ) zone applies, with the key limits. Every value cites its paragraph and opens
the regulation PDF at that exact place, highlighted.

> Prototype. The XI. district zones and the PDF in `public/docs/` are **DEMO data**, not real regulation.

## Run

```sh
npm install
npm run dev        # http://localhost:5173
npm run build      # static site in dist/
```

## Deploy (Cloudflare Pages)

Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git → pick this repo.
Build command `npm run build`, output directory `dist`. Every push deploys; each branch gets a preview URL.

## Data (`public/data/`)

| File | What |
|---|---|
| `districts.geojson` | 23 district boundaries from OSM (`npm run fetch:districts`) |
| `zones.geojson` | Zone polygons: `{ code, regulation }` |
| `zone-types.json` | Zone limits; each value is `{ value, cite: { reg, page, para, quote } }` |
| `regulations.json` | Regulation metadata: local PDF mirror, official URL, retrieval date, sha256; per-district coverage |

A citation's `quote` is the anchor and `page` is only a hint: if a newer PDF version moves the text,
the viewer searches the whole document. Regulation PDFs are mirrored locally because the official
sites don't allow cross-origin loading, and the mirror pins the exact version each citation was checked against.

`scripts/make-demo-doc.mjs` regenerates the demo PDF and its cited zone data.
