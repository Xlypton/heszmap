"""The area a partial KÉSZ plan regulates, from its boundary drawn as a chain of hollow squares, written as plan.clip.

    python3 scripts/plan_area_loop.py <key> "<note>"

Budapest XII. KÉSZ sheets draw the plan's own boundary as black hollow squares on a line, black like the plot
lines and text, and the land outside it with plots but no fills. plan_area.py's flood fill per sheet leaks
through the gaps where squares sit under other symbols and at sheet edges. Here the squares of every sheet
(plan.area_line: colour rule; plan.area_line_squares: [min side px, max side px]) are put on one map in
metres through each sheet's saved fit, the gaps closed (plan.area_line_gap_m), and the area is what the
closed loop encloses: no seed points. Uses scripts/plans/<key>.json; run plan_georef.py again afterwards.
Check the result: scripts/.cache/<key>-area.geojson (DEBUGIMG=<png> saves the mosaic).
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_georef as pg  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
RES = 2.0  # m per mosaic pixel


def squares(rgb, rule, sq):
    """Centres (px) of hollow squares that sit in a chain of at least three."""
    b = dcfg.mask(rgb, rule).astype(np.uint8)
    b = cv2.morphologyEx(b, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))  # thin plot lines away
    n, lab, st, cen = cv2.connectedComponentsWithStats(b, 8)
    w, h, a = st[:, 2], st[:, 3], st[:, 4]
    ok = (w >= sq[0]) & (w <= sq[1]) & (h >= sq[0]) & (h <= sq[1]) & (a >= 0.2 * w * h) & (a <= 0.6 * w * h)
    ok[0] = False
    ok &= lab[cen[:, 1].astype(int), cen[:, 0].astype(int)] != np.arange(n)  # hollow
    c = cen[ok]
    if len(c) < 3:
        return c[:0]
    d, _ = cKDTree(c).query(c, k=3)
    return c[(d[:, 1] < 2 * sq[1]) & (d[:, 2] < 3 * sq[1])]


def main(key, note):
    cfg = dcfg.load(key)
    plan = cfg["plan"]
    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    local = pg.Local(*fit["local"])
    pts = []
    # plan.area_line_from: neighbouring plans of the same series whose sheets draw the shared boundary too
    # (Budapest XII.: Észak-Hegyvidék's squares are faint where Dél-Hegyvidék's sheets show them well).
    for k in [key, *plan.get("area_line_from", [])]:
        kc = dcfg.load(k)
        kfit = json.loads((ROOT / "scripts/plans" / f"{k}.json").read_text())
        klocal = pg.Local(*kfit["local"])
        for i, (path, f) in enumerate(zip(dcfg.sheet_paths(kc), kfit["sheets"])):
            if f.get("skipped"):
                continue
            model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
            c = squares(np.asarray(Image.open(path).convert("RGB"), dtype=np.int16), plan["area_line"], plan["area_line_squares"])
            frame = (kc["plan"].get("frames") or [None] * 999)[i]
            if frame is not None and len(c):
                x0, y0, x1, y1 = frame
                c = c[(c[:, 0] > x0) & (c[:, 0] < x1) & (c[:, 1] > y0) & (c[:, 1] < y1)]
            if len(c):
                m = model(c)
                pts.append(np.column_stack(local.to_m(*klocal.to_ll(m[:, 0], m[:, 1]))))
        print(f"{k}: {sum(map(len, pts))} boundary squares so far")
    pts = np.vstack(pts)
    geo = json.loads((ROOT / "public/data/districts.geojson").read_text())
    dist = shape(next(f["geometry"] for f in geo["features"] if f["properties"]["id"] == cfg["district"]))
    b = dist.bounds  # the mosaic covers the whole district
    dlo, dhi = np.column_stack(local.to_m(np.array([b[0], b[2]]), np.array([b[1], b[3]])))
    lo = np.minimum(pts.min(0), dlo) - 200
    size = np.ceil((np.maximum(pts.max(0), dhi) + 200 - lo) / RES).astype(int)
    img = np.zeros((size[1], size[0]), np.uint8)
    px = np.round((pts - lo) / RES).astype(int)
    img[size[1] - 1 - px[:, 1], px[:, 0]] = 1
    gap = plan.get("area_line_gap_m", 40)
    rg = max(1, int(gap / 2 / RES))
    line = cv2.morphologyEx(cv2.dilate(img, np.ones((3, 3), np.uint8)), cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rg + 1, 2 * rg + 1)))
    # Longer gaps (squares under a road fill, a sheet with a weak fit): join each pair of line pieces by
    # their nearest squares, up to plan.area_line_join_m apart.
    join = plan.get("area_line_join_m", 150) / RES
    n, lab = cv2.connectedComponents(line, connectivity=8)
    pl = lab[size[1] - 1 - px[:, 1], px[:, 0]]
    groups = {g: px[pl == g] for g in range(1, n) if (pl == g).sum() >= 5}  # stray squares are not the line
    trees = {g: cKDTree(p) for g, p in groups.items()}
    for a in groups:
        for b in groups:
            if a < b:
                d, j = trees[b].query(groups[a])
                k = int(d.argmin())
                if d[k] < join:
                    p, q = groups[a][k], groups[b][j[k]]
                    cv2.line(line, (int(p[0]), int(size[1] - 1 - p[1])), (int(q[0]), int(size[1] - 1 - q[1])), 1, 2)
                    print(f"  joined two line pieces {d[k] * RES:.0f} m apart")
    # The district border is a wall too: where the plan's area reaches it, the squares often stop
    # (Budapest XII. Észak-Hegyvidék). The area is then every piece the walls cut out that holds
    # at least three of the plan's zone labels (scripts/plans/<key> georef output).
    ring = np.array(dist.exterior.coords if dist.geom_type == "Polygon" else max(dist.geoms, key=lambda g: g.area).exterior.coords)
    q = np.column_stack(local.to_m(ring[:, 0], ring[:, 1]))
    qp = np.round((q - lo) / RES).astype(np.int32)
    qp[:, 1] = size[1] - 1 - qp[:, 1]
    inside = np.zeros_like(line)
    cv2.fillPoly(inside, [qp], 1)
    cv2.polylines(line, [qp], True, 1, 2)
    n, lab = cv2.connectedComponents(((line == 0) & (inside == 1)).astype(np.uint8), connectivity=4)
    labels = json.loads((ROOT / f"public/data/zone-labels-{key}.geojson").read_text())["features"]
    seeds = np.array([f["geometry"]["coordinates"] for f in labels])
    sp = np.round((np.column_stack(local.to_m(seeds[:, 0], seeds[:, 1])) - lo) / RES).astype(int)
    ok = (sp[:, 0] >= 0) & (sp[:, 0] < size[0]) & (sp[:, 1] >= 0) & (sp[:, 1] < size[1])
    hits = np.bincount(lab[size[1] - 1 - sp[ok, 1], sp[ok, 0]], minlength=n)
    hits[0] = 0
    keep = np.nonzero(hits >= 3)[0]
    print(f"  {ok.sum()} zone labels; pieces with 3 or more: {[int(hits[k]) for k in keep]}, "
          f"left out: {int(hits.sum() - hits[keep].sum())} labels in other pieces")
    region = np.isin(lab, keep).astype(np.uint8)
    region = cv2.dilate(region, np.ones((5, 5), np.uint8)) & inside  # over the drawn line's width
    if os.environ.get("DEBUGIMG"):
        dbg = np.full(img.shape + (3,), 255, np.uint8)
        dbg[region == 1] = (150, 230, 150)
        dbg[line == 1] = (0, 0, 0)
        Image.fromarray(dbg).save(os.environ["DEBUGIMG"])
    cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    big = max(cv2.contourArea(c) for c in cnts)
    polys = []
    for c in cnts:
        if cv2.contourArea(c) < 0.02 * big:
            continue
        c = c[:, 0, :].astype(float)
        mx = c[:, 0] * RES + lo[0]
        my = (size[1] - 1 - c[:, 1]) * RES + lo[1]
        polys.append(Polygon(np.column_stack(local.to_ll(mx, my))).buffer(0))
    area = unary_union(polys).intersection(dist).simplify(0.00003)
    parts = [g for g in getattr(area, "geoms", [area]) if g.geom_type == "Polygon" and g.area > 0.02 * area.area]
    km2 = sum(Polygon(np.column_stack(local.to_m(*np.array(g.exterior.coords).T))).area for g in parts) / 1e6
    print(f"{len(pts)} squares, gap {gap} m: {len(parts)} pieces, {km2:.2f} km²")
    rings = [[[round(x, 7), round(y, 7)] for x, y in g.exterior.coords] for g in parts]
    p = ROOT / f"districts/{key}.json"
    c = json.loads(p.read_text())
    c["plan"]["clip"] = {"note": note, "keep": "inside", **({"polygon": rings[0]} if len(rings) == 1 else {"polygons": rings})}
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n")
    (ROOT / f"scripts/.cache/{key}-area.geojson").write_text(json.dumps(
        {"type": "Feature", "properties": {}, "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
