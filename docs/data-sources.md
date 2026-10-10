# Better data sources for heszmap (checked 2026-10-09)

A second, independent survey (2026-10-10) with more sources, among them the Danube-bank regulation (DÉSZ) zones, the XVII. KÉSZ in GIS form, the EOV correction grid, the monument register API and Budapest's local protection list: [data-sources-survey.md](data-sources-survey.md).

Every service marked "tested" was queried from the cloud environment on 2026-10-09. Nothing was bulk-downloaded.

> ## ⚠️ IMPORTANT: licensing is NOT cleared
> Peti decided on 2026-10-09 that heszmap is a proof of concept, so these sources may be used now (as selectable overlays and inside the pipelines) **without asking permission first**.
> **Before any public launch or wider use, get written permission or confirm a reuse license for every source below.** The full list, with who to ask, is the **Permission register** just below. None of them states a reuse license, and the Budapest and OÉNY services are only meant to be served to their own web apps.
> - OÉNY / Lechner land-registry map (national plots): ask Lechner Tudásközpont, téradat-szolgáltatás (teradatszolgaltatas@lechnerkozpont.hu). The data is "nem közhiteles" (not authoritative).
> - Budapest city GIS (plots, KÉSZ, FRSZ/TSZT, orthophotos): ask Budapest Közút Zrt. (kapu@budapestkozut.hu) or the Főváros.
> - Lechner INSPIRE orthophotos: viewing only (newer than 10 years is free only to 1:50,000).
> - Show attribution ("© Lechner Tudásközpont", "© Budapest Közút Zrt.") on every overlay meanwhile.
> - Be gentle: OÉNY's address/parcel API answered "IP permanently blacklisted" after a handful of test calls. Do not script that API. The WMS still worked. Throttle tile fetches and cache them.

## Permission register: every source heszmap uses (checked 2026-10-09)

This is the list to work through before a public launch. "Ask" means written permission is needed first; "Conditions" means no permission is needed, as long as the stated rules are followed. Where a contact is marked "not verified", it was not confirmed from an official page.

