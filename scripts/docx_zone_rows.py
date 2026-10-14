"""Zone limits tables published as a .docx annex (Budapest XXII. Duna menti KÉSZ 28/2016. and 19/2018.):
read every table whose header names the zone code ("Építési övezet jele") straight from the Word XML, and
write zoneTablePdf.rows for ingest-pdf-zones.mjs, which converts the .docx to PDF and checks each row's
quote in that PDF's text.

Config (zoneTablePdf): "docxFields": one app field per column right of the row number (the first is the
code; null = no app field; "buildingMode" is kept as text). The category is the heading paragraph above
the table ("Kisvárosias lakóterületek"); footnote numbers printed as superscripts are kept in the quote
and dropped from the value; the note rows under the table ("1: …", "*: …") go to the rows that use them. "docxCodes": codes
without a - or / ("KÖk"). "docxCategory": the category when no heading names one (Budafok: "Intézményi terület").

    python3 scripts/docx_zone_rows.py <annex.docx> <districts/key.json>
"""
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def runs(el):
    """(text, superscript) for each run in the element, in order."""
    out = []
    for r in el.iter(W + "r"):
        sup = any(v.get(W + "val") == "superscript" for v in r.iter(W + "vertAlign"))
        t = "".join(x.text or "" for x in r.iter(W + "t"))
        if t:
            out.append((t, sup))
    return out


def text(el, keep_sup=True):
    return re.sub(r"\s+", " ", "".join(t for t, s in runs(el) if keep_sup or not s)).strip()


def num(s):
    v = s.replace(" ", "").replace("*", "")
    v = re.sub(r"^(\d{1,3})((?:\.\d{3})+)$", lambda m: m.group(1) + m.group(2).replace(".", ""), v)
    m = re.match(r"^(\d+(?:,\d+)?)$", v)
    return float(m.group(1).replace(",", ".")) if m else None


def main(docx, cfg_path):
    cfg = json.load(open(cfg_path))
    t = cfg["zoneTablePdf"]
    fields = t["docxFields"]
    body = ET.fromstring(zipfile.ZipFile(docx).read("word/document.xml")).find(W + "body")
    rows, cat, pending = [], t.get("docxCategory"), []
    for el in body:
        if el.tag == W + "p":
            s = text(el)
            # The heading above a table ("Kisvárosias lakóterületek", numbered by Word itself), not the annex title.
            if s and "melléklet" not in s and "határérték" not in s:
                cat = re.sub(r"^\d+\.\s*", "", s)
            continue
        if el.tag != W + "tbl":
            continue
        pending = []
        for tr in el.iter(W + "tr"):
            cells = [tc for tc in tr.findall(W + "tc")]
            if len(cells) < 2:
                # A note row under the table ("1: Az építési övezet …"): for the rows using mark "1".
                m = re.match(r"^(\d+|\*+)\s*:\s*\S", text(cells[0])) if cells else None
                for r in pending if m else []:
                    if m.group(1) in r["_marks"]:
                        r.setdefault("notes", []).append(text(cells[0]))
                continue
            vals = cells[1:]
            code = text(vals[0], keep_sup=False).replace(" ", "")
            if not re.match(r"^[A-ZÁÉÍÓÖŐÚÜŰ][A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{0,4}[-/]", code) and code not in t.get("docxCodes", []):
                continue
            values, marks = {}, set()
            for f, tc in zip(fields[1:], vals[1:]):
                if not f:
                    continue
                full, clean = text(tc), text(tc, keep_sup=False)
                marks |= {s.strip() for s, sup in runs(tc) if sup} | set(re.findall(r"\*+", full))
                values[f] = clean if f == "buildingMode" else [clean, num(clean)]
            row = {"code": code, "quote": " ".join(text(tc) for tc in vals), "values": values,
                   "heightIs": t.get("heightIs", "épületmagasság"), "category": cat, "_marks": marks}
            rows.append(row)
            pending.append(row)
    for r in rows:
        r.pop("_marks")
    t["rows"] = rows
    json.dump(cfg, open(cfg_path, "w"), ensure_ascii=False, indent=2)
    open(cfg_path, "a").write("\n")
    for r in rows:
        print(r["code"], r["category"], [v if isinstance(v, str) else v[0] for v in r["values"].values()], r.get("notes", ""))
    print(len(rows), "rows")


if __name__ == "__main__":
    main(*sys.argv[1:3])
