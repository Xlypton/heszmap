"""Read a vector zoning plan (PDF) directly: no rendering, no colour guessing, no OCR.

1. Legend: find the standard legend entries in the PDF's text ("építési övezet, övezet határa",
   "szabályozási vonal", ...) and read the drawing style of the symbol drawn beside each one:
   stroke colour and width, or fill colour and size for dotted lines.
2. Map: every path with the same style outside the legend is that element.
3. Zones: the areas enclosed by zone boundaries and regulation lines are the zones; each takes
   the zone codes printed inside it, kept only if the regulation's own text uses that code.

4. Streets: the plan is georeferenced from its street names (text layer -> OSM streets), and the
   plots an OSM road runs along are street plots: they never merge with building plots.
5. Review: writes public/review/<key>/ (plan image, overlays, zones, legend styles, candidate
   styles) for review.html. A reviewer's corrections go into districts/<key>.json under
   "vector": {"styles": {element: [style, ...]}} and replace the automatic legend styles.

    python3 scripts/plan_vector.py <key>
"""
import html as htmllib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pymupdf
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HU = str.maketrans("áéíóöőúüűÁÉÍÓÖŐÚÜŰ", "aeiooouuuAEIOOOUUU")
LEGEND = {
    "zone_boundary": ["ovezetek hatara", "teruletfelhasznalas hatara", "terulet-felhasznalas hatara", "ovezet hatara", "ovezethatar", "ovezeti hatar", "ovezetek hatara", "terulet-felhasznalasi egyseg hatara",
                      "epitesi ovezet hatara", "ovezet-hatar", "ovezetek kozti hatar", "ovezethatar"],
    "regulation_line": ["szabalyozasi vonal"],
    "parcel": ["telekhatar", "meglevo telekhatar", "foldreszlet hatar"],
    "inner_area": ["belterulet hatara", "belteruleti hatar"],
    "admin": ["kozigazgatasi hatar"],
    "street": ["kozlekedesi terulet", "kozuti kozlekedesi terulet", "kozterulet", "kozut"],
}
# Hungarian zone codes: a land-use family letter group, optionally followed by an index.
MAX_STYLES = 4
SNAP_PT = 8
HATCH_MERGE_PT = 1.0
# Symbols drawn in a boundary's style: both sides between these sizes (pt). Dots and dashes are
# thinner, real boundary paths longer.
SYMBOL_MIN_PT, SYMBOL_MAX_PT = 4, 40  # ~5 m at 1:2000, ~11 m at 1:4000
CODE = re.compile(r"^(?:L[nkfe]e?|Vt|Vi|Vk|Gksz|Gip|Gipe|Gá|K[a-zA-ZÖöÜü]{0,4}|Kö[a-z]{0,2}|Üh|Üü|Ü|M[a-zá]{0,2}|E[a-z]{0,2}|Z[a-z]{0,2}|V[a-z]{0,2}|Lf|Lke|Lk|Ln|B|Á)"
                  r"(?:[-‐–][\w/.,‐–-]{1,10}|\d{1,2}(?:/\d+)?)?$")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.translate(HU).lower()).strip()


def text_lines(page):
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if t:
                yield t, pymupdf.Rect(ln["bbox"]), ln["dir"]


def style_of(d):
    if d["type"] in ("s", "fs") and d.get("color") is not None:
        return ("stroke", tuple(round(c, 2) for c in d["color"]), round(d.get("width") or 0, 2))
    if d["type"] == "f" and d.get("fill") is not None:
        r = pymupdf.Rect(d["rect"])
        return ("fill", tuple(round(c, 2) for c in d["fill"]), round(max(r.width, r.height), 1))
    return None


