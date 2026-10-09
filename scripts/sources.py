"""Fetch plots, buildings and zones from external map services into GeoJSON for the pipeline.

LICENSING IS NOT CLEARED for any of these services (see docs/data-sources.md): fine for the
prototype, but get permission before a public launch.

Usage:
  python3 scripts/sources.py oeny-parcels <district>     land-registry plots with hrsz, any town
  python3 scripts/sources.py oeny-buildings <district>   land-registry buildings
  python3 scripts/sources.py bp-zones-vi                 VI KÉSZ-1/2 zones with their limits
Budapest plots come from scripts/fetch_btp_parcels.py (the city GIS), so there is no bp-plots here.
<district> is a key (viii, xx, csobanka), a districts.geojson id (8), or --bbox W,S,E,N.
Writes scripts/.cache/sources/<command>-<district>.geojson (not committed). Raw responses are
cached per cell, so a rerun or an interrupted run re-fetches nothing.

oeny-* read the WMS behind Lechner's free HRSZ finder (oeny.hu). Its GetMap answers in KML with
the vector features and their attributes (hrsz, ksh_kod, fekves, obj_fels). The service blocked
the cloud egress after a handful of scripted calls to its search API (hk-api), so this only asks
the WMS, one cell at a time, at most one request every OENY_DELAY_S seconds.
"""
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from shapely.geometry import box, mapping, shape

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scripts" / ".cache" / "sources"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

OENY_WMS = "https://www.oeny.hu/hk-geoserver/hrsz/wms"
OENY_REFERER = "https://www.oeny.hu/oeny/hrsz-kereso/"
OENY_CELL = 0.01  # degrees; ~750 x 1100 m, ~700 plots and ~2 MB of KML in central Budapest
OENY_DELAY_S = 1.5

BP_REFERER = "https://budapestkozut.maps.arcgis.com/"
BP_VI = ("https://utility.arcgis.com/usrsvcs/servers/35162649113d4ce494bb6a4129c763bf"
         "/rest/services/terezvaros/terezvaros_publikus/MapServer")
BP_VI_ZONE_LAYERS = {34: "KÉSZ-2 35/2020", 82: "KÉSZ-1 23/2019"}  # "Építési övezet(, övezet) jele"

ROMAN = {r: i for i, r in enumerate(("i ii iii iv v vi vii viii ix x xi xii xiii xiv xv xvi xvii xviii xix xx "
                                      "xxi xxii xxiii").split(), 1)}
KML = "{http://www.opengis.net/kml/2.2}"
ATTR = re.compile(r'atr-name">([^<]+)</span>:</strong>\s*<span class="atr-value">([^<]*)<')


