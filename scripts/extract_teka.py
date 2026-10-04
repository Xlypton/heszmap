"""TÉKA (280/2024. (IX. 30.) Korm. rendelet) provisions that apply regardless of the local plan.

TÉKA 136. § (2): for procedures started after 2025-06-30 the listed provisions apply "a helyi
építési szabályzat hatálybalépésének időpontjától függetlenül", and conflicting local provisions
cannot be applied. Everything else in TÉKA only applies to new településtervek (136. § (1) d)); an
older KÉSZ applies together with the OTÉK state named in 136. § (1) a)–c).

Usage: python3 scripts/extract_teka.py
Writes public/data/teka-rules.json.
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_rules as er  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NJT_ID = "2024-280-20-22"

# 136. § (2), transcribed: § -> paragraphs (None = the whole §).
MANDATORY = {
    "1": None, "2": None, "4": None, "7": ["6"], "8": ["9", "10"], "10": ["4"], "21": ["1", "4", "5", "6"],
    "22": ["4", "5", "6"], "29": [str(i) for i in range(4, 14)], "34": [str(i) for i in range(6, 13)],
    "35": None, "36": None, "40": None, "41": ["1", "2"], "42": None, "43": None, "44": None,
    "47": ["5", "5a", "8", "9"], "48": None, "50": None, "51": None, "52": None, "59": None, "60": None, "67": None,
}
MANDATORY_CHAPTERS = {"VI", "VII", "VIII", "IX", "X", "XI"}


def mandatory(unit) -> bool:
    m = re.match(r"^(\d+(?:/[A-Z])?)\. §(?: \((\w+)\))?", unit["id"])
    para, bek = m.group(1), m.group(2)
    if unit["chapterNo"] in MANDATORY_CHAPTERS:
        return True
    if para not in MANDATORY:
        return False
    allowed = MANDATORY[para]
    return allowed is None or bek in allowed


def main():
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg = regs["regulations"]["teka"]
    raw = (ROOT / "scripts/.cache" / f"njt-{NJT_ID}.html").read_text(encoding="utf-8")
    units = er.parse_units(er.to_lines(raw, False), er.to_lines(raw, True))
    pages = [er.squash(p.get_text()) for p in pymupdf.open(ROOT / "public" / reg["pdf"])]

    out, basis, missing = [], [], []
    for u in units:
        is_basis = u["id"] in ("136. § (1)", "136. § (2)")
        if not (mandatory(u) or is_basis):
            continue
        words = u["quoteFull"].split()
        quote = page = None
        for n in (len(words), 60, 40, 25, 15, 10):
            q = " ".join(words[:n])
            hit = next((i + 1 for i, p in enumerate(pages) if er.squash(q) in p), None)
            if hit:
                quote, page = q, hit
                break
        if not quote:
            missing.append(u["id"])
            continue
        item = {"id": u["id"], "chapter": f"{u['chapterNo']}. {u['chapter']}", "section": u["section"], "text": u["text"],
                "cite": {"reg": "teka", "page": page, "para": u["id"], "quote": quote}}
        (basis if is_basis else out).append(item)
    if missing:
        sys.exit(f"quotes not found in the PDF: {', '.join(missing)}")
    (ROOT / "public/data/teka-rules.json").write_text(json.dumps({"basis": basis, "rules": out}, ensure_ascii=False, indent=1) + "\n")
    reg["mandatoryRules"] = "teka-rules.json"
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    chapters = {}
    for r in out:
        chapters.setdefault(r["chapter"], 0)
        chapters[r["chapter"]] += 1
    for c, n in chapters.items():
        print(f"{n:4d}  {c}")
    print(f"{len(out)} mandatory TÉKA provisions, all quotes verified")


if __name__ == "__main__":
    main()
