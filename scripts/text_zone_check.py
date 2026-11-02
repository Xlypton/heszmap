"""Zones the regulation TEXT gives for named plots, read for the warning-only check Z8.

Some paragraphs name a zone and a plot number together, e.g. "Az Ln-1/I/01 jelű építési övezetben
a 7221, 7246/2 hrsz telken ...", or list a zone's plots ("KÖk-1/IX-K jelű övezet ...: 38028/1,
38028/2 hrsz"). Each such sentence says plot N lies in zone X. This script collects those
statements, each with its verbatim quote; check_district.py (Z8, standard library only) compares
them with the zone the map gives the plot today and warns on every disagreement.

The text is only a cross-check. It never sets or changes a zone: the plan drawing is the authority,
and a disagreement is either a map error to fix or a sentence the reader misunderstood, which is
recorded in acceptance.text_zones_ok {"<hrsz>": "why"}.

Only plain statements are taken: exactly one zone code in the paragraph, the plot number right
after it, and the number naming the plot the rule is about ("telken", "ingatlanon", or a list
after a colon), not a neighbour, a street the plot faces, or a plot "részben" (partly) in the zone.

    python3 scripts/text_zone_check.py <key> [--list]    one plan (needs pdftotext, poppler-utils)
    python3 scripts/text_zone_check.py --all             every plan with a zone table

Writes scripts/plans/<key>-textzones.json: {"statements": [{"hrsz", "code", "doc", "quote"}]}; on a
plan that numbers its zones (Győr) a statement names the zone number and the code(s) printed with it:
{"hrsz", "zone", "codes", "doc", "quote"}.

Why not streets: a survey of all 78 ingested regulations (docs/onboarding/text-zone-survey.md)
found only ~3 sentences where streets define a zone's extent; "által határolt" with a zone code is
almost always a rule for a part of a zone, not its edge.
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public/data"

NUM = r"\(?\d{3,6}(?:/\d+(?:-\d+)?)?\)?"
LIST = NUM + r"(?:\s*(?:,|és|valamint)\s*" + NUM + r")*"
# "7221, 7246/2 hrsz telken" (numbers, then hrsz, then the plot noun a few words on)
BEFORE = re.compile(r"(" + LIST + r")\s*(?:hrsz|helyrajzi\s+sz[aá]m)[\w\.\-\)]*\s*(?:ú\s+|-ú\s+)?[^;:\d]{0,50}?(telk|ingatlan|terület|tel\(k\))", re.I)
# "a hrsz.: 14894 ingatlanon" / "(hrsz: 13424/1)"
AFTER = re.compile(r"(?:hrsz|helyrajzi\s+sz[aá]m)[\w\.\-]*\s*:\s*(" + LIST + r")", re.I)
# "KÖk-1/IX-K jelű övezet ...: 38028/1, 38028/2 hrsz" (a list after a colon)
COLON = re.compile(r":\s*\(?(" + LIST + r")\s*\)?\s*(?:hrsz|helyrajzi)", re.I)
# the number is about some other plot than the one the zone rule is about
NOT_MEMBER = re.compile(r"határos|szomszéd|felől|felöli|csatlakoz|megközelít|közterület|közút|mentén|mellett|"
                        r"kapcsol|részben|kívül|kivételével|helyett|gépjármű|parkol", re.I)


def pdf_text(pdf):
    try:
        return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        sys.exit("pdftotext not found (apt install poppler-utils)")


def paragraphs(text):
    text = re.sub(r"-\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    # split at "(3)", "a)", "12. §" that start a new rule, and at "(3a)12 Az ..." amendment marks
    return re.split(r"(?<=[;\.:,])\s+(?=(?:\(\d+[a-z]?\)|[a-z]{1,2}\)|\d+\.\s*§))|\s(?=\(\d+[a-z]?\)\d*\s+[AaÁ]z?\s)", text)


def expand(tok):
    tok = tok.strip("() ")
    m = re.match(r"(\d+)/(\d+)-(\d+)$", tok)
    if m and int(m[3]) - int(m[2]) < 20:
        return [f"{m[1]}/{i}" for i in range(int(m[2]), int(m[3]) + 1)]
    return [tok]


def statements(key):
    cfg = json.loads((ROOT / "districts" / f"{key}.json").read_text())
    reg_id = cfg.get("regulation", {}).get("reg") or f"{key}-kesz"
    regs = json.loads((DATA / "regulations.json").read_text())["regulations"]
    zt = (regs.get(reg_id) or {}).get("zoneTypes")
    if not zt or not (DATA / zt).exists():
        return None
    codes = sorted((c for c in json.loads((DATA / zt).read_text()) if len(c) >= 2 and not c.startswith("_")), key=len, reverse=True)
    alt = "|".join(re.escape(c) for c in codes)
    any_code = re.compile(r"(?<![\w/\-])(" + alt + r")(?![\w/\-])")
    governs = re.compile(r"(?<![\w/\-])(" + alt + r")(?![\w/\-])\s*,?\s*(?:jelű\s+)?(?:építési\s+)?(?:övezet|közkert|közpark|-\s)")
    out, seen = [], set()
    texts = {}
    for rid in sorted(r for r in regs if r == reg_id or r.startswith(reg_id + "-")):
        pdf = ROOT / "public" / regs[rid].get("pdf", "")
        if regs[rid].get("pdf") and pdf.exists():
            texts[rid] = pdf_text(pdf)
    for rid, text in texts.items():
        for para in paragraphs(text):
            if not re.search(r"hrsz|helyrajzi", para, re.I):
                continue
            gov = governs.search(para)
            if not gov or len(set(any_code.findall(para))) != 1:
                continue
            tail = para[gov.end():]
            for rx in (BEFORE, AFTER, COLON):
                for m in rx.finditer(tail):
                    lead = tail[max(0, m.start() - 60):m.start()]
                    trail = tail[m.end():m.end() + 40]
                    if NOT_MEMBER.search(lead) or NOT_MEMBER.search(m.group(0)) or re.match(r"\s*(?:részben|kell biztosítani)", trail):
                        continue
                    for tok in re.findall(NUM, m[1]):
                        for h in expand(tok):
                            if (h, gov[1]) in seen:
                                continue
                            seen.add((h, gov[1]))
                            out.append({"hrsz": h, "code": gov[1], "doc": rid, "quote": para[:400].strip()})
    return out + numbered_statements(key, texts)


# --- plans that number every zone (Győr: "00492" printed above "Lke06/I/30/50-/075/02-20/32/") ----
# The text then keys its zone-specific rules by that number (GYÉSZ 103. § table: "00492 Az övezet
# területén belül lévő 3562 hrsz.-ú ingatlanon ..."). The number is found on the plan's text layer
# (scripts/plans/<key>-ocr-<sheet>.json, placed with the sheet fits in scripts/plans/<key>.json) and
# resolved to the code label printed with it; the statement then says plot N has that code.
ZONE_NO = r"0\d{4}(?:/[A-Z])?"
# a table row starts with the zone number, often glued to a footnote number ("02971447 Az ...",
# "01836 366 - A ...", "01118304 15%-ot ...")
ENTRY = re.compile(r"(?:^|(?<=\s))(" + ZONE_NO + r")\*?(?:\d{1,4}(?:,\d{1,4})*)?(?:\s\d{1,4}(?=\s+[-–A-ZÁÉÍÓÖŐÚÜŰ]))?\s+(?!sz\.|hrsz|helyrajzi|és\s|övezet)(?=\S)")
NO_LABEL_M = 25   # the code label sits right under its number


def zone_number_points(key):
    """{zone number: [(lng, lat), ...]} from the plan's text layer; {} when the plan prints none."""
    fit_p = ROOT / "scripts/plans" / f"{key}.json"
    if not fit_p.exists():
        return {}
    fit = json.loads(fit_p.read_text())
    lng0, lat0 = fit["local"]
    kx, ky = 111_320 * math.cos(math.radians(lat0)), 110_540
    pts = {}
    for i, sh in enumerate(fit["sheets"]):
        f = ROOT / "scripts/plans" / f"{key}-ocr-{i}.json"
        if sh.get("skipped") or sh.get("coef") is None or not f.exists():
            continue
        coef, centre, scale, order = sh["coef"], sh["centre"], sh["scale"], sh["order"]
        for lab in json.loads(f.read_text())["labels"]:
            t = lab["text"].rstrip("*")
            if not re.fullmatch(ZONE_NO, t):
                continue
            u = (sum(p[0] for p in lab["box"]) / 4 - centre[0]) / scale
            v = (sum(p[1] for p in lab["box"]) / 4 - centre[1]) / scale
            terms = [u ** (a - b) * v ** b for a in range(order + 1) for b in range(a + 1)]  # plan_georef.PolyModel
            x = sum(t_ * c[0] for t_, c in zip(terms, coef))
            y = sum(t_ * c[1] for t_, c in zip(terms, coef))
            pts.setdefault(t, []).append((x / kx + lng0, y / ky + lat0))
    return pts if len(pts) >= 100 else {}