def get(url, referer, retries=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network errors of every kind get the same backoff
            if attempt == retries - 1:
                raise
            print(f"  retry after {e}", file=sys.stderr)
            time.sleep(5 * 2 ** attempt)


def area(arg):
    """(name, shapely geometry) of a district key, districts.geojson id or --bbox W,S,E,N."""
    if arg.startswith("--bbox="):
        w, s, e, n = map(float, arg.split("=", 1)[1].split(","))
        return f"bbox-{w}-{s}-{e}-{n}", box(w, s, e, n)
    fc = json.loads((ROOT / "public" / "data" / "districts.geojson").read_text())
    key = arg.lower()
    want = int(key) if key.isdigit() else ROMAN.get(key)
    for f in fc["features"]:
        p = f["properties"]
        if p["id"] == want or str(p.get("name", "")).lower().startswith(key) and want is None:
            return key, shape(f["geometry"])
    sys.exit(f"unknown district {arg!r}: use a key (viii), an id (8) or --bbox=W,S,E,N")


def cells(geom, size):
    w, s, e, n = geom.bounds
    y = s
    while y < n:
        x = w
        while x < e:
            c = box(x, y, min(x + size, e), min(y + size, n))
            if c.intersects(geom):
                yield c
            x += size
        y += size


def kml_features(data, layer):
    """Polygons and attributes of a GeoServer KML GetMap response, keyed by feature id."""
    out = {}
    for pm in ET.fromstring(data).iter(f"{KML}Placemark"):
        fid = pm.get("id") or ""
        if not fid.startswith(layer + "."):
            continue
        polys = []
        for poly in pm.iter(f"{KML}Polygon"):
            rings = []
            for tag in ("outerBoundaryIs", "innerBoundaryIs"):
                for ring in poly.iter(f"{KML}{tag}"):
                    coords = ring.find(f".//{KML}coordinates").text.split()
                    rings.append([[float(v) for v in c.split(",")[:2]] for c in coords])
            polys.append(rings)
        if not polys:
            continue
        props = dict(ATTR.findall(pm.findtext(f"{KML}description") or ""))
        geom = {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else \
            {"type": "MultiPolygon", "coordinates": polys}
        out[fid] = {"type": "Feature", "id": fid, "properties": props, "geometry": geom}
    return out


def oeny(layer, name, geom):
    raw = CACHE / "raw" / f"oeny-{layer}"
    raw.mkdir(parents=True, exist_ok=True)
    feats = {}
    todo = list(cells(geom, OENY_CELL))
    for i, c in enumerate(todo, 1):
        w, s, e, n = c.bounds
        url = OENY_WMS + "?" + urllib.parse.urlencode({
            "service": "WMS", "version": "1.1.0", "request": "GetMap", "layers": f"hrsz:{layer}",
            "styles": "", "srs": "EPSG:4326", "bbox": f"{w:.6f},{s:.6f},{e:.6f},{n:.6f}",
            "width": 1024, "height": 1024, "format": "application/vnd.google-earth.kml+xml",
            "format_options": "kmscore:100"})
        path = raw / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".kml")
        if not path.exists():
            time.sleep(OENY_DELAY_S)
            data = get(url, OENY_REFERER)
            if b"<kml" not in data[:500]:
                sys.exit(f"cell {c.bounds}: not KML: {data[:300]!r}")
            path.write_bytes(data)
        got = kml_features(path.read_bytes(), layer)
        feats.update(got)
        print(f"  cell {i}/{len(todo)}: {len(got)} features, {len(feats)} total", file=sys.stderr)
    # A feature is kept when it touches the area: plots on the border belong to both neighbours.
    return [f for f in feats.values() if shape(f["geometry"]).intersects(geom)]


def arcgis(layer_url, geom, fields="*", where="1=1"):
    """Every feature of an ArcGIS MapServer layer intersecting geom (paged), as GeoJSON features."""
    out, offset = [], 0
    w, s, e, n = geom.bounds
    while True:
        q = urllib.parse.urlencode({
            "where": where, "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": fields,
            "returnGeometry": "true", "resultOffset": offset, "resultRecordCount": 2000, "f": "geojson"})
        page = json.loads(get(f"{layer_url}/query?{q}", BP_REFERER))
        if "error" in page:
            sys.exit(f"{layer_url}: {page['error']}")
        got = page.get("features", [])
        out += [f for f in got if f.get("geometry") and shape(f["geometry"]).intersects(geom)]
        print(f"  {len(out)} features", file=sys.stderr)
        if len(got) < 2000 and not page.get("exceededTransferLimit"):
            return out
        offset += len(got)


def write(cmd, name, feats, source):
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{cmd}-{name}.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "source": source,
                               "license": "NOT CLEARED: prototype use only, see docs/data-sources.md",
                               "fetched": time.strftime("%Y-%m-%d"), "features": feats}, ensure_ascii=False))
    print(f"{out.relative_to(ROOT)}: {len(feats)} features")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd = argv[1]
    if cmd == "bp-zones-vi":
        _, geom = area("vi")
        feats = []
        for layer, kesz in BP_VI_ZONE_LAYERS.items():
            for f in arcgis(f"{BP_VI}/{layer}", geom):
                f["properties"]["source_layer"] = kesz
                feats.append(f)
        return write(cmd, "vi", feats, "Budapest Közút Zrt., terezvaros_publikus")
    if len(argv) < 3:
        sys.exit(__doc__)
    name, geom = area(argv[2])
    if cmd in ("oeny-parcels", "oeny-buildings"):
        layer = "foldreszlet" if cmd == "oeny-parcels" else "epulet"
        return write(cmd, name, oeny(layer, name, geom), f"Lechner Tudásközpont, OÉNY hrsz:{layer}")
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
