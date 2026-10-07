"""Parcels (telkek) from the scanned zoning plan: the regions enclosed by the blue parcel lines,
georeferenced with the fitted sheet transforms and labelled with the hrsz printed inside them.

Usage: python3 scripts/plan_parcels.py xx sheet0.jpg sheet1.jpg
Needs scripts/plans/<key>.json (fit) and scripts/plans/<key>-ocr-<i>.json.
Writes grid chunks to public/data/parcels-<key>/<ix>_<iy>.json.
"""
import json
import re
from collections import Counter
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_georef as pg  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
MIN_M2, MAX_M2 = 40, 60_000
FRAGMENT_M2 = 150  # an unnumbered region this small that shares a building with a numbered one is a fragment
OSM_TOL_M = 2.0  # plan/OSM alignment is ~1.5 m: overlaps within this band are not disagreements
ROAD_IN_PARCEL_M = 15
# OSM street classes that are public space; "service" ways (driveways, yards) do run inside plots.
STREET_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "minor"}
CELL = (0.004, 0.003)  # ~300 x 330 m
TEXT_PAD_PX = 4  # OCR boxes are tight: glyph edges and JPEG halos stick out a little
MAX_TEXT_PX = 60  # letter height of the largest map labels, with margin
SMOOTH_PX = 3
BRIDGE_MARGIN_PX = 40  # look this far around a label for the lines it covers
BRIDGE_MIN_PX = 20  # line evidence needed outside the label (in px of ink)
GAP_PX = 3  # line dilation; parcels are grown back by this much
# Zone codes (Vt-H/Lk2, Lk-1/K2, Zkp-Kp, ...): the big bold blue lettering that otherwise reads as parcel lines.
ZONE_LABEL = re.compile(r"^[A-Z][A-Za-z]{0,3}-[\w/.-]+$")
STYLES = dcfg.DEFAULTS["styles"]  # replaced by the district's styles in main()
HRSZ = re.compile(r"^\(?(\d{5,6}(?:/\d+)?)\)?$")


def label_ink(rgb, text_boxes, pad=TEXT_PAD_PX):
    """Zone codes (Vt-H/Lk2, ...) are printed in bold saturated blue, parcel lines in a thin lighter
    blue: the label ink is the saturated blue inside the OCR'd zone labels (rotated boxes), grown by a
    pixel for its JPEG halo. Returns (ink, label boxes)."""
    sat = dcfg.mask(rgb, STYLES["zone_code"])
    boxes = np.zeros(sat.shape, np.uint8)
    for box in text_boxes:
        cv2.fillPoly(boxes, [np.round(box).astype(np.int32)], 1)
    boxes = cv2.dilate(boxes, np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)) > 0
    return ndimage.binary_dilation(sat & boxes), boxes


def bridge_lines(lines, text_boxes, boxes, pad=TEXT_PAD_PX):
    """A parcel line running under a label loses the pixels the letters covered. Find the straight
    lines around each label (with a gap allowance as long as the label) and redraw them across it."""
    h, w = lines.shape
    out = lines.copy()
    for box in text_boxes:
        m = BRIDGE_MARGIN_PX
        x0, y0 = np.maximum(box.min(0).astype(int) - m, 0)
        x1, y1 = np.minimum(box.max(0).astype(int) + m, [w - 1, h - 1])
        win = lines[y0:y1 + 1, x0:x1 + 1].astype(np.uint8)
        gap = int(np.linalg.norm(box.max(0) - box.min(0))) + 2 * pad
        segs = cv2.HoughLinesP(win, 1, np.pi / 360, threshold=BRIDGE_MIN_PX, minLineLength=BRIDGE_MIN_PX, maxLineGap=gap)
        if segs is None:
            continue
        draw = np.zeros(win.shape, np.uint8)
        for sx0, sy0, sx1, sy1 in segs.reshape(-1, 4):
            cv2.line(draw, (int(sx0), int(sy0)), (int(sx1), int(sy1)), 1, 1)
        out[y0:y1 + 1, x0:x1 + 1] |= (draw > 0) & boxes[y0:y1 + 1, x0:x1 + 1]
    return out


