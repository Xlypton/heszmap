"""Zone limits rows of Pécs's HÉSZ annex 2 ("Övezeti előírások"): one table per zone family (Ln, Lk, …),
one row per zone: row no., code (4 characters, X/Y/Z = set by special rules), special-rules code in
brackets ("(Bf)"), building mode, min plot area / width / depth, max coverage, max FAR (SZTM), min green,
min / max building height (ÉM), front garden, units per plot.

The columns are found per page from the header words ("területe", "szélessége", …): a value belongs to
the column whose header centre is nearest. The quote is the row's words in reading order, which is how
ingest-pdf-zones.mjs finds it in the PDF text.

    python3 scripts/pecs_zone_rows.py <annex.pdf> districts/pecs.json   -> writes zoneTablePdf.rows
"""
import json
import re
import sys

import pymupdf

HEAD = [  # header word -> field
    ("területe", "minPlotM2"), ("szélessége", "minPlotWidthM"), ("mélysége", None),
    ("beépítettsége", "maxCoveragePct"), ("(SZTM)", "maxFar"), ("mértéke", "minGreenPct"),
    ("min.", "minHeightM"), ("max.", "maxHeightM"), ("Előkert", None), ("száma", None),
]
MODE_X = ("mód", "buildingMode")
CODE = re.compile(r"^\d[\dXYZ]{3}$")


def num(s):
    s = s.strip()
    m = re.fullmatch(r"(\d+(?:,\d+)?)", s)
    return float(m.group(1).replace(",", ".")) if m else None


def page_rows(page, names, state):
    words = page.get_text("words")
    head = {}
    for w in words:
        if w[1] < 200:
            for h, f in HEAD + [MODE_X]:
                if w[4] == h and h not in head:
                    head[h] = ((w[0] + w[2]) / 2, f)
    cols = sorted(head.values())
    # A family heading left of the header (Ln, Lk, Lke …) starts a table; the K and beépítésre nem
    # szánt tables list several and name the family in a row of its own ("K-i").
    heads = [w for w in words if w[0] < 100 and 100 < w[1] < 200 and re.fullmatch(r"[A-ZÉ][\w\-]*", w[4])]
    if len(heads) == 1:
        state["family"] = heads[0][4]
    anchors = [w for w in words if w[0] < 95 and w[1] > 195 and re.fullmatch(r"\d{1,3}", w[4])]
    # A row printed without its row number (Pécs Vt 5572): its code anchors it instead.
    anchors += [w for w in words if 95 <= w[0] < 125 and w[1] > 195 and CODE.match(w[4])
                and not any(abs(a[1] - w[1]) < 10 for a in anchors)]
    anchors.sort(key=lambda w: w[1])
    rows = []
    for k, a in enumerate(anchors):
        # A row's code can sit a few points above or below its row number: the band runs halfway to
        # the neighbouring row numbers.
        y0 = (anchors[k - 1][1] + a[1]) / 2 if k else a[1] - 8
        y1 = (a[1] + anchors[k + 1][1]) / 2 if k + 1 < len(anchors) else a[3] + 30
        ws = sorted([w for w in words if y0 <= w[1] < y1 and w[0] >= 95], key=lambda w: (w[0], w[1]))  # by column: a row's words are not on one baseline
        if CODE.match(a[4]):  # anchored by its code: no row number
            ws = [a] + [w for w in ws if w is not a]
        if not ws:
            continue
        first = ws[0][4]
        nb = any(w[4] == "jel" and w[1] < 200 for w in words)  # beépítésre nem szánt table: "Övezeti jel" column
        if nb:
            # Övezeti jel (merged over the rows below it), then the övezet kódja: "Kb-np 2813" -> Kb-np-2813;
            # a row with only a code keeps the jel above; a jel without a code is the code (Zkp).
            if CODE.match(first):
                code = f"{state['jel']}-{first}"
            elif re.fullmatch(r"[A-ZÉ][\w\-]*", first):
                state["jel"] = first
                if len(ws) > 1 and CODE.match(ws[1][4]):
                    code = f"{first}-{ws[1][4]}"
                    ws = ws[1:]
                else:
                    code = first
            else:
                continue
        elif CODE.match(first):
            code = f"{state['family']}-{first}"
        elif re.fullmatch(r"[A-ZÉ][A-Za-zéáő]*(-[a-zöő]+)?", first) and len(ws) == 1:
            state["family"] = first  # a family row in the K table
            continue
        else:
            continue
        spec, values = None, {}
        for w in ws[1:]:
            t = w[4]
            if spec is None and (w[0] + w[2]) / 2 < 158 and re.fullmatch(r"\(?[A-ZÁÉÍÓÖŐÚÜŰ][\wÁÉ]*\)?", t):
                spec = t.strip("()")
                continue
            x = (w[0] + w[2]) / 2
            cx, f = min(cols, key=lambda c: abs(c[0] - x))
            if f and f not in values:
                values[f] = t
        full = code + (f"({spec})" if spec else "")
        out = {}
        for f, t in values.items():
            out[f] = t if f == "buildingMode" else [t, num(t)]
        order = {id(w): i for i, w in enumerate(words)}
        quote = " ".join(w[4] for w in sorted([a] + ws, key=lambda w: order[id(w)]))
        fam = state["jel"] if nb else state["family"]
        rows.append({"code": full, "quote": quote, "values": out, "category": names.get(fam, fam), "rowno": a[4]})
    return rows


