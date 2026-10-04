"""Fetch the 23 Budapest district boundaries, plus the other processed settlements, from OSM
(Nominatim) into GeoJSON.

Usage: python3 scripts/fetch_districts.py               # everything
       python3 scripts/fetch_districts.py --settlements # only (re)fetch SETTLEMENTS, keep the rest
       python3 scripts/fetch_districts.py --add 2001 "Budaörs" "Budaörs, Pest vármegye"
                                                         # add/replace one settlement (for registry fragments)
Writes public/data/districts.geojson. Stdlib only; respects Nominatim's 1 req/s policy.
Settlements outside Budapest get ids from 1001 up (Budapest districts are 1-23).
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
         "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII"]
OUT = Path(__file__).resolve().parent.parent / "public" / "data" / "districts.geojson"
# (id, name shown in the app, Nominatim query)
SETTLEMENTS = [(1001, "Csobánka", "Csobánka, Pest vármegye")]
UA = "heszmap/0.1 (https://github.com/xlypton/heszmap)"


def fetch(query: str) -> dict:
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "polygon_geojson": 1,
        "polygon_threshold": 0.0002,
        "limit": 5,
    })
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{params}",
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        results = json.load(r)
    for hit in results:
        if hit["class"] == "boundary" and hit["geojson"]["type"] in ("Polygon", "MultiPolygon"):
            return hit["geojson"]
    raise RuntimeError(f"No boundary polygon found for {query}")


def main() -> None:
    import sys
    if "--add" in sys.argv:
        i = sys.argv.index("--add")
        sid, name, query = int(sys.argv[i + 1]), sys.argv[i + 2], sys.argv[i + 3]
        data = json.loads(OUT.read_text())
        data["features"] = [f for f in data["features"] if f["properties"]["id"] != sid] + \
            [{"type": "Feature", "properties": {"id": sid, "name": name}, "geometry": fetch(query)}]
        OUT.write_text(json.dumps(data, ensure_ascii=False))
        print(f"ok {name} ({sid})")
        return
    features = []
    if "--settlements" in sys.argv:
        ids = {i for i, _, _ in SETTLEMENTS}
        features = [f for f in json.loads(OUT.read_text())["features"] if f["properties"]["id"] not in ids]
    budapest = [] if "--settlements" in sys.argv else ROMAN
    for i, numeral in enumerate(budapest, start=1):
        geometry = fetch(f"{numeral}. kerület, Budapest")
        features.append({
            "type": "Feature",
            "properties": {"id": i, "name": f"{numeral}. kerület"},
            "geometry": geometry,
        })
        print(f"ok {numeral}")
        time.sleep(1.1)
    for i, name, query in SETTLEMENTS:
        features.append({"type": "Feature", "properties": {"id": i, "name": name}, "geometry": fetch(query)})
        print(f"ok {name}")
        time.sleep(1.1)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