| # | Source | Where heszmap uses it | Needs | Who to ask / contact |
|---|---|---|---|---|
| 1 | **Budapest city GIS plots** (FRSZ layer 9 "Telekhatár", Budapest Közút ArcGIS) | Pipeline: `scripts/fetch_btp_parcels.py` builds the plot outlines for II, V, VIII and X. **The app serves these outlines publicly** (`public/data/parcels-ii`, `-v`, `-viii`, `-x`), which is redistribution of their data. | **Ask** (highest priority) | Budapest Közút Zrt., which runs the Budapest Térinformatikai Portál: kapu@budapestkozut.hu. The data may belong to the Főváros (Budapest Főváros Önkormányzata, Városépítési Főosztály), so ask them to confirm who can grant it. |
| 2 | **Budapest city GIS map layers**: 2024 orthophoto, FRSZ, TSZT, VI KÉSZ | App: "Légifotó 2024", "FRSZ", "TSZT" and "VI. kerület KÉSZ" overlays, through the tile proxy in `worker/index.js`. Pipeline: `scripts/sources.py bp-zones-vi`. | **Ask** | Same as #1. |
| 3 | **OÉNY land-registry map** (Lechner, `hk-geoserver/hrsz/wms`) | App: "Telekhatárok, hrsz" and "Épületek" overlays. Pipeline: `scripts/oeny_parcels.py` builds the plots, zone areas and built-up share for XX and Csobánka. **The app serves these outlines publicly** (`parcels-xx`, `parcels-csobanka`). | **Ask** | Lechner Tudásközpont, téradat-szolgáltatás: teradatszolgaltatas@lechnerkozpont.hu. Mention that the map is used as "nem közhiteles" reference only. |
| 4 | **Lechner INSPIRE orthophoto 2015** | App: "Légifotó 2015" overlay (proxied and cached). | **Ask** to cache and re-serve it. Viewing 10+ year old imagery at 1:2,000 is free, but proxying it through our own server is not covered. | Lechner Tudásközpont: teradatszolgaltatas@lechnerkozpont.hu |
| 5 | **Regulation texts and plan annexes from Nemzeti Jogszabálytár** (njt.jog.gov.hu): the KÉSZ/HÉSZ decrees, their plan PDFs and the scanned PNG plans (Csobánka) | Pipeline: `scripts/ingest-kesz.mjs`, `njt.py`, `extract_*.py` and the whole plan pipeline (sheets, OCR, georeferencing, zones, plots). App: rule text, plan tiles shown on the map, zone areas and zone labels derived from the plans. | **Probably none, but confirm.** Under Szjt. 1. § (4), laws and other legal rules are not protected by copyright, and the plan annexes are part of the local decree. The plans are drawn by private planning firms, so get a short written confirmation from each municipality before launch. | Each municipality's chief architect (főépítész) for its plans; the contact is on the municipality's website (not verified). For the NJT site itself: the Igazságügyi Minisztérium, which runs it, via the contact page on njt.jog.gov.hu (not verified). |
| 6 | **Pesterzsébet Településképi Arculati Kézikönyv** (pesterzsebet.hu PDF) | App: linked from the XX regulation entry (`scripts/ingest-kesz.mjs`). Only linked, not copied. | **None** while it is only a link. Ask before copying images or text from it. | XX. kerület Pesterzsébet Önkormányzata, főépítészi iroda (not verified). |
| 7 | **OpenStreetMap data via OpenFreeMap tiles** | App: basemap (`tiles.openfreemap.org/styles/liberty`). Pipeline: `scripts/osm_ref.py` reads roads and buildings from the same tiles to georeference plans and to find streets. | **Conditions**: ODbL attribution "© OpenStreetMap contributors" (and "OpenFreeMap © OpenMapTiles") visible on the map. No permission needed. | None. |
| 8 | **Nominatim** (nominatim.openstreetmap.org) | App: address search (`src/geocode.ts`). Pipeline: district boundaries (`fetch_districts.py`, so `districts.geojson` and `registry/*.json` are OSM data), plan georeferencing (`plan_georef.py`), and protected-building points in XX (`protected-xx.geojson`, `source: "geocode"`). | **Conditions, and a change before launch.** The public Nominatim usage policy allows at most 1 request per second and forbids heavy or autocomplete use, so a public app should switch to its own Nominatim or a paid geocoder. Files built from OSM (boundaries, geocoded points) are ODbL data: keep the attribution, and share-alike applies to them. | None for permission. The usage policy is at operations.osmfoundation.org/policies/nominatim. |

