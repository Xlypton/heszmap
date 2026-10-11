# Public data sources for heszmap

Survey of public data that could make heszmap more accurate and more useful: plots, zones in GIS form,
reference geometry, regulation sources, and other information an architect checks for a plot.
Probed 2026-10-07 to 2026-10-10 from the build machine with `curl` (through the agent proxy). Every test
request was small (one point, one small bbox, `count`/`resultRecordCount` ≤ 3, or a count-only query).

**Status labels used below**

| Label | Meaning |
|---|---|
| **verified** | Requested from this machine; HTTP status and response size are given |
| **verified (Referer)** | Works only when the request carries the `Referer` of the public viewer that uses it (an ArcGIS Online "utility" proxy or a GeoServer behind a Referer filter). Without it: HTTP 403 |
| **documented, not tested** | Described in official pages, not requested (or not requestable without an account) |
| **blocked / login** | Responds, but needs registration, credentials or payment; or the proxy could not reach it |

**Licence caveat.** None of the sources found that carry plot or zone geometry has an open licence
(CC-BY, OGL, etc.) published next to it. Where terms exist they are quoted. "Free to view" in a public
viewer is not a licence to copy data into a product. The integration sketches below say which ones
need written permission first.

Coordinates in examples: EOV (EPSG:23700), `x` = easting (≈ 650 000 in Budapest), `y` = northing
(≈ 239 000). Test point: Vörösmarty tér, Budapest V = WGS84 19.0510, 47.4965 = EOV 650267.9, 239173.7.

---

## 1. Cadastral plots (földrészletek, helyrajzi számok)