def pdfjs_quote(items, rowno, code, spec):
    """The row as pdf.js reads it (ingest-pdf-zones.mjs searches that text): from the row number to the
    next row number."""
    it = [x.strip() for x in items if x.strip()]
    if CODE.match(rowno):  # a row without a number: from its code to the next row number or code
        for i in range(len(it)):
            if it[i] == rowno:
                j = i + 1
                while j < len(it) and j < i + 30 and not CODE.match(it[j]) and not (
                        re.fullmatch(r"\d{1,3}", it[j]) and j + 1 < len(it) and CODE.match(it[j + 1])):
                    j += 1
                return " ".join(it[i:j])
        return None
    for i in range(len(it) - 1):
        if it[i] == rowno and it[i + 1] == code:
            j = i + 2
            while j < len(it) and j < i + 30 and not (re.fullmatch(r"\d{1,3}", it[j]) and int(it[j]) == int(rowno) + 1):
                j += 1
            return " ".join(it[i:j])
    return None


def main(pdf, cfg_path):
    cfg = json.load(open(cfg_path))
    t = cfg["zoneTablePdf"]
    names = t.get("familyNames", {})
    doc = pymupdf.open(pdf)
    texts = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
    rows, seen, state = [], set(), {"family": None, "jel": None}
    hand_pages = set(t.get("handPages", []))
    for p in doc:
        if p.number + 1 in hand_pages:
            continue
        for r in page_rows(p, names, state):
            if texts:
                items = texts[p.number].split("\x01")
                kod = re.sub(r"\(.*", "", r["code"]).rsplit("-", 1)[-1]
                q = None
                for second in (kod, r["quote"].split()[1] if len(r["quote"].split()) > 1 else kod):
                    q = q or pdfjs_quote(items, r["rowno"], second, None)
                if q:
                    r["quote"] = q
            r.pop("rowno")
            if r["code"] in seen:
                print("duplicate", r["code"], "kept the first")
                continue
            seen.add(r["code"])
            rows.append(r)
    # Rows transcribed by hand (merged cells the position reader cannot follow):
    # [row no., jel, kód, sajátos, mód, telek területe, beépítettség, zöldfelület, ÉM min, ÉM max]
    fields = ["buildingMode", "minPlotM2", "maxCoveragePct", "minGreenPct", "minHeightM", "maxHeightM"]
    for no, jel, kod, spec, *vals in t.get("handRows", []):
        code = (f"{jel}-{kod}" if kod else jel) + (f"({spec})" if spec else "")
        values = {f: (v if f == "buildingMode" else [v, num(v.replace(" ", "")) if re.fullmatch(r"[\d ]+(,\d+)?", v) else None])
                  for f, v in zip(fields, vals) if v}
        q = None
        for pn in sorted(hand_pages):
            items = texts[pn - 1].split("\x01") if texts else []
            for second in (jel, kod, f"({spec})"):
                q = q or pdfjs_quote(items, str(no), second, None)
        if not q:
            print("no quote for hand row", no, code)
            continue
        if code in seen:
            print("duplicate", code, "kept the first")
            continue
        seen.add(code)
        rows.append({"code": code, "quote": q, "values": values, "category": names.get(jel, jel)})
    t["rows"] = rows
    json.dump(cfg, open(cfg_path, "w"), ensure_ascii=False, indent=2)
    open(cfg_path, "a").write("\n")
    print(f"{len(rows)} rows")


if __name__ == "__main__":
    main(*sys.argv[1:3])
