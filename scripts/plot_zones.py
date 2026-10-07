"""Zones from the plots, for plans that label each block of plots instead of drawing zone outlines
(the Budapest KÉSZ plans: plots in blue, streets left white, one zone code per block or part of a block).

    python3 scripts/plot_zones.py <key>

Needs the plots (plan_parcels.py: public/data/parcels-<key>/) and the zone labels
(public/data/zone-labels-<key>.geojson). For each plot:
  1. a zone code printed on the plot itself: that zone ("plan": the plan names it on the plot);
  2. else the codes printed in its block (the plots between the surrounding streets):
     one code in the block: that zone ("plan": the block is bounded by streets the plan draws);
     several codes: the nearest one ("estimated": the zone boundary inside the block is not traced);
  3. else the nearest code across the street, within MAX_BORROW_M ("estimated").
Public-space plots (number in brackets: streets, squares) take a zone only from a code printed on
them (KÖu, Zkp, ...); otherwise they are left as street.
The zone areas are the plots of one zone in one block, merged. Writes public/data/zones-<key>/ and
rewrites the plots' "zones"; sets zoneAreas in regulations.json.
"""
import json
import sys
from collections import Counter
from pathlib import Path

from shapely.geometry import Point, shape, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CELL = (0.004, 0.003)  # same grid as the plots
TOUCH_DEG = 0.00002  # ~1.5 m: plots this close belong to one block
MAX_BORROW_M = 120


def metres(a, b):
    import math
    return math.hypot((a.x - b.x) * 111_320 * math.cos(math.radians(a.y)), (a.y - b.y) * 110_540)


def load_chunks(d):
    feats, seen = [], set()
    for f in sorted(d.glob("*.json")):
        for ft in json.loads(f.read_text())["features"]:
            k = json.dumps(ft["geometry"]["coordinates"][0][:3])
            if k not in seen:
                seen.add(k)
                feats.append(ft)
    return feats


def write_chunks(d, feats):
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.json"):
        f.unlink()
    cells = {}
    for f in feats:
        g = shape(f["geometry"])
        x0, y0, x1, y1 = g.bounds
        for ix in range(int(x0 // CELL[0]), int(x1 // CELL[0]) + 1):
            for iy in range(int(y0 // CELL[1]), int(y1 // CELL[1]) + 1):
                cells.setdefault(f"{ix}_{iy}", []).append(f)
    for k, fs in cells.items():
        (d / f"{k}.json").write_text(json.dumps({"type": "FeatureCollection", "features": fs}, separators=(",", ":")))
    return len(cells)


def rounded(geom):
    g = mapping(geom.simplify(0.000004))

    def r(c):
        return [r(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 6), round(c[1], 6)]
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def main():
    key = sys.argv[1]
    cfg = dcfg.load(key)
    reg_id = dcfg.reg_id(cfg)
    regs_path = ROOT / "public/data/regulations.json"
    regs = json.loads(regs_path.read_text())
    reg = regs["regulations"][reg_id]
    pdir = ROOT / "public/data" / f"parcels-{key}"
    plots = load_chunks(pdir)
    area = (reg.get("plan") or {}).get("area")
    if area:
        # A regulation covering part of the district (Budapest VI.): only the plots in its own area.
        from shapely.geometry import Polygon
        own = Polygon(area[0])
        plots = [f for f in plots if own.contains(shape(f["geometry"]).representative_point())]
    polys = [shape(f["geometry"]) for f in plots]
    # Public space: a number in brackets, or (number unread) an OSM street running through the plot.
    public = [bool(f["properties"].get("public")) or "road" in f["properties"].get("check", []) for f in plots]
    labels = [(f["properties"]["code"], Point(f["geometry"]["coordinates"]))
              for f in json.loads((ROOT / "public/data" / reg["zoneLabels"]).read_text())["features"]]
    tree = STRtree(polys)

    # 1. Codes printed on each plot.
    on_plot = [Counter() for _ in plots]
    for code, pt in labels:
        for j in tree.query(pt):
            if polys[j].contains(pt):
                on_plot[j][code] += 1

    # 2. Blocks: the private plots that touch (public plots, the streets, separate them).
    priv = [i for i in range(len(plots)) if not public[i]]
    grown = {i: polys[i].buffer(TOUCH_DEG) for i in priv}
    gtree = STRtree([grown[i] for i in priv])
    parent = {i: i for i in priv}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, i in enumerate(priv):
        for b in gtree.query(grown[i]):
            j = priv[int(b)]
            if j > i and grown[i].intersects(grown[j]):
                parent[root(i)] = root(j)
    blocks = {}
    for i in priv:
        blocks.setdefault(root(i), []).append(i)
    block_of = {i: r for r, ms in blocks.items() for i in ms}
    block_codes = {r: Counter(c for i in ms for c in on_plot[i].elements()) for r, ms in blocks.items()}
    block_pts = {r: [(c, pt) for i in ms for c, pt in labels if on_plot[i][c] and polys[i].contains(pt)] for r, ms in blocks.items()}

    zone_of = [None] * len(plots)
    for i in range(len(plots)):
        here = on_plot[i]
        if here:
            zone_of[i] = (here.most_common(1)[0][0], "plan")
        elif public[i]:
            continue
        else:
            r = block_of[i]
            codes = block_codes[r]
            c0 = polys[i].representative_point()
            if len(codes) == 1:
                zone_of[i] = (next(iter(codes)), "plan")
            elif codes:
                zone_of[i] = (min(block_pts[r], key=lambda cp: cp[1].distance(c0))[0], "estimated")
            else:
                near = [(metres(pt, c0), c) for c, pt in labels]
                d, c = min(near, default=(1e9, None))
                if d <= MAX_BORROW_M:
                    zone_of[i] = (c, "estimated")

    # 3. Zone areas: plots of one zone in one block (public plots by themselves), merged.
    groups = {}
    for i, z in enumerate(zone_of):
        if z:
            groups.setdefault((block_of.get(i, ("pub", i)), z[0]), []).append(i)
    zones = []
    for (_, code), ms in groups.items():
        status = "plan" if all(zone_of[i][1] == "plan" for i in ms) else "estimated"
        geom = unary_union([polys[i].buffer(TOUCH_DEG / 2) for i in ms]).buffer(-TOUCH_DEG / 2)
        if geom.is_empty:
            continue
        zones.append({"type": "Feature", "properties": {"code": code, "status": status, "street": False}, "geometry": rounded(geom)})

    for f, z in zip(plots, zone_of):
        f["properties"]["zones"] = [{"code": z[0], "status": z[1], "share": 1.0}] if z else []
    write_chunks(pdir, plots)
    n = write_chunks(ROOT / "public/data" / f"zones-{key}", zones)
    reg["zoneAreas"] = {"dir": f"zones-{key}", "cell": CELL}
    regs_path.write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    st = Counter(z[1] for z in zone_of if z)
    print(f"{len(plots)} plots ({sum(public)} public), {len(blocks)} blocks; zone: {dict(st)}, none {sum(z is None for z in zone_of)}; "
          f"{len(zones)} zone areas in {n} cells")


if __name__ == "__main__":
    main()