| Source | Endpoint | Contents | Coverage | Format | Access / licence | Verified | Use in heszmap |
|---|---|---|---|---|---|---|---|
| **Budapest FRSZ map service, layers `Telekhatár` (9) and `HRSZ` (13)** (Budapest Közút Zrt. for the Főváros; the same parcel layer also appears in the TSZT, DÉSZ, BTVT and FHV services) | `https://utility.arcgis.com/usrsvcs/servers/1f424e22b69d4ea890228a42f375d9ce/rest/services/btp_frsz/frsz_2021/MapServer/9/query` | Parcel polygons with `meb` (hrsz, e.g. `(24432)`), `fekves`, `kerulet`, EOTR sheet, `start_date`/`end_date` (validity) | **All of Budapest: 237 897 parcels**; latest `start_date` 2026-01-01 | ArcGIS REST, `f=json` / `f=geojson`, `outSR=4326` supported; maxRecordCount 10 000 | Public viewer `btp-frsz.budapestkozut.hu`; copyright text "Budapest Közút Zrt."; no licence published. Referer-gated proxy | **verified (Referer)**: service JSON 200, 13 073 B; point query on layer 9 200, 1 315 B (one GeoJSON polygon, hrsz 24432, V. ker.); count query 200, 16 B | **Vector plots for all 23 districts**: replace `plan_parcels.py` traced outlines in Budapest, or use them as the check/snap target. Needs permission (see Top 5) |
| **Lechner HRSZ-kereső backend** (`www.oeny.hu/hk-api`) | `GET https://www.oeny.hu/hk-api/parcels/at?x=<EOV x>&y=<EOV y>` | The parcel at a point: outline (MultiPolygon, EOV, full precision), bbox, settlement KSH code, `lotNumber` (hrsz), `layment` (bel-/külterület), addresses | National (≈ 8 million parcels per the service page) | JSON | Backend of the public app `https://www.oeny.hu/oeny/hrsz-kereso/` ("nyílt és ingyenes helyrajziszám-kereső"). Undocumented internal API, no published terms. **Rate-limited**: a few requests apart returned HTTP 429 | **verified** once: 200, 5 307 B (hrsz 24432, 131-vertex outline). Second request minutes later: **429**, 26 B | On-click lookup "which plot is this, official outline" — but only with Lechner's agreement; it is not meant as a public API |
| HRSZ-kereső parcel raster | `https://www.oeny.hu/hk-geoserver/hrsz/wms` layers `hrsz:foldreszlet`, `hrsz:epulet`, `hrsz:felirat_kat` | Parcel lines, cadastral buildings, hrsz labels as PNG | National | WMS 1.1.0 GetMap only (GetCapabilities, GetFeatureInfo and WFS fail with "Null charset name") | Referer `https://www.oeny.hu/oeny/hrsz-kereso/` required; no published terms | **verified (Referer)**: GetMap 500×500 EOV bbox 200, 57 950 B PNG (parcel lines, transparent). Without Referer: 403 page | A raster overlay of official plot lines nationwide; a georeferencing check target outside Budapest (line-to-line fit of plan plot lines). Permission needed |
| **Lechner HRSZ-lista generátor API ("HRSZ terminátor")** – Lechner's first *documented* open API | `GET https://api.lechnerkozpont.hu/hrsz-terminator/api/hrsz?geojson={"type":"Point","coordinates":[x,y]}` (EOV, ≤ 1 decimal) | Settlement, `fekves`, hrsz of every parcel touching a Point/LineString/Polygon. **No geometry** | National | JSON. Limits: 80 vertices, line ≤ 1 km, polygon ≤ 1 km², ≤ 500 parcels, URL < 2048 chars | OpenAPI: `…/hrsz-terminator/documentation/openapi.yaml`. Terms (ÁFF, 2026-10-06): free within the limits; data **"kizárólag saját céljaira"** (own purposes only), no passing on or reselling; business use needs an individual agreement; public display only with **"Forrás: Lechner Nonprofit Kft."** | **verified**: V point 200, 91 B → `BUDAPEST V.KERÜLET / 1 / 24432`; XX point 200, 93 B → `171115`; Csobánka point 200, 78 B → `35`; 50×50 m polygon 200, 225 B → 3 hrsz. One request got a connection reset, retry worked | Label the clicked plot with its official hrsz (and check our traced plot ids). Allowed use for a public app is unclear: ask Lechner |
| INSPIRE CP (Lechner) | `https://inspire.lechnerkozpont.hu/geoserver/ows` `CP:CP.CadastralParcels` | Parcels | **Sample only: Mesterszállás, 1 774 parcels** (already known) | WFS 2.0 | AccessConstraints NONE | **verified**: hits 200, 722 B | None for coverage area |
| Terézváros (VI) public service, `Telekhatár` layers (67, 74, 299–301) | `https://utility.arcgis.com/usrsvcs/servers/35162649113d4ce494bb6a4129c763bf/rest/services/terezvaros/terezvaros_publikus/MapServer` | Plot polygons with hrsz, block no., street + house number, area, width, depth, corner plot, year built, architect, building height (layer 67) | VI. ker. | ArcGIS REST | Viewer `terezvaros-terinformatika.budapestkozut.hu`; no licence | **verified (Referer)**: service JSON 200, 64 312 B; layer 67 count 56 (KÉSZ-2 area only); other telekhatár layers not counted | Richer per-plot attributes for VI |
| Rákosmente (XVII) public service, "Földhivatali alaptérkép 2025.07.01." group (layers 2–29: földrészlet, alrészlet, épület, …) | `https://utility.arcgis.com/usrsvcs/servers/0bdd54959954484ebbe077b969dfa81b/rest/services/rakosmente/rakosmente_publikus/MapServer` | A full cadastral base map copy (parcels, buildings, walls, fences…) | XVII. ker. (not in heszmap yet) | ArcGIS REST | Viewer; no licence | **verified (Referer)**: service JSON 200, 49 580 B; layer 4 `Földrészlet` count 28 298 | Plots if XVII is added |
| Óbuda (III) public service | `…/f5579d1a4f654ddb85ce3cd182e7d595/rest/services/obuda/obuda_public/MapServer` | Unknown | III. ker. | ArcGIS REST | | **blocked**: 403 with the generic Referer tried (viewer Referer not tried) | – |
| Újbuda (XI) térinformatika | `https://terinfo.ujbuda.hu/` | District GIS | XI. ker. | – | – | documented, not tested | – |
| Geoshop (Lechner) | `https://geoshop.hu/` | "Ingatlan-nyilvántartási térképi adatbázis térinformatikai másolata" (DAT copy), orthophotos, boundaries | National | Files | Free and paid products; DAT copy is a paid product as far as the service page says | documented, not tested | Bulk official plots for a settlement if bought |
| TAKARNET / E-ING, e-ingatlan | – | Land register | National | – | Login / fee | blocked / login (not tested) | – |

