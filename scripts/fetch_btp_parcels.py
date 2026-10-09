"""Plot outlines with parcel numbers for a Budapest district from the city's GIS (Budapest
Térinformatikai Portál, run by Budapest Közút Zrt.): the "Telekhatár" layer of the FRSZ map service.
Replaces tracing plots from a scanned plan.

    python3 scripts/fetch_btp_parcels.py <key>
    python3 scripts/plan_vector_parcels.py <key> --zones-only   # then zone the plots as usual

Writes public/data/parcels-<key>/ (public spaces, bracketed numbers, flagged "street"); the raw
answer is cached in scripts/.cache/<key>/btp-parcels.geojson.

!!! LICENCE NOT CLEARED (see /mnt/project-files/heszmap/data-sources.md, docs/data-sources.md):
!!! the service states no licence and only answers requests carrying the Referer of Budapest
!!! Közút's own web apps. Peti allowed using it for the proof of concept (2026-10-09). Before any
!!! public launch, get written permission from Budapest Közút Zrt. (kapu@budapestkozut.hu) or the
!!! Főváros; until then show "© Budapest Közút Zrt." with the plots.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
from plan_vector_parcels import area_m2, chunks  # noqa: E402
from shapely import force_2d  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SERVICE = ("https://utility.arcgis.com/usrsvcs/servers/1f424e22b69d4ea890228a42f375d9ce/rest/services/"
           "btp_frsz/frsz_2021/MapServer/9/query")
REFERER = "https://budapestkozut.maps.arcgis.com/apps/webappviewer/index.html?id=a0f09e6392a049e88b11ff6f6d6bd462"
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV",
         "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII"]


def fetch(kerulet: str) -> dict:
    q = urllib.parse.urlencode({"where": f"kerulet='{kerulet}'", "outFields": "meb,start_date,end_date",
                                "outSR": 4326, "returnGeometry": "true", "f": "geojson"})
    req = urllib.request.Request(f"{SERVICE}?{q}", headers={"Referer": REFERER, "User-Agent": "heszmap/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def main():
    key = sys.argv[1]
    cfg = dcfg.load(key)
    roman = cfg["plan"].get("btp_kerulet") or key.rstrip("0123456789").upper()
    assert roman in ROMAN, f"not a Budapest district key: {key}"
    cache = ROOT / "scripts/.cache" / key / "btp-parcels.geojson"
    if cache.exists() and "--refresh" not in sys.argv:
        fc = json.loads(cache.read_text())
    else:
        fc = fetch(f"{roman}.")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(fc))
    feats = []
    for f in fc["features"]:
        meb = (f["properties"].get("meb") or "").strip()
        g = force_2d(shape(f["geometry"])).buffer(0)
        if g.is_empty:
            continue
        street = meb.startswith("(")
        feats.append({"type": "Feature", "properties": {
            "hrsz": meb.strip("()") or None, "areaM2": round(area_m2(g)), "check": ["street"] if street else [],
            "zones": [], "source": "btp"}, "geometry": mapping(g)})
    n, size = chunks(feats, ROOT / "public/data" / f"parcels-{key}")
    print(f"{len(feats)} plots ({sum('street' in f['properties']['check'] for f in feats)} public spaces) "
          f"from the Budapest city GIS, {n} cells, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
