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

Writes scripts/plans/<key>-textzones.json: {"statements": [{"hrsz", "code", "doc", "quote"}]}.

Why not streets: a survey of all 78 ingested regulations (docs/onboarding/text-zone-survey.md)
found only ~3 sentences where streets define a zone's extent; "által határolt" with a zone code is
almost always a rule for a part of a zone, not its edge.
"""
import json
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
    for rid in sorted(r for r in regs if r == reg_id or r.startswith(reg_id + "-")):
        pdf = ROOT / "public" / regs[rid].get("pdf", "")
        if not regs[rid].get("pdf") or not pdf.exists():
            continue
        for para in paragraphs(pdf_text(pdf)):
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
    return out


def run(key, show=False):
    st = statements(key)
    if st is None:
        return None
    p = ROOT / "scripts/plans" / f"{key}-textzones.json"
    p.write_text(json.dumps({"statements": st}, ensure_ascii=False, indent=1) + "\n")
    if show:
        for s in st:
            print(f"  {s['hrsz']:>12}  {s['code']:<20} {s['doc']}: {s['quote'][:120]}")
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