**Vector vs raster:** downloadable vector plot geometry exists for all of Budapest (FRSZ service,
Referer-gated, licence unclear) and per point nationally (HRSZ-kereső backend, rate-limited, internal).
National bulk vector plots are not public; the national WMS is raster only.

---

## 2. Zoning plans in GIS form

| Source | Endpoint | Contents | Coverage | Format | Access / licence | Verified | Use in heszmap |
|---|---|---|---|---|---|---|---|
| **Terézváros (VI) KÉSZ-1 (23/2019) and KÉSZ-2 (35/2020) layers** | `…/35162649113d4ce494bb6a4129c763bf/rest/services/terezvaros/terezvaros_publikus/MapServer` — KÉSZ-2: 34 `Építési övezet, övezet jele`, 33 zone boundaries, 37 PM; KÉSZ-1: 82 `Építési övezet jele`, 81 boundaries, 83–85 építési hely/határvonal, 88 PM; plus 2016 and pre-2016 plans | **Zone polygons with limits as attributes**: `ovezeti_jel` (e.g. `Vt-V/VI/5`), `beep_mod`, `telek_m`, `beep_max`, `ta_beep_ma`, `szm_á`, `szm_p`, `zold_min`, `epmag_min/max`, `pm`, `kész` (paragraph, e.g. `KÉSZ-2 19.§`) | The two KÉSZ areas of VI = heszmap `vi.json` (23/2019) and `vi2.json` (35/2020) | ArcGIS REST, GeoJSON | Viewer; no licence; "Budapest Közút Zrt./GIS" | **verified (Referer)**: layer 34 count 19, 3-record sample 200 with full attributes | **Ground truth for VI**: compare our derived zone cells and parsed limits; or use directly with permission |
| **Budapest DÉSZ (Duna-menti Építési Szabályzat)** | `…/5a4bbc3b8dd44cb292bbda2340336d5c/rest/services/btp_desz/desz/MapServer` (27 `Építési övezet, övezet felirata` polygons with `ovezet`, `utem`, `modositas_szama`; 26 zone boundaries; 28 szabályozási vonal; 39 plan extent) | Zones of the Danube-bank regulation (fővárosi rendelet) | Danube banks, all riverside districts incl. I, II, V, XIII, XX parts | ArcGIS REST | Viewer `btp-desz.budapestkozut.hu`; "Budapest Közút Zrt."; service dated 2026-07-08 | **verified (Referer)**: layer 27 count 1 076; sample 200 (`Kt-Kgy`, `KÖk`, `Vf/Ez`) | Plots on the Danube bank are governed by DÉSZ, not the district KÉSZ: detect and show it |
| **Budapest FRSZ 2021** | `…/1f424e22b69d4ea890228a42f375d9ce/rest/services/btp_frsz/frsz_2021/MapServer` layer 36 `Területfelhasználási egységek` (+ 46 height areas, 51 high-rise areas, 40 25 m karakterőrző cornice) | Land-use units with `terfel` (e.g. `Vt-V`), `bs`, `bsa`, `bsp` (beépítési sűrűség) | All of Budapest, 3 608 polygons | ArcGIS REST | as above | **verified (Referer)**: point query 200, 6 440 B (`Vt-V`, bs 6.5) | Show the FRSZ frame (density caps, height areas) the KÉSZ must respect, for every Budapest plot |
| Budapest TSZT 2021 | `…/03ff87e7da1f48c39be230fb703540a4/rest/services/btp_tszt/tszt_2021/MapServer` | Structure plan land use | Budapest | ArcGIS REST | as above | **verified (Referer)**: service JSON 200, 34 167 B | Context layer |
| Budapest VÉSZ (Városligeti ÉSZ) | `…/44b58390cd3146d4be99ec22ac4ce855/rest/services/btp_vesz/vesz_2020/MapServer` | Városliget regulation | XIV (Városliget) | ArcGIS REST | as above | listed in webmap; service not queried | XIV plots in the Városliget |
| Rákosmente (XVII) RKÉSZ | `…/0bdd54959954484ebbe077b969dfa81b/…/rakosmente_publikus/MapServer` layers 61–140 (63 zone codes, 68 zone boundaries, 140 `Övezet, építési övezet`), building bans, protections | Full KÉSZ in GIS | XVII | ArcGIS REST | Viewer; "RKÉSZ 2025" | **verified (Referer)**: service JSON 200 | If XVII is added: zones without tracing |
| Lechner Székesfehérvár test | `https://arcgisserver.lechnerkozpont.hu:6443/arcgis/rest/services/szekesfehervar/…` | `Szekesfehervar_epulet_ovezet` | Székesfehérvár | ArcGIS (AGOL items by a Lechner user) | | documented (AGOL search), not tested | – |
| E-TÉR (Lechner) | `https://www.oeny.hu/oeny/4tr/` | Regional plans (OTrT, BATrT, county plans) as WMS; Helyi Művi Értékvédelmi Kataszter | National (regional, not local plans) | WMS | Public viewer; GeoServer behind it (`oeny.e-epites.hu/geoserver/{otrt,ba,bku}-4tr/ows`, from a BME guide) returns **401 Basic auth** | **blocked**: 401, 720 B | – |
| Budapest V. district map (`otker.intermap.hu/fortemap`) | linked from belvaros-lipotvaros.hu | Legacy FonixMap viewer (Google Maps v3.3) | V | HTML | | 200, 25 245 B; no zoning service found | – |
| ArcGIS Online search | `https://www.arcgis.com/sharing/rest/search?q=…` | Searched "szabályozási terv", "KÉSZ", "HÉSZ", "építési övezet", "telekhatár", "földrészlet" | | | | verified | Only Budapest Közút (`owner:bkk_kozut`, 261 items) and the Lechner test above |

