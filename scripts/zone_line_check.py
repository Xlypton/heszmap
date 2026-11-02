"""Do the zone areas respect the plan's red dotted zone boundary lines?

A zone area (public/data/zones-<key>/) must never have a red dotted boundary line running through
its inside: that is a zone spilling over into its neighbour, and the neighbour coming out too small.
The lines are the ones plan_dotlines.py read from the plan's own tiles (scripts/plans/<key>-dotlines.geojson).

A zone area crosses a line when more than CROSS_M of line runs through it at least INSET_M from its
edge (plots and plan sit up to ~3 m apart, and a line drawn along a zone's edge is not a crossing).

    python3 scripts/zone_line_check.py <key> [--list]       crossings of one plan
    python3 scripts/zone_line_check.py --all                every plan with zone areas

Writes scripts/plans/<key>-zonelines.json, which check_district.py (criteria Z1 and Z7, standard
library only) reads; it holds a fingerprint of the zone areas it measured, so a rebuild of the zones
without a new check shows as stale.
"""
import glob
import json
import math
import sys
from pathlib import Path

from shapely import affinity
from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
INSET_M = 5.0   # plots and plan ~1-3 m apart; a line a few metres inside a plot's edge cuts a sliver, not a zone
STREET = __import__("re").compile(r"^(KÖ|Kt-K|Kt-Fk|Köu|Kök)")
CROSS_M = 10.0  # ~2 dot gaps


def zone_areas(key, data=None):
    seen, out = set(), []
    for f in glob.glob(str(Path(data or ROOT / "public/data") / f"zones-{key}" / "*.json")):
        for ft in json.loads(Path(f).read_text())["features"]:
            if ft["properties"].get("street"):
                continue
            g = shape(ft["geometry"])
            if g.wkb in seen:
                continue
            seen.add(g.wkb)
            out.append((ft["properties"]["code"], g))
    return out


def crossings(key, data=None):
    """(zone areas checked, [(code, metres of line inside, lng, lat)], lines found?)"""
    import plan_dotlines
    lines = plan_dotlines.lines(key)
    if lines is None:
        if not (ROOT / "scripts/plans" / f"{key}-dotlines.geojson").exists() and (ROOT / "public/pmtiles" / key).exists():
            plan_dotlines.read(key)
            lines = plan_dotlines.lines(key)
    areas = zone_areas(key, data)
    if lines is None or not areas:
        return len(areas), [], lines is not None
    lat = lines.centroid.y
    k = math.cos(math.radians(lat))
    # work in a local metric frame: degrees * (111 km · cos lat, 111 km)
    to_m = lambda g: affinity.scale(g, 111_320 * k, 110_540, origin=(0, 0))
    lm = to_m(lines)
    parts = list(getattr(lm, "geoms", [lm]))
    tree = STRtree(parts)
    labels = []
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())["regulations"]
    for r in regs.values():
        zl = r.get("zoneLabels")
        if zl and (r.get("zoneAreas") or {}).get("dir") == f"zones-{key}" and (ROOT / "public/data" / zl).exists():
            labels += [(f["properties"]["code"], shape(f["geometry"])) for f in json.loads((ROOT / "public/data" / zl).read_text())["features"]]
    ltree = STRtree([p for _, p in labels]) if labels else None
    bad = []
    for code, g in areas:
        gm = to_m(g)
        near = tree.query(gm)
        if not len(near):
            continue
        inner = gm.buffer(-INSET_M)
        if inner.is_empty:
            continue
        inside = sum(parts[j].intersection(inner).length for j in near)
        if inside > CROSS_M:
            c = g.representative_point()
            # another zone's code printed inside the area: the area surely took in its neighbour
            other = sorted({labels[j][0] for j in ltree.query(g) if labels[j][0] != code and g.contains(labels[j][1])
                            and not STREET.match(labels[j][0])}) if ltree is not None else []
            bad.append((code, round(inside), round(c.x, 6), round(c.y, 6), other))
    return len(areas), sorted(bad, key=lambda b: (-len(b[4]), -b[1])), True


def fingerprint(key):
    """sha1 over the zone area chunks, as check_district.py computes it."""
    import hashlib
    h = hashlib.sha1()
    for f in sorted(glob.glob(str(ROOT / "public/data" / f"zones-{key}" / "*.json"))):
        h.update(Path(f).name.encode())
        h.update(Path(f).read_bytes())
    return h.hexdigest()


def save(key, n, bad, have):
    import plan_dotlines
    info = {}
    p = ROOT / "scripts/plans" / f"{key}-dotlines.geojson"
    if p.exists():
        info = json.loads(p.read_text())["properties"]
    out = {"zones": fingerprint(key), "zoneAreas": n, "lines": info, "linesFound": have,
           "insetM": INSET_M, "crossM": CROSS_M,
           "crossings": [{"code": c, "m": m, "at": [x, y], "otherCodesInside": o} for c, m, x, y, o in bad]}
    (ROOT / "scripts/plans" / f"{key}-zonelines.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


def main():
    keys = sorted(p.name[len("zones-"):] for p in (ROOT / "public/data").glob("zones-*")) if "--all" in sys.argv else [sys.argv[1]]
    data = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--data=")), None)  # another build's public/data
    for key in keys:
        n, bad, have = crossings(key, data)
        if not data and n:
            save(key, n, bad, have)
        if not have:
            print(f"{key:14s} {n:5d} zone areas, no red dotted lines on the plan")
            continue
        print(f"{key:14s} {n:5d} zone areas, {len(bad):4d} cross a red dotted line ({sum(b[1] for b in bad)} m of line inside), "
              f"{sum(bool(b[4]) for b in bad)} of them with another zone's code printed inside")
        if "--list" in sys.argv:
            for b in bad:
                print(f"    {b[0]:18s} {b[1]:5d} m   https://heszmap.xlypton.workers.dev/#18/{b[3]}/{b[2]}  {' '.join(b[4])}")


if __name__ == "__main__":
    main()