def legend(page, drawings):
    """{element: {"style": ..., "label": ..., "rect": ...}} from the legend entries found."""
    rects = np.array([[*d["rect"]] for d in drawings]) if drawings else np.zeros((0, 4))
    out, legend_area = {}, []
    lines = list(text_lines(page))
    for name, terms in LEGEND.items():
        # The entry that is closest to a bare term ("szabályozási vonal", not "10 éven túli
        # szabályozási vonal"): fewest extra characters.
        cands = sorted(((len(norm(t)) - max(len(term) for term in terms if term in norm(t)), t, r)
                        for t, r, _ in lines if any(term in norm(t) for term in terms) and len(norm(t)) <= 80),
                       key=lambda c: c[0])
        found = []
        for _, t, r in cands:
            h = r.height
            # The symbol: left of the label on the same row (legend symbols are 5-20 mm wide).
            # In a multi-column legend the window stops at the nearest text to the left on the
            # same row (the previous column's label).
            left = max([q.x1 for _, q, _ in lines if q.x1 < r.x0 - 0.5 * h and q.y0 < r.y1 - 0.3 * h and q.y1 > r.y0 + 0.3 * h],
                       default=r.x0 - 25 * h)
            sym = pymupdf.Rect(max(left + 0.5 * h, r.x0 - 25 * h), r.y0 - 0.3 * h, r.x0 - 0.2 * h, r.y1 + 0.3 * h)
            inside = np.where((rects[:, 0] >= sym.x0) & (rects[:, 2] <= sym.x1) & (rects[:, 1] >= sym.y0) & (rects[:, 3] <= sym.y1))[0]
            if name == "street":  # an area: a real fill, or (CAD exports) a hatch of thin strokes
                sty = Counter(style_of(drawings[j]) for j in inside
                              if style_of(drawings[j]) and not all(it[0] in ("re", "qu") for it in drawings[j]["items"]))
                fills = Counter(("fill", tuple(round(c, 2) for c in drawings[j]["fill"]), 0) for j in inside
                                if drawings[j]["type"] in ("f", "fs") and drawings[j].get("fill") is not None)
                sty.update(fills)
                sty = Counter({k: v for k, v in sty.items() if k[1] != (1.0, 1.0, 1.0)})
                if sty:
                    found.append({"style": sty.most_common(1)[0][0], "label": t, "rect": [round(v) for v in sym]})
                    legend_area.append(sym | r)
                continue
            styles = Counter()
            for j in inside:
                st = style_of(drawings[j])
                items = drawings[j]["items"]
                # The symbol's box (any colour) and its white background are not the symbol.
                frame = bool(items) and all(it[0] in ("re", "qu") for it in items) and st and st[0] == "stroke"
                if st and not frame and st[1] != (1.0, 1.0, 1.0):
                    styles[st] += 1
            if styles:
                # A plan can draw one element in several styles (existing vs planned regulation
                # line, land-use vs zone boundary): every matching legend entry counts.
                best = styles.most_common(1)[0][0]
                found.append({"style": best, "label": t, "rect": [round(v) for v in sym]})
                legend_area.append(sym | r)
        if found:
            out[name] = found[:MAX_STYLES]
    return out, legend_area


def segments(d):
    """Polylines of a path (get_cdrawings gives plain tuples)."""
    pts = []
    xy = lambda v: (float(v[0]), float(v[1]))
    for it in d["items"]:
        if it[0] == "l":
            pts.append([xy(it[1]), xy(it[2])])
        elif it[0] == "c":
            pts.append([xy(it[1]), xy(it[4])])
        elif it[0] == "re":
            x0, y0, x1, y1 = pymupdf.Rect(it[1])
            pts.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
        elif it[0] == "qu":
            q = [xy(v) for v in it[1]]
            pts.append(q + q[:1])
    return pts