**Machine-readable zone polygons found:** Budapest VI (both KÉSZ), DÉSZ (Danube banks), FRSZ (city-wide
land use, not building zones), XVII (RKÉSZ). Nothing found for I, II, V, VIII, X, XIV, XX district KÉSZ
or Csobánka. No national local-plan repository with GIS data was found: TÉKA (280/2024 Korm. rendelet)
and 419/2021 set content rules; the plans themselves stay on municipal websites and njt annexes.

---

## 3. Reference geometry for georeferencing

| Source | Endpoint | Contents | Coverage | Format | Access / licence | Verified | Use in heszmap |
|---|---|---|---|---|---|---|---|
| **Budapest orthophoto 2024** (Budapest Közút) | `…/eed286ab5f824a65ac42a7925ce6f732/rest/services/ortofoto/ortofoto_2024_2_rgb/MapServer` (tiled, EOV, finest LOD 0.04 m/px); also `ortofoto_2024_2_rgb_wgs` (Web Mercator), and 2005–2022 vintages, CIR | True orthophoto | Budapest (extent x 619 442–689 756, y 209 501–265 990) | ArcGIS tiles / `export` | Viewer; "Budapest Közút Zrt."; no licence | **verified (Referer)**: `export` 512×512 over Vörösmarty tér 200, 95 756 B JPEG | Visual check of fits; building-edge alignment; optional basemap (permission) |
| Lechner orthophoto WMTS | `https://www.oeny.hu/hk-fomi-mapservice/ortofoto/lf/hrszkereso/wmts`; `http://map.fomi.hu/orto_lf/map.php` | National orthophoto (EOV) | National | WMTS/WMS | hk-fomi: 403 page; map.fomi.hu: **401 "bejelentkezés szükséges"**; Lechner "WMTS-szolgáltatások": free registration | **blocked / login** | After registration: reference outside Budapest (Csobánka) |
| **NTA basemap tiles** (Nemzeti Térinformatikai Alaptérkép) | `https://api.lechnerkozpont.hu/hrsz-terminator/app/basemap/nta.php/{level}/{col}/{row}.png` (EOV grid, origin 426000/363000, 512 px, level 11 = 0.265 m/px); official WMTS at `nta.lechnerkozpont.hu` needs free registration | Cadastral-derived buildings with house numbers, streets, boundaries | National | JPEG tiles | Demo-app proxy, not for reuse; official WMTS: registration | **verified**: level 10 tile 200, 74 737 B (Vigadó tér: buildings + house numbers) | Official building outlines as a fit target (better than OSM where OSM is coarse); via the registered WMTS |
| **INSPIRE AU** (Lechner) | `https://inspire.lechnerkozpont.hu/geoserver/ows` `AU.2025:AdministrativeUnits.2025` (also `.LF`, 2023, 2024) | Settlements, districts (járás level incl. Budapest kerületek) with population | National, 3 581 units | WFS 2.0, GML/GeoJSON | AccessConstraints NONE, Fees NONE (INSPIRE/HVD) | **verified**: hits 200; bbox GetFeature 200, 7 201 B (Budapest 06., 07. kerület). **Caveat:** `srsName=EPSG:4326` output is rounded to 2 decimals (~1 km); request native EOV (2 decimals = cm) and reproject locally | Replace OSM district boundaries in `districts.geojson` with official ones |
| INSPIRE BU (Lechner) | same, `BU:Building` | Buildings with LOD1 height, z_min/z_max | **Sample only: 921 buildings, Mesterszállás** (no features in a Budapest V bbox) | WFS | | **verified**: hits 200; Budapest bbox 0 features | None |
| INSPIRE GN (Lechner) | `GN.2026:GeographicalNames.2026` | Place names | National, 90 463 | WFS | | **verified** hits | Minor |
| Budapest base map (Budapest Közút "KAPU"/`btp_alapterkep`, FHV alap) | `…/96d8a77cc4e74c4fba0eb51698877d5c/rest/services/btp_fhv/fhv_alap/MapServer` (house numbers, buildings, parcels, public-space parcels) | Large-scale base map | Budapest | ArcGIS REST | as above | **verified (Referer)**: service JSON 200, 5 054 B | House-number points and building outlines as anchors |
| **EOV ↔ ETRS89 grid `hu_bme_hd72corr`** (BME, in PROJ-data) | `https://cdn.proj.org/hu_bme_hd72corr.tif` | Correction grid HD72 → ETRF2000; per EPSG emulates the official EHT2 to < 2 mm | Hungary | GeoTIFF (251×121) | **CC-BY** (PROJ-data) | **verified**: 200, 78 982 B | Use `EPSG:23700` + this grid (PROJ ≥ 9.5.1, pyproj with network or the file) instead of the default 7-parameter `+towgs84`, which is decimetre-to-half-metre level. Matters when we ingest EOV vectors (FRSZ, HRSZ) and compare with OSM |
| EHT2 online | `eht2.gnssnet.hu` (GNSSnet.hu, Lechner) | Official transformation | | Web form | Free only for manual input | documented, not tested | Not needed if the grid above is used |
| Address points (KCR / INSPIRE AD) | `cimregiszter.hu`, `kozigazgatas.magyarorszag.hu` | Central address register | | | | **blocked**: proxy CONNECT 502 to both hosts; no public API found in search | – |
| Address search (HRSZ-kereső backend) | `https://www.oeny.hu/hk-api/addresses/search?kshCode=…&searchString=…`, `…/addresses/position?id=` | EHA address → point (+ outline) | National | JSON | as HRSZ-kereső (internal, rate-limited) | **verified** 200, 2 B (`[]`, query string format probably wrong) | Not recommended without agreement |

