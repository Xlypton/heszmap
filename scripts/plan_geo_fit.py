"""Georeference a vector plan that has NO street names and an unknown scale: one huge page that draws a
whole municipality (Mosonmagyaróvár: 14173 pt square, no street labels, a scale bar that does not match).

A CAD plan is an exact similarity of the national grid, so four numbers place it: scale (m per page
point), rotation (grid north vs true north, ~1.3° at 17.3°E) and a translation. They are found from the
drawing itself, in three stages, with nothing but the PDF paths and OpenStreetMap:

1. Outline: the plot lines (all of the municipality's cadastre) are filled to one silhouette and slid over
   the municipality's boundary polygon (scale x rotation grid, translation by FFT correlation, best
   intersection over union). Mosonmagyaróvár: IoU 0.98.
2. Buildings: the plan's building outlines (blue hairlines, grey fills) against OSM building edges, from
   a 60 m blur down to 2.5 m, one Nelder-Mead per blur, so a start 200 m off still ends in the right place.
3. Check: median distance of every plan building point to the nearest OSM building edge, overall and per
   2 km cell (a drifting cell would mean the plan is not a pure similarity).

    python3 scripts/plan_geo_fit.py <key>

Config, districts/<key>.json plan.geo_fit: {
  "plot_line": [[r, g, b], width_pt],          the cadastre line style (default black 0.72)
  "building_lines": [[[r, g, b], width_pt], ...], stroked building outlines (default blue hairline)
  "building_fills": [[r, g, b], ...],          filled building shapes (default two greys)
  "scale_m_per_pt": [lo, hi], "rotation_deg": [lo, hi]   search ranges (default 1.0-2.0, -4..4)
}
Writes scripts/plans/<key>.json (the saved fit plan_georef.py --reuse-fit uses; sheet pixels at plan.dpi)
and scripts/plans/<key>-fit-0.json (the report).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pymupdf
from scipy import ndimage, optimize
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import osm_ref  # noqa: E402
import plan_georef as pg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def near(c, t, tol=0.02):
    return c is not None and all(abs(a - b) < tol for a, b in zip(c, t))


def read_features(page, conf):
    """Line segments (page pts) of the cadastre lines, the building outlines, the filled buildings."""
    pl = conf.get("plot_line", [[0, 0, 0], 0.72])
    bl = conf.get("building_lines", [[[0, 0, 1], 0.0]])
    bf = conf.get("building_fills", [[0.74, 0.74, 0.74], [0.44, 0.44, 0.44]])
    plot, bld = [], []
    for d in page.get_drawings():
        col, fill, w = d.get("color"), d.get("fill"), d.get("width") or 0
        target = None
        if fill is None and near(col, pl[0]) and abs(w - pl[1]) < 0.02:
            target = plot
        elif fill is None and any(near(col, c) and w <= wd + 0.1 for c, wd in bl):
            target = bld
        elif fill is not None and any(near(fill, c) for c in bf):
            target = bld
        if target is None:
            continue
        for it in d["items"]:
            if it[0] == "l":
                target.append((it[1].x, it[1].y, it[2].x, it[2].y))
    return np.array(plot), np.array(bld)


def sample(seg, step):
    n = np.maximum((np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1]) / step).astype(int), 1)
    out = []
    for (x0, y0, x1, y1), k in zip(seg, n):
        t = (np.arange(k) + 0.5) / k
        out.append(np.column_stack([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]))
    return np.vstack(out)


def to_m(P, s, th, t):
    """Page points (y down) -> local metres (x east, y north): the same convention as plan_fit.to_metres."""
    c, sn = math.cos(th), math.sin(th)
    return s * np.column_stack([P[:, 0], -P[:, 1]]) @ np.array([[c, -sn], [sn, c]]).T + t


def outline_fit(plot, local, ring, s_range, th_range):
    import cv2
    mx, my = local.to_m(ring[:, 0], ring[:, 1])
    CELL, N = 40.0, 900
    off = -N * CELL / 2
    D = np.zeros((N, N), np.uint8)
    cv2.fillPoly(D, [np.column_stack([(mx - off) / CELL, (my - off) / CELL]).astype(np.int32)], 1)
    D = D.astype(np.float32)
    PC = 20.0
    pts = sample(plot, 6.0)
    M = int(pts.max() / PC) + 2
    pm = np.zeros((M, M), np.uint8)
    ij = (pts / PC).astype(int)
    pm[ij[:, 1], ij[:, 0]] = 1
    pm = ndimage.binary_opening(ndimage.binary_fill_holes(ndimage.binary_closing(pm, iterations=3)), iterations=2)
    ys, xs = np.nonzero(pm)
    Q = np.column_stack([(xs + .5) * PC, (ys + .5) * PC])
    Dp = np.fft.rfft2(D)
    best = (0, None)
    for s in np.arange(s_range[0], s_range[1], 0.01):
        for th in np.radians(np.arange(th_range[0], th_range[1] + 0.01, 0.5)):
            m = to_m(Q, s, th, 0)
            img = np.zeros((N, N), np.float32)
            np.add.at(img, ((np.round((m[:, 1] - off) / CELL).astype(int)) % N, (np.round((m[:, 0] - off) / CELL).astype(int)) % N), 1)
            img = ndimage.binary_closing(img > 0, iterations=1).astype(np.float32)
            I = np.fft.irfft2(np.fft.rfft2(img) * np.conj(Dp), s=(N, N))
            iou = I / (img.sum() + D.sum() - I)
            k = np.unravel_index(np.argmax(iou), iou.shape)
            if iou[k] > best[0]:
                wrap = lambda v: (v + N * CELL / 2) % (N * CELL) - N * CELL / 2
                best = (float(iou[k]), (s, th, wrap(-k[1] * CELL), wrap(-k[0] * CELL)))
    return best


def main(key):
    cfg = dcfg.load(key)
    conf = cfg["plan"].get("geo_fit", {})
    dpi = cfg["plan"]["dpi"]
    zoom = dpi / 72
    dist = json.loads((ROOT / "public/data/districts.geojson").read_text())
    geom = next(f["geometry"] for f in dist["features"] if f["properties"]["id"] == cfg["district"])
    ring = np.array((geom["coordinates"][0] if geom["type"] == "Polygon" else max(geom["coordinates"], key=lambda p: len(p[0]))[0]))
    local = pg.Local(float(ring[:, 0].mean()), float(ring[:, 1].mean()))
    bbox = [ring[:, 0].min() - 0.01, ring[:, 1].min() - 0.01, ring[:, 0].max() + 0.01, ring[:, 1].max() + 0.01]

    ref = cfg["plan"]["annexes"][0]
    pdf = dcfg.work_dir(key) / "annex" / Path(ref).name
    page = pymupdf.open(pdf)[cfg["plan"]["pages"][0] - 1]
    plot, bld = read_features(page, conf)
    print(f"{len(plot)} cadastre segments, {len(bld)} building segments")

    iou, (s, th, tx, ty) = outline_fit(plot, local, ring, conf.get("scale_m_per_pt", [1.0, 2.0]), conf.get("rotation_deg", [-4, 4]))
    print(f"outline: IoU {iou:.3f}, {s:.3f} m/pt, {math.degrees(th):.2f} deg, t=({tx:.0f}, {ty:.0f})")

    buildings, _ = osm_ref.fetch(bbox, whole_buildings=True)
    edges = []
    for r in buildings:
        x, y = local.to_m(r[:, 0], r[:, 1])
        for i in range(len(x) - 1):
            k = max(int(math.hypot(x[i + 1] - x[i], y[i + 1] - y[i])), 1)
            t = np.arange(k) / k
            edges.append(np.column_stack([x[i] + (x[i + 1] - x[i]) * t, y[i] + (y[i + 1] - y[i]) * t]))
    O = np.vstack(edges)
    P = sample(bld, 3.0)
    x0, y0 = O.min(0) - 200
    x1, y1 = O.max(0) + 200

    def field(cell, sigma):
        img = np.zeros((int((y1 - y0) / cell) + 1, int((x1 - x0) / cell) + 1), np.float32)
        np.add.at(img, (((O[:, 1] - y0) / cell).astype(int), ((O[:, 0] - x0) / cell).astype(int)), 1)
        img = ndimage.gaussian_filter(img, sigma / cell)
        return img / img.max()

    def score(p, fld, cell, sub):
        m = to_m(P[::sub], p[0], p[1], p[2:4])
        return -ndimage.map_coordinates(fld, [(m[:, 1] - y0) / cell, (m[:, 0] - x0) / cell], order=1, mode="constant", cval=0).mean()

    x = np.array([s, th, tx, ty])
    for sigma, cell, sub in [(60, 20, 5), (30, 10, 4), (15, 5, 3), (8, 3, 2), (4, 1.5, 1), (2.5, 1, 1)]:
        fld = field(cell, sigma)
        sd = np.array([0.01, math.radians(0.3), 30, 30]) * (sigma / 60) ** 0.5
        r = optimize.minimize(lambda z: score(x + z * sd, fld, cell, sub), np.zeros(4), method="Nelder-Mead",
                              options={"xatol": 1e-3, "fatol": 1e-6, "maxiter": 400})
        x = x + r.x * sd
        print(f"  blur {sigma:>4} m: {x[0]:.4f} m/pt, {math.degrees(x[1]):.3f} deg, t=({x[2]:.1f}, {x[3]:.1f})", flush=True)

    # check
    m = to_m(P, x[0], x[1], x[2:4])
    d, idx = cKDTree(O).query(m)
    cells = {}
    gx, gy = np.floor(m[:, 0] / 2000).astype(int), np.floor(m[:, 1] / 2000).astype(int)
    off = O[idx] - m
    for a in sorted(set(zip(gx.tolist(), gy.tolist()))):
        k = (gx == a[0]) & (gy == a[1])
        if (k & (d < 8)).sum() > 400:
            cells[f"{a[0]},{a[1]}"] = {"points": int(k.sum()), "medianOffsetM": [round(float(v), 2) for v in np.median(off[k & (d < 8)], axis=0)],
                                      "medianNearestM": round(float(np.median(d[k])), 2)}
    report = {"sheet": 0, "method": "plan_geo_fit", "outlineIoU": round(iou, 3), "mPerPt": round(float(x[0]), 5),
              "rotationDeg": round(math.degrees(x[1]), 4), "translationM": [round(float(v), 2) for v in x[2:]],
              "buildingMedianNearestM": round(float(np.median(d)), 2), "within10mShare": round(float((d < 10).mean()), 3),
              "cells2km": cells}
    print(json.dumps({k: v for k, v in report.items() if k != "cells2km"}))
    (ROOT / "scripts/plans" / f"{key}-fit-0.json").write_text(json.dumps(report, indent=1) + "\n")

    # the saved fit: sheet pixels (at plan.dpi) -> local metres
    W = round(page.rect.width * zoom)
    H = round(page.rect.height * zoom)
    g = np.stack(np.meshgrid(np.linspace(0, W, 15), np.linspace(0, H, 15)), -1).reshape(-1, 2)
    model = pg.PolyModel.fit(g, to_m(g / zoom, x[0], x[1], x[2:4]), 1, np.array([W, H], float) / 2, W / 3)
    sheet = dcfg.sheet_paths(cfg)[0].name
    (ROOT / "scripts/plans" / f"{key}.json").write_text(json.dumps(
        {"local": [local.lng0, local.lat0], "sheets": [{"sheet": sheet, **model.to_json()}]}, indent=1) + "\n")
    print("saved scripts/plans/%s.json" % key)


if __name__ == "__main__":
    main(sys.argv[1])
