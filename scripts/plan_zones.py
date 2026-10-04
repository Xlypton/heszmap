"""Zone areas (övezetek) from the scanned zoning plan.

A zone is the area enclosed by the plan's zone boundaries (red dotted line, "Építési övezet, övezet
határa"), its regulation lines (solid red, "Szabályozási vonal") and the street areas (yellow), and it is
named by the zone code printed inside it. Each enclosed area gets the code(s) of the labels inside it;
an area with none, or with conflicting ones, is kept and marked so the app can say "check this".

Usage: python3 scripts/plan_zones.py xx sheet0.jpg sheet1.jpg
Needs scripts/plans/<key>.json (fit), scripts/plans/<key>-ocr-<i>.json and public/data/zone-types-<key>.json.
Writes grid chunks to public/data/zones-<key>/<ix>_<iy>.json and a cross-check report to
scripts/plans/<key>-zone-check.json.
"""
import json
import sys
from collections import Counter
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
CELL = (0.004, 0.003)  # same grid as the parcels
MIN_M2 = 150  # smaller enclosed bits are hatching cells, symbols and letter counters
SPREAD_DOWN = 4  # labels are spread on a grid this many plan pixels coarser
MAX_SPREAD_M = 400  # a label names nothing farther than this
SAME_LABEL_PX = 40
DOT_AREA_PX = (40, 400)  # a boundary dot (the XX plan: ~13 px wide, ~130 px)
DOT_MAX_PX = 30
DOT_LINK = 1.6  # join dots up to this many times the median dot spacing apart
STREET_EDGE_PX = 6
EXTEND_PX = 120  # ~20 m: how far a loose end of a dotted boundary is continued
TOUCH_DEG = 0.000012  # ~1 m: cells this close are touching
MAX_BORROW_M = 120  # an unlabelled block takes the zone of a label at most this far across the street
DOT_JOIN_PX = 7  # the boundary dots are ~10 px wide, ~8 px apart: grow them until they touch
THIN_PX = 2  # hatching ("építési hely"), the cancel star and red lettering are thinner than this

STYLES = dcfg.DEFAULTS["styles"]  # replaced by the district's styles in main()