---

## 4. Regulation sources

| Source | Endpoint | Contents | Coverage | Format | Access / licence | Verified | Use |
|---|---|---|---|---|---|---|---|
| njt.jog.gov.hu (already used) | `https://njt.jog.gov.hu/jogszabaly/<id>`, municipal search `https://njt.jog.gov.hu/or`, ELI search `https://njt.jog.gov.hu/eli/kereses` | Consolidated municipal decrees since 2013-07-01 (legal obligation to publish), with annexes | National | HTML (+ PDF annexes) | Official, free. **No public API or bulk download found**; the site throttles ("Túl sok lekérdezés") | **verified**: `/or` 200, 63 154 B; V KÉSZ page 200, 599 378 B | Keep scraping politely; ELI URLs (`/eli/OR/<year>/…`) are stable identifiers worth storing in `regulations.json` |
| net.jogtar.hu municipal decree service (Wolters Kluwer, used by districts) | e.g. `https://net.jogtar.hu/rendelet?council=lipotvaros&dbnum=565&docid=A2000006.05R` (V KÉSZ) | Consolidated text with time states (`timeshift=`), linked from district sites | Districts that subscribe (e.g. V) | HTML | Free to read; commercial publisher, no reuse licence | **verified**: 200, 1 508 131 B | Cross-check that njt's consolidated version is current; detect amendments not yet on njt |
| District websites | V: `https://www.belvaros-lipotvaros.hu/telepulesrendezesi-dokumentumok` (KÉSZ amendment, plan sheet PDF, **a 2025 Kúria decision**); XVI: `https://www.bp16.hu/keruleti-epitesi-szabalyzat`; XII: `hegyvidek.hu/…/keruleti-epitesi`; II: `masodikkerulet.hu/szabalyzatok/telepuleskep-kesz` (403 to WebFetch) | Plan PDFs, amendment decrees, court decisions | Per district | PDF | Official | V page read via WebFetch; others found in search only | The V page links a **Kúria határozat (2025)**: Kúria decisions can annul KÉSZ provisions; heszmap should check and flag them (Kúria Önkormányzati Tanács decisions are published on kuria-birosag.hu, not tested) |
| Fővárosi Közgyűlés papers | `einfoszab.budapest.hu` (council session documents) | Előterjesztések incl. FRSZ/DÉSZ amendments | Budapest | PDF | Public | found in search, not tested | Watch for FRSZ/DÉSZ changes |
| Budapest planning archive | `https://archiv.budapest.hu/telepulesrendezesitervek/TSZT/FRSZ/…` | FRSZ/TSZT PDFs | Budapest | PDF | Public | found in search, not tested | Citations for FRSZ values |

