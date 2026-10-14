"""Zone limits tables whose text runs one cell per line in reading order (Budapest XI. KÉSZ 5 and 8, drawn by
the same planner): the zone code, then its cells left to right, then the next code. Writes
zoneTablePdf.rows into the config for ingest-pdf-zones.mjs, which verifies every quote in the PDF.

Config (zoneTablePdf): "codeRe", "seqFields" (one field per cell, null = no app field; "buildingMode" is
kept as text) or "seqGroups" [{"pages": [1-based], "fields": [...]}] for tables whose columns differ by page
(XVIII.: building zones, then the not-built-up zones), "footMarks" (regex for the footnote-mark lines, "" for none), "starNotes" (attach the page's "* …" footnote lines
to rows with a starred cell), "handRows" (rows transcribed by hand, replacing a parsed row of the same code), "joinCell" (regex for a line that continues the cell above), "ignoreText" (invisible text items to drop, as in ingest-pdf-zones.mjs). A cell split
across two text items ("15" + ",0", or "12,0" + "(7,5)" for an exception value) is joined; a line holding the code and its first cell
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
    groups = t.get("seqGroups") or [{"pages": None, "fields": t["seqFields"]}]
    rows = []
    for grp in groups:
        rows += parse(pdf, t, code_re, grp["fields"], grp["pages"])
    for r in rows:  # "categories": {code prefix: category} for tables whose headings carry no "(Lk-2)" (XVIII.)
        pre = r["code"].split("/")[0].split("-")[0]
        if not r.get("category") and pre in t.get("categories", {}):
            r["category"] = t["categories"][pre]
    hand = t.get("handRows", [])  # transcribed by hand (merged cells, scanned pages), kept across runs; they replace a parsed row
    rows = [r for r in rows if r["code"] not in {h["code"] for h in hand}] + hand
    for r in rows:  # "7,5 m" / "800 m2" / "25 %" (XVIII.): the unit is the field's; the card adds it to a plain number
        for f, v in r["values"].items():
            if isinstance(v, list) and f.endswith(("M", "M2", "Pct")):
                v[0] = re.sub(r"^([\d,.]+)\s*(?:m2?|%)(\**)$", r"\1\2", v[0].strip())
    t["rows"] = rows
    json.dump(cfg, open(cfg_path, "w"), ensure_ascii=False, indent=2)
    open(cfg_path, "a").write("\n")
    for r in rows:
        print(r["code"], [v for v in r["values"].values()], r.get("notes", ""))
    print(len(rows), "rows")


def parse(pdf, t, code_re, fields, pages):
    """The rows of the given pages (1-based; None = all) read with these fields."""
    lines, raws, line_page = [], [], []  # raws: the same lines with footnote superscripts kept, for the quote
    for page in pymupdf.open(pdf):
        if pages and page.number + 1 not in pages:
            continue
        if t.get("minCellSize"):  # drop footnote superscripts ("8,0" + small "1" reads "8,01"; XI. KÉSZ 3)
            pairs = [("".join(s["text"] for s in l["spans"] if s["size"] >= t["minCellSize"]), "".join(s["text"] for s in l["spans"]))
                     for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])]
        else:
            pairs = [(l, l) for l in page.get_text().split("\n")]
        for clean, raw in pairs:
            for junk in t.get("ignoreText", []):
                clean, raw = clean.replace(junk, ""), raw.replace(junk, "")
            if clean.strip():
                lines.append(clean.strip())
                raws.append(raw.strip())
                line_page.append(page.number)
    if t.get("joinCodeLines"):  # XVII.: a code wrapped in its cell ("Vi-2/" + "köz-01", "Lke1/köz-" + "01")
        k = 0
        while k < len(lines) - 1:
            if re.match(r"^[A-ZÁÉÍÓÖŐÚÜŰ][\w/-]*[/-]$", lines[k]) and re.match(r"^(?:[a-záéíóöőúüű]+-)?\d+$", lines[k + 1]):
                lines[k] += lines[k + 1]
                raws[k] += raws[k + 1]
                del lines[k + 1], raws[k + 1], line_page[k + 1]
            k += 1
    # Footnotes: "(x)" / "(xx)" / "[ ]" / "Z" on a line, the text on the next lines until the next mark.
    notes, k = {}, 0
    marks = re.compile(t.get("footMarks", r"^(\(x+\)|\(X\)|\[ \]|Z)$") or r"(?!)")
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
            cat = re.sub(r"^(?:\d+[a-z]?\.\s*)?(?:\d+(?:\.\d+[a-z]?)*\.?\s+)?", "", re.sub(r"\s*\([^)]*\)$", "", l)) or cat  # "11. 7.3. Kertvárosias …"
        if code_re.match(head):
            cells = [l[len(head):].strip()] if l != head else []
            rcells = [raws[i][len(head):].strip()] if l != head else []
            j = i + 1
            while len(cells) < len(fields) and j < first_note:
                c = lines[j]
                if code_re.match(c.split(" ")[0]):  # the next row: this one has empty cells (XVIII.: "KÖu-3" alone)
                    break
                if t.get("rowNumbers") and re.match(r"^\d+[a-z]?\.(?:\s|$)", c):  # XXI.: the next row's number ("23.")
                    break
                if c.startswith(",") and cells:  # "15" + ",0"
                    cells[-1] += c
                    rcells[-1] += raws[j]
                elif t.get("joinCell") and re.match(t["joinCell"], c) and cells:  # XVIII.: "75%" + "100% PH" (the parking-house value)
                    cells[-1] += " " + c
                    rcells[-1] += " " + raws[j]
                elif re.match(r"^\([\d,]+\)$", c) and cells:  # "12,0" + "(7,5)": the exception value under the cell's own
                    cells[-1] += " " + c
                    rcells[-1] += " " + raws[j]
                else:
                    cells.append(c)
                    rcells.append(raws[j])
                j += 1
            while j < first_note and (lines[j].startswith(",") or re.match(r"^\([\d,]+\)$", lines[j])):
                cells[-1] += lines[j] if lines[j].startswith(",") else " " + lines[j]
                rcells[-1] += raws[j] if raws[j].startswith(",") else " " + raws[j]
                j += 1
            values = {}
            for f, c in zip(fields, cells):
                if f == "buildingMode":
                    values[f] = c
                elif f:
                    values[f] = [c, num(c) if c.lower() != "kialakult" else None]
            # "Kt-U*": the star marks a footnote (XXI.), not part of the code.
            row = {"code": head.replace("--", "-").rstrip("*"), "quote": " ".join([head] + rcells), "values": values,
                   "heightIs": "épületmagasság", "category": cat}
            def marked(m):
                if m == "[ ]":
                    return any("[" in c for c in cells)
                if m == "Z":
                    return any(re.search(r"\)Z$", c) for c in cells)
                n = len(m) - 2  # "(xx)": cells carry "xx" (any case) not inside a longer run
                return any(re.search(rf"(?<![xX]){'[xX]' * n}(?![xX])", c) for c in cells)
            used = [n for m, n in notes.items() if marked(m)]
            paren = next((l for l in lines if l.startswith("( ) ")), None)  # "( ) a rendelet … eltéréssel alkalmazható határértékek"
            if paren and any(re.search(r"\(\d", c) for c in cells):
                used.append(paren)
            if t.get("starNotes") and any("*" in c for c in cells):
                # "* BP/1002/… eltérési engedély alapján": the star footnotes printed on the row's page.
                stars = {len(m) for c in cells for m in re.findall(r"\*+", c)}
                used += [l for l, pg in zip(lines, line_page)
                         if pg == line_page[i] and re.match(r"^\*+\s*\S", l) and len(re.match(r"\*+", l).group()) in stars]
            if used:
                row["notes"] = used
            rows.append(row)
            i = j
            continue
        i += 1
    return rows


if __name__ == "__main__":
    main(*sys.argv[1:3])
