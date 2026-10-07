"""Plots and zone areas from a vector plan PDF: the plot lines are read as paths, not pixels.

A vector plan draws every plot line as a path in one stroke style (Budapest VI.: blue, 0.48 pt).
Those paths are polygonized; each region that holds exactly one parcel number (hrsz, from the text
layer) is that plot. A number in brackets, "(28666)", is a public street. The regions are
georeferenced with the sheet fit plan_georef.py saved (scripts/plans/<key>.json).

Zones: each plot takes the zone code printed inside it; else the one code in the area the plan's
zone boundary lines enclose around it (plan.zone_lines, see write()); else the nearest code printed in its block
(the plots that touch it, up to the streets); else the nearest code within NEAR_M. The zone areas are
the plots of one zone in one block, merged.

    python3 scripts/plan_vector_parcels.py <key>
    python3 scripts/plan_vector_parcels.py <key> --zones-only [--smooth]   zones for plots plan_parcels.py traced

Config, districts/<key>.json:
  "plan": {"parcel_strokes": [[[r, g, b], width_pt | "fill"], ...]}   plot line styles (colour 0..1);
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
# Budapest parcel numbers have 4-6 digits; 3-digit numbers on these plans are heights and sheet
# numbers. A district can set its own pattern ("plan": {"hrsz": ...}, one group for the number).
HRSZ = re.compile(r"^(\()?(\d{4,6}(?:/\d+)?)(\))?$")
HRSZ_DEFAULT = HRSZ
MIN_M2, MAX_M2 = 15, 200_000
NEAR_M = {False: 150, True: 60}  # a plot with no code in its block takes the nearest code this close (building plot, street)
LABEL_REACH_M = 12  # a zone code printed off the plots belongs to a building plot this close
EXTEND_PT = 0.8  # ~0.5-1 m at 1:2000-1:2500
# A traced building plot whose outline is this much longer than its convex hull's (a rectangle,
# however long, is 1.0; an L-shaped plot ~1.1) is a comb cut by hatching, which the tracer reads as
# plot lines: it is left out rather than shown wrong.
MAX_RAGGED = 1.3
MIN_WIDTH_M = 3.5  # mean width (2·area / perimeter; an 8 x 80 m plot is 7.3 m): narrower is a strip between hatch lines
SMOOTH_M = 1.2  # --smooth: slits and spikes narrower than ~2.4 m go
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


_DRAWINGS = {}


def drawings(page):
    k = (page.parent.name, page.number)
    if k not in _DRAWINGS:
        _DRAWINGS.clear()  # one page at a time: a sheet has up to ~200k paths
        _DRAWINGS[k] = page.get_drawings()
    return _DRAWINGS[k]


def style_of(d, fill=False):
    """A path's style key: (stroke colour, width), or (fill colour, "fill") for the outline of a
    filled area (Budapest XIV.: a street's edge is where its fill ends, with no line drawn)."""
    if fill:
        return (tuple(round(c, 2) for c in d["fill"]), "fill") if d.get("fill") and "f" in d["type"] else None
    return (tuple(round(c, 2) for c in d["color"]), round(d.get("width") or 0, 2)) if d.get("color") and "s" in d["type"] else None


def strokes(page, styles):
    """Line segments of the paths drawn in one of the plot line styles, in page points."""
    want = {(tuple(round(c, 2) for c in rgb), w if w == "fill" else round(w, 2)) for rgb, w in styles}
    out = []
    for d in drawings(page):
        if style_of(d) not in want and style_of(d, True) not in want:
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
            if not m or (m.re is HRSZ_DEFAULT and bool(m.group(1)) != bool(m.group(3))):
                continue
            x0, y0, x1, y1 = ln["bbox"]
            k = (t, round(x0 / 3), round(y0 / 3))
            if k not in seen:
                seen.add(k)
                num = m.group(2) if m.re is HRSZ_DEFAULT else m.group(1)
                out.append((num, m.re is HRSZ_DEFAULT and bool(m.group(1)), Point((x0 + x1) / 2, (y0 + y1) / 2)))
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
    for d in drawings(page):
        for k in (style_of(d), style_of(d, True)):
            if k:
                count[k] += len(d["items"])
    cands = [[list(k[0]), k[1]] for k, n in count.most_common(24) if n > 50]
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


def fill_polygon(d):
    """The area a filled path covers, in page points."""
    polys, pts = [], []
    for it in d["items"]:
        if it[0] == "re":
            polys.append(box(*it[1]))
        elif it[0] == "qu":
            polys.append(Polygon([tuple(p) for p in it[1]]))
        else:
            a, b = tuple(it[1]), tuple(it[-1])
            if pts and pts[-1] != a:
                if len(pts) > 2:
                    polys.append(Polygon(pts))
                pts = []
            if not pts:
                pts.append(a)
            pts.append(b)
    if len(pts) > 2:
        polys.append(Polygon(pts))
    return unary_union([q.buffer(0) for q in polys])


def sheet_zone_lines(cfg, i, page, fit, local):
    """The plan's zone boundary and regulation lines on one sheet, as lng/lat polygons: each line
    drawn plan.zone_lines ([[r, g, b], width_pt, reach_pt], ...) widened by its reach. A dotted
    boundary needs a reach of about half its dot spacing to read as one unbroken line. Dots drawn as
    marker characters: {"glyph": "!", "font": "ESRIDefaultMarker", "color": "#ff0000", "reach": 4}."""
    zoom = cfg["plan"]["dpi"] / 72
    mat = page.rotation_matrix * pymupdf.Matrix(zoom, zoom)
    f = fit["sheets"][i]
    model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
    bars = []
    paths = [x for x in cfg["plan"]["zone_lines"] if isinstance(x, list)]
    glyphs = [x for x in cfg["plan"]["zone_lines"] if isinstance(x, dict)]
    if glyphs:  # a dotted line drawn as marker characters (ESRI exports: "!" in ESRIDefaultMarker)
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln["spans"]:
                    for gl in glyphs:
                        if (sp["text"].strip() == gl["glyph"] and sp["font"] == gl["font"]
                                and sp["color"] == int(gl["color"].lstrip("#"), 16)):
                            x0, y0, x1, y1 = sp["bbox"]
                            bars.append(Point((x0 + x1) / 2, (y0 + y1) / 2).buffer(gl["reach"], 4))
    for d in drawings(page):
        if not d.get("color"):
            continue
        for rgb, w, reach in paths:
            if np.allclose(d["color"], rgb, atol=0.02) and abs((d.get("width") or 0) - w) < 0.02:
                for it in d["items"]:
                    if it[0] == "l":
                        bars.append(LineString([tuple(it[1]), tuple(it[2])]).buffer(reach, 4))
                    elif it[0] == "c":
                        bars.append(LineString([tuple(q) for q in it[1:5]]).buffer(reach, 4))
                    elif it[0] == "re":
                        bars.append(box(*it[1]).buffer(reach, 4))
                break
    if not bars:
        return []
    u = unary_union(bars)
    to_ll = lambda ring: np.column_stack(local.to_ll(*model(np.array([tuple(pymupdf.Point(x, y) * mat) for x, y in ring.coords])).T))
    out = []
    for part in (u.geoms if u.geom_type == "MultiPolygon" else [u]):
        g = Polygon(to_ll(part.exterior), [to_ll(h) for h in part.interiors]).buffer(0)
        if not g.is_empty:
            out.append(g)
    return out


def raster_zone_lines(key, cfg, fit, local):
    """Zone boundary and regulation lines found in scanned sheets by colour (styles.zone_boundary):
    an opening drops thin red hatching and lettering, a dilation by plan.zone_line_reach_px (half
    the dot spacing) joins the dots into one band."""
    import cv2
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    open_px = cfg["plan"].get("zone_line_open_px", 4)
    reach = cfg["plan"].get("zone_line_reach_px", 6)
    out = []
    for i, path in enumerate(dcfg.sheet_paths(cfg)):
        f = fit["sheets"][i] if i < len(fit["sheets"]) else {}
        if f.get("skipped") or f.get("coef") is None:
            continue
        model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
        rgb = np.array(Image.open(path).convert("RGB"))
        m = dcfg.mask(rgb, cfg["styles"]["zone_boundary"]).astype(np.uint8)
        del rgb
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_px, open_px)))
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * reach + 1, 2 * reach + 1)))
        frame = cfg["plan"].get("frames", [None] * (i + 1))[i]
        if frame:
            keep = np.zeros_like(m)
            keep[frame[1]:frame[3], frame[0]:frame[2]] = 1
            m &= keep
        contours, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hier is None:
            continue
        to_ll = lambda c: np.column_stack(local.to_ll(*model(c.reshape(-1, 2).astype(float)).T))
        for k, c in enumerate(contours):
            if hier[0][k][3] != -1 or len(c) < 3:
                continue  # holes are taken with their outer ring
            holes = []
            h = hier[0][k][2]
            while h != -1:
                if len(contours[h]) >= 3:
                    holes.append(to_ll(contours[h]))
                h = hier[0][h][0]
            g = Polygon(to_ll(c), holes).buffer(0)
            if not g.is_empty:
                out.append(g)
        print(f"  sheet{i}: zone lines found by colour")
    print(f"zone boundary lines: {len(out)} pieces (from the scans)")
    return out