Data this repo builds itself (zone areas, zone labels, rule tables) inherits the conditions of the source it was built from: from the plans (#5), and from the city GIS (#1) where plots come from there.

## National (all of Hungary)

### N1. OÉNY land-registry map: plot lines + hrsz + buildings, whole country (tested)
- **What:** the map behind Lechner's free HRSZ finder (https://www.oeny.hu/oeny/hrsz-kereso/, launched October 2025, no login). It is the state land-registry map (ingatlan-nyilvántartási térkép), refreshed about monthly.
- **Service:** GeoServer WMS `https://www.oeny.hu/hk-geoserver/hrsz/wms`, layers `hrsz:foldreszlet` (plot lines), `hrsz:epulet` (buildings) and `hrsz:felirat_kat` (hrsz labels). Any EPSG:4326 or EOV bbox works. There is also a basemap WMTS `/hk-fomi-mapservice/nta/lf/hrszkereso/wmts` (EOV).
- **Tested:** GetMap over Budapest VIII returned crisp black plot lines with hrsz labels (35283 to 35301), and Veszprém worked too. GetCapabilities, GetFeatureInfo and WFS fail on a server charset bug, **but GetMap with `format=application/vnd.google-earth.kml+xml` returns the plots as vector polygons with `hrsz`, `ksh_kod`, `fekves` and `obj_fels`**. A 0.01° cell in VIII returns 678 plots (about 2 MB, 7 s).
- **In the repo:** `scripts/sources.py oeny-parcels <district>` (and `oeny-buildings`) fetches them as GeoJSON, throttled and cached. The app's "Telekhatárok, hrsz" overlay shows the line art through the tile proxy in `worker/index.js`.
- **In the pipeline:** `scripts/oeny_parcels.py <key>` (after `plan_zones.py`) replaces the traced plots of a municipality with these: every plot gets its hrsz, its zones from the plan's zone areas, and its built-up footprint from `hrsz:epulet`. The app's zone areas are then drawn along these plot lines (`zone-plots-<key>/`). `scripts/hrsz_index.py` builds the parcel-number search. Used for XX and Csobánka since 2026-10-09; Budapest districts on the city GIS keep `fetch_btp_parcels.py`.
- **Verdict:** best national source. It gives official plot shapes with hrsz for any town, with no tracing needed. Licensing: see the warning above.

### N2. Lechner INSPIRE services (tested)
- Orthophotos for 2000 to 2025 (`inspire.lechnerkozpont.hu/geoserver/OI.<year>/wms`). 2015 and older is sharp; newer years are blurred to 12.5 m for public use.
- Free administrative boundaries (AU.2025), geographic names (GN.2026) and a DEM.
- Cadastral parcels and buildings there are sample areas only.

### N3. OpenStreetMap (known)
- Buildings and addresses for the whole country, under ODbL (free with attribution). No plots.

### Zoning (HÉSZ/KÉSZ) nationally
- There is no free national vector zoning source yet. Plans adopted since 2022 must be uploaded to Lechner's E-TÉR as shapefiles, but its public viewer shows only regional plans so far. Re-check later.
- Some towns run public GIS portals with their plans (vendors such as Minerva, ErdaGIS; e.g. Érd, Szombathely, Újbuda). Check case by case when a town is onboarded.
- njt.hu plan PDFs remain the national source.

## Budapest (ranked)

### 1. Budapest city GIS: plot outlines with hrsz for every district (tested)
- **What:** the "Hrsz" layer behind Budapest's public map apps, which Budapest Közút Zrt. runs on ArcGIS Online (org `U5XLnNfWSBVhIdqv`, "Budapest Térinformatikai Portál").
  `…/btp_varosterkep/Kompakt_varos/MapServer/1`, proxied via `utility.arcgis.com/usrsvcs/servers/6bfb82a58b904f9b96ca1316e0c039de/rest/services/…`
- **Content:** 183,861 plot polygons with an `hrsz` field, covering all of Budapest. Item last modified 2024-09-10.
- **Coverage spot checks (plots in a small test box):** VIII 2,007 (e.g. hrsz 35288, 35510), II 2,317, XIV 3,587, X 1,390, V 654, I 544.
- **Format:** ArcGIS REST MapServer query, JSON/GeoJSON, any output CRS, up to 1,000,000 records per request.
- The FRSZ and TSZT services (below) also have `Telekhatár` and `HRSZ` layers. Their service text is dated 2026-06-24, so they may be fresher than this one.
- **Access:** the proxy only answers requests that carry the Referer of their ArcGIS apps (e.g. `https://budapestkozut.maps.arcgis.com/`). Without it, you get a 403. No license is stated on the item.
- **Verdict:** this is the best fix for plot outlines, including VIII. It would replace PDF tracing of plots for all Budapest districts. Since it is only served to their own apps and no license is stated, ask before building on it. Contact Budapest Közút (`kapu@budapestkozut.hu`, the address on their district portals) or the Főváros.

### 2. Same portal: district KÉSZ as vector, VI now (tested)
- `…/terezvaros/terezvaros_publikus/MapServer` holds VI KÉSZ-1 (23/2019) and KÉSZ-2 (35/2020). Layers include building-zone boundaries and zone codes (34, 81, 82), regulation lines, plot lines "Telekhatár KÉSZ", buildings from the land-registry map, and protected buildings.
- Layer 34 has zone polygons with `ovezeti_jel` (zone code), `beep_max` (max coverage), `szm_*` (floor-area ratio), `zold_min` (min green), `epmag_min` and `epmag_max` (height), `telek_m` (min plot size), and `kész`.
- Óbuda (III) and Rákosmente (XVII) have similar public district services, which would help if those districts get onboarded. The Terézváros web portal itself needs a login, but its map service is used by a public StoryMap.
- **Verdict:** VI zones and limits could come straight from vector data, with no tracing. Same permission caveat as #1.

### 3. Same portal: Budapest framework plans FRSZ / TSZT as vector (tested, layer lists only)
- `…/btp_frsz/frsz_2021/MapServer` and `…/btp_tszt/tszt_2021/MapServer`, with the service description dated 2026-06-24.
- They contain land-use units (területfelhasználási egységek), building density, height limits and height-regulated areas, world-heritage zones, and protected built environment.
- Budapest adopted a new FRSZ, 3/2026 (II.12.). It is unconfirmed whether these services already carry it; the name still says 2021. (Inferred from a search result; not checked.)
- **Verdict:** a useful second layer, giving city-level density and height on top of the district KÉSZ. Same permission caveat.

### 4. Same portal: 2024 Budapest orthophoto (tested)
- `…/ortofoto/ortofoto_2024_2_rgb_wgs/MapServer` is a cached Web Mercator tile set down to about 2 cm per pixel. There are also 2005 to 2022 years, plus colour-infrared versions.
- A test tile in VIII was sharp, with individual roofs and courtyards visible.
- **Verdict:** a good basemap and a good check for traced outlines. Same permission caveat (copyright: Budapest Közút Zrt.).

### 5. Lechner national orthophotos (INSPIRE WMS) (tested)
- `https://inspire.lechnerkozpont.hu/geoserver/OI.<year>/wms`, layer `OrthoimageCoverage<year>`, 2000 to 2025.
- **Terms:** imagery under 10 years old is free to view only down to 1:50,000 (12.5 m pixels). A 2023 to 2025 test tile over VIII was a blur. Imagery 10 or more years old is free to view down to 1:2,000. The 2015 test tile was sharp at plot level, but 2016 was still blurred.
- **Verdict:** 2015 can be used now as a free background or for checking outlines. Newer years are useless at plot zoom.

### 6. OpenStreetMap buildings and addresses (known)
- Free (ODbL). Good building outlines and house numbers in Budapest, but no plot boundaries or hrsz.
- **Verdict:** fine for address search or a building layer, not for plots.

## Not usable
| Source | Why |
|---|---|
| INSPIRE cadastral parcels `CP:CP.CadastralParcels` (Lechner) | Sample only: 1,774 parcels nationwide, 0 in Budapest (tested). |
| INSPIRE buildings `BU:Building` (Lechner) | Sample only: 921 buildings, 0 in Budapest (tested). |
| Land registry (Földhivatal Online, E-ING, TAKARNET) | Map copies are per plot and paid, about 5,000 Ft per plot per a county fee list. Bulk DAT extracts are on request, with a fee and reuse limits. Too costly and restricted for a whole district. |
| e-közmű | Utility data for registered designers. Not a plot or zoning source. |
| E-TÉR (Lechner) | New-type plans since 2022 must be uploaded as shapefiles. Its public viewer currently shows only regional plans (OTrT, BATrT, Balaton); settlement plans are promised "at full launch". Worth re-checking later. |
| TEIR / oeny.hu | Login for authorities only (403). |
| Terézváros district portal (terezvaros.budapestkozut.hu) | Login only. Its data is reachable via #2. |
| opendata.budapest.hu, nta.lechnerkozpont.hu | Did not respond from this environment. |

## Suggested next step
Email Budapest Közút / Főváros asking permission to use the Hrsz plot layer, the district KÉSZ layers and the orthophoto in a free public app with attribution. If they agree, plots for every district (VIII included) can come from #1, and VI zones from #2.
