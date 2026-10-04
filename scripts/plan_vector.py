"""Read a vector zoning plan (PDF) directly: no rendering, no colour guessing, no OCR.

1. Legend: find the standard legend entries in the PDF's text ("építési övezet, övezet határa",
   "szabályozási vonal", ...) and read the drawing style of the symbol drawn beside each one:
   stroke colour and width, or fill colour and size for dotted lines.
2. Map: every path with the same style outside the legend is that element.
3. Zones: the areas enclosed by zone boundaries and regulation lines are the zones; each takes
   the zone codes printed inside it, kept only if the regulation's own text uses that code.

    python3 scripts/plan_vector.py plan.pdf [--codes-from regulation.html] [--page N] [--png out.png]
Prints a JSON report.
"""
import html as htmllib
import json
import re
import sys
from collections import Counter

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


def analyse(path, page_no=0, codes_from=None, png=None):
    doc = pymupdf.open(path)
    page = doc[page_no]
    drawings = page.get_cdrawings()
    leg, legend_area = legend(page, drawings)
    allowed = regulation_codes(codes_from)
    # Zone codes printed on the map.
    words = [(w[4].replace("‐", "-").replace("–", "-"), pymupdf.Rect(w[:4])) for w in page.get_text("words")]
    codes = [(t, r) for t, r in words if CODE.match(t) and (allowed is None or t in allowed)
             and not any(r.intersects(e) for e in legend_area)]
    report = {"file": path.split("/")[-1], "page": page_no + 1, "drawings": len(drawings),
              "legend": {k: [{"label": e["label"], "style": e["style"]} for e in v] for k, v in leg.items()},
              "code_labels": len(codes), "distinct_codes": len({c for c, _ in codes})}
    bounds = []
    for name in ("zone_boundary", "regulation_line", "inner_area", "admin"):
        for e in leg.get(name, []):
            g = element_lines(drawings, e["style"], legend_area)
            report[f"{name}_segments"] = report.get(f"{name}_segments", 0) + len(g)
            bounds += g
    if not bounds or not codes:
        report["zones"] = None
        return report
    # Plot lines: the legend's, plus the base map's (often not in the legend): the stroke style
    # drawn closest around the printed parcel numbers.
    pstyles = [e["style"] for e in leg.get("parcel", [])]
    base = parcel_style(drawings, words, legend_area)
    if base and base not in pstyles:
        pstyles.append(base)
    report["parcel_styles"] = pstyles
    plines = [g for st in pstyles for g in element_lines(drawings, st, legend_area)]
    eps = 1.0
    bounds += close_dangles(bounds, SNAP_PT)
    zwalls = unary_union([g.buffer(eps * 1.3) for g in bounds])
    walls = unary_union([zwalls] + [g.buffer(eps) for g in plines])
    area = box(*page.rect).difference(walls)
    cells = [p for p in getattr(area, "geoms", [area]) if p.area > 30]
    # Neighbouring cells (plots) belong to one zone unless a zone boundary or regulation line
    # runs between them.
    parent = list(range(len(cells)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Street areas (the legend's fill) are their own layer: a street plot never merges with a
    # building plot, or every block would connect through the road network.
    street_fill = []
    for e in leg.get("street", []):
        st = e["style"]
        for d in drawings:
            if any(pymupdf.Rect(d["rect"]).intersects(x) for x in legend_area):
                continue
            # Same colour, however it is drawn (the legend swatch and the map may differ).
            if d["type"] in ("f", "fs") and d.get("fill") is not None and tuple(round(c, 2) for c in d["fill"]) == tuple(st[1]):
                street_fill += [Polygon(p).buffer(0) for p in segments(d) if len(p) >= 4]
            elif d["type"] in ("s", "fs") and d.get("color") is not None and tuple(round(c, 2) for c in d["color"]) == tuple(st[1]) \
                    and (d.get("width") or 0) < 1.0:
                # A hatch: its strokes, widened until neighbouring strokes merge into an area.
                street_fill += [LineString(p).buffer(HATCH_MERGE_PT) for p in segments(d) if len(p) >= 2]
    streets = unary_union(street_fill) if street_fill else None
    if streets is not None:
        streets = streets.buffer(-HATCH_MERGE_PT * 0.5)  # drop isolated strokes' halos
    is_street = [bool(streets is not None and c.intersection(streets).area > 0.5 * c.area) for c in cells]
    report["street_plots"] = sum(is_street)
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
    polys = [unary_union([cells[i] for i in m]) for m in groups.values()]
    report["plots"] = len(cells)
    tree = STRtree(polys)
    per = {}
    for c, r in codes:
        pt = Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        hit = [int(j) for j in tree.query(pt) if polys[j].contains(pt)]
        if not hit:  # the code's own circle or box cut it out: nearest zone
            hit = [int(min(tree.query(pt.buffer(15)), key=lambda j: polys[j].distance(pt), default=-1))]
        if hit[0] >= 0:
            per.setdefault(hit[0], Counter())[c] += 1
    labelled = list(per.values())
    report["zones"] = {
        "zones": len(polys),
        "with_codes": len(per),
        "one_code": sum(len(v) == 1 for v in labelled),
        "conflicting": sum(len(v) > 1 for v in labelled),
        "codes_placed": sum(sum(v.values()) for v in labelled),
    }
    if png:
        z = 2400 / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z))
        from PIL import Image, ImageDraw
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("RGBA")
        ov = Image.new("RGBA", im.size)
        dr = ImageDraw.Draw(ov)
        rng = np.random.default_rng(1)
        for j, cnt in per.items():
            col = tuple(int(v) for v in rng.integers(40, 230, 3)) + (110 if len(cnt) == 1 else 40,)
            for p in getattr(polys[j], "geoms", [polys[j]]):
                ring = p.exterior
                dr.polygon([(x * z, y * z) for x, y in ring.coords], fill=col, outline=(0, 0, 0, 255) if len(cnt) == 1 else (255, 0, 0, 255))
        for g in bounds:
            dr.line([(x * z, y * z) for x, y in g.coords], fill=(255, 0, 255, 255), width=2)
        Image.alpha_composite(im, ov).convert("RGB").save(png)
    return report


if __name__ == "__main__":
    args = sys.argv[1:]
    opt = lambda k: args[args.index(k) + 1] if k in args else None
    print(json.dumps(analyse(args[0], int(opt("--page") or 1) - 1, opt("--codes-from"), opt("--png")), ensure_ascii=False, default=str, indent=1))