def element_lines(drawings, style, exclude):
    """Map geometry drawn in one style. Dotted and dashed lines are drawn as many short pieces
    (tiny strokes with round caps, small filled dots, dashes): their ends are joined to the
    nearest piece within a few line widths, which closes the line."""
    geoms, dots = [], []
    for d in drawings:
        if style_of(d) != style or any(pymupdf.Rect(d["rect"]).intersects(e) for e in exclude):
            continue
        r = pymupdf.Rect(d["rect"])
        if SYMBOL_MIN_PT < min(r.width, r.height) and max(r.width, r.height) < SYMBOL_MAX_PT:
            continue  # a small closed symbol (the circle or box around a zone code), not a line
        if style[0] == "fill" and style[2] < 8:
            r = pymupdf.Rect(d["rect"])
            dots.append(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
        else:
            geoms += [LineString(p) for p in segments(d) if len(p) >= 2]
    ends = dots + [c for g in geoms for c in (g.coords[0], g.coords[-1])]
    if ends:
        width = style[2] if style[0] == "stroke" else style[2]
        gap = max(6 * width, 3.0)
        pts = np.array(ends)
        owner = list(range(len(dots))) + [len(dots) + k // 2 for k in range(2 * len(geoms))]
        tree = STRtree([Point(p) for p in pts])
        joins = []
        for i, p in enumerate(pts):
            near = [j for j in tree.query(Point(p).buffer(gap)) if owner[j] != owner[i]]
            if near:
                j = min(near, key=lambda j: np.hypot(*(pts[j] - p)))
                joins.append(LineString([p, pts[j]]))
        geoms += joins
    return geoms


def close_dangles(lines, reach):
    """Line ends that stop short of another boundary (drafting gaps at junctions) are joined to
    the nearest other boundary within `reach` points."""
    merged = unary_union(lines)
    parts = list(getattr(merged, "geoms", [merged]))
    tree = STRtree(parts)
    out = []
    for i, g in enumerate(parts):
        for end in (Point(g.coords[0]), Point(g.coords[-1])):
            near = [j for j in tree.query(end.buffer(reach)) if j != i]
            if any(parts[j].distance(end) < 0.3 for j in near):
                continue  # already connected
            if near:
                j = min(near, key=lambda j: parts[j].distance(end))
                if parts[j].distance(end) <= reach:
                    from shapely.ops import nearest_points
                    out.append(LineString([end, nearest_points(end, parts[j])[1]]))
    return out


HRSZ_WORD = re.compile(r"^0?\d{1,5}(?:/\d{1,3})?$")


def parcel_style(drawings, words, exclude):
    """The stroke style of the lines nearest around parcel numbers: the base map's plot lines.
    (Votes per segment: one path can hold every line of a map, so its box says nothing.)"""
    segs, sid, styles = [], [], []
    for d in drawings:
        st = style_of(d)
        if not st or st[0] != "stroke":
            continue
        if st not in styles:
            styles.append(st)
        k = styles.index(st)
        for p in segments(d):
            for a, b in zip(p[:-1], p[1:]):
                segs.append((*a, *b))
                sid.append(k)
    if not segs:
        return None
    S, sid = np.array(segs), np.array(sid)
    votes = Counter()
    nums = [r for t, r in words if HRSZ_WORD.match(t) and not any(r.intersects(e) for e in exclude)]
    for r in nums[:300]:
        c = np.array([(r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2])
        d = S[:, 2:] - S[:, :2]
        t = np.clip(((c - S[:, :2]) * d).sum(1) / np.maximum((d * d).sum(1), 1e-9), 0, 1)
        dist = np.hypot(*(S[:, :2] + d * t[:, None] - c).T)
        near = np.argsort(dist)[:12]
        for k in set(sid[near].tolist()):
            votes[styles[k]] += 1
    return votes.most_common(1)[0][0] if votes else None


def regulation_codes(path):
    if not path:
        return None
    t = htmllib.unescape(re.sub(r"<[^>]+>", " ", open(path, errors="replace").read()))
    return {m.replace("‐", "-").replace("–", "-") for m in re.findall(r"\b[A-ZÁÉÍÓÖŐÚÜŰ][\wÁÉÍÓÖŐÚÜŰáéíóöőúüű]{0,4}(?:[-‐–][\w/]{1,8}){0,3}\b", t)}


ROOT = Path(__file__).resolve().parent.parent
IMG_MAX_PX = 3200  # long side of the review image
STREET_HALF_M = 6  # an OSM road centre line covers ~6 m either side
STREET_SHARE = 0.5  # a plot this much inside the road band is a street plot
OSM_STREET_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "minor"}
ELEMENT_COLOURS = {"zone_boundary": (230, 0, 160), "regulation_line": (255, 120, 0), "inner_area": (120, 60, 200),
                   "admin": (60, 60, 60), "parcel": (0, 90, 255)}


def as_style(s):
    return (s[0], tuple(s[1]), s[2])


def georeference(page, cfg):
    """Fit the page (points) to OSM streets by the street names printed on it.
    Returns (pt->local metres affine A, metres->pt affine B, Local, bbox, info) or None."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import plan_georef as pg
    area = cfg.get("geocode_area") or cfg["name"]
    hits = [h for h in pg.nominatim({"q": f"{area}, Magyarország", "limit": 5})
            if h.get("class") in ("boundary", "place")]
    if not hits:
        return None, {"ok": False, "why": f"{area}: not found in OSM"}
    lat0, lat1, lng0, lng1 = map(float, hits[0]["boundingbox"])
    bbox = (lng0 - 0.01, lat0 - 0.01, lng1 + 0.01, lat1 + 0.01)
    local = pg.Local((lng0 + lng1) / 2, (lat0 + lat1) / 2)
    labels = []
    for t, r, _ in text_lines(page):
        t = re.sub(r"\bu\.?$", "utca", t.strip())  # "Petőfi S. u." -> "... utca"
        labels.append({"text": t, "conf": 1.0, "box": [[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]]})
    found = pg.street_labels({"labels": labels})
    names = sorted({n for n, _ in found})
    streets = {n: pg.street_segments(n, area, local, bbox) for n in names}
    info = {"street_labels": len(found), "streets": len(names), "streets_in_osm": sum(v is not None for v in streets.values())}
    named = [(n, np.asarray(q, float)) for n, q in found if streets.get(n) is not None]
    if len({n for n, _ in named}) < 3:
        return None, {**info, "ok": False, "why": "fewer than 3 named streets found in OSM"}
    A, res, used = fit_similarity(named, streets, pg)
    info.update(labels_used=used)
    # The inverse (metres -> page points), from a grid of page points.
    gx, gy = np.meshgrid(np.linspace(0, page.rect.width, 6), np.linspace(0, page.rect.height, 6))
    P = np.column_stack([gx.ravel(), gy.ravel()])
    M = np.hstack([P, np.ones((len(P), 1))]) @ A
    B = pg.solve_affine(M, P)
    scale = float(np.sqrt(abs(np.linalg.det(A[:2]))))
    return (A, B, local, bbox), {**info, "ok": True, "residual_m": round(res, 1), "m_per_pt": round(scale, 3)}


def umeyama(P, Q):
    """Similarity (rotation, uniform scale, shift, no shear) with Q ≈ s R P + t, as a 3x2 affine."""
    mp, mq = P.mean(0), Q.mean(0)
    X, Y = P - mp, Q - mq
    U, S, Vt = np.linalg.svd(Y.T @ X / len(P))
    D = np.diag([1, np.sign(np.linalg.det(U @ Vt))])
    R = U @ D @ Vt
    s = np.trace(np.diag(S) @ D) / (X ** 2).sum(1).mean()
    t = mq - s * R @ mp
    return np.vstack([(s * R).T, t])


def fit_similarity(named, streets, pg):
    """Street-name ICP like plan_georef.fit_sheet, but with a similarity transform: a plan has no
    shear, and four parameters stay well determined by a handful of labels on a few streets
    (a free affine stretches to fit labels that lie mostly along one direction)."""
    px = np.array([q for _, q in named])
    cs = {}
    for n, q in named:
        cs.setdefault(n, []).append(q)
    A = umeyama(np.array([np.mean(v, 0) for v in cs.values()]), np.array([streets[n][:, :2].mean(0) for n in cs]))
    keep = np.ones(len(px), bool)
    for it in range(60):
        m_pred = np.hstack([px, np.ones((len(px), 1))]) @ A
        tq = [pg.nearest_on_polyline(mp, streets[n]) for (n, _), mp in zip(named, m_pred)]
        targets, d = np.array([q for q, _ in tq]), np.array([dd for _, dd in tq])
        if it > 5:
            keep = d < max(3 * np.median(d[keep]), 10.0)
        A_new = umeyama(px[keep], targets[keep])
        if np.abs(A_new - A).max() < 1e-7:
            break
        A = A_new
    print(f"  similarity fit: {keep.sum()}/{len(px)} labels, residual median {np.median(d[keep]):.1f} m")
    return A, float(np.median(d[keep])), int(keep.sum())


def osm_roads_on_page(geo):
    import osm_ref
    A, B, local, bbox = geo
    _, roads = osm_ref.fetch(bbox, road_classes=OSM_STREET_CLASSES)
    out = []
    for ln in roads:
        x, y = local.to_m(ln[:, 0], ln[:, 1])
        pts = np.hstack([np.column_stack([x, y]), np.ones((len(x), 1))]) @ B
        if len(pts) >= 2:
            out.append(LineString(pts))
    return out


def build(key):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import district
    import njt
    cfg = district.load(key)
    ref = cfg["plan"]["annexes"][0]
    url = ref if ref.startswith("http") else njt.NJT + ref
    pdf = njt.download(url, district.work_dir(key) / "annex" / Path(url).name)
    reg_html = None
    if cfg.get("regulation", {}).get("njtId"):
        njt.annexes(cfg["regulation"]["njtId"])  # caches the decree's text
        reg_html = Path(__file__).resolve().parent / ".cache" / f"njt-{cfg['regulation']['njtId']}.html"
    page = pymupdf.open(pdf)[cfg["plan"].get("page", 1) - 1]
    drawings = page.get_cdrawings()
    auto, legend_area = legend(page, drawings)
    # Reviewer corrections replace the automatic styles element by element.
    overrides = (cfg.get("vector") or {}).get("styles") or {}
    leg = {k: [{**e, "source": "legend"} for e in v] for k, v in auto.items()}
    for k, styles in overrides.items():
        leg[k] = [{"style": as_style(st), "label": "(review)", "source": "review"} for st in styles]
    allowed = regulation_codes(reg_html) if reg_html else None
    words = [(w[4].replace("‐", "-").replace("–", "-"), pymupdf.Rect(w[:4])) for w in page.get_text("words")]
    codes = [(t, r) for t, r in words if CODE.match(t) and (allowed is None or t in allowed)
             and not any(r.intersects(e) for e in legend_area)]
    report = {"key": key, "name": cfg["name"], "source": url, "page": cfg["plan"].get("page", 1),
              "size_pt": [round(page.rect.width, 1), round(page.rect.height, 1)],
              "code_labels": len(codes), "distinct_codes": sorted({c for c, _ in codes})}

    lines = {}
    for name in ("zone_boundary", "regulation_line", "inner_area", "admin"):
        lines[name] = [g for e in leg.get(name, []) for g in element_lines(drawings, as_style(e["style"]), legend_area)]
    bounds = [g for v in lines.values() for g in v]
    if "parcel" not in overrides:
        base = parcel_style(drawings, words, legend_area)
        if base and all(as_style(e["style"]) != base for e in leg.get("parcel", [])):
            leg.setdefault("parcel", []).append({"style": base, "label": "alaptérkép (a hrsz-ek körüli vonalak)", "source": "parcel numbers"})
    lines["parcel"] = [g for e in leg.get("parcel", []) for g in element_lines(drawings, as_style(e["style"]), legend_area)]

    geo, report["georef"] = georeference(page, cfg)
    roads = osm_roads_on_page(geo) if geo else []
    report["osm_roads"] = len(roads)

    zones, cells, is_street = [], [], []
    if bounds:
        eps = 1.0
        bounds += close_dangles(bounds, SNAP_PT)
        zwalls = unary_union([g.buffer(eps * 1.3) for g in bounds])
        walls = unary_union([zwalls] + [g.buffer(eps) for g in lines["parcel"]])
        area = box(*page.rect).difference(walls)
        cells = [p for p in getattr(area, "geoms", [area]) if p.area > 30]
        # Street plots: inside the legend's street areas, or along an OSM road.
        street_area = street_layer(leg, drawings, legend_area)
        if roads:
            band = unary_union([r.buffer(STREET_HALF_M / report["georef"]["m_per_pt"]) for r in roads])
            street_area = band if street_area is None else unary_union([street_area, band])
        is_street = [bool(street_area is not None and c.intersection(street_area).area > STREET_SHARE * c.area) for c in cells]
        zones = merge_zones(cells, is_street, zwalls, eps)
    polys = [unary_union([cells[i] for i in m]) for m in zones]
    tree = STRtree(polys) if polys else None
    per = {}
    for c, r in codes:
        if tree is None:
            break
        pt = Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        hit = [int(j) for j in tree.query(pt) if polys[j].contains(pt)]
        if not hit:  # the code's own circle or box cut it out: nearest zone
            near = list(tree.query(pt.buffer(15)))
            hit = [int(min(near, key=lambda j: polys[j].distance(pt)))] if near else []
        if hit:
            per.setdefault(hit[0], Counter())[c] += 1
    report["plots"] = len(cells)
    report["street_plots"] = int(sum(is_street))
    labelled = list(per.values())
    report["zones"] = {"zones": len(polys), "with_codes": len(per), "one_code": sum(len(v) == 1 for v in labelled),
                       "conflicting": sum(len(v) > 1 for v in labelled)}
    write_bundle(key, page, drawings, legend_area, leg, lines, roads, polys, zones, is_street, per, report)
    return report


def street_layer(leg, drawings, legend_area):
    fill = []
    for e in leg.get("street", []):
        st = as_style(e["style"])
        for d in drawings:
            if any(pymupdf.Rect(d["rect"]).intersects(x) for x in legend_area):
                continue
            if d["type"] in ("f", "fs") and d.get("fill") is not None and tuple(round(c, 2) for c in d["fill"]) == st[1]:
                fill += [Polygon(p).buffer(0) for p in segments(d) if len(p) >= 4]
            elif d["type"] in ("s", "fs") and d.get("color") is not None and tuple(round(c, 2) for c in d["color"]) == st[1] \
                    and (d.get("width") or 0) < 1.0:
                fill += [LineString(p).buffer(HATCH_MERGE_PT) for p in segments(d) if len(p) >= 2]
    return unary_union(fill).buffer(-HATCH_MERGE_PT * 0.5) if fill else None


def merge_zones(cells, is_street, zwalls, eps):
    """Neighbouring plots form one zone unless a zone boundary or regulation line runs between
    them, or one is a street plot and the other is not."""
    parent = list(range(len(cells)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grown = [c.buffer(eps * 1.6) for c in cells]
    tree = STRtree(grown)
    for i, g in enumerate(grown):
        for j in tree.query(g):
            j = int(j)
            if j <= i or root(i) == root(j) or is_street[i] != is_street[j]:
                continue
            strip = g.intersection(grown[j])
            if strip.is_empty or strip.area < 0.5:
                continue
            if strip.intersection(zwalls).area < 0.5 * strip.area:
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(cells)):
        groups.setdefault(root(i), []).append(i)
    return list(groups.values())


def candidate_styles(drawings, legend_area, n=24):
    """The plan's most used drawing styles (by drawn length), for the reviewer to assign."""
    length = Counter()
    for d in drawings:
        st = style_of(d)
        if not st or st[1] == (1.0, 1.0, 1.0) or any(pymupdf.Rect(d["rect"]).intersects(e) for e in legend_area):
            continue
        r = pymupdf.Rect(d["rect"])
        length[st] += r.width + r.height
    return [st for st, _ in length.most_common(n)]


def write_bundle(key, page, drawings, legend_area, leg, lines, roads, polys, zones, is_street, per, report):
    from PIL import Image, ImageDraw
    out = ROOT / "public/review" / key
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*"):
        f.unlink()
    z = IMG_MAX_PX / max(page.rect.width, page.rect.height)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
    Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(out / "plan.jpg", quality=82)
    size = (pix.width, pix.height)

    def layer(name, geoms, colour, width=3):
        im = Image.new("RGBA", size)
        dr = ImageDraw.Draw(im)
        for g in geoms:
            for part in getattr(g, "geoms", [g]):
                coords = part.exterior.coords if part.geom_type == "Polygon" else part.coords
                dr.line([(x * z, y * z) for x, y in coords], fill=colour + (255,), width=width)
        im.save(out / f"{name}.png", optimize=True)

    for name, geoms in lines.items():
        if geoms:
            layer(name, geoms, ELEMENT_COLOURS[name], 2 if name == "parcel" else 3)
    if roads:
        layer("osm_roads", roads, (0, 170, 200), 4)
    cands = candidate_styles(drawings, legend_area)
    for i, st in enumerate(cands):
        layer(f"cand{i}", element_lines(drawings, st, legend_area), (230, 0, 160), 3)
    zjson = []
    for j, (poly, members) in enumerate(zip(polys, zones)):
        cnt = per.get(j, Counter())
        street = all(is_street[i] for i in members)
        if not cnt and poly.area < 400:
            continue
        rings = []
        for part in getattr(poly, "geoms", [poly]):
            part = part.simplify(1.5 / z)
            rings.append("M" + "L".join(f"{x * z:.0f},{y * z:.0f}" for x, y in part.exterior.coords) + "Z")
        zjson.append({"id": j, "codes": dict(cnt), "status": "conflict" if len(cnt) > 1 else "ok" if cnt else "unlabelled",
                      "street": street, "plots": len(members), "path": "".join(rings),
                      "bbox": [round(v * z) for v in poly.bounds]})
    review = {**report, "image": {"src": "plan.jpg", "size": size, "px_per_pt": z},
              "layers": sorted(p.stem for p in out.glob("*.png") if not p.stem.startswith("cand")),
              "legend": {k: [{"style": list(as_style(e["style"])), "label": e["label"], "source": e["source"]} for e in v]
                         for k, v in leg.items()},
              "candidates": [{"style": [st[0], list(st[1]), st[2]], "layer": f"cand{i}"} for i, st in enumerate(cands)],
              "zones": sorted(zjson, key=lambda q: (q["status"] != "conflict", q["status"] != "unlabelled"))}
    (out / "review.json").write_text(json.dumps(review, ensure_ascii=False))
    idx_path = ROOT / "public/review/index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else []
    idx = [e for e in idx if e["key"] != key] + [{"key": key, "name": report["name"], "zones": report["zones"],
                                                   "georef": report["georef"].get("ok")}]
    idx_path.write_text(json.dumps(sorted(idx, key=lambda e: e["name"]), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    for key in sys.argv[1:]:
        r = build(key)
        print(json.dumps({k: v for k, v in r.items() if k not in ("distinct_codes",)}, ensure_ascii=False, default=str))
