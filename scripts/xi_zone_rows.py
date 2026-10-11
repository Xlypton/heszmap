"""Budapest XI. KÉSZ zone tables (2. melléklet PDF, no column letters): every row is the zone code and
11 cells in a fixed order. Reads the rows from the PDF text into "rows" for ingest-pdf-zones.mjs (which
re-verifies every quote against the PDF). A row whose cells do not fit the 11-cell pattern is skipped and
reported, never guessed.

    python3 scripts/xi_zone_rows.py <annex.pdf> <districts/key.json>
"""
import json
import re
import sys

import pymupdf

FIELDS = ["minPlotM2", "minPlotWidthM", "buildingMode", "maxCoveragePct", "maxUndergroundPct",
          "minHeightM", "maxHeightM", "maxFar", None, "maxFarParking", "minGreenPct"]
# (szm összesen = maxFar; szmá = the general share of it, not mapped; szmp = parking)
CODE = re.compile(r"^[A-ZÁÉÍÓÖŐÚÜŰ][A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{0,4}(?:-[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9]+)*-XI(?:-[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9]+)+$")
VALUE = re.compile(r"^(?:-|[\d.,]+%?\**|[A-ZÁÉÍÓÖŐÚÜŰ]{1,3}|K|kialakult|\d+[\d.,]*\s*\*+)$")


def num(s):
    s = s.replace(" ", "")
    m = re.match(r"^(\d+(?:[.,]\d+)?)$", s)
    return float(m.group(1).replace(",", ".")) if m else None


def main(pdf, cfg_path):
    doc = pymupdf.open(pdf)
    rows, skipped = [], []
    for page in doc:
        lines = [l.strip() for l in page.get_text().split("\n")]
        lines = [l for l in lines if l]
        cat = None
        for i, l in enumerate(lines):
            if l.endswith("jelű") or (i + 1 < len(lines) and lines[i + 1] == "jelű"):
                pass
            m = re.match(r"^(.+?)\s*(?:építési\s*)?övezet(?:ei|eine)?k?\s*szabályozási", l)
            if m and not CODE.match(l):
                cat = l
            if not CODE.match(l):
                continue
            toks, j = [], i + 1
            while j < len(lines) and not CODE.match(lines[j]) and len(toks) < 11:
                t = lines[j]
                if t in ("pm:", "ém:") and j + 1 < len(lines):
                    toks.append(f"{t} {lines[j + 1]}")
                    j += 2
                    continue
                if not VALUE.match(t):
                    break
                toks.append(t)
                j += 1
            if len(toks) != 11:
                skipped.append((l, toks))
                continue
            vals = {}
            for f, t in zip(FIELDS, toks):
                if not f:
                    continue
                if f in ("minHeightM", "maxHeightM"):
                    n = num(t[3:]) if t.startswith("ém:") else None  # pm: = párkánymagasság: no number
                    vals[f] = [t, n]
                elif f == "buildingMode":
                    vals[f] = t
                else:
                    vals[f] = [t, num(t.rstrip("%"))]
            quote = " ".join([l] + [x for t in toks for x in t.split(" ")])
            rows.append({"code": l, "quote": quote, "values": vals})
    cfg = json.load(open(cfg_path))
    cfg["zoneTablePdf"]["rows"] = rows
    open(cfg_path, "w").write(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(rows)} rows; skipped {len(skipped)}:")
    for s in skipped:
        print("  ", s[0], s[1])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
