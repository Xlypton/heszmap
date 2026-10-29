"""Zone limits tables in a PDF annex whose column letters do not match the cells (Budapest XXIII.: the
letters A–H head column groups, the cells under them are more): reads every row by position instead.

Each table's unit row ("(m2) (m) (%) rövidítés …") gives the columns; "zoneTablePdf.layouts" in the
config maps that unit sequence to fields (null = a column the app has no field for), and
"modeHeader" names a column without a unit (the building mode) by its header text. A row is the zone
code and the cells in its height band, assigned to the nearest column. Footnote markers (small
superscript numbers of the consolidated text) are not values. The quote is every text item of the row
in content order, so ingest-pdf-zones.mjs finds it in the PDF text; a row that does not fill its
columns is skipped and reported, never guessed.

    python3 scripts/pdf_zone_rows.py <annex.pdf> <districts/key.json>
"""
import json
import re
import sys

import pymupdf

UNIT = re.compile(r"^\((?:m2|m|%|m2/m2)\)$|^rövidítés$")


def num(s):
    # Two numbers in one cell ("45 75": general / corner plot) are not one number; "10 000" is.
    if re.search(r"\d\s+\d", s) and not re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+\s*\**", s.strip()):
        return None
    s = s.rstrip("*").replace(" ", "")
    s = re.sub(r"^(\d{1,3})((?:\.\d{3})+)$", lambda m: m.group(1) + m.group(2).replace(".", ""), s)
    m = re.match(r"^(\d+(?:,\d+)?)$", s)
    return float(m.group(1).replace(",", ".")) if m else None


