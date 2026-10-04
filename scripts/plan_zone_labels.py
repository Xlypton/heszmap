"""Find every zone code on a plan sheet, including the ones the general OCR pass missed.

Zone codes are the only bold, saturated-blue lettering on the plan ("Építési övezet, övezet jele").
Each cluster of that ink is cut out, turned upright along its long axis, enlarged and read again,
and the reading is snapped to the KÉSZ's own list of codes (exact after normalising, else one edit
away from exactly one code). Readings that match no code are reported, not guessed.

Usage: python3 scripts/plan_zone_labels.py xx sheet0.jpg sheet1.jpg
Writes scripts/plans/<key>-zlabels-<i>.json: [{code, x, y, conf, text}] in sheet pixels.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_georef as pg  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
WORD_JOIN_PX = 9  # letters of one code are closer than this; neighbouring labels are farther apart
MIN_H, MAX_H = 14, 70  # letter height range of zone codes, px
MIN_INK = 120  # px of ink: smaller blobs are dots and line fragments
SCALE = 2  # enlarge crops before reading

STYLES = dcfg.DEFAULTS["styles"]  # replaced by the district's styles in main()


def edit1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    return any(a == b[:i] + b[i + 1:] for i in range(len(b)))


def snap(text: str, by_norm: dict) -> str | None:
    n = pg.norm_code(text.strip())
    if n in by_norm:
        return by_norm[n]
    near = {c for k, c in by_norm.items() if edit1(n, k)}
    return near.pop() if len(near) == 1 else None


def clusters(rgb):
    sat = dcfg.mask(rgb, STYLES["zone_code"]).astype(np.uint8)
    joined = cv2.dilate(sat, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (WORD_JOIN_PX,) * 2))
    lab, n = ndimage.label(joined)
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        ys, xs = np.nonzero((lab[sl] == i) & (sat[sl] > 0))
        if len(xs) < MIN_INK:
            continue
        pts = np.column_stack([xs + sl[1].start, ys + sl[0].start]).astype(np.float32)
        (cx, cy), (w, h), ang = cv2.minAreaRect(pts)
        if w < h:
            w, h, ang = h, w, ang + 90
        if not (MIN_H <= h <= MAX_H) or w < 1.5 * h:
            continue
        yield (cx, cy), (w, h), ang


def upright(im_rgb, centre, size, ang, pad=8):
    w, h = size[0] + 2 * pad, size[1] + 2 * pad
    M = cv2.getRotationMatrix2D(centre, ang, SCALE)
    M[:, 2] += [w * SCALE / 2 - centre[0], h * SCALE / 2 - centre[1]]
    return cv2.warpAffine(im_rgb, M, (int(w * SCALE), int(h * SCALE)), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def main():
    global STYLES
    key, images = sys.argv[1], sys.argv[2:]
    STYLES = dcfg.load(key)["styles"]
    images = images or [str(p) for p in dcfg.sheet_paths(dcfg.load(key))]
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg = regs["regulations"][f"{key}-kesz"]
    codes = list(json.loads((ROOT / "public/data" / reg["zoneTypes"]).read_text()))
    by_norm = {}
    for c in codes:
        by_norm.setdefault(pg.norm_code(c), set()).add(c)
    by_norm = {k: next(iter(v)) for k, v in by_norm.items() if len(v) == 1}
    ocr = RapidOCR()
    for i, img_path in enumerate(images):
        rgb = np.asarray(Image.open(img_path).convert("RGB"))
        frame = pg.map_frame(Image.open(img_path))
        x0, y0, x1, y1 = frame
        found, unmatched = [], []
        for centre, size, ang in clusters(rgb.astype(np.int16)):
            if not (x0 <= centre[0] < x1 and y0 <= centre[1] < y1):
                continue  # the legend
            crop = upright(rgb, centre, size, ang)
            best = None
            for img in (crop, cv2.rotate(crop, cv2.ROTATE_180)):
                res, _ = ocr(img, use_det=False, use_cls=False)  # the crop is one upright line already
                for text, conf in res or []:
                    code = snap(text, by_norm)
                    if code and (best is None or conf > best[2]):
                        best = (code, text, float(conf))
                    elif not code:
                        unmatched.append(text)
            if best:
                found.append({"code": best[0], "x": round(centre[0], 1), "y": round(centre[1], 1),
                              "conf": round(best[2], 3), "text": best[1]})
        out = ROOT / "scripts/plans" / f"{key}-zlabels-{i}.json"
        out.write_text(json.dumps({"labels": found, "unmatched": sorted(set(unmatched))}, ensure_ascii=False, indent=0))
        print(f"{img_path}: {len(found)} zone codes read; {len(set(unmatched))} readings matched no code -> {out.name}")


if __name__ == "__main__":
    main()
