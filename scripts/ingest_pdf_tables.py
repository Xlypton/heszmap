"""Zone limits tables printed in an annex PDF instead of the decree's text (Budapest XV., XVI.).

ingest-kesz.mjs reads tables from njt's HTML; some decrees only link their "Építési övezetek …
előírásai" annex as a PDF. This script reads that PDF's tables (PyMuPDF), maps columns by the
table's own column letters (A, B, C, …, set per municipality), and cites every row by its text,
verified against the annex PDF itself, which is published unchanged next to the regulation text as a
separate citable document.

    python3 scripts/ingest_pdf_tables.py <key>

districts/<key>.json:
  "pdfTables": {
    "reg": "xvi-kesz-2m",               # id of the annex document (citations point to it)
    "of": "xvi-kesz",                   # the regulation whose zone types these are
    "title": "...", "decree": "...",
    "annex": "/document/...pdf",        # njt path or full URL
    "columns": {"A": "code", "B": "buildingMode", ...},
    "codePattern": "^...$",             # a row is a zone row if its code cell matches (whitespace removed)
    "codeFix": [["\\s+", ""]]           # optional regex replacements on the code
  }
Writes public/data/zone-types-<key>.json, public/docs/<annex reg>.pdf, and updates regulations.json
(the annex entry, and "zoneTypes" of the regulation). Run ingest-kesz.mjs <key> (with "tables": false)
first for the regulation text itself.
"""
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district  # noqa: E402
import njt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
squash = lambda s: re.sub(r"\s+", "", s or "")


def num(s):
    s = re.sub(r"\s", "", s)
    s = re.sub(r"^(\d{1,3})((?:\.\d{3})+)$", lambda m: m.group(1) + m.group(2).replace(".", ""), s)
    m = re.match(r"^(\d+(?:[.,]\d+)?)\**$", s)
    return float(m.group(1).replace(",", ".")) if m else None


def main(key):
    cfg = district.load(key)
    pt = cfg["pdfTables"]
    url = pt["annex"] if pt["annex"].startswith("http") else njt.NJT + pt["annex"]
    src = njt.download(url, district.work_dir(key) / "annex" / Path(url).name)
    out_pdf = ROOT / "public/docs" / f"{pt['reg']}.pdf"
    out_pdf.write_bytes(src.read_bytes())  # unchanged copy of the official annex
    doc = pymupdf.open(out_pdf)
    page_text = [squash(p.get_text()) for p in doc]
    code_re = re.compile(pt["codePattern"])
    letters = pt["columns"]
    zones, missing = {}, []
    for pno, page in enumerate(doc):
        lines = [(b[1], b[3], " ".join(b[4].split())) for b in page.get_text("blocks") if b[4].strip()]
        for t in page.find_tables().tables:
            rows = t.extract()
            head = next((r for r in rows if sum(1 for c in r if (c or "").strip() in letters) >= 3), None)
            if head is None:
                continue
            col = {}
            for c, v in enumerate(head):
                f = letters.get((v or "").strip())
                if f and f not in col.values():
                    col[c] = f
            code_col = next(c for c, f in col.items() if f == "code")
            # The category heading: the closest text block above the table ending in "(…)".
            above = [l for l in lines if l[1] <= t.bbox[1] + 2 and re.search(r"\([^)]+\)\s*$", l[2])]
            cat = max(above, key=lambda l: l[1])[2] if above else None
            for r in rows:
                cells = [(c or "").replace("\n", " ").strip() for c in r]
                # A value split over merged columns of the same letter: take the first non-empty one.
                code = cells[code_col]
                for a, b in pt.get("codeFix", [[r"\s+", ""]]):
                    code = re.sub(a, b, code)
                if not code_re.match(code):
                    continue
                quote = " ".join(c for c in cells if c)
                found = squash(quote) in page_text[pno]
                if not found:
                    missing.append(code); print("  not found:", quote, "| page", pno + 1)
                    continue
                cite = {"reg": pt["reg"], "page": pno + 1, "para": f"{pt.get('para', '2. melléklet')} – {code} sor", "quote": quote}
                z = {"name": f"{re.sub(r'^[0-9.]+', '', cat).strip()}" if cat else code, "category": cat}
                if cat and squash(cat) in page_text[pno]:
                    z["cite"] = {"reg": pt["reg"], "page": pno + 1, "para": pt.get("para", "2. melléklet"), "quote": cat}
                else:
                    z["cite"] = cite
                if pt.get("heightIs"):
                    z["heightIs"] = pt["heightIs"]
                for c, f in col.items():
                    if f == "code":
                        continue
                    v = cells[c] if c < len(cells) else ""
                    if not v:  # merged columns: the next column with the same letter
                        same = [k for k, x in enumerate(head) if (x or "").strip() == (head[c] or "").strip()]
                        v = next((cells[k] for k in same if k < len(cells) and cells[k]), "")
                    z[f] = {"text": v, "num": None if f == "buildingMode" else num(v), "cite": cite}
                if code in zones:
                    print(f"duplicate zone code {code}, keeping the first")
                    continue
                zones[code] = z
    if missing:
        sys.exit(f"rows not found verbatim in the PDF text: {missing}")
    (ROOT / "public/data" / f"zone-types-{key}.json").write_text(json.dumps(zones, ensure_ascii=False, indent=1) + "\n")
    regs_path = ROOT / "public/data/regulations.json"
    regs = json.loads(regs_path.read_text())
    regs["regulations"][pt["of"]]["zoneTypes"] = f"zone-types-{key}.json"
    regs["regulations"][pt["reg"]] = {
        "title": pt["title"], "decree": pt.get("decree"), "status": "linked", "pdf": f"docs/{pt['reg']}.pdf",
        "officialUrl": url, "retrievedAt": date.today().isoformat(),
        "sha256": hashlib.sha256(out_pdf.read_bytes()).hexdigest(), "annexes": [],
    }
    regs_path.write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    print(f"{key}: {len(zones)} zones from {len(doc)} annex pages, all rows verified")


if __name__ == "__main__":
    main(sys.argv[1])
