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


def code_ink(rgb):
    """The zone-code lettering. A plan that prints codes in the same black as its thin lines and
    other text (Csobánka) sets "open_px": opening by that size keeps only the bold strokes."""
    st = STYLES["zone_code"]
    sat = dcfg.mask(rgb, st).astype(np.uint8)
    if st.get("open_px"):
        k = st["open_px"]
        bold = cv2.morphologyEx(sat, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
        # Keep the full letters (thin parts included) around the bold strokes.
        sat = sat & cv2.dilate(bold, np.ones((5, 5), np.uint8))
    if st.get("drop_plus"):
        sat = drop_plus(sat, st["drop_plus"])
    return sat


def drop_plus(ink, max_px):
    """Remove the "+" signs of a hatch pattern printed in the same ink as the codes (Csobánka's forest):
    small symmetric components whose middle row and column are full and whose corners are empty."""
    lab, n = ndimage.label(ink)
    out = ink.copy()
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (5 <= h <= max_px and 5 <= w <= max_px and abs(h - w) <= 2):
            continue
        m = lab[sl] == i
        cy, cx = h // 2, w // 2
        row = m[max(cy - 1, 0):cy + 2].any(0).mean()
        col = m[:, max(cx - 1, 0):cx + 2].any(1).mean()
        corners = m[:2, :2].any() or m[:2, -2:].any() or m[-2:, :2].any() or m[-2:, -2:].any()
        if row > 0.8 and col > 0.8 and not corners:
            out[sl][m] = 0
    return out


def clusters(sat):
    st = STYLES["zone_code"]
    join = st.get("join_px", WORD_JOIN_PX)
    min_h, max_h, min_ink = st.get("min_h", MIN_H), st.get("max_h", MAX_H), st.get("min_ink", MIN_INK)
    joined = cv2.dilate(sat, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (join,) * 2))
    lab, n = ndimage.label(joined)
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        ys, xs = np.nonzero((lab[sl] == i) & (sat[sl] > 0))
        if len(xs) < min_ink:
            continue
        pts = np.column_stack([xs + sl[1].start, ys + sl[0].start]).astype(np.float32)
        (cx, cy), (w, h), ang = cv2.minAreaRect(pts)
        if w < h:
            w, h, ang = h, w, ang + 90
        if not (min_h <= h <= max_h) or w < st.get("min_aspect", 1.5) * h:
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
    cfg = dcfg.load(key)
    STYLES = cfg["styles"]
    images = images or [str(p) for p in dcfg.sheet_paths(cfg)]
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg = regs["regulations"][dcfg.reg_id(cfg)]
    codes = list(json.loads((ROOT / "public/data" / reg["zoneTypes"]).read_text()))
    by_norm = {}
    for c in codes:
        by_norm.setdefault(pg.norm_code(c), set()).add(c)
    by_norm = {k: next(iter(v)) for k, v in by_norm.items() if len(v) == 1}
    ocr = RapidOCR()
    for i, img_path in enumerate(images):
        im = pg.blank_sheet(cfg["plan"], i, Image.open(img_path).convert("RGBA"))
        rgb = np.asarray(im.convert("RGB"))
        alpha = np.asarray(im.getchannel("A"))
        frame = pg.sheet_frame(cfg["plan"], i, im)
        x0, y0, x1, y1 = frame
        found, unmatched = [], []
        ink = code_ink(rgb.astype(np.int16))
        # Read the code's own ink only, so neighbouring text in other colours cannot join it.
        read = np.where(cv2.dilate(ink, np.ones((3, 3), np.uint8))[..., None] > 0, rgb, 255).astype(np.uint8) \
            if STYLES["zone_code"].get("isolate") else rgb
        for centre, size, ang in clusters(ink):
            if not (x0 <= centre[0] < x1 and y0 <= centre[1] < y1) or not alpha[int(centre[1]), int(centre[0])]:
                continue  # the legend
            crop = upright(read, centre, size, ang)
            best = None
            for img in (crop, cv2.rotate(crop, cv2.ROTATE_180)):
                res, _ = ocr(img, use_det=False, use_cls=False)  # the crop is one upright line already
                for text, conf in res or []:
                    code = snap(text, by_norm)
                    if code and (best is None or conf > best[2]):
                        best = (code, text, float(conf))
                    elif not code:
                        unmatched.append(text)
            if best and best[2] < STYLES["zone_code"].get("min_conf", 0):
                unmatched.append(best[1])  # a weak reading: better no label than a wrong one
                best = None
            if best:
                found.append({"code": best[0], "x": round(centre[0], 1), "y": round(centre[1], 1),
                              "conf": round(best[2], 3), "text": best[1]})
        out = ROOT / "scripts/plans" / f"{key}-zlabels-{i}.json"
        out.write_text(json.dumps({"labels": found, "unmatched": sorted(set(unmatched))}, ensure_ascii=False, indent=0))
        print(f"{img_path}: {len(found)} zone codes read; {len(set(unmatched))} readings matched no code -> {out.name}")


if __name__ == "__main__":
    main()