---

## 5. Other data useful when checking a plot

| Source | Endpoint | Contents | Coverage | Format | Access / licence | Verified | Use |
|---|---|---|---|---|---|---|---|
| **E-örökség public API** (Lechner, national monument register OVNyR) | `GET https://www.oeny.hu/oeny/eorok/public/api/v1/ovnyr/search/MUEMLEK?page=0&size=20&searchText=…`; record `…/ovnyr/muemlek/{azon}` | Monuments: name, törzsszám, protection type and fine category, address, **WGS84 and EOV point**, **list of hrsz** (`connectedIngatlanList`), descriptions, photos | National; 2 541 hits for "Budapest" | JSON (paged) | Public portal; no API terms published | **verified**: search 200, 3 414 B (Pesti Vigadó, azon 664); record 200, 13 277 B (EOV 650153/239113, hrsz 24429/1 …) | "Műemlék" badge on a plot by hrsz match; link to the record |
| E-örökség archaeological sites | `…/ovnyr/search/LELOHELY`, `…/ovnyr/lelohely/{id}` | Only a showcase set (10 hits for "Budapest"), **no geometry** | – | JSON | | **verified**: 200, 4 976 B / 5 211 B | Not usable for plot checks; site polygons are not public (they appear as "tájékoztató elem" in some KÉSZ GIS, e.g. VI layer 111, XVII layer 100) |
| **Budapest FHV (fővárosi helyi védelem)** | `…/84664ad480624e649fbad47fb77d1644/rest/services/btp_fhv/fhv/MapServer` (2 `Védett építmények (aktuális)` → 5 `Építmények`, 4 `Földrészletek`; 6 épületegyüttesek; 10–17 terminated protections) | Locally protected buildings and ensembles with hrsz, address, decree dates, architect, style | Budapest, 1 370 protected buildings (layer 5) | ArcGIS REST | Viewer `btp-fhv.budapestkozut.hu` (Referer of app `cbe859be…`) | **verified (Referer)**: count 200, 14 B; attribute query 200 | "Fővárosi helyi védelem" flag per plot |
| District protection layers | VI: layers 20 Műemlék (183), 21 műemléki környezet, 22 fővárosi védelem (88), 23 kerületi védelem (702), 19 világörökség; XVII: 54–56 | | VI, XVII | ArcGIS REST | as above | **verified (Referer)** counts | Kerületi védelem is otherwise only in district decrees |
| Budapest helyi természetvédelem (BTVT) | `…/7859ea98bc5340e5aa06a78d361b62cc/rest/services/btp_btvt/btvt/MapServer` | Local protected nature areas (several dates), ex lege springs, bogs, earthworks, caves + buffers, **Natura 2000**, ökológiai hálózat, forests | Budapest | ArcGIS REST | as above | **verified (Referer)**: service JSON 200, 9 649 B | Nature constraints for Budapest plots |
| **Natura 2000 (EEA)** | `https://bio.discomap.eea.europa.eu/arcgis/rest/services/ProtectedSites/Natura2000Sites/MapServer/0/query` | SAC/SPA polygons, site code and name | EU; 479 HU sites | ArcGIS REST / download (EEA) | EEA data policy: free reuse with attribution | **verified**: count 200, 13 B; buffered point near Csobánka 200, 475 B (features returned) | Natura flag for Csobánka and other non-Budapest settlements |
| Flood hazard/risk maps (OVF, ÁKK 2021) | PDFs on `vizeink.hu/wp-content/uploads/2021/05/akk/…` | Hazard (3 scenarios) and risk maps | Major river basins | PDF | Public | found in search, no WMS found | Low priority (would need georeferencing) |
| Budapest strategic noise map | geoportal.budapest.hu → "Stratégiai zajtérkép 2007" | Noise | Budapest | Viewer | | page exists, not tested; 2007 data | Low |
| Other Budapest Közút services | Szolár (`btp_solar`), BKAE, BVMT (lighting masterplan), Kompakt város | | Budapest | ArcGIS REST | | listed (AGOL), not tested | Solar potential could interest architects |
| Building-permit statistics | KSH STADAT (lakásépítési engedélyek by district/settlement, quarterly) | Counts only | National | Tables | KSH open | found via news articles; table not fetched | Context only; ÉTDR has no public per-plot data |