def red_boundaries(rgb, street=None):
    zb = STYLES["zone_boundary"]
    red = dcfg.mask(rgb, zb) | dcfg.mask(rgb, STYLES["regulation_line"])
    thin_px, join_px = zb.get("thin_px", THIN_PX), zb.get("join_px", DOT_JOIN_PX)
    # Dots and the regulation line are thick; hatching and lettering are thin: open them away.
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * thin_px + 1, 2 * thin_px + 1))
    thick = cv2.morphologyEx(red.astype(np.uint8), cv2.MORPH_OPEN, k)
    barrier = cv2.dilate(thick, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * join_px + 1,) * 2))
    # A dotted boundary is only a line if its dots are joined: growing them is not enough where the
    # spacing is a little wider (~27 px apart, ~13 px gaps on the XX plan). Chain each dot to its
    # nearest neighbours.
    lab, n = ndimage.label(thick)
    if n:
        sizes = ndimage.sum_labels(thick, lab, np.arange(1, n + 1))
        boxes = ndimage.find_objects(lab)
        dots = np.array([[(b[1].start + b[1].stop) / 2, (b[0].start + b[0].stop) / 2] for b, a in zip(boxes, sizes)
                         if DOT_AREA_PX[0] <= a <= DOT_AREA_PX[1] and max(b[0].stop - b[0].start, b[1].stop - b[1].start) <= DOT_MAX_PX])
        if len(dots) > 2:
            from scipy.spatial import cKDTree
            tree = cKDTree(dots)
            d, j = tree.query(dots, k=3)
            spacing = np.median(d[:, 1])
            links = {i: set() for i in range(len(dots))}
            for i in range(len(dots)):
                for dd, jj in zip(d[i, 1:], j[i, 1:]):
                    if dd <= DOT_LINK * spacing:
                        links[i].add(int(jj))
                        links[int(jj)].add(i)
                        cv2.line(barrier, tuple(map(int, dots[i])), tuple(map(int, dots[jj])), 1, 2 * join_px // 2 + 3)
            # A dotted line often stops a little short of the street or of the next boundary (the
            # rest of the edge follows a plot line, undotted). Continue each loose end in its own
            # direction until it meets a street or another boundary.
            stop = (barrier > 0) | (street if street is not None else False)
            h, w = barrier.shape
            for i, nb in links.items():
                if len(nb) != 1:
                    continue
                prev = dots[next(iter(nb))]
                v = dots[i] - prev
                v = v / (np.hypot(*v) or 1)
                start = dots[i] + v * (join_px + DOT_MAX_PX / 2)
                for t in range(0, EXTEND_PX, 2):
                    x, y = (start + v * t).astype(int)
                    if not (0 <= x < w and 0 <= y < h):
                        break
                    if stop[y, x]:
                        cv2.line(barrier, tuple(map(int, dots[i])), (int(x), int(y)), 1, 2 * join_px // 2 + 3)
                        break
    return barrier > 0


def street_mask(rgb):
    yellow = dcfg.mask(rgb, STYLES["street"]).astype(np.uint8)
    # Street names and line symbols are printed on the yellow: close them into the street.
    yellow = cv2.morphologyEx(yellow, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    return cv2.morphologyEx(yellow, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0


def zone_regions(im, frame):
    """Enclosed areas: building-zone areas and street areas are labelled separately."""
    rgb = np.asarray(im.convert("RGB"), dtype=np.int16)
    street = street_mask(rgb)
    barrier = red_boundaries(rgb, street)
    x0, y0, x1, y1 = frame
    inside = np.zeros(barrier.shape, bool)
    inside[y0:y1, x0:x1] = True
    # Where a boundary line ends at a street it stops a few pixels short of the yellow: the
    # street's edge closes it.
    edge = cv2.dilate(street.astype(np.uint8), np.ones((2 * STREET_EDGE_PX + 1,) * 2, np.uint8)) > 0
    barrier = barrier | (edge & ~street)  # also for the label spreading below
    lab_a, na = ndimage.label(~barrier & inside & ~street)
    lab_s, ns = ndimage.label(~barrier & street & inside)
    labels = np.where(lab_s > 0, lab_s + na, lab_a)
    return labels, na + ns, street, barrier, inside


def spread(seeds, allowed, max_steps):
    """Geodesic nearest-seed labelling: grow every seed one pixel per step through allowed pixels.
    Where boundaries are drawn the growth stops at them; where one is missing, the nearest label
    reachable without crossing a boundary wins, not the nearest as the crow flies."""
    lab = seeds.astype(np.uint16)
    k = np.ones((3, 3), np.uint8)
    for _ in range(max_steps):
        grown = cv2.dilate(lab, k)
        new = (lab == 0) & allowed & (grown > 0)
        if not new.any():
            break
        lab[new] = grown[new]
    return lab


def merged_labels(key, i, ocr, codes):
    """Zone codes from the general OCR pass plus the targeted re-read of the blue lettering
    (plan_zone_labels.py). The same label read by both counts once; where they disagree, the more
    confident reading wins."""
    found = [(c, np.asarray(p, float), conf) for c, p, conf in pg.zone_labels(ocr, codes)]
    extra = ROOT / "scripts/plans" / f"{key}-zlabels-{i}.json"
    if extra.exists():
        for l in json.loads(extra.read_text())["labels"]:
            p = np.array([l["x"], l["y"]])
            same = [k for k, (_, q, _) in enumerate(found) if np.linalg.norm(q - p) < SAME_LABEL_PX]
            if not same:
                found.append((l["code"], p, l["conf"]))
            elif all(found[k][2] < l["conf"] and found[k][0] != l["code"] for k in same):
                for k in same:
                    found[k] = (l["code"], found[k][1], l["conf"])
    return found


def text_check(key, feats):
    """Cross-check with the KÉSZ text: provisions that name zones for an area bounded by named streets
    ("X utca – Y utca … által határolt területén"). Every named zone should appear on the plan inside
    that area; a named zone that is missing points at a wrong label reading or a wrong block outline."""
    from shapely.geometry import Polygon, shape
    eff_path = ROOT / "public/data" / f"effective-{key}.json"
    if not eff_path.exists():
        return
    eff = json.loads(eff_path.read_text())
    cells = [(shape(f["geometry"]).buffer(0), f["properties"]) for f in feats if not f["properties"]["street"]]
    report = []
    for name, ring in eff["blocks"].items():
        block = Polygon(ring).buffer(0)
        named = sorted({z for o in eff["overrides"] if (o.get("condition") or {}).get("block") == name for z in o["zones"]})
        on_plan = Counter()
        for g, p in cells:
            a = g.intersection(block).area
            if a > 0.02 * block.area or a > 0.5 * g.area:
                on_plan[p["code"]] += a / block.area
        missing = [z for z in named if z not in on_plan]
        report.append({"block": name, "namedInText": named, "onPlan": {k: round(v, 2) for k, v in on_plan.most_common()},
                       "missingOnPlan": missing})
        print(f"text check {name}: text names {named}; plan has {dict((k, round(v, 2)) for k, v in on_plan.most_common(4))}"
              + (f"; MISSING {missing}" if missing else " ✓"))
    (ROOT / "scripts/plans" / f"{key}-zone-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")


def main():
    global STYLES
    key, images = sys.argv[1], sys.argv[2:]
    STYLES = dcfg.load(key)["styles"]
    images = images or [str(p) for p in dcfg.sheet_paths(dcfg.load(key))]
    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    local = pg.Local(*fit["local"])
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg_id = f"{key}-kesz"
    reg = regs["regulations"][reg_id]
    codes = list(json.loads((ROOT / "public/data" / reg["zoneTypes"]).read_text()))
    districts = json.loads((ROOT / "public/data/districts.geojson").read_text())

    from shapely.geometry import Polygon, shape
    district_id = next(int(d) for d, v in regs["districts"].items() if reg_id in v["regulations"])
    district = shape(next(f["geometry"] for f in districts["features"] if f["properties"]["id"] == district_id))

    areas = []  # (polygon, code, status, street?)
    label_points = []
    for i, img_path in enumerate(images):
        f = fit["sheets"][i]
        model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
        m_per_px = np.sqrt(abs(np.linalg.det(model.coef[1:3, :2]))) / model.scale
        im = Image.open(img_path)
        frame = pg.map_frame(im)
        labels, n, street, barrier, inside = zone_regions(im, frame)
        ocr = json.loads((ROOT / "scripts/plans" / f"{key}-ocr-{i}.json").read_text())
        found = merged_labels(key, i, ocr, codes)
        label_points += [(code, p, model) for code, p, _ in found]
        # Which codes each enclosed area holds: one code means the plan itself closes the zone.
        area_codes = {}
        seeds_full = []
        for code, p, conf in found:
            x, y = int(p[0]), int(p[1])
            win = labels[max(y - 6, 0):y + 7, max(x - 6, 0):x + 7].ravel()
            win = win[win > 0]
            if not len(win):
                continue
            a_id = int(np.bincount(win).argmax())
            area_codes.setdefault(a_id, set()).add(code)
            seeds_full.append((code, x, y, a_id))
        # Spread the labels on a coarser grid (D px per cell) for speed.
        D = SPREAD_DOWN
        h, w = labels.shape
        small = lambda m: cv2.resize(m.astype(np.uint8) * 255, (w // D, h // D), interpolation=cv2.INTER_AREA)
        blocked = small(barrier) > 0
        is_street = small(street) > 127
        ins = small(inside) > 127
        out_lab = np.zeros(blocked.shape, np.uint16)
        for layer in (False, True):
            seeds = np.zeros(blocked.shape, np.uint16)
            for k, (code, x, y, a_id) in enumerate(seeds_full, 1):
                sy, sx = min(y // D, seeds.shape[0] - 1), min(x // D, seeds.shape[1] - 1)
                if bool(street[y, x]) == layer:
                    seeds[sy, sx] = k
            allowed = ins & ~blocked & (is_street == layer)
            lab = spread(seeds, allowed, int(MAX_SPREAD_M / (m_per_px * D)))
            out_lab[allowed] = lab[allowed]
        # A block whose label could not be read: take the zone across the street, marked as estimated.
        building = ins & ~blocked & ~is_street
        hole = building & (out_lab == 0)
        seeds = np.where(building, out_lab, 0).astype(np.uint16)
        lab = spread(seeds, ins & ~blocked, int(MAX_BORROW_M / (m_per_px * D)))
        borrowed = hole & (lab > 0)
        out_lab[borrowed] = lab[borrowed]
        boxes = ndimage.find_objects(out_lab)
        kept = 0
        for k, (code, x, y, a_id) in enumerate(seeds_full, 1):
            if k > len(boxes) or boxes[k - 1] is None:
                continue
            sl = boxes[k - 1]
            mask = (out_lab[sl] == k).astype(np.uint8)
            cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cs:
                if cv2.contourArea(c) * (m_per_px * D) ** 2 < MIN_M2:
                    continue
                piece = np.zeros(mask.shape, np.uint8)
                cv2.drawContours(piece, [c], -1, 1, -1)
                was_borrowed = borrowed[sl][piece > 0].mean() > 0.5
                c = cv2.approxPolyDP(c, 1.0, True)[:, 0, :].astype(float)
                if len(c) < 3:
                    continue
                px = (c + [sl[1].start, sl[0].start] + 0.5) * D
                mx, my = model(px).T
                lng, lat = local.to_ll(mx, my)
                poly = Polygon(np.column_stack([lng, lat])).buffer(0)
                if poly.geom_type == "MultiPolygon":
                    poly = max(poly.geoms, key=lambda g: g.area)
                if poly.is_empty or not district.intersects(poly.representative_point()):
                    continue
                # Grow back over the (thickened) boundary line so neighbouring cells meet.
                poly = poly.buffer(DOT_JOIN_PX * m_per_px / 111_000, join_style=2)
                status = "plan" if area_codes.get(a_id) == {code} and not was_borrowed else "estimated"
                areas.append((poly, code, status, bool(street[y, x])))
                kept += 1
        print(f"{img_path}: {len(found)} zone labels; {sum(len(v) == 1 for v in area_codes.values())} areas closed by "
              f"the plan with one code, {sum(len(v) > 1 for v in area_codes.values())} open areas; {kept} zone cells")

    # Sheets overlap, and a zone crossing the sheet seam is cut in two, one half on each sheet:
    # cells of the same code that overlap or touch are one zone (dissolved). A cell overlapped
    # mostly by a cell of another code is a duplicate from the other sheet: the plan-closed or
    # larger one wins.
    areas.sort(key=lambda a: (a[2] != "plan", -a[0].area))
    from shapely.strtree import STRtree
    from shapely.ops import unary_union
    kept, geoms = [], []
    for a in areas:
        if geoms:
            tree = STRtree(geoms)
            if any(kept[j][1] != a[1] and geoms[j].intersection(a[0]).area > 0.5 * a[0].area for j in tree.query(a[0])):
                continue
        kept.append(a)
        geoms.append(a[0])
    parent = list(range(len(kept)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grown = [g.buffer(TOUCH_DEG) for g in geoms]
    tree = STRtree(grown)
    for i, g in enumerate(grown):
        for j in tree.query(g):
            j = int(j)
            if j > i and kept[i][1] == kept[j][1] and kept[i][3] == kept[j][3] and g.intersects(grown[j]):
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(kept)):
        groups.setdefault(root(i), []).append(i)
    merged = []
    for members in groups.values():
        poly = unary_union([grown[i] for i in members]).buffer(-TOUCH_DEG)
        status = "plan" if all(kept[i][2] == "plan" for i in members) else "estimated"
        merged.append((poly, kept[members[0]][1], status, kept[members[0]][3]))
    print(f"{len(kept)} cells -> {len(merged)} zones after joining same-code cells across the sheet seam")
    kept = merged

    feats = []
    for poly, code, status, is_street in kept:
        poly = poly.simplify(0.000005)
        parts = [p for p in getattr(poly, "geoms", [poly]) if p.area > 0]
        geom = {"type": "MultiPolygon", "coordinates": [[[[round(x, 6), round(y, 6)] for x, y in p.exterior.coords]] for p in parts]} \
            if len(parts) > 1 else {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in parts[0].exterior.coords]]}
        feats.append({"type": "Feature", "properties": {"code": code, "status": status, "street": is_street}, "geometry": geom})
    st = Counter(f["properties"]["status"] for f in feats)
    print(f"{len(feats)} zone cells: {dict(st)}")

    text_check(key, feats)

    # The label points (shown on the map and as "nearby labels" in the app).
    from shapely.geometry import Point
    pts, seen_pts = [], []
    for code, p, model in label_points:
        mx, my = model(np.array([p]))[0]
        lng, lat = local.to_ll(mx, my)
        q = np.array([lng, lat])
        if not district.contains(Point(lng, lat)) or any(c == code and np.abs(q - o).max() < 0.0002 for c, o in seen_pts):
            continue
        seen_pts.append((code, q))
        pts.append({"type": "Feature", "properties": {"code": code, "reg": reg_id},
                    "geometry": {"type": "Point", "coordinates": [round(float(lng), 7), round(float(lat), 7)]}})
    (ROOT / "public/data" / reg["zoneLabels"]).write_text(json.dumps({"type": "FeatureCollection", "features": pts}, ensure_ascii=False))
    print(f"{len(pts)} zone labels")

    out_dir = ROOT / "public/data" / f"zones-{key}"
    if out_dir.exists():
        for f in out_dir.glob("*.json"):
            f.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = {}
    for f in feats:
        rings = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
        xs = [c[0] for r in rings for c in r[0]]
        ys = [c[1] for r in rings for c in r[0]]
        for ix in range(int(min(xs) // CELL[0]), int(max(xs) // CELL[0]) + 1):
            for iy in range(int(min(ys) // CELL[1]), int(max(ys) // CELL[1]) + 1):
                cells.setdefault(f"{ix}_{iy}", []).append(f)
    for k, fs in cells.items():
        (out_dir / f"{k}.json").write_text(json.dumps({"type": "FeatureCollection", "features": fs}, separators=(",", ":")))
    reg["zoneAreas"] = {"dir": f"zones-{key}", "cell": CELL}
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    total = sum(f.stat().st_size for f in out_dir.glob("*.json"))
    print(f"{len(cells)} cells, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
