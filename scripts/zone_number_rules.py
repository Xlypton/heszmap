"""Zone-specific rules keyed by a zone number printed on the plan, for the card.

Some plans give every zone area a number besides its code (Győr: "00492" printed above
"Lke06/I/30/50-/075/02-20/32/"), and the text keys its zone-specific rules by that number (GYÉSZ
103. § table: "00492 Az övezet területén belül lévő 3562 hrsz.-ú ingatlanon ..."). Codes repeat
across the city, so these rules can only reach the right zone area through the number.

    python3 scripts/zone_number_rules.py <key> [--list]

Reads the zone numbers off the plan's text layer (text_zone_check.zone_number_points: the
scripts/plans/<key>-ocr-*.json labels placed with the sheet fits) and the rule rows from the
regulation text, and writes public/data/zone-numbers-<key>.json:
    {"00492": {"code": "Lke06/...", "at": [[lng, lat], ...],
               "rules": [{"text": "...", "cite": {"reg", "page", "para", "quote"}}]}}
Only numbers that have a rule row are written. Then set "zoneNumbers": "zone-numbers-<key>.json" on
the regulation (registry/<key>.json, registry.py build); the card shows the rows of the numbered zone
whose label lies in the tapped zone area.
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text_zone_check as tzc  # noqa: E402

ROOT = tzc.ROOT
DATA = tzc.DATA
FOOTNOTE = re.compile(r"^\*?(?:\d{1,4}(?:,\d{1,4})*)?\s*")


def pages(pdf):
    """The text of each page (pdftotext, pages split at form feeds)."""
    out = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return [re.sub(r"\s+", " ", re.sub(r"-\n\s*", "", p)) for p in out.split("\f")]


def rows(reg_id, pts):
    """{zone number: [{text, cite}]} from the regulation's rule table."""
    regs = json.loads((DATA / "regulations.json").read_text())["regulations"]
    out = {}
    for rid in sorted(r for r in regs if r == reg_id or r.startswith(reg_id + "-")):
        pdf = ROOT / "public" / regs[rid].get("pdf", "")
        if not regs[rid].get("pdf") or not pdf.exists():
            continue
        pg = pages(pdf)
        flat = " ".join(pg)
        starts, n = [], 0
        for p in pg:
            starts.append(n)
            n += len(p) + 1
        heads = [m for m in tzc.ENTRY.finditer(flat) if m[1] in pts]
        for a, b in zip(heads, heads[1:] + [None]):
            # A row runs to the next row's number, never past a new chapter; the last row is cut short.
            body = flat[a.end():b.start() if b and b.start() - a.end() < 3000 else a.end() + 600]
            body = re.split(r"\s(?=[IVX]+\.\s+Fejezet)", body)[0][:1500].strip()
            body = re.sub(r"\s\d{1,4}$", "", FOOTNOTE.sub("", body))  # a footnote number glued to the end
            if len(body) < 15 or not re.search(r"[a-záéíóöőúüű]{3}", body):
                continue
            page = max(i for i, s in enumerate(starts) if s <= a.start()) + 1
            out.setdefault(a[1], []).append({"text": body, "cite": {
                "reg": rid, "page": page, "para": f"{a[1]} sz. övezet", "quote": body[:80]}})
    return out


def build(key, show=False):
    cfg = json.loads((ROOT / "districts" / f"{key}.json").read_text())
    reg_id = cfg.get("regulation", {}).get("reg") or f"{key}-kesz"
    pts = tzc.zone_number_points(key)
    if not pts:
        print(f"{key}: the plan prints no zone numbers")
        return None
    regs = json.loads((DATA / "regulations.json").read_text())["regulations"]
    labels = []
    for r in regs.values():
        zl = r.get("zoneLabels")
        if zl and (r.get("parcels") or {}).get("dir") == f"parcels-{key}" and (DATA / zl).exists():
            labels += [(f["properties"]["code"], f["geometry"]["coordinates"]) for f in json.loads((DATA / zl).read_text())["features"]]
    kx = 111_320 * math.cos(math.radians(labels[0][1][1])) if labels else 75_000
    out = {}
    for no, rr in sorted(rows(reg_id, pts).items()):
        code = None
        for lng, lat in pts[no]:
            d, c = min(((math.hypot((c_[0] - lng) * kx, (c_[1] - lat) * 110_540), code_) for code_, c_ in labels), default=(1e9, None))
            if d < tzc.NO_LABEL_M:
                code = c
                break
        out[no] = {"code": code, "at": [[round(x, 6), round(y, 6)] for x, y in pts[no]], "rules": rr}
        if show:
            print(f"{no} {code}: {rr[0]['text'][:110]}")
    p = DATA / f"zone-numbers-{key}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{key}: {len(out)} numbered zones with rules ({sum(len(v['rules']) for v in out.values())} rows), "
          f"{sum(1 for v in out.values() if not v['code'])} without a code label next to the number -> {p.name}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        build(sys.argv[1], "--list" in sys.argv)