---

## Top 5 to integrate first

1. **Budapest-wide official plots from the FRSZ map service (layer 9 `Telekhatár`).**
   *Why:* 237 897 parcels with hrsz for all 23 districts, current to 2026-01-01; removes the weakest step
   (`plan_parcels.py` tracing) in every Budapest district and gives each plot its official hrsz.
   *Sketch:* first ask Budapest Közút Zrt. / Főpolgármesteri Hivatal for permission and terms (the service is
   public but Referer-gated, no licence). Then a `scripts/fetch_bp_parcels.py` that pages
   `…/MapServer/9/query?where=kerulet='V.'&outFields=meb,fekves,kerulet,start_date,end_date&returnGeometry=true&outSR=23700&f=geojson&resultOffset=…&resultRecordCount=2000`,
   reprojects EOV → WGS84 with pyproj + `hu_bme_hd72corr`, and writes `public/data/parcels-<key>.geojson`.
   `plan_parcels.py` keeps its traced plots only as a cross-check: zone assignment then runs on the official
   polygons (`plan_zones.py` zone cells ∩ parcel). The parcel outlines also become a georeferencing check:
   the fraction of plan plot lines within 1 m of official parcel edges is a better fit metric than OSM buildings.

2. **Ground-truth zones for VI (both KÉSZ) and the DÉSZ overlay.**
   *Why:* VI's own GIS publishes every zone polygon with its limits and paragraph (`ovezeti_jel`, `beep_max`,
   `szm_á`, `zold_min`, `pm`, `kész`), the same regulations as `vi.json`/`vi2.json`. DÉSZ covers the Danube-bank
   plots of I, II, V, XIII, XX, which heszmap now attributes to the district KÉSZ.
   *Sketch:* a validation script `scripts/compare_zones.py vi2` that downloads layer 34 (and 82 for vi) once,
   computes per-zone IoU against `plan_zones.py` output and per-zone agreement of parsed limits in
   `zone-types-vi2.json`; report into `scripts/plans/vi2-compare.json`. For DÉSZ, fetch layer 27 + extent 39 and
   mark plots inside the DÉSZ area with "DÉSZ applies" and its zone code until DÉSZ text is ingested from njt
   (it is a fővárosi rendelet). Publishing their geometry needs permission; using it for validation does not
   expose it.