def spans(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip():
                    out.append(s)
    return out


def main(pdf, cfg_path):
    cfg = json.load(open(cfg_path))
    t = cfg["zoneTablePdf"]
    code_re = re.compile(t["codeRe"])
    layouts = t["layouts"]
    mode_header = t.get("modeHeader", "beépítés módja")
    min_size = t.get("minCellSize", 7.5)
    doc = pymupdf.open(pdf)
    rows, skipped, seen = [], [], set()
    prev, prev_cat = None, None
    for page in doc:
        ss = spans(page)
        order = {id(s): i for i, s in enumerate(ss)}
        big = [s for s in ss if s["size"] >= min_size - 0.6]
        # Unit rows: units on one line, left to right (a span may hold two: "(m2/m2) (m2/m2)").
        units = []
        for s in ss:
            # "(m" + superscript "2" + ")" is "(m2)" set in three items.
            parts = [{"(m": "(m2)", "(%": "(%)", "(m2/": "(m2)"}.get(p, p) for p in s["text"].split()]
            if parts and all(UNIT.match(p) for p in parts):
                x0, x1 = s["bbox"][0], s["bbox"][2]
                w = (x1 - x0) / len(parts)
                for k, p in enumerate(parts):
                    units.append((round(s["bbox"][1]), x0 + w * (k + 0.5), p))
        heads = {}
        for y, x, p in units:
            key = next((k for k in heads if abs(k - y) <= t.get("unitRowTolerance", 2)), y)
            heads.setdefault(key, []).append((x, p))
        tables = []
        for y, us in sorted(heads.items()):
            us.sort()
            seq = "".join(p for _, p in us)
            if seq not in layouts:
                raise SystemExit(f"page {page.number + 1}: unknown unit row {seq}")
            fields = layouts[seq]
            xs = [x for x, _ in us]
            if isinstance(fields, dict):
                # Columns without a unit found by their header text (XI. KÉSZ 9: the plot area column has
                # no unit on some pages): {"fields": [...], "headers": ["Kialakítható legkisebb telekterület", …]}.
                for h in fields["headers"]:
                    hs = [s for s in ss if h in s["text"] and y - 300 < s["bbox"][1] < y]
                    if not hs:
                        raise SystemExit(f"page {page.number + 1}: no '{h}' header above y={y}")
                    xs.append((hs[-1]["bbox"][0] + hs[-1]["bbox"][2]) / 2)
                xs.sort()
                fields = fields["fields"]
            elif len(fields) == len(xs) + 1:  # a column without unit: the building mode
                mh = [s for s in ss if mode_header in s["text"] and s["bbox"][1] < y and s["bbox"][1] > y - 200]
                mh = [s for s in ss if s["bbox"][3] < y and s["bbox"][1] > y - 150 and s["bbox"][2] < us[0][0]
                      and s["text"].strip() in mode_header.split()] if not mh else mh
                if not mh:
                    raise SystemExit(f"page {page.number + 1}: no '{mode_header}' header above y={y}")
                xs = sorted([sum((s["bbox"][0] + s["bbox"][2]) / 2 for s in mh) / len(mh)] + xs)
            assert len(fields) == len(xs), (seq, fields)
            # The height columns' kind printed in the table head (Budapest XI.: "párkánymagasság (pm)" or
            # "épületmagasság (ém)"): "heightKinds" maps it to the row's heightIs, or to a text prefix
            # ("pm: ") with no number when the value is not an épületmagasság.
            kind = None
            for k in t.get("heightKinds", {}):
                if any(k in s["text"] and y - 300 < s["bbox"][1] < y for s in ss):
                    kind = k
            tables.append((y, xs, fields, kind))
        # Category title above each table ("1. Kisvárosias lakóterületek építési övezeteinek …").
        titles = [s for s in ss if re.match(r"^\d+\.\s+[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]", s["text"].strip())
                  and "terület" in s["text"]]
        if t.get("categoryTitleRe"):
            # Budapest XI.: "1. Ln-1-XI jelű" above the category's name on the next line.
            titles = []
            for k, s in enumerate(ss[:-1]):
                if re.match(t["categoryTitleRe"], s["text"].strip()):
                    ss[k + 1]["category"] = True
                    titles.append(ss[k + 1])
        # Rows above the page's first table continue the previous page's last table.
        if prev:
            tables.insert(0, (-1, *prev[1:]))
        # A code split in two items ("Má-" + "XXIII-1") is joined.
        for a, b in zip(ss, ss[1:]):
            beside = abs(a["bbox"][1] - b["bbox"][1]) < 2 and 0 <= b["bbox"][0] - a["bbox"][2] < 6
            below = a["bbox"][0] - 2 <= b["bbox"][0] and b["bbox"][2] <= a["bbox"][2] + 2 and 0 <= b["bbox"][1] - a["bbox"][3] < 6  # "Ln-1-XI-I-" / "01"
            if (a["text"].strip().endswith("-") or b["text"].strip().startswith("-")) and (beside or below):
                j = a["text"].strip().lstrip("*") + b["text"].strip()
                if code_re.match(j.replace(" ", "").rstrip("*")):
                    a["joined"] = j
                    a["bbox0"] = a["bbox"]
                    a["bbox"] = (a["bbox"][0], a["bbox"][1], max(a["bbox"][2], b["bbox"][2]), a["bbox"][3] if beside else b["bbox"][3])
                    b["text"] = ""
        text = lambda s: s.get("joined", s["text"])
        codes = [s for s in ss if s["size"] >= min_size - 0.6 and code_re.match(text(s).replace(" ", "").strip("*"))]
        codes.sort(key=lambda s: s["bbox"][1])
        # Note lines ("* Zártudvaros …", "**legfeljebb 300 m2/épület"), continuation lines joined.
        lines = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                tx = "".join(s["text"] for s in l["spans"]).strip()
                if tx:
                    lines.append((l["bbox"][1], l["bbox"][0], tx))
        lines.sort()
        notes = []
        for k, (y, x, tx) in enumerate(lines):
            if not tx.startswith("*"):
                continue
            full, ly = tx, y
            for y2, x2, t2 in lines[k + 1:]:
                if y2 - ly > 14 or t2.startswith("*") or re.match(r"^\d", t2) or abs(x2 - x) > 20:
                    break
                full, ly = full + " " + t2, y2
            if any(abs(c["bbox"][1] - y) < 2 for c in codes):
                continue  # a starred zone code ("*Ln-T-XI-U1-"), not a note
            notes.append((y, len(re.match(r"^\*+", full).group(0)), full))
        for i, c in enumerate(codes):
            y0 = c["bbox"][1] - 2
            tab = max((tb for tb in tables if tb[0] < y0), key=lambda tb: tb[0], default=None)
            if not tab:
                continue
            nxt = codes[i + 1]["bbox"][1] - 2 if i + 1 < len(codes) else c["bbox"][3] + 4
            if t.get("rowBand") == "centred":
                # Cells of several lines are centred on their row (Budapest XI.: "30" over "(15)"): the
                # band runs from halfway to the previous code to halfway to the next one.
                mid = lambda s: (s.get("bbox0", s["bbox"])[1] + s.get("bbox0", s["bbox"])[3]) / 2
                h = c.get("bbox0", c["bbox"])[3] - c.get("bbox0", c["bbox"])[1]
                y0 = (mid(codes[i - 1]) + mid(c)) / 2 if i and mid(c) - mid(codes[i - 1]) < 4 * h else c["bbox"][1] - h
                nxt = (mid(c) + mid(codes[i + 1])) / 2 if i + 1 < len(codes) and mid(codes[i + 1]) - mid(c) < 4 * h else c["bbox"][3] + h
                y0 = max([y0] + [tb[0] + 4 for tb in tables if tb[0] < c["bbox"][1]])  # not into the table head
            nxt = min(nxt, y0 + 30)
            # A table below ends this row's band.
            for tb in tables:
                if c["bbox"][1] < tb[0] < nxt:
                    nxt = tb[0] - 60
            band = [s for s in ss if s["text"] and y0 <= (s["bbox"][1] + s["bbox"][3]) / 2 < nxt and s["bbox"][0] >= c["bbox"][0] - 1]
            # Footnote lines ("*Legalább …") start at the code column: they are not cells.
            band = [s for s in band if s is c or not s["text"].lstrip().startswith("*") or s["bbox"][0] > c["bbox"][2]]
            band = [s for s in band if s is c or not any(abs(s["bbox"][1] - ny) < 2 for ny, _, _ in notes)]
            _, xs, fields, hkind = tab
            hk = t.get("heightKinds", {}).get(hkind, {})
            cells = [[] for _ in xs]
            for s in band:
                if s is c or s["size"] < min_size - 0.6 or re.match(r"^(?=.*[m()])[()/m2%\s]+$", s["text"].strip()):
                    continue  # the code, a footnote mark, a piece of a unit ("m2)")
                cx = (s["bbox"][0] + s["bbox"][2]) / 2
                if cx <= c["bbox"][2]:
                    continue
                parts = re.findall(r"\d{1,3}(?:[ .]\d{3})+\**|\S+", s["text"])
                # "4 000 10 000", "10.000 10.000", "2000**** SZ****": two cells in one text item, across two columns.
                inside = [x for x in xs if s["bbox"][0] - 2 <= x <= s["bbox"][2] + 2]
                if len(parts) > 1 and len(inside) == len(parts):
                    for x, p in zip(inside, parts):
                        cells[xs.index(x)].append(p)
                    continue
                cells[min(range(len(xs)), key=lambda j: abs(xs[j] - cx))].append(s["text"].strip())
            code = text(c).replace(" ", "").strip().strip("*")
            texts = [" ".join(x) for x in cells]
            if code in seen:
                skipped.append((code, "duplicate"))
                continue
            if any(not x for x, f in zip(texts, fields) if f):
                skipped.append((code, texts))
                continue
            vals = {}
            for f, x in zip(fields, texts):
                if not f:
                    continue
                if f in ("minHeightM", "maxHeightM") and hk.get("prefix"):
                    vals[f] = [hk["prefix"] + x, None]
                else:
                    vals[f] = x if f == "buildingMode" else [x, num(x) if "*" not in x else None]
            # The quote: the text items from the code to the row's last cell in content order (so it is
            # one run of the PDF text), including items between them that fell outside the band.
            lo, hi = order[id(c)], max(order[id(s)] for s in band)
            quote = " ".join(s["text"].strip() for s in ss[lo:hi + 1] if s["text"].strip())
            if c.get("joined"):
                # the second item ("01") was emptied for the join: put it back where it was printed
                quote = quote.replace(c["text"].strip(), c["text"].strip() + c["joined"][len(c["text"].strip().lstrip("*")):], 1)
            row = {"code": code, "quote": quote, "values": vals}
            if hk.get("heightIs"):
                row["heightIs"] = hk["heightIs"]
            title = max((s for s in titles if s["bbox"][1] < y0), key=lambda s: s["bbox"][1], default=None)
            cat = re.sub(r"\s+(?:építési\s+)?övezet\w*(?:\s+szabályozási.*)?$", "", re.sub(r"^\d+\.\s+", "", text(title).strip())) if title else prev_cat
            if cat:
                row["category"] = re.sub(r"\s+", " ", cat)
            # The table's starred notes, for the marks this row uses ("Z**," -> the "**" note).
            marks = {len(m) for x in texts for m in re.findall(r"\*+", x)}
            nxt_tab = min((tb[0] for tb in tables if tb[0] > y0), default=1e9)
            ns = [n for y, k, n in notes if y > c["bbox"][1] and y < nxt_tab and k in marks]
            if ns:
                row["notes"] = ns
            seen.add(code)
            rows.append(row)
        if tables:
            prev = tables[-1]
        if titles:
            last = max(titles, key=lambda s: s["bbox"][1])
            prev_cat = re.sub(r"\s+", " ", re.sub(r"\s+(?:építési\s+)?övezet\w*(?:\s+szabályozási.*)?$", "", re.sub(r"^\d+\.\s+", "", last["text"].strip())))
    t["rows"] = rows
    open(cfg_path, "w").write(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(rows)} rows; skipped {len(skipped)}:")
    for s in skipped:
        print("  ", s[0], s[1])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
