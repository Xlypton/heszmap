"""The area a partial KÉSZ plan regulates, from where its zone codes are printed, written as plan.clip.

    python3 scripts/plan_area_labels.py <key> <buffer_m> "<note>" [<other key> ...]

Budapest IV. (Újpest): each unit plan prints only its own unit's zone codes, over a base map that runs on
into the neighbouring units, and marks its boundary with short runs of blue squares at the corners
only, so there is no line to follow. The area is the concave hull of the zone labels the georeferencing
kept (public/data/zone-labels-<key>.geojson), widened by buffer_m to reach the plots at the edge; where
it overlaps the area of another key given after the note (a neighbouring unit), each point goes to the
unit whose nearest label is nearer. An approximation along the edges: check it on the map.
"""
import json
import sys
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import MultiPoint, Point, Polygon, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_georef as pg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def labels_m(key, local):
    f = json.loads((ROOT / f"public/data/zone-labels-{key}.geojson").read_text())["features"]
    ll = np.array([x["geometry"]["coordinates"] for x in f])
    return np.column_stack(local.to_m(ll[:, 0], ll[:, 1]))


def hull(pts, buffer_m):
    return shapely.concave_hull(MultiPoint(pts), ratio=0.3).buffer(buffer_m, join_style="mitre", mitre_limit=2)


def main(key, buffer_m, note, others):
    cfg = dcfg.load(key)
    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    local = pg.Local(*fit["local"])
    own = labels_m(key, local)
    area = hull(own, buffer_m)
    tree = cKDTree(own)
    for o in others:
        theirs = labels_m(o, local)
        overlap = area.intersection(hull(theirs, buffer_m))
        if overlap.is_empty:
            continue
        # Cut the overlap on a 5 m grid: cells nearer to the other unit's labels go to it.
        x0, y0, x1, y1 = overlap.bounds
        xs, ys = np.meshgrid(np.arange(x0, x1, 5.0), np.arange(y0, y1, 5.0))
        g = np.column_stack([xs.ravel(), ys.ravel()])
        theirs_nearer = cKDTree(theirs).query(g)[0] < tree.query(g)[0]
        cells = [Point(p).buffer(3.6, cap_style="square") for p in g[theirs_nearer]]
        lose = shapely.union_all(cells).intersection(overlap) if cells else None
        if lose is not None and not lose.is_empty:
            area = area.difference(lose)
            print(f"  {o}: {lose.area / 1e4:.1f} ha of overlap given to it")
    geo = json.loads((ROOT / "public/data/districts.geojson").read_text())
    dist = shape(next(f["geometry"] for f in geo["features"] if f["properties"]["id"] == cfg["district"]))
    ring = np.array(dist.exterior.coords if dist.geom_type == "Polygon" else max(dist.geoms, key=lambda g: g.area).exterior.coords)
    area = area.intersection(Polygon(np.column_stack(local.to_m(ring[:, 0], ring[:, 1]))))
    parts = [g for g in getattr(area, "geoms", [area]) if g.geom_type == "Polygon" and g.area > 0.02 * area.area]
    print(f"{key}: {len(own)} labels, {len(parts)} pieces, {sum(g.area for g in parts) / 1e6:.2f} km²")
    rings = []
    for g in parts:
        g = g.simplify(2)
        lng, lat = local.to_ll(*np.array(g.exterior.coords).T)
        rings.append([[round(float(a), 7), round(float(b), 7)] for a, b in zip(lng, lat)])
    p = ROOT / f"districts/{key}.json"
    c = json.loads(p.read_text())
    c["plan"]["clip"] = {"note": note, "keep": "inside", **({"polygon": rings[0]} if len(rings) == 1 else {"polygons": rings})}
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n")
    (ROOT / f"scripts/.cache/{key}-area.geojson").write_text(json.dumps(
        {"type": "Feature", "properties": {}, "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}}))


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4:])