def zone_lines(key, cfg, fit, local):
    """Zone boundary lines of every sheet (sheet_zone_lines), or None when plan.zone_lines is not
    configured. plan.zone_lines "raster": found by colour in the scans (raster_zone_lines)."""
    if not cfg["plan"].get("zone_lines"):
        return None
    if cfg["plan"]["zone_lines"] == "raster":
        return raster_zone_lines(key, cfg, fit, local)
    out, i = [], 0
    for ref in cfg["plan"]["annexes"]:
        doc = pymupdf.open(dcfg.work_dir(key) / "annex" / Path(ref).name)
        for page in doc:
            if cfg["plan"].get("pages") and page.number + 1 not in cfg["plan"]["pages"]:
                continue
            if i < len(fit["sheets"]) and fit["sheets"][i].get("coef") is not None:
                out += sheet_zone_lines(cfg, i, page, fit, local)
            i += 1
    print(f"zone boundary lines: {len(out)} pieces")
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


def write(key, reg_id, reg, plots, checks=None, lines=None):
    """Zone of each plot, then the plot and zone area chunks. plots: (polygon, hrsz, street, m²).
    lines: the plan's zone boundary lines (zone_lines). Touching plots are in one zone unless such a
    line runs between them; a group of plots holding exactly one zone code takes that code. A plot
    whose group holds none or several is flagged "zone-unclear" and takes the nearest code."""
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
    # Blocks: building plots that touch (within ~0.5 m), never across a street plot, nor across a
    # zone boundary line when the plan's lines are known.
    eps = dcfg.load(key)["plan"].get("block_gap_m", 0.5) / 111_000  # traced plots: ~2 m gaps along the lines
    parent = list(range(len(plots)))
    btree = STRtree(lines) if lines else None

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def divided(a, b):
        """A zone boundary line covers most of the strip where plots a and b touch."""
        strip = geoms[a].buffer(eps).intersection(geoms[b].buffer(eps))
        if strip.is_empty or not strip.area:
            return False
        near = [lines[j] for j in btree.query(strip)]
        return bool(near) and strip.intersection(unary_union(near)).area > 0.6 * strip.area
    cut = 0
    for a, g in enumerate(geoms):
        if plots[a][2]:
            continue
        for b in ptree.query(g.buffer(eps)):
            if b > a and not plots[b][2] and g.distance(geoms[b]) < eps and find(a) != find(b):
                if btree is not None and divided(a, b):
                    cut += 1
                    continue
                parent[find(a)] = find(b)
    block_labels = defaultdict(list)
    for j, (code, pt) in enumerate(labels):
        on = [a for a in ptree.query(pt) if geoms[a].contains(pt) and not plots[a][2]]
        if not on and not STREET_CODE.match(code):
            # A building zone's code printed off the traced plots (on a plot that was not traced,
            # or straddling a plot line): it belongs to the nearest building plot.
            near = [a for a in ptree.query(pt.buffer(LABEL_REACH_M / 111_000)) if not plots[a][2]]
            if near:
                b = min(near, key=lambda a: geoms[a].distance(pt))
                if geoms[b].distance(pt) * 111_000 <= LABEL_REACH_M:
                    on = [b]
        for a in on:
            block_labels[find(a)].append(j)
    checks = [list(c) for c in checks] if checks else [["street"] if p[2] else [] for p in plots]
    by_block = [None] * len(plots)
    # Plots someone checked on the plan (review_zones.py): the reviewed zone holds for the plot and
    # counts as a code printed in its group.
    rp = ROOT / "scripts/reviews" / f"{key}.json"
    reviews = json.loads(rp.read_text()) if rp.exists() else {}
    reviewed = defaultdict(set)
    # Unnumbered plots are reviewed by a point inside them ("@lng,lat").
    by_point = {}
    for k, r in reviews.items():
        if k.startswith("@"):
            pt = Point(*map(float, k[1:].split(",")))
            for a in ptree.query(pt):
                if plots[a][1] is None and geoms[a].contains(pt):
                    by_point[a] = r
    for a, p in enumerate(plots):
        r = reviews.get(p[1]) if p[1] is not None else by_point.get(a)
        if not r or p[2]:
            continue
        checks[a].append("reviewed")
        if r.get("outline") == "wrong":
            checks[a].append("outline-wrong")
        if r.get("zone"):
            on_plot[a] = r["zone"]
            reviewed[find(a)].add(r["zone"])
    if reviews:
        print(f"reviews: {sum(1 for a, p in enumerate(plots) if p[1] in reviews or a in by_point)} plots reviewed on the plan")
    if lines:
        unclear, why = 0, Counter()
        for a, (g, hrsz, street, _) in enumerate(plots):
            if street or on_plot[a]:
                continue
            codes = {labels[j][0] for j in block_labels.get(find(a), []) if not STREET_CODE.match(labels[j][0])} | reviewed[find(a)]
            if len(codes) == 1:
                by_block[a] = next(iter(codes))
            else:
                checks[a].append("zone-unclear")
                unclear += 1
                why[min(len(codes), 2)] += 1
        print(f"  unclear: {why[0]} in a group with no code, {why[2]} with several")
        print(f"zone boundaries: {cut} plot edges on a boundary; {sum(map(bool, by_block))} plots in a group "
              f"with one code, {unclear} unclear")
    zone, status = [], []
    m_per_deg = 111_000
    for a, (g, hrsz, street, _) in enumerate(plots):
        code, st = on_plot[a] or by_block[a], "plan"
        if code is None:
            st = "estimated"
            c = g.representative_point()
            cand = block_labels.get(find(a), []) if not street else []
            if cand:
                code = labels[min(cand, key=lambda j: labels[j][1].distance(c))][0]
            else:
                near = [j for j in ltree.query(c.buffer(NEAR_M[street] / m_per_deg))
                        if bool(STREET_CODE.match(labels[j][0])) == street]
                if near:
                    j = min(near, key=lambda j: labels[j][1].distance(c))
                    if labels[j][1].distance(c) * m_per_deg <= NEAR_M[street]:
                        code = labels[j][0]
        zone.append(code)
        status.append(st)

    feats = []
    for k, ((g, hrsz, street, a), code, st) in enumerate(zip(plots, zone, status)):
        g = g.simplify(0.000002)
        feats.append({"type": "Feature", "properties": {
            "hrsz": hrsz, "areaM2": round(a), "check": checks[k],
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


def smooth(g, d=SMOOTH_M):
    """A plot traced from a scan comes out ragged where hatching or lettering cut slits into it:
    close the slits, drop the spikes, then straighten the edges."""
    e = d / 111_000
    s = g.buffer(e, join_style=2).buffer(-2 * e, join_style=2).buffer(e, join_style=2).simplify(e / 3)
    if s.geom_type == "MultiPolygon":
        s = max(s.geoms, key=lambda p: p.area)
    return s if s.geom_type == "Polygon" and not s.is_empty else g


def read_parcels(key, smoothing=False):
    """The plots plan_parcels.py traced from a raster plan (no zone cells): a street is a plot an OSM
    road runs through or a bracketed number. smoothing: see smooth()."""
    import glob
    seen, plots, checks, ragged = set(), [], [], 0
    for f in sorted(glob.glob(str(ROOT / "public/data" / f"parcels-{key}" / "*.json"))):
        for ft in json.loads(Path(f).read_text())["features"]:
            g = shape(ft["geometry"])
            if g.wkb in seen:
                continue
            seen.add(g.wkb)
            ch = [c for c in ft["properties"].get("check", []) if c != "zone-unclear"]  # recomputed by write()
            street = "road" in ch or "street" in ch
            if smoothing:
                g = smooth(g)
                if not street and (g.length / g.convex_hull.length > MAX_RAGGED
                                   or 2 * area_m2(g) / (g.length * 92_000) < MIN_WIDTH_M):
                    ragged += 1
                    continue
            plots.append((g, ft["properties"]["hrsz"], "road" in ch or "street" in ch, round(area_m2(g))))
            checks.append(ch)
    if smoothing:
        print(f"dropped {ragged} ragged plots (traced through hatching)")
    return plots, checks


def main():
    global HRSZ
    key = sys.argv[1]
    cfg = dcfg.load(key)
    if cfg["plan"].get("hrsz"):
        HRSZ = re.compile(cfg["plan"]["hrsz"])
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
    if "--zones-only" in sys.argv:
        write(key, reg_id, reg, *read_parcels(key, "--smooth" in sys.argv), lines=zone_lines(key, cfg, fit, local))
        (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
        return

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

    write(key, reg_id, reg, plots, lines=zone_lines(key, cfg, fit, local))
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