3. **Official hrsz on click (Lechner HRSZ terminátor API).**
   *Why:* documented, free, national (works in Csobánka too), gives the official lot number for any point.
   *Sketch:* a Cloudflare Worker route `/api/hrsz?lat=&lon=` that converts to EOV (1 decimal), calls
   `api.lechnerkozpont.hu/hrsz-terminator/api/hrsz`, caches by rounded coordinate, and returns
   `{telepules, fekves, hrsz}`; the side panel shows "Hrsz: 24432 (Forrás: Lechner Nonprofit Kft.)".
   Before launch, ask Lechner whether a public, free tool counts as "saját cél" under the ÁFF; if not, request
   the individual agreement the ÁFF offers. Do **not** use the internal `hk-api` (429 after a few requests).

4. **Protection flags: national monuments (E-örökség) + Budapest FHV.**
   *Why:* "is it a műemlék / fővárosi védett?" is the first question after the zone; both sources link to hrsz.
   *Sketch:* offline job per settlement: page `ovnyr/search/MUEMLEK?searchText=Budapest 5` (size 50, slowly),
   fetch each record, keep `azon, nev, vedelemFajtaja, birsagKategoria, eovPointList, connectedIngatlanList`;
   write `public/data/monuments-<key>.json` keyed by hrsz. With item 1 in place, join on hrsz; before that, join
   on the EOV point inside the traced plot. For Budapest add FHV layer 5/4 the same way (permission as in 1).
   Show a badge with a link to `https://www.oeny.hu/oeny/eorok/public/…` for the record.

5. **Accurate CRS handling and official boundaries.**
   *Why:* everything above arrives in EOV; the default EPSG:23700 → WGS84 transform is off by decimetres to
   ~0.5 m, which shows when official outlines are drawn over OSM. Official AU boundaries fix district edges.
   *Sketch:* ship `hu_bme_hd72corr.tif` (CC-BY, 79 kB) under `scripts/data/`, build transformers with
   `pyproj.Transformer.from_pipeline("+proj=pipeline +step +inv +proj=somerc … +step +proj=hgridshift +grids=hu_bme_hd72corr.tif …")`
   (or `TransformerGroup` with network enabled), use it in every new fetch script and in `plan_fit.py` reporting.
   Replace `npm run fetch:districts` input with `AU.2025:AdministrativeUnits.2025` fetched in native EOV
   (never `srsName=EPSG:4326`, which the server rounds to 0.01°).

---

## Not found / dead ends

- No public national vector cadastre (INSPIRE CP and BU are Mesterszállás samples only).
- No public WMS/WFS for local plans in E-TÉR (GeoServer 401) and no national "Tervtár" with GIS data.
- No KCR / INSPIRE AD address service reachable (hosts unreachable through the proxy, no API documented).
- No njt API or bulk export; archaeological site polygons are not public.
- `teir.hu`, `gis.teir.hu`, `geo.termeszetvedelem.hu`: connection reset / 502 through the proxy (not a
  statement about the services themselves).
