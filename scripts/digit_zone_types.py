"""Zone types for plans whose zone code spells its limits out in digits, read through the regulation's
tables (Mosonmagyaróvár HÉSZ 20/2014., 55. § and the 1.-2. számú táblázat).

    LKE-CS.3.1.5.3.(AK)
    |   |  | | | |  '- special-area suffix: "sajátos előírásai (AK)" (101. §) overrides the code's values (80. §)
    |   |  | | | '- building height code            (1. táblázat: 3 = 4,5 m)
    |   |  | | '- building coverage code            (5 = 30 %)
    |   |  | '- plot area code                      (1 = as built, 0 = not set, 2..9 = 300..5000 m²)
    |   |  '- building mode code                    (3 = oldalhatáros)
    |   '- building character (TV, PV, CS, TE, EGY)
    '- zone role (LN, LK, LKE, VT, VI, GK, GE, ÜÜ, ÜH, KR/x, KH, KM)

Every value is cited to the table row that defines it (quote found in public/docs/<reg>.pdf, searched from
the table's page on, so a number like "30 5" cannot land on another page). Plot width and depth come from the
2. táblázat by plot area and building mode. 0 = not set, 1 = as built ("kialakult", 55. § (3)). X in the
coverage place means "set by the special area's text" (GA: 65 %, 86. § (4); OT: 85 % on two plots, 82. § (6)).
Zones without digits (forest, farmland, parks, water, mining) are rows of plain words in the text and come from
config "plain". Special-area suffixes are read from the headings "... sajátos előírásai (XX)" of the text; a suffix
the plan prints that the text never defines is reported, not skipped.

    python3 scripts/digit_zone_types.py <key> [--placed]   (--placed after georef: only codes placed on the map)

Config, districts/<key>.json "digits": {
    "roles":   {role: [name, quote defining the role, quote of its rules heading or null, "§"]},
    "characters": {code: [name, quote of its § heading]},
    "table": {"heading": "1. számú táblázat", "mode": {digit: [name, quote]}, "plot": {digit: [m2, quote]},
              "coverage": {digit: [pct, quote]}, "height": {digit: [m, quote, text]},
              "widths": {plot digit: {"depth": [m, quote], "byMode": {mode digit: [m, quote]}}}},
    "as_built": [text, quote], "x": {suffix: [pct, quote, para]}, "suffixAlias": {"ÓT": "OT"},
    "override": [text, quote],                  the sentence that special areas override the plan's codes
    "plain": {code: {"name", "cite": [quote, para], "values": {field: [text, num, quote, para], ...}, "notes": [[text, quote, para]]}}
}
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CODE = re.compile(r"^(?P<role>[A-ZÁÉÍÓÖŐÚÜŰ]{2,3}(?:/[A-Z])?)-(?P<ch>TV|PV|CS|TE|EGY)\.(?P<m>[0-9X])\.(?P<a>[0-9X])\.(?P<c>[0-9X])\.(?P<h>[0-9X])(?:\.\((?P<suf>[^)]+)\))?$")


def squash(s):
    return re.sub(r"\s+", "", s)


def fmt(v):
    return f"{v:g}".replace(".", ",")


def main(key):
    cfg = dcfg.load(key)
    conf = cfg["digits"]
    reg = cfg["regulation"]["reg"]
    pdf = pymupdf.open(ROOT / "public" / "docs" / f"{reg}.pdf")
    raw = [p.get_text() for p in pdf]
    pages = [squash(t) for t in raw]
    table_page = next(i for i, t in enumerate(raw) if re.search(rf"^{re.escape(conf['table']['heading'])}\s*$", t, re.M))

    def cite(quote, para, start=0, span=None):
        q = squash(quote)
        rng = range(start, len(pages) if span is None else min(start + span, len(pages)))
        page = next((i + 1 for i in rng if q in pages[i]), None)
        if not page:
            sys.exit(f"quote not found in {reg}.pdf (pages {start + 1}+): {quote!r}")
        return {"reg": reg, "page": page, "para": para, "quote": quote}

    T = conf["table"]
    tcite = lambda q, para: cite(q, para, table_page, 4)
    roles = {r: (v[0], cite(v[1], "szerepkörök"), v[2] and cite(v[2], v[3] + " – rendeltetési előírások"), v[3]) for r, v in conf["roles"].items()}
    chars = {c: (n, cite(q, "építési karakter")) for c, (n, q) in conf["characters"].items()}
    mode = {d: (n, tcite(q, "1. számú táblázat – beépítési mód")) for d, (n, q) in T["mode"].items()}
    plot = {d: (v, tcite(q, "1. számú táblázat – legkisebb telekterület")) for d, (v, q) in T["plot"].items()}
    cov = {d: (v, tcite(q, "1. számú táblázat – legnagyobb beépítés")) for d, (v, q) in T["coverage"].items()}
    hgt = {d: (v, tcite(q, "1. számú táblázat – legnagyobb épületmagasság"), txt) for d, (v, q, txt) in T["height"].items()}
    depth = {d: (v["depth"][0], tcite(v["depth"][1], "2. számú táblázat – legkisebb telekmélység")) for d, v in T["widths"].items()}
    width = {(d, m): (w[0], tcite(w[1], "2. számú táblázat – telekszélesség")) for d, v in T["widths"].items() for m, w in v["byMode"].items()}
    built = (conf["as_built"][0], cite(conf["as_built"][1], "55. § (3)"))
    override = {"text": conf["override"][0], "cite": cite(conf["override"][1], "80. §")}

    # special-area suffixes: "<title> sajátos előírásai (XX)" and the § it stands in
    sufdef = {}
    for i, t in enumerate(raw):
        for m in re.finditer(r"([^\n§]{3,90}?)\s*sajátos előírásai\s*\(([^)]{1,3})\)", t):
            before = t[:m.start()]
            num = re.findall(r"(\d+(?:/[A-Z])?)\. §", before)
            if not num and i:
                num = re.findall(r"(\d+(?:/[A-Z])?)\. §", raw[i - 1])
            title = re.sub(r"^[\d/A-Z]*\.? ?§?\s*(\(\d\)\s*)?\d*\s*", "", m.group(1)).strip(" „\"")
            sufdef.setdefault(m.group(2), (title, num[-1] if num else "?", m.group(0).strip(), i))
    alias = conf.get("suffixAlias", {})

    seen, bad = {}, {}
    ocr = ROOT / "scripts/plans"
    for f in sorted(ocr.glob(f"{key}-ocr-*.json")):
        for l in json.loads(f.read_text())["labels"]:
            for tok in l["text"].split():
                tok = tok.replace("–", "-")
                seen[tok] = seen.get(tok, 0) + 1
    placed = None
    if "--placed" in sys.argv:
        placed = {x["properties"]["code"] for x in json.loads((ROOT / "public/data" / f"zone-labels-{key}.geojson").read_text())["features"]}

    out, unknown_suffix, outside = {}, {}, []
    for code in sorted(seen):
        m = CODE.match(code)
        if m:
            role = m["role"]
            if role not in roles:
                bad[code] = f"role {role} not in the regulation's list"
                continue
            if placed is not None and code not in placed:
                continue
            name, rcite, rules, para = roles[role]
            ch = m["ch"]
            z = {"name": f"{name} ({code})", "category": name, "cite": rcite}
            notes = []
            if rules:
                notes.append({"text": f"A rendeltetési előírásokat a(z) {para} tartalmazza.", "cite": rules})
            notes.append({"text": f"Építési karakter: {chars[ch][0]} ({ch}).", "cite": chars[ch][1]})
            nm = {"text": "", "cite": None}
            md = m["m"]
            suf = alias.get(m["suf"], m["suf"]) if m["suf"] else None
            if md in mode:
                z["buildingMode"] = {"text": f"{mode[md][0]} ({md})", "num": None, "cite": mode[md][1]}
            elif md == "1":
                z["buildingMode"] = {"text": "kialakult", "num": None, "cite": built[1]}
            ad = m["a"]
            if ad in plot:
                z["minPlotM2"] = {"text": fmt(plot[ad][0]), "num": plot[ad][0], "cite": plot[ad][1]}
                if (ad, md) in width:
                    w = width[(ad, md)]
                    z["minPlotWidthM"] = {"text": fmt(w[0]), "num": w[0], "cite": w[1]}
                if ad in depth:
                    notes.append({"text": f"Telek legkisebb mélysége: {fmt(depth[ad][0])} m", "cite": depth[ad][1]})
            elif ad == "1":
                z["minPlotM2"] = {"text": "kialakult", "num": None, "cite": built[1]}
            cd = m["c"]
            if cd in cov:
                z["maxCoveragePct"] = {"text": fmt(cov[cd][0]), "num": cov[cd][0], "cite": cov[cd][1]}
            elif cd == "1":
                z["maxCoveragePct"] = {"text": "kialakult", "num": None, "cite": built[1]}
            elif cd == "X":
                xv = conf.get("x", {}).get(suf or "")
                if xv:
                    z["maxCoveragePct"] = {"text": fmt(xv[0]), "num": xv[0], "cite": cite(xv[1], xv[2])}
                else:
                    z["maxCoveragePct"] = {"text": "X", "num": None, "cite": cite(conf["x_unset"][1], conf["x_unset"][2])}
                    notes.append({"text": conf["x_unset"][0], "cite": cite(conf["x_unset"][1], conf["x_unset"][2])})
            hd = m["h"]
            if hd in hgt:
                z["maxHeightM"] = {"text": hgt[hd][2] or fmt(hgt[hd][0]), "num": hgt[hd][0], "cite": hgt[hd][1], "label": "épületmagasság"}
            elif hd == "1":
                z["maxHeightM"] = {"text": "kialakult", "num": None, "cite": built[1], "label": "épületmagasság"}
            if suf:
                d = sufdef.get(suf)
                if d:
                    title, para_s, quote, pg = d
                    notes.append({"text": f"Sajátos előírási terület ({suf}): {title}. A sajátos előírások felülírják a szabályozási terven jelölt építési kód előírásait; a(z) {para_s}. § tartalmazza őket.",
                                  "cite": cite(quote, f"{para_s}. §", pg, 2)})
                    notes.append(override)
                else:
                    unknown_suffix[suf] = unknown_suffix.get(suf, 0) + seen[code]
                    notes.append({"text": f"A tervlap ({suf}) jelű sajátos előírási területet jelöl, de a rendelet szövege nem határoz meg ilyen jelű területet: az előírás a tervlapról nem olvasható ki.", "cite": override["cite"]})
            if md == "0":
                notes.append({"text": "A beépítési mód kódja 0: a rendelet szerint nincs meghatározva.", "cite": built[1]})
            z["notes"] = notes
            out[code] = z
        elif code.split(".(")[0] in conf["plain"] and (code in conf["plain"] or re.match(r"^[^.]+\.\([^)]{1,3}\)$", code)):
            if placed is not None and code not in placed:
                continue
            base, _, sx = code.partition(".(")
            sx = alias.get(sx.rstrip(")"), sx.rstrip(")"))
            p = conf["plain"][base]
            z = {"name": p["name"], "category": p.get("category", p["name"]), "cite": cite(p["cite"][0], p["cite"][1])}
            for field, (text, num, q, para) in p.get("values", {}).items():
                z[field] = {"text": text, "num": num, "cite": cite(q, para)}
                if field == "maxHeightM":
                    z[field]["label"] = "épületmagasság"
            z["notes"] = [{"text": t, "cite": cite(q, para)} for t, q, para in p.get("notes", [])]
            if sx:
                z["name"] = f"{p['name']} – {sx}"
                d = sufdef.get(sx)
                if d:
                    title, para_s, quote, pg = d
                    z["notes"] += [{"text": f"Sajátos előírási terület ({sx}): {title}. A(z) {para_s}. § sajátos előírásai felülírják a szabályozási terven jelölt kód előírásait.", "cite": cite(quote, f"{para_s}. §", pg, 2)}, override]
                else:
                    unknown_suffix[sx] = unknown_suffix.get(sx, 0) + seen[code]
            out[code] = z
    dest = ROOT / "public/data" / f"zone-types-{key}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    regs_path = ROOT / "public/data/regulations.json"
    regs = json.loads(regs_path.read_text())
    regs["regulations"][reg]["zoneTypes"] = dest.name
    regs_path.write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    digits = sum(1 for c in out if CODE.match(c))
    print(f"{len(out)} zone codes ({digits} with digits, {len(out) - digits} plain words)")
    if bad:
        print("NOT DECODED:", bad)
    if unknown_suffix:
        print("SUFFIXES THE TEXT NEVER DEFINES (plan prints them):", unknown_suffix)
    print("suffixes defined in the text:", " ".join(sorted(sufdef)))


if __name__ == "__main__":
    main(sys.argv[1])
