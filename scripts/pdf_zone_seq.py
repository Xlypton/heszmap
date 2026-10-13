"""Zone limits tables whose text runs one cell per line in reading order (Budapest XI. KÉSZ 5 and 8, drawn by
the same planner): the zone code, then its cells left to right, then the next code. Writes
zoneTablePdf.rows into the config for ingest-pdf-zones.mjs, which verifies every quote in the PDF.

Config (zoneTablePdf): "codeRe", "seqFields" (one field per cell, null = no app field; "buildingMode" is
kept as text), "ignoreText" (invisible text items to drop, as in ingest-pdf-zones.mjs). A cell split
across two text items ("15" + ",0") is joined; a line holding the code and its first cell
("Lke-3-XI-Kv-01 kialakult") is split. The category is the last "… (Lk-2)" heading line above the row.
Footnote marks stay in the cell text ("15 (20)xx[35]"); the number is the leading one (the base rule).
Footnotes "(x) …" under the table are attached to the rows whose cells carry that mark.

    python3 scripts/pdf_zone_seq.py <annex.pdf> <districts/key.json>
"""
import json
import re
import sys

import pymupdf


def num(s):
    m = re.match(r"^(\d[\d ]*(?:,\d+)?)(?![\d])", s.strip())
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def main(pdf, cfg_path):
    cfg = json.load(open(cfg_path))
    t = cfg["zoneTablePdf"]
    code_re = re.compile(t["codeRe"])
    fields = t["seqFields"]
    lines = []
    for page in pymupdf.open(pdf):
        tx = page.get_text()
        for junk in t.get("ignoreText", []):
            tx = tx.replace(junk, "")
        lines += [l.strip() for l in tx.split("\n") if l.strip()]
    # Footnotes: "(x)" / "(xx)" / "[ ]" / "Z" on a line, the text on the next lines until the next mark.
    notes, k = {}, 0
    marks = re.compile(r"^(\(x+\)|\(X\)|\[ \]|Z)$")
    first_note = next((i for i, l in enumerate(lines) if marks.match(l) and i > 0 and not code_re.match(lines[i - 1])), len(lines))
    for i in range(first_note, len(lines)):
        if marks.match(lines[i]):
            body = []
            for l in lines[i + 1:]:
                if marks.match(l):
                    break
                body.append(l)
            notes[lines[i]] = (lines[i] + " " + " ".join(body)).strip()
    rows, cat = [], None
    i = 0
    while i < first_note:
        l = lines[i]
        head = l.split(" ")[0]
        if re.search(r"\([A-ZÁÉÍÓÖŐÚÜŰ][\w-]*\)$", l) and not code_re.match(head):
            cat = re.sub(r"\s*\([^)]*\)$", "", l)
        if code_re.match(head):
            cells = [l[len(head):].strip()] if l != head else []
            j = i + 1
            while len(cells) < len(fields) and j < first_note:
                c = lines[j]
                if c.startswith(",") and cells:  # "15" + ",0"
                    cells[-1] += c
                else:
                    cells.append(c)
                j += 1
            while j < first_note and lines[j].startswith(","):
                cells[-1] += lines[j]
                j += 1
            values = {}
            for f, c in zip(fields, cells):
                if f == "buildingMode":
                    values[f] = c
                elif f:
                    values[f] = [c, num(c) if c.lower() != "kialakult" else None]
            row = {"code": head.replace("--", "-"), "quote": " ".join([head] + cells), "values": values,
                   "heightIs": "épületmagasság", "category": cat}
            def marked(m):
                if m == "[ ]":
                    return any("[" in c for c in cells)
                if m == "Z":
                    return any(re.search(r"\)Z$", c) for c in cells)
                n = len(m) - 2  # "(xx)": cells carry "xx" (any case) not inside a longer run
                return any(re.search(rf"(?<![xX]){'[xX]' * n}(?![xX])", c) for c in cells)
            used = [n for m, n in notes.items() if marked(m)]
            if used:
                row["notes"] = used
            rows.append(row)
            i = j
            continue
        i += 1
    t["rows"] = rows
    json.dump(cfg, open(cfg_path, "w"), ensure_ascii=False, indent=2)
    open(cfg_path, "a").write("\n")
    for r in rows:
        print(r["code"], [r["values"].get(f) for f in fields if f], r.get("notes", ""))
    print(len(rows), "rows")


if __name__ == "__main__":
    main(*sys.argv[1:3])
