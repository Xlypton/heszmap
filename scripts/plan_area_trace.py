"""The area a partial KÉSZ plan regulates, traced by hand on its sheet, written as plan.clip.

    python3 scripts/plan_area_trace.py <key> "<note>" '<[[x, y], ...] in sheet pixels>' [<other key> ...]

Budapest IV. (Újpest) units 6 and 10: the plan colours its own unit and has no boundary line a script
can follow, and its zone codes are too few for plan_area_labels.py to outline the unit. The outline is
picked by eye on sheet 0 (along the edge roads, streams and railway) and placed through the saved fit
(scripts/plans/<key>.json). Where it overlaps the area of another key given after the points (a
neighbouring unit), each point goes to the unit whose nearest zone label is nearer. The area is then
cut to the district. The traced points are kept in plan.clip.traced, so the area can be redone.
"""
import json
import sys
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_georef as pg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GRID_DEG = 0.00005  # cell size (about 4-5 m) for splitting overlaps between units


def main(key, note, traced, others):
    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    f = fit["sheets"][0]
    local = pg.Local(*fit["local"])
    model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
    m = model(np.array(traced, float))
    area = Polygon(np.column_stack(local.to_ll(m[:, 0], m[:, 1]))).buffer(0)

    def labels_m(k):
        feats = json.loads((ROOT / f"public/data/zone-labels-{k}.geojson").read_text())["features"]
        ll = np.array([x["geometry"]["coordinates"] for x in feats])
        return np.column_stack(local.to_m(ll[:, 0], ll[:, 1]))

    own = cKDTree(labels_m(key))
    for o in others:
        c = json.loads((ROOT / f"districts/{o}.json").read_text())["plan"]["clip"]
        overlap = area.intersection(shapely.union_all([Polygon(r).buffer(0) for r in c.get("polygons") or [c["polygon"]]]))
        if overlap.is_empty:
            continue
        x0, y0, x1, y1 = overlap.bounds
        xs, ys = np.meshgrid(np.arange(x0, x1, GRID_DEG), np.arange(y0, y1, GRID_DEG))
        g = np.column_stack([xs.ravel(), ys.ravel()])
        gm = np.column_stack(local.to_m(g[:, 0], g[:, 1]))
        theirs_nearer = cKDTree(labels_m(o)).query(gm)[0] < own.query(gm)[0]
        cells = [Point(p).buffer(GRID_DEG * 0.72, cap_style="square") for p in g[theirs_nearer]]
        if cells:
            area = area.difference(shapely.union_all(cells).intersection(overlap))
            print(f"  {o}: part of the overlap given to it")
    cfg = json.loads((ROOT / f"districts/{key}.json").read_text())
    geo = json.loads((ROOT / "public/data/districts.geojson").read_text())
    dist = shape(next(x["geometry"] for x in geo["features"] if x["properties"]["id"] == cfg["district"]))
    area = area.intersection(dist)
    parts = [g for g in getattr(area, "geoms", [area]) if g.geom_type == "Polygon" and g.area > 0.02 * area.area]
    km2 = sum(Polygon(np.column_stack(local.to_m(*np.array(g.exterior.coords).T))).area for g in parts) / 1e6
    print(f"{key}: {len(parts)} pieces, {km2:.2f} km²")
    rings = [[[round(x, 7), round(y, 7)] for x, y in g.simplify(0.00002).exterior.coords] for g in parts]
    cfg["plan"]["clip"] = {"note": note, "keep": "inside", **({"polygon": rings[0]} if len(rings) == 1 else {"polygons": rings}),
                           "traced": {"sheet": 0, "px": traced, "others": others}}
    (ROOT / f"districts/{key}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), sys.argv[4:])
