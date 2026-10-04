"""Parcels (telkek) from the scanned zoning plan: the regions enclosed by the blue parcel lines,
georeferenced with the fitted sheet transforms and labelled with the hrsz printed inside them.

Usage: python3 scripts/plan_parcels.py xx sheet0.jpg sheet1.jpg
Needs scripts/plans/<key>.json (fit) and scripts/plans/<key>-ocr-<i>.json.
Writes grid chunks to public/data/parcels-<key>/<ix>_<iy>.json.
"""
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_georef as pg  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
MIN_M2, MAX_M2 = 40, 60_000
CELL = (0.004, 0.003)  # ~300 x 330 m
GAP_PX = 3  # line dilation; parcels are grown back by this much
HRSZ = re.compile(r"^\(?(\d{5,6}(?:/\d+)?)\)?$")


def parcel_regions(im: Image.Image, frame):
    """Label the areas between parcel lines inside the map frame."""
    rgb = np.asarray(im.convert("RGB"), dtype=np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Parcel lines are thin, blue-tinted and broken up by JPEG: take the tint, then close gaps.
    lines = ((b - (r + g) / 2) > 18) & ((r + g + b) / 3 < 235)
    # Street areas (yellow) and regulation lines (red) are not drawn with blue edges: they bound plots too.
    yellow = (r > 225) & (g > 215) & (b < 200)
    red = (r > 180) & (g < 120) & (b < 120)
    lines = ndimage.binary_dilation(lines, iterations=GAP_PX) | ndimage.binary_dilation(yellow | red, iterations=1)
    x0, y0, x1, y1 = frame
    inside = np.zeros_like(lines)
    inside[y0:y1, x0:x1] = True
    labels, n = ndimage.label(~lines & inside)
    return labels, n


def main():
    key, images = sys.argv[1], sys.argv[2:]
    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    local = pg.Local(*fit["local"])
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    districts = json.loads((ROOT / "public/data/districts.geojson").read_text())
    reg = regs["regulations"][f"{key}-kesz"]

    from shapely.geometry import Point, Polygon, shape
    from shapely.strtree import STRtree
    district_id = next(int(d) for d, v in regs["districts"].items() if f"{key}-kesz" in v["regulations"])
    district = shape(next(f["geometry"] for f in districts["features"] if f["properties"]["id"] == district_id))

    parcels = []
    for i, img_path in enumerate(images):
        f = fit["sheets"][i]
        model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
        m_per_px2 = abs(np.linalg.det(model.coef[1:3, :2])) / model.scale ** 2
        im = Image.open(img_path)
        frame = pg.map_frame(im)
        labels, n = parcel_regions(im, frame)
        sizes = ndimage.sum_labels(np.ones_like(labels), labels, index=np.arange(n + 1))
        keep = np.where((sizes * m_per_px2 >= MIN_M2) & (sizes * m_per_px2 <= MAX_M2))[0]
        keep = keep[keep > 0]
        boxes = ndimage.find_objects(labels)
        ocr = json.loads((ROOT / "scripts/plans" / f"{key}-ocr-{i}.json").read_text())["labels"]
        numbers = [(HRSZ.match(l["text"].strip()).group(1), np.array(l["box"], float).mean(0))
                   for l in ocr if HRSZ.match(l["text"].strip()) and l["conf"] > 0.8]
        print(f"{img_path}: {n} regions, {len(keep)} parcel-sized, {len(numbers)} parcel numbers")
        for lab in keep:
            sl = boxes[lab - 1]
            mask = (labels[sl] == lab).astype(np.uint8)
            mask = ndimage.binary_fill_holes(mask).astype(np.uint8)  # text inside a parcel makes holes
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
            poly = poly.buffer(GAP_PX * np.sqrt(m_per_px2) / 111_000, join_style=2)
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

    feats = []
    for poly, hrsz in kept:
        poly = poly.simplify(0.000004)
        if poly.geom_type == "MultiPolygon":  # buffer(0) of a self-touching outline
            poly = max(poly.geoms, key=lambda g: g.area)
        area = poly.area * 111_320 * np.cos(np.radians(poly.centroid.y)) * 110_540
        feats.append({"type": "Feature", "properties": {"hrsz": hrsz, "areaM2": round(area)},
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
