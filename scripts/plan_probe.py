"""Profile a zoning-plan PDF before choosing how to read it.

For each page: size, whether it is vector (drawn paths + real text) or a scan (one big image),
how much text is extractable, the dominant ink colours, and whether a legend
("Jelmagyarázat") and the standard legend entries can be found.

    python3 scripts/plan_probe.py plan.pdf [more.pdf ...]   -> JSON per file on stdout
"""
import json
import re
import sys
from collections import Counter

import numpy as np
import pymupdf

# Standard legend entries (OTÉK / 9/2024 TÉKA symbol names), normalised to ASCII lowercase.
LEGEND_TERMS = {
    "legend": ["jelmagyarazat", "jelkulcs"],
    "zone_boundary": ["ovezet hatara", "ovezethatar", "epitesi ovezet hatara", "ovezeti hatar"],
    "zone_code": ["ovezet jele", "ovezeti jel", "epitesi ovezet jele"],
    "regulation_line": ["szabalyozasi vonal"],
    "parcel": ["telekhatar"],
    "building_line": ["epitesi vonal", "epitesi hely"],
    "inner_area": ["belterulet hatara", "belteruleti hatar"],
}
HU = str.maketrans("áéíóöőúüűÁÉÍÓÖŐÚÜŰ", "aeiooouuuAEIOOOUUU")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.translate(HU).lower())


def ink_colours(pix: pymupdf.Pixmap, n=8):
    """Dominant non-paper colours, quantised to 32 levels."""
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[..., :3].astype(int)
    a = a[::2, ::2].reshape(-1, 3)
    ink = a[(a.min(1) < 200) | (a.max(1) - a.min(1) > 60)]
    q = Counter(map(tuple, (ink // 32 * 32 + 16)))
    total = max(len(a), 1)
    return [{"rgb": list(map(int, c)), "share": round(k / total, 4)} for c, k in q.most_common(n)]


def probe(path: str) -> dict:
    doc = pymupdf.open(path)
    pages = []
    for i, page in enumerate(doc):
        if i >= 6:
            break
        text = page.get_text()
        images = page.get_images(full=True)
        # Size of the page's drawing instructions: a scan is one image and a few bytes of
        # instructions, a vector plan is megabytes of path operators. (Counting paths is slow.)
        stream_kb = len(page.read_contents()) // 1024
        area = page.rect.width * page.rect.height
        big_img = 0.0
        for img in images:
            for r in page.get_image_rects(img[0]):
                big_img = max(big_img, r.width * r.height / area)
        kind = "scan" if big_img > 0.6 and stream_kb < 50 else "vector" if stream_kb > 200 else "mixed"
        found = {k: any(t in norm(text) for t in v) for k, v in LEGEND_TERMS.items()}
        codes = sorted(set(re.findall(r"\b(?:L[kfneu]|Vt|Vi|Gksz|Gip|Ksp|Kk|Ki?ö|Lke|Lk|Mk|Má|Ev|Eg|Ek|Zkp|Zkk|Zk|V|Lf|Üh|Ü)[-‐–]?[A-Za-zÁÉÍÓÖŐÚÜŰ0-9/]{0,8}\b", text)))[:25]
        pix = page.get_pixmap(dpi=20)
        pages.append({
            "page": i + 1,
            "size_mm": [round(page.rect.width / 72 * 25.4), round(page.rect.height / 72 * 25.4)],
            "kind": kind, "stream_kb": stream_kb, "images": len(images), "largest_image_share": round(big_img, 2),
            "text_chars": len(text), "legend_terms": found, "zone_codes_in_text": codes,
            "ink": ink_colours(pix),
        })
    return {"file": path, "pages_total": len(doc), "pages": pages}


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(probe(p), ensure_ascii=False), flush=True)