def parcel_regions(im: Image.Image, frame, text_boxes):
    """Label the areas between parcel lines inside the map frame."""
    rgb = np.asarray(im.convert("RGB"), dtype=np.int16)
    # Parcel lines are thin, blue-tinted and broken up by JPEG: take the tint, drop the zone lettering, then close gaps.
    # (Requiring a dark navy core would drop the pale JPEG fringe along grey buildings, but thin lines
    # are pale too and break: plots merge three times as often. The fringe notches are smoothed below.)
    lines = dcfg.mask(rgb, STYLES["parcel_line"])
    ink, boxes = label_ink(rgb, text_boxes)
    lines = bridge_lines(lines & ~ink, text_boxes, boxes)
    # Street areas (yellow) and regulation lines (red) are not drawn with blue edges: they bound plots too.
    yellow = dcfg.mask(rgb, STYLES["street"])
    red = dcfg.mask(rgb, STYLES["regulation_line"]) | dcfg.mask(rgb, STYLES["zone_boundary"])
    lines = ndimage.binary_dilation(lines, iterations=GAP_PX) | ndimage.binary_dilation(yellow | red, iterations=1)
    x0, y0, x1, y1 = frame
    inside = np.zeros_like(lines)
    inside[y0:y1, x0:x1] = True
    if im.mode == "RGBA":  # blanked legend / title boxes
        inside &= np.asarray(im.getchannel("A")) > 0
    labels, n = ndimage.label(~lines & inside)
    return labels, n


def is_hrsz_ink(im, box):
    """Parcel numbers are printed in the base map's colour ("hrsz_text" style); other numbers on the
    plan (contour heights, dimensions) in theirs. Without the style every number counts."""
    st = STYLES.get("hrsz_text")
    if not st:
        return True
    b = np.array(box, float)
    x0, y0 = np.maximum(b.min(0).astype(int), 0)
    x1, y1 = b.max(0).astype(int) + 1
    rgb = np.asarray(im.crop((x0, y0, x1, y1)).convert("RGB"), dtype=np.int16)
    ink = rgb.mean(-1) < 200
    return ink.sum() > 0 and dcfg.mask(rgb, st)[ink].mean() >= 0.5


def _m2(geom, lat):
    return geom.area * 111_320 * np.cos(np.radians(lat)) * 110_540


