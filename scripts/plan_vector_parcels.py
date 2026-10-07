"""Plots and zone areas from a vector plan PDF: the plot lines are read as paths, not pixels.

A vector plan draws every plot line as a path in one stroke style (Budapest VI.: blue, 0.48 pt).
Those paths are polygonized; each region that holds exactly one parcel number (hrsz, from the text
layer) is that plot. A number in brackets, "(28666)", is a public street. The regions are
georeferenced with the sheet fit plan_georef.py saved (scripts/plans/<key>.json).

Zones: each plot takes the zone code printed inside it; else the nearest code printed in its block
(the plots that touch it, up to the streets); else the nearest code within NEAR_M. The zone areas are
the plots of one zone in one block, merged.

    python3 scripts/plan_vector_parcels.py <key>

Config, districts/<key>.json:
  "plan": {"parcel_strokes": [[[r, g, b], width_pt], ...]}   plot line styles (colour 0..1);
                                                              found from the parcel numbers when not given
          "parcel_numbers": false                             numbers are not text: every region is a plot
Writes public/data/parcels-<key>/ and zones-<key>/ as grid chunks, and their entries in regulations.json.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pymupdf
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_georef as pg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CELL = (0.004, 0.003)  # same grid as plan_parcels.py
HRSZ = re.compile(r"^(\()?(\d{3,6}(?:/\d+)?)(\))?$")
MIN_M2, MAX_M2 = 15, 200_000
NEAR_M = 60  # a plot with no code in its block takes the nearest code this close
EXTEND_PT = 0.8  # ~0.5-1 m at 1:2000-1:2500
STREET_CODE = re.compile(r"^(KÖ|Kt-K|Kt-Fk|Köu|Kök)")


def is_hatch(items):
    """A hatch: a path of separate parallel strokes side by side (drawn across a plot, not around it).
    Collinear pieces of one broken line are not a hatch."""
    lines = [it for it in items if it[0] == "l"]
    if len(lines) < 4 or len(lines) < len(items):
        return False
    a = np.array([[p.x, p.y, q.x, q.y] for _, p, q in lines])
    ang = np.arctan2(a[:, 3] - a[:, 1], a[:, 2] - a[:, 0])
    if np.ptp(np.unwrap(ang * 2) / 2) > 0.05:
        return False
    n = np.array([-np.sin(ang[0]), np.cos(ang[0])])
    offsets = np.round(((a[:, :2] + a[:, 2:]) / 2) @ n, 1)
    return len(set(offsets)) >= len(lines) * 0.75


def extend(seg, d=EXTEND_PT):
    """A segment lengthened at both ends: plot lines that stop just short of each other still meet
    (the overshoot is a dangle polygonize drops)."""
    a = np.array(seg, float)
    if len(a) < 2:
        return a
    for i, j in ((0, 1), (-1, -2)):
        v = a[i] - a[j]
        n = np.hypot(*v)
        if n > 1e-6:
            a[i] = a[i] + v / n * d
    return a


def faces(segs):
    """The regions the lines enclose, holes filled: a building drawn inside a plot is a hole in the
    plot's face, and the plot's number is often printed on the building."""
    return [Polygon(f.exterior) for f in polygonize(unary_union([LineString(extend(x)) for x in segs if len(x) > 1]))]


def assign(polys, nums):
    """Each number goes to the largest region that holds it and no other number: the plot, not the
    building on it, nor a block or frame drawn around many plots."""
    tree, held = STRtree(polys), defaultdict(set)
    hits = []
    for hrsz, street, pt in nums:
        h = [j for j in tree.query(pt) if polys[j].contains(pt)]
        hits.append(h)
        for j in h:
            held[j].add(hrsz)
    inside = defaultdict(list)
    for (hrsz, street, _), h in zip(nums, hits):
        own = [j for j in h if len(held[j]) == 1]
        if own:
            inside[max(own, key=lambda j: polys[j].area)].append((hrsz, street))
    return inside


def strokes(page, styles):
    """Line segments of the paths drawn in one of the plot line styles, in page points."""
    want = {(tuple(round(c, 2) for c in rgb), round(w, 2)) for rgb, w in styles}
    out = []
    for d in page.get_drawings():
        col = d.get("color")
        if not col or "s" not in d["type"] or (tuple(round(c, 2) for c in col), round(d.get("width") or 0, 2)) not in want:
            continue
        if is_hatch(d["items"]):
            continue
        for it in d["items"]:
            if it[0] == "l":
                out.append([tuple(it[1]), tuple(it[2])])
            elif it[0] == "c":  # a curve: its chord is close enough at plot scale
                out.append([tuple(it[1]), tuple(it[4])])
            elif it[0] == "re":
                r = it[1]
                out.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)])
            elif it[0] == "qu":
                q = it[1]
                out.append([tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll), tuple(q.ul)])
    return out


def numbers(page):
    """Parcel numbers in the text layer: (hrsz, is_street, point). Bold text is drawn many times
    over itself, so repeats at the same place count once."""
    seen, out = set(), []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            m = HRSZ.match(t)
            if not m or bool(m.group(1)) != bool(m.group(3)):
                continue
            x0, y0, x1, y1 = ln["bbox"]
            k = (m.group(2), round(x0 / 3), round(y0 / 3))
            if k not in seen:
                seen.add(k)
                out.append((m.group(2), bool(m.group(1)), Point((x0 + x1) / 2, (y0 + y1) / 2)))
    return out


def region_score(page, styles, nums):
    """Regions that hold exactly one parcel number when these styles are the plot lines."""
    segs = strokes(page, styles)
    polys = faces(segs) if segs else []
    if not polys:
        return 0
    return sum(len({h for h, _ in x}) == 1 for x in assign(polys, nums).values())


def detect_strokes(page):
    """The plot line styles, when the config does not give them: the stroke style whose regions
    best hold one parcel number each, plus any style that adds 3% more such regions."""
    nums = numbers(page)
    count = Counter()
    for d in page.get_drawings():
        if d.get("color") and "s" in d["type"]:
            count[(tuple(round(c, 2) for c in d["color"]), round(d.get("width") or 0, 2))] += len(d["items"])
    cands = [[list(k[0]), k[1]] for k, n in count.most_common(20) if n > 50]
    score = sorted(((region_score(page, [c], nums), c) for c in cands), key=lambda x: -x[0])
    if not score or not score[0][0]:
        return []
    chosen, best = [score[0][1]], score[0][0]
    for _, c in score[1:8]:
        s = region_score(page, chosen + [c], nums)
        if s > best * 1.03:
            chosen, best = chosen + [c], s
    print(f"  plot line styles: {chosen} ({best}/{len(nums)} numbers in a region of their own)")
    return chosen


def sheet_parcels(cfg, i, page, fit, local):
    """The plots on one sheet, as (lng/lat polygon, hrsz, street)."""
    zoom = cfg["plan"]["dpi"] / 72
    mat = page.rotation_matrix * pymupdf.Matrix(zoom, zoom)  # page points -> sheet pixels
    f = fit["sheets"][i]
    model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
    styles = cfg["plan"].get("parcel_strokes") or detect_strokes(page)
    polys = faces(strokes(page, styles))
    inside = assign(polys, numbers(page))
    if cfg["plan"].get("parcel_numbers") is False:
        # Plans whose parcel numbers are drawn as curves (Budapest VI. north): every region is a plot.
        inside = {j: [(None, False)] for j in range(len(polys))}
    frame = cfg["plan"].get("frames", [None] * (i + 1))[i]
    blanks = [box(*b[1:]) for b in cfg["plan"].get("blank", []) if b[0] == i]
    out = []
    for j, labs in inside.items():
        if len({h for h, _ in labs}) != 1:
            continue  # two numbers: the region is two plots whose shared line is missing
        pts = np.array([tuple(pymupdf.Point(x, y) * mat) for x, y in polys[j].exterior.coords])
        c = pts.mean(0)
        if frame and not (frame[0] <= c[0] <= frame[2] and frame[1] <= c[1] <= frame[3]):
            continue
        if any(b.contains(Point(*c)) for b in blanks):
            continue
        lng, lat = local.to_ll(*model(pts).T)
        poly = Polygon(np.column_stack([lng, lat])).buffer(0)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        if not poly.is_empty:
            out.append((poly, labs[0][0], labs[0][1]))
    print(f"sheet{i}: {len(polys)} regions, {len(inside)} with a number, {len(out)} plots")
    return out


def area_m2(g):
    return g.area * 111_320 * np.cos(np.radians(g.centroid.y)) * 110_540


def chunks(feats, out_dir):
    """Grid chunks: the app loads only the cell around a tap (a feature is stored in every cell it touches)."""
    if out_dir.exists():
        for f in out_dir.glob("*.json"):
            f.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = defaultdict(list)
    for f in feats:
        g = shape(f["geometry"])
        x0, y0, x1, y1 = g.bounds
        for ix in range(int(x0 // CELL[0]), int(x1 // CELL[0]) + 1):
            for iy in range(int(y0 // CELL[1]), int(y1 // CELL[1]) + 1):
                cells[f"{ix}_{iy}"].append(f)
    for k, fs in cells.items():
        (out_dir / f"{k}.json").write_text(json.dumps({"type": "FeatureCollection", "features": fs}, separators=(",", ":")))
    return len(cells), sum(f.stat().st_size for f in out_dir.glob("*.json"))


def coords(g):
    r = lambda ring: [[round(x, 6), round(y, 6)] for x, y in ring.coords]
    if g.geom_type == "Polygon":
        return {"type": "Polygon", "coordinates": [r(g.exterior)] + [r(h) for h in g.interiors]}
    return {"type": "MultiPolygon", "coordinates": [[r(p.exterior)] + [r(h) for h in p.interiors] for p in g.geoms]}


def main():
    key = sys.argv[1]
    cfg = dcfg.load(key)
    reg_id = dcfg.reg_id(cfg)
    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    local = pg.Local(*fit["local"])
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg = regs["regulations"][reg_id]
    districts = json.loads((ROOT / "public/data/districts.geojson").read_text())
    district_id = next(int(d) for d, v in regs["districts"].items() if reg_id in v["regulations"])
    area = shape(next(f["geometry"] for f in districts["features"] if f["properties"]["id"] == district_id))
    if reg.get("plan", {}).get("area"):
        area = area.intersection(Polygon(reg["plan"]["area"][0]))

    # Sheets in plan_sheets.py order: every page of every annex, minus plan.pages.
    plots, i = [], 0
    for ref in cfg["plan"]["annexes"]:
        doc = pymupdf.open(dcfg.work_dir(key) / "annex" / Path(ref).name)
        for page in doc:
            if cfg["plan"].get("pages") and page.number + 1 not in cfg["plan"]["pages"]:
                continue
            if i < len(fit["sheets"]) and fit["sheets"][i].get("coef") is not None:
                plots += sheet_parcels(cfg, i, page, fit, local)
            i += 1

    # Sheets overlap: one plot per number, the largest copy; then nothing outside the plan's area.
    best = {}
    for poly, hrsz, street in plots:
        a = area_m2(poly)
        k = hrsz if hrsz is not None else poly.representative_point().wkt
        if MIN_M2 <= a <= MAX_M2 and area.contains(poly.representative_point()) and (k not in best or a > best[k][3]):
            best[k] = (poly, hrsz, street, a)
    plots = list(best.values())
    print(f"{len(plots)} plots ({sum(p[2] for p in plots)} streets)")

    # Zone of each plot.
    labels = [(f["properties"]["code"], Point(f["geometry"]["coordinates"]))
              for f in json.loads((ROOT / "public/data" / reg["zoneLabels"]).read_text())["features"]
              if f["properties"].get("reg", reg_id) == reg_id]
    ltree = STRtree([p for _, p in labels])
    geoms = [p[0] for p in plots]
    ptree = STRtree(geoms)
    on_plot = []
    for g in geoms:
        codes = [labels[j][0] for j in ltree.query(g) if g.contains(labels[j][1])]
        on_plot.append(Counter(codes).most_common(1)[0][0] if codes else None)
    # Blocks: building plots that touch (within ~0.5 m), never across a street plot.
    eps = 0.5 / 111_000
    parent = list(range(len(plots)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, g in enumerate(geoms):
        if plots[a][2]:
            continue
        for b in ptree.query(g.buffer(eps)):
            if b != a and not plots[b][2] and g.distance(geoms[b]) < eps:
                parent[find(a)] = find(b)
    block_labels = defaultdict(list)
    for j, (code, pt) in enumerate(labels):
        for a in ptree.query(pt):
            if geoms[a].contains(pt) and not plots[a][2]:
                block_labels[find(a)].append(j)
    zone, status = [], []
    m_per_deg = 111_000
    for a, (g, hrsz, street, _) in enumerate(plots):
        code, st = on_plot[a], "plan"
        if code is None:
            st = "estimated"
            c = g.representative_point()
            cand = block_labels.get(find(a), []) if not street else []
            if cand:
                code = labels[min(cand, key=lambda j: labels[j][1].distance(c))][0]
            else:
                near = [j for j in ltree.query(c.buffer(NEAR_M / m_per_deg))
                        if bool(STREET_CODE.match(labels[j][0])) == street]
                if near:
                    j = min(near, key=lambda j: labels[j][1].distance(c))
                    if labels[j][1].distance(c) * m_per_deg <= NEAR_M:
                        code = labels[j][0]
        zone.append(code)
        status.append(st)

    feats = []
    for (g, hrsz, street, a), code, st in zip(plots, zone, status):
        g = g.simplify(0.000002)
        feats.append({"type": "Feature", "properties": {
            "hrsz": hrsz, "areaM2": round(a), "check": ["street"] if street else [],
            "zones": [{"code": code, "status": st, "share": 1.0}] if code else []},
            "geometry": coords(g)})
    n_cells, size = chunks(feats, ROOT / "public/data" / f"parcels-{key}")
    print(f"parcels: {len(feats)}, {sum(bool(z) for z in zone)} with a zone "
          f"({sum(s == 'plan' for s, z in zip(status, zone) if z)} printed on the plot), {n_cells} cells, {size / 1e6:.1f} MB")

    # Zone areas: the plots of one zone in one block (streets: connected street plots of one code).
    groups = defaultdict(list)
    for a, code in enumerate(zone):
        if code:
            groups[(code, plots[a][2], None if plots[a][2] else find(a))].append(a)
    zfeats = []
    for (code, street, _), members in groups.items():
        u = unary_union([geoms[a].buffer(eps) for a in members]).buffer(-eps)
        parts = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
        for part in parts:
            if part.is_empty:
                continue
            has_label = any(part.contains(labels[j][1]) and labels[j][0] == code for j in ltree.query(part))
            zfeats.append({"type": "Feature", "properties": {"code": code, "status": "plan" if has_label else "estimated", "street": street},
                           "geometry": coords(part.simplify(0.000002))})
    n_cells, size = chunks(zfeats, ROOT / "public/data" / f"zones-{key}")
    print(f"zone areas: {len(zfeats)}, {n_cells} cells, {size / 1e6:.1f} MB")

    reg["parcels"] = {"dir": f"parcels-{key}", "cell": list(CELL)}
    reg["zoneAreas"] = {"dir": f"zones-{key}", "cell": list(CELL)}
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
