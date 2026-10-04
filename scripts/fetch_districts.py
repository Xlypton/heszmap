"""Fetch the 23 Budapest district boundaries from OSM (Nominatim) into GeoJSON.

Usage: python3 scripts/fetch_districts.py
Writes public/data/districts.geojson. Stdlib only; respects Nominatim's 1 req/s policy.
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
         "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII"]
OUT = Path(__file__).resolve().parent.parent / "public" / "data" / "districts.geojson"
UA = "heszmap/0.1 (https://github.com/xlypton/heszmap)"


def fetch(numeral: str) -> dict:
    params = urllib.parse.urlencode({
        "q": f"{numeral}. kerület, Budapest",
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
    raise RuntimeError(f"No boundary polygon found for district {numeral}")


def main() -> None:
    features = []
    for i, numeral in enumerate(ROMAN, start=1):
        geometry = fetch(numeral)
        features.append({
            "type": "Feature",
            "properties": {"id": i, "name": f"{numeral}. kerület"},
            "geometry": geometry,
        })
        print(f"ok {numeral}")
        time.sleep(1.1)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