def numbered_statements(key, texts):
    pts = zone_number_points(key)
    if not pts:
        return []
    regs = json.loads((DATA / "regulations.json").read_text())["regulations"]
    labels = []
    for r in regs.values():
        zl = r.get("zoneLabels")
        if zl and (r.get("parcels") or {}).get("dir") == f"parcels-{key}" and (DATA / zl).exists():
            labels += [(f["properties"]["code"], f["geometry"]["coordinates"]) for f in json.loads((DATA / zl).read_text())["features"]]
    if not labels:
        return []
    kx = 111_320 * math.cos(math.radians(labels[0][1][1]))

    def codes_of(no):
        out = set()
        for lng, lat in pts.get(no, []):
            d, code = min((math.hypot((c[0] - lng) * kx, (c[1] - lat) * 110_540), code) for code, c in labels)
            if d < NO_LABEL_M:
                out.add(code)
        return sorted(out)

    out, seen = [], set()
    for rid, text in texts.items():
        flat = re.sub(r"\s+", " ", re.sub(r"-\n\s*", "", text))
        heads = list(ENTRY.finditer(flat))
        for a, b in zip(heads, heads[1:] + [None]):
            no, body = a[1], flat[a.end():b.start() if b else a.end() + 600][:600]
            if no not in pts or not re.search(r"hrsz|helyrajzi", body, re.I):
                continue
            for m in BEFORE.finditer(body):
                if NOT_MEMBER.search(body[max(0, m.start() - 60):m.start()]) or NOT_MEMBER.search(m.group(0)):
                    continue
                codes = codes_of(no)
                for tok in re.findall(NUM, m[1]):
                    for h in expand(tok):
                        if codes and (h, no) not in seen:
                            seen.add((h, no))
                            out.append({"hrsz": h, "zone": no, "codes": codes, "doc": rid, "quote": f"{no} {body[:400].strip()}"})
    return out


def run(key, show=False):
    st = statements(key)
    if st is None:
        return None
    p = ROOT / "scripts/plans" / f"{key}-textzones.json"
    p.write_text(json.dumps({"statements": st}, ensure_ascii=False, indent=1) + "\n")
    if show:
        for s in st:
            print(f"  {s['hrsz']:>12}  {s.get('code') or s['zone'] + ' ' + '/'.join(s['codes']):<20} {s['doc']}: {s['quote'][:120]}")
    return st


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    keys = sorted(p.stem for p in (ROOT / "registry").glob("*.json")) if "--all" in args else [a for a in args if not a.startswith("--")]
    for k in keys:
        if not (ROOT / "districts" / f"{k}.json").exists():
            continue
        st = run(k, "--list" in args)
        if st is not None:
            print(f"{k}: {len(st)} plot-zone statements in the text")


if __name__ == "__main__":
    main()
