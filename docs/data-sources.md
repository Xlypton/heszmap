# Better data sources for heszmap (checked 2026-10-09)

Every service marked "tested" was queried from the cloud environment on 2026-10-09. Nothing was bulk-downloaded.

> ## ⚠️ IMPORTANT: licensing is NOT cleared
> Peti decided on 2026-10-09 that heszmap is a proof of concept, so these sources may be used now (as selectable overlays and inside the pipelines) **without asking permission first**.
> **Before any public launch or wider use, get written permission or confirm a reuse license for every source below.** None of them states a reuse license, and the Budapest and OÉNY services are only meant to be served to their own web apps.
> - OÉNY / Lechner land-registry map (national plots): ask Lechner Tudásközpont, téradat-szolgáltatás (teradatszolgaltatas@lechnerkozpont.hu). The data is "nem közhiteles" (not authoritative).
> - Budapest city GIS (plots, KÉSZ, FRSZ/TSZT, orthophotos): ask Budapest Közút Zrt. (kapu@budapestkozut.hu) or the Főváros.
> - Lechner INSPIRE orthophotos: viewing only (newer than 10 years is free only to 1:50,000).
> - Show attribution ("© Lechner Tudásközpont", "© Budapest Közút Zrt.") on every overlay meanwhile.
> - Be gentle: OÉNY's address/parcel API answered "IP permanently blacklisted" after a handful of test calls. Do not script that API. The WMS still worked. Throttle tile fetches and cache them.

## National (all of Hungary)

### N1. OÉNY land-registry map: plot lines + hrsz + buildings, whole country (tested)
- **What:** the map behind Lechner's free HRSZ finder (https://www.oeny.hu/oeny/hrsz-kereso/, launched October 2025, no login). It is the state land-registry map (ingatlan-nyilvántartási térkép), refreshed about monthly.
- **Service:** GeoServer WMS `https://www.oeny.hu/hk-geoserver/hrsz/wms`, layers `hrsz:foldreszlet` (plot lines), `hrsz:epulet` (buildings) and `hrsz:felirat_kat` (hrsz labels). Any EPSG:4326 or EOV bbox works. There is also a basemap WMTS `/hk-fomi-mapservice/nta/lf/hrszkereso/wmts` (EOV).
- **Tested:** GetMap over Budapest VIII returned crisp black plot lines with hrsz labels (35283 to 35301), and Veszprém worked too. GetCapabilities, GetFeatureInfo and WFS fail on a server charset bug, so it is images only, not vectors.
- **Verdict:** best national source. Rendering it at high resolution gives clean line art with hrsz text. Feeding that into the existing raster plot-tracing pipeline should make plots accurate in any town, VIII included, far better than tracing scanned plans. It also works as a user-selectable "plots" overlay. Licensing: see the warning above.

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