def osm_check(parcels, district):
    """Compare the traced parcels with OSM, an independent source drawn from aerial imagery.

    - A small fragment without a parcel number that shares an OSM building with a numbered parcel is a
      piece of that parcel cut off by lettering on the plan: it is merged back.
    - Disagreements that remain are flagged per parcel, and the app shows them:
      "road": an OSM street runs through the parcel (it may be part of a public space);
      "nohrsz": no parcel number could be read inside.
    """
    import osm_ref
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    from shapely.strtree import STRtree

    lng0, lat0, lng1, lat1 = district.bounds
    buildings, roads = osm_ref.fetch((lng0, lat0, lng1, lat1), road_classes=STREET_CLASSES, whole_buildings=True)
    lat = (lat0 + lat1) / 2
    bpolys = [g for g in (Polygon(r).buffer(0) for r in buildings if len(r) >= 4) if _m2(g, lat) >= 25]
    rlines = [LineString(r) for r in roads if len(r) >= 2]
    polys = [p for p, _ in parcels]
    hrsz = [h for _, h in parcels]
    tree = STRtree(polys)

    # Union-find merge of lettering fragments into their numbered neighbour.
    parent = list(range(len(polys)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    merged = 0
    for b in bpolys:
        ba = b.area
        share = {int(j): polys[j].intersection(b).area / ba for j in tree.query(b)}
        share = {j: v for j, v in share.items() if v >= 0.25}
        numbered = [j for j in share if hrsz[j]]
        for j in share:
            if not hrsz[j] and _m2(polys[j], lat) < FRAGMENT_M2 and numbered:
                t = max(numbered, key=lambda k: share[k])
                if root(j) != root(t):
                    parent[root(j)] = root(t)
                    merged += 1
    groups = {}
    for i in range(len(polys)):
        groups.setdefault(root(i), []).append(i)
    out = []
    for r, members in groups.items():
        poly = unary_union([polys[i] for i in members])
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        out.append((poly, hrsz[r]))
    print(f"OSM: {len(bpolys)} buildings, {len(rlines)} street lines; merged {merged} lettering fragments")

    # Flags.
    rtree = STRtree(rlines)
    checks = []
    for poly, h in out:
        flags = []
        inner = poly.buffer(-OSM_TOL_M / 111_000)
        # (A "building straddles the outline" flag was tried: OSM buildings span several plots and
        # the plan's building fringes notch outlines, so it fired on a quarter of all plots. Not used.)
        if not inner.is_empty:
            road_m = sum(rlines[j].intersection(inner).length for j in rtree.query(inner)) * 111_000
            if road_m >= ROAD_IN_PARCEL_M:
                flags.append("road")
        if not h:
            flags.append("nohrsz")
        checks.append(flags)
    n = len(out)
    print(f"flags: road {sum('road' in c for c in checks)}/{n}, "
          f"nohrsz {sum('nohrsz' in c for c in checks)}/{n}")
    return out, checks


def parcel_zones(polys, key):
    """Which zone cells (plan_zones.py) each parcel lies in, by share of its area: a parcel split by a
    zone boundary has two."""
    import glob
    from shapely.geometry import shape
    from shapely.strtree import STRtree
    cells, seen = [], set()
    for f in glob.glob(str(ROOT / "public/data" / f"zones-{key}" / "*.json")):
        for ft in json.loads(Path(f).read_text())["features"]:
            g = shape(ft["geometry"])
            if g.wkb not in seen and not ft["properties"]["street"]:
                seen.add(g.wkb)
                cells.append((g, ft["properties"]))
    if not cells:
        print("no zone cells: run plan_zones.py first")
        return [[] for _ in polys]
    tree = STRtree([g for g, _ in cells])
    from shapely.geometry import Point
    reg = json.loads((ROOT / "public/data/regulations.json").read_text())["regulations"][dcfg.reg_id(dcfg.load(key))]
    labels = [(f["properties"]["code"], Point(f["geometry"]["coordinates"]))
              for f in json.loads((ROOT / "public/data" / reg["zoneLabels"]).read_text())["features"]]
    out = []
    for poly in polys:
        share = {}
        for j in tree.query(poly):
            g, p = cells[j]
            a = g.intersection(poly).area / poly.area
            if a >= 0.05:
                k = (p["code"], p["status"])
                share[k] = share.get(k, 0) + a
        zs = [{"code": c, "status": st, "share": round(min(a, 1), 2)}
              for (c, st), a in sorted(share.items(), key=lambda kv: -kv[1])]
        # A zone boundary splits a plot only where the plan draws one through it. In estimated
        # cells the split is just where two labels' spreading met: the plot takes one zone, the
        # label printed on it, else the nearest label among the candidate codes.
        if len({z["code"] for z in zs}) > 1 and any(z["status"] == "estimated" for z in zs):
            cand = {z["code"] for z in zs}
            on_plot = [c for c, pt in labels if c in cand and poly.contains(pt)]
            if on_plot:
                code = Counter(on_plot).most_common(1)[0][0]
            else:
                c0 = poly.centroid
                code = min(cand, key=lambda c: min((c0.distance(pt) for k, pt in labels if k == c), default=1e9))
            zs = [{"code": code, "status": "estimated", "share": 1.0}]
        out.append(zs)
    split = sum(len({z["code"] for z in zs if z["share"] >= 0.15}) > 1 for zs in out)
    print(f"zones: {sum(bool(z) for z in out)}/{len(out)} parcels in a zone cell, {split} split by a zone boundary")
    return out


def main():
    global STYLES
    key, images = sys.argv[1], sys.argv[2:]
    cfg = dcfg.load(key)
    STYLES = cfg["styles"]
    images = images or [str(p) for p in dcfg.sheet_paths(cfg)]
    reg_id = dcfg.reg_id(cfg)
    # Parcel numbers: 5-6 digits in Budapest; a village's run from 1 (and 0... outside the built-up area).
    hrsz_re = re.compile(cfg["plan"]["hrsz"]) if cfg["plan"].get("hrsz") else HRSZ
    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    local = pg.Local(*fit["local"])
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    districts = json.loads((ROOT / "public/data/districts.geojson").read_text())
    reg = regs["regulations"][reg_id]

    from shapely.geometry import Point, Polygon, shape
    from shapely.strtree import STRtree
    district_id = next(int(d) for d, v in regs["districts"].items() if reg_id in v["regulations"])
    district = shape(next(f["geometry"] for f in districts["features"] if f["properties"]["id"] == district_id))

    parcels = []
    for i, img_path in enumerate(images):
        f = fit["sheets"][i]
        model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
        m_per_px2 = abs(np.linalg.det(model.coef[1:3, :2])) / model.scale ** 2
        if i not in cfg["plan"].get("zone_sheets", range(len(images))):
            continue  # an overview sheet: plots are traced on the detail sheet
        im = pg.blank_sheet(cfg["plan"], i, Image.open(img_path).convert("RGBA"))
        frame = pg.sheet_frame(cfg["plan"], i, im)
        ocr = json.loads((ROOT / "scripts/plans" / f"{key}-ocr-{i}.json").read_text())["labels"]
        labels, n = parcel_regions(im, frame, [np.array(l["box"], float) for l in ocr if ZONE_LABEL.match(l["text"].strip())])
        sizes = ndimage.sum_labels(np.ones_like(labels), labels, index=np.arange(n + 1))
        # A district can cap the plot size: larger regions there are plots merged through a gap in the lines.
        max_m2 = cfg["plan"].get("max_parcel_m2", MAX_M2)
        keep = np.where((sizes * m_per_px2 >= MIN_M2) & (sizes * m_per_px2 <= max_m2))[0]
        keep = keep[keep > 0]
        boxes = ndimage.find_objects(labels)
        numbers = [(hrsz_re.match(l["text"].strip()).group(1), np.array(l["box"], float).mean(0))
                   for l in ocr if hrsz_re.match(l["text"].strip()) and l["conf"] > 0.8 and is_hrsz_ink(im, l["box"])]
        print(f"{img_path}: {n} regions, {len(keep)} parcel-sized, {len(numbers)} parcel numbers")
        for lab in keep:
            sl = boxes[lab - 1]
            mask = (labels[sl] == lab).astype(np.uint8)
            mask = ndimage.binary_fill_holes(mask)  # text inside a parcel makes holes
            # Grey building outlines nibble small notches into the edge: close them.
            mask = ndimage.binary_closing(np.pad(mask, SMOOTH_PX), iterations=SMOOTH_PX)[SMOOTH_PX:-SMOOTH_PX, SMOOTH_PX:-SMOOTH_PX]
            mask = ndimage.binary_fill_holes(mask).astype(np.uint8)
            cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cs:
                continue
            c = max(cs, key=cv2.contourArea)
            c = cv2.approxPolyDP(c, 1.5, True)[:, 0, :].astype(float)
            if len(c) < 3:
                continue
            # The region stops at the dilated line: it is grown back below to sit on the line.
            px = c + [sl[1].start, sl[0].start]
            mx, my = model(px).T
            lng, lat = local.to_ll(mx, my)
            poly = Polygon(np.column_stack([lng, lat])).buffer(0)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda g: g.area)
            if poly.is_empty or not district.intersects(poly.centroid):
                continue
            poly = poly.buffer(GAP_PX * np.sqrt(m_per_px2) / 111_000, join_style=2).buffer(0)  # a mitred spike can self-cross
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda g: g.area)
            # hrsz: the parcel number printed inside the region.
            inside_nums = [num for num, p in numbers if mask.shape[0] > p[1] - sl[0].start >= 0 and
                           mask.shape[1] > p[0] - sl[1].start >= 0 and mask[int(p[1] - sl[0].start), int(p[0] - sl[1].start)]]
            parcels.append((poly, inside_nums[0] if len(inside_nums) == 1 else None, i))

    # The sheets overlap: drop a parcel when most of it is already covered by one from the other sheet.
    parcels.sort(key=lambda p: (p[1] is None, -p[0].area))
    kept, tree_geoms = [], []
    for poly, hrsz, sheet in parcels:
        if tree_geoms:
            tree = STRtree(tree_geoms)
            if any(tree_geoms[j].intersection(poly).area > 0.5 * poly.area for j in tree.query(poly)):
                continue
        kept.append((poly, hrsz))
        tree_geoms.append(poly)

    kept, checks = osm_check(kept, district)
    zones = parcel_zones([p for p, _ in kept], key)

    feats = []
    for (poly, hrsz), check, zs in zip(kept, checks, zones):
        poly = poly.simplify(0.000004)
        if poly.geom_type == "MultiPolygon":  # buffer(0) of a self-touching outline
            poly = max(poly.geoms, key=lambda g: g.area)
        area = poly.area * 111_320 * np.cos(np.radians(poly.centroid.y)) * 110_540
        feats.append({"type": "Feature", "properties": {"hrsz": hrsz, "areaM2": round(area), "check": check, "zones": zs},
                      "geometry": {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in poly.exterior.coords]]}})
    # Grid chunks: the app loads only the cell around a tap (a parcel is stored in every cell it touches).
    out_dir = ROOT / "public/data" / f"parcels-{key}"
    if out_dir.exists():
        for f in out_dir.glob("*.json"):
            f.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = {}
    for f in feats:
        xs = [c[0] for c in f["geometry"]["coordinates"][0]]
        ys = [c[1] for c in f["geometry"]["coordinates"][0]]
        for ix in range(int(min(xs) // CELL[0]), int(max(xs) // CELL[0]) + 1):
            for iy in range(int(min(ys) // CELL[1]), int(max(ys) // CELL[1]) + 1):
                cells.setdefault(f"{ix}_{iy}", []).append(f)
    for k, fs in cells.items():
        (out_dir / f"{k}.json").write_text(json.dumps({"type": "FeatureCollection", "features": fs}, separators=(",", ":")))
    reg["parcels"] = {"dir": f"parcels-{key}", "cell": CELL}
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    total = sum(f.stat().st_size for f in out_dir.glob("*.json"))
    print(f"{len(feats)} parcels, {sum(f['properties']['hrsz'] is not None for f in feats)} with hrsz, "
          f"{len(cells)} cells, {total / 1e6:.1f} MB total, largest cell {max(f.stat().st_size for f in out_dir.glob('*.json')) / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
