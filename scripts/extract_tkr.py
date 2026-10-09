"""Split a településképi rendelet (TKR) into paragraphs scoped by character area or protection, and
geolocate the protected buildings and street sections it lists.

TKR rules do not follow KÉSZ zones: they apply per "településképi szempontból meghatározó terület"
(character area, drawn on the TKR's 1. melléklet map), per protected building or street section,
or everywhere. Scopes are a reviewed table in scripts/rules/<key>_tkr_scope.py.

Usage: python3 scripts/extract_tkr.py xx
Writes public/data/tkr-rules-<key>.json and public/data/protected-<key>.geojson.
"""
import importlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "rules"))
import extract_rules as er  # noqa: E402
import oeny_parcels  # noqa: E402
import plan_georef as pg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def first_page(pages, words):
    for n in (len(words), 60, 40, 25, 15, 10):
        q = " ".join(words[:n])
        hit = next((i + 1 for i, p in enumerate(pages) if er.squash(q) in p), None)
        if hit:
            return q, hit
    return None, None


def main():
    key = sys.argv[1]
    scope = importlib.import_module(f"{key}_tkr_scope")
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg_id = f"{key}-tkr"
    reg = regs["regulations"][reg_id]
    raw = (ROOT / "scripts/.cache" / f"njt-{scope.NJT_ID}.html").read_text(encoding="utf-8")
    plain, withsup = er.to_lines(raw, False), er.to_lines(raw, True)
    units = er.parse_units(plain, withsup)
    pages = [er.squash(p.get_text()) for p in pymupdf.open(ROOT / "public" / reg["pdf"])]

    rules, missing = [], []
    for u in units:
        para_no = u["id"].split(".")[0]
        sc = scope.SCOPES.get(para_no)
        if sc is None:
            continue
        quote, page = first_page(pages, u["quoteFull"].split())
        if not quote:
            missing.append(u["id"])
            continue
        rules.append({"id": u["id"], "section": u["section"], "text": u["text"], **sc,
                      "cite": {"reg": reg_id, "page": page, "para": u["id"], "quote": quote}})
    if missing:
        sys.exit(f"quotes not found in the PDF: {', '.join(missing)}")

    # Parcel numbers read off the zoning plan -> map position (centre of the printed number).
    parcels = {}
    if getattr(scope, "PLAN_OCR", None):
        fit = json.loads((ROOT / scope.PLAN_FIT).read_text())
        plan_local = pg.Local(*fit["local"])
        for path, f in zip(scope.PLAN_OCR, fit["sheets"]):
            model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
            for l in json.loads((ROOT / path).read_text())["labels"]:
                t = l["text"].strip().strip("()")
                if re.fullmatch(r"\d{5,6}(/\d+)?", t) and l["conf"] > 0.8:
                    mx, my = model(np.array(l["box"], dtype=float).mean(0))[0]
                    lng, lat = plan_local.to_ll(mx, my)
                    parcels.setdefault(t, (float(lng), float(lat)))
        print(f"parcel numbers on the plan: {len(parcels)}")

    registry = oeny_parcels.plot_points(key)

    # Protected buildings (2. melléklet): place on the parcel number, else geocode the address.
    lines = plain[plain.index("2. melléklet"):]
    district_q = scope.DISTRICT_QUERY
    local = pg.Local(19.115, 47.435)
    feats = []
    for l in lines:
        m = re.match(r"^(\d+[a-z]?)\. (.+?) [-–] ([\d/, ]+) hrsz", l)
        if not m:
            continue
        no, addr, hrsz = m.groups()
        q = re.sub(r"\s*[-–]\s*templom|\s*[-–]\s*Élmunkás ltp\.", "", addr).replace("Szt.", "Szent")
        am = re.match(r"^(.+?) (\d+[a-z]?(?:/[a-z])?)\.?$", q.strip())
        on_plan = next((parcels[h] for h in re.split(r"[,\s]+", hrsz) if h in parcels), None)
        # Plots with registry numbers (oeny_parcels.py) beat both the plan's printed numbers and geocoding.
        on_plan = next((registry[h] for h in re.split(r"[,\s]+", hrsz) if h in registry), on_plan)
        if on_plan:
            h, precise, source = {"lon": on_plan[0], "lat": on_plan[1]}, True, "hrsz"
        else:
            hits = pg.nominatim({"q": f"{q}, {district_q}", "limit": 1})
            if not hits:
                print(f"  not found: {addr}")
                continue
            h = hits[0]
            precise = (h.get("addresstype") or h.get("type")) not in ("road", "street", "residential", "suburb", "quarter")
            source = "geocode"
        feats.append({"type": "Feature", "properties": {
            "kind": "egyedi", "name": addr, "hrsz": hrsz.strip(), "ref": f"2. melléklet {no}.",
            # Only house-level geocodes are used by distance; the rest match by searched address.
            "approx": not precise, "source": source, "street": am.group(1) if am else None, "number": am.group(2) if am else None},
            "geometry": {"type": "Point", "coordinates": [float(h["lon"]), float(h["lat"])]}})
    print(f"protected buildings: {len(feats)} placed, {sum(f['properties']['source'] == 'hrsz' for f in feats)} by parcel number, "
          f"{sum(f['properties']['approx'] for f in feats)} only approximately")

    # Protected street sections (VU) and protected structure (TSZ): street geometry between cross streets.
    bbox = [18.9, 47.3, 19.3, 47.6]
    for vu in scope.STREET_SECTIONS:
        main = pg.street_segments(vu["street"], district_q, local, bbox)
        if main is None:
            print(f"  street not found: {vu['street']}")
            continue
        pts = np.vstack([main[:, :2], main[-1:, 2:]])
        if vu.get("between"):
            ends = []
            for cross in vu["between"]:
                other = pg.street_segments(cross, district_q, local, bbox)
                if other is None:
                    print(f"  cross street not found: {cross}")
                    break
                d = [pg.nearest_on_polyline(p, other)[1] for p in main[:, :2]]
                ends.append(int(np.argmin(d)))
            if len(ends) < 2:
                continue
            a, b = sorted(ends)
            seg = main[a:b + 1]
        else:
            seg = main
        lines_ll = []
        for s in seg:
            x, y = local.to_ll(np.array([s[0], s[2]]), np.array([s[1], s[3]]))
            lines_ll.append([[round(float(x[0]), 7), round(float(y[0]), 7)], [round(float(x[1]), 7), round(float(y[1]), 7)]])
        feats.append({"type": "Feature", "properties": {"kind": "VU", "name": vu["name"], "ref": vu["ref"], "side": vu.get("side")},
                      "geometry": {"type": "MultiLineString", "coordinates": lines_ll}})
    for vu in getattr(scope, "VU_ADDRESSES", []):
        for addr in vu["addresses"]:
            hits = pg.nominatim({"q": f"{addr}, {district_q}", "limit": 1})
            if hits:
                feats.append({"type": "Feature", "properties": {"kind": "VU", "name": vu["name"], "ref": vu["ref"]},
                              "geometry": {"type": "Point", "coordinates": [float(hits[0]["lon"]), float(hits[0]["lat"])]}})

    tsz = getattr(scope, "TSZ", None)
    if tsz:
        geoms = [pg.street_segments(n, district_q, local, bbox) for n in tsz["ring"]]
        if all(g is not None for g in geoms):
            corners = []
            for a, b in zip(geoms, geoms[1:] + geoms[:1]):
                pa = np.vstack([a[:, :2], a[-1:, 2:]])
                d = [pg.nearest_on_polyline(p, b) for p in pa]
                i = int(np.argmin([x[1] for x in d]))
                corners.append((pa[i] + d[i][0]) / 2)
            ring = [list(map(lambda v: round(float(v), 7), local.to_ll(c[0], c[1]))) for c in corners]
            ring.append(ring[0])
            feats.append({"type": "Feature", "properties": {"kind": "TSZ", "name": tsz["name"], "ref": tsz["ref"]},
                          "geometry": {"type": "Polygon", "coordinates": [ring]}})
    print(f"protected features: {len(feats)} total")

    (ROOT / "public/data" / f"protected-{key}.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (ROOT / "public/data" / f"tkr-rules-{key}.json").write_text(json.dumps(
        {"areas": scope.AREAS, "zoneArea": scope.ZONE_AREA, "rules": rules}, ensure_ascii=False, indent=1) + "\n")
    reg["tkr"] = f"tkr-rules-{key}.json"
    reg["protected"] = f"protected-{key}.geojson"
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    for r in rules:
        print(f"{r['id']:<12} {r['scope']:<10} {','.join(r.get('areas', [])):<40} {r['text'][:60]}")
    print(f"{len(rules)} TKR provisions, all quotes verified")


if __name__ == "__main__":
    main()
