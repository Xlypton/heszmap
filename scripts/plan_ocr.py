"""OCR a scanned zoning plan sheet into text labels with pixel positions.

Usage: python3 scripts/plan_ocr.py sheet.jpg out.json
Tiles the image with overlap, runs RapidOCR, and de-duplicates labels seen in two tiles.
"""
import json
import sys

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

Image.MAX_IMAGE_PIXELS = None
TILE, OVERLAP = 1600, 250


def main(src: str, out: str) -> None:
    im = Image.open(src).convert("RGB")
    w, h = im.size
    ocr = RapidOCR()
    labels = []
    step = TILE - OVERLAP
    for y in range(0, h, step):
        for x in range(0, w, step):
            crop = im.crop((x, y, min(x + TILE, w), min(y + TILE, h)))
            res, _ = ocr(crop)
            for box, text, conf in res or []:
                xs = [p[0] + x for p in box]
                ys = [p[1] + y for p in box]
                labels.append({"text": text, "conf": round(float(conf), 3), "box": [[round(a), round(b)] for a, b in zip(xs, ys)]})
            print(f"tile {x},{y}: {len(labels)} labels so far", flush=True)

    # Labels in the overlap are found twice: keep the more confident one.
    def centre(l):
        return sum(p[0] for p in l["box"]) / 4, sum(p[1] for p in l["box"]) / 4

    kept = []
    for l in sorted(labels, key=lambda l: -l["conf"]):
        cx, cy = centre(l)
        if any(k["text"] == l["text"] and abs(centre(k)[0] - cx) < 40 and abs(centre(k)[1] - cy) < 40 for k in kept):
            continue
        kept.append(l)
    json.dump({"image": src, "size": [w, h], "labels": kept}, open(out, "w"), ensure_ascii=False)
    print(f"wrote {out}: {len(kept)} labels")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
