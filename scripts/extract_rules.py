"""Split a KÉSZ into paragraph-level provisions and work out which zones each one applies to.

Scope comes from (in order): a reviewed override in scripts/rules/<key>_scope.py, zone codes the
paragraph itself names, then the codes in its section/chapter heading, else the whole district.
Every quote is verified against the regulation PDF and gets its page.

Usage: python3 scripts/extract_rules.py xx path/to/njt.html
Writes public/data/rules-<key>.json and prints the assignments for review.
"""
import html
import importlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "rules"))

PREFIXES = ["Ln", "Lke", "Lk", "Vt", "Vi", "Gksz", "K", "KÖu", "KÖk", "Kt", "Zkp", "Ek", "Ev", "Má", "Mk", "Kb", "Vf", "Vá"]
CODE_RE = re.compile(r"(?<![\wÁÉÍÓÖŐÚÜŰáéíóöőúüű])(" + "|".join(sorted(PREFIXES, key=len, reverse=True)) +
                     r")((?:-\w+)*(?:/[\w-]+)?)(?!\w)")

# Table values a paragraph can change, by the words it uses.
PARAM_WORDS = {
    "maxHeightM": r"párkánymagasság|épületmagasság|beépítési magasság|legmagasabb pont|tűzfala? (?:legfeljebb|nem)",
    "minHeightM": r"legkisebb épületmagasság",
    "maxCoveragePct": r"beépítettség|beépítési mérték|beépítés mértéke",
    "minGreenPct": r"zöldfelület legkisebb|zöldfelületi arány|zöldfelület legkisebb megengedett",
    "maxFar": r"szintterületi mutató|parkolásra fordítható szintterület",
    "minPlotM2": r"telek terület|telekterület|telek szélessége|kialakítható telek",
    "setbacks": r"előkert|oldalkert|hátsókert|építési vonal",
    "units": r"rendeltetési egység|lakás helyezhető el",
    "kialakult": r"„kialakult\"|„kialakult”|kialakult\"",
}
CONDITIONAL_RE = re.compile(r"mellékleten (?:jelölt|lehatárolt|kijelölt)|által határolt területén|menti (?:telk|ingatlan|teleksor|épület)|"
                            r"úttal (?:szomszédos|határos)|utcára merőleges|irányában|hrsz|helyrajzi számú")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("‐", "-").replace("–", "-")
    s = re.sub(r"\bGksz (\d)", r"Gksz-\1", s)
    return s.replace("Vi-2/LZ", "Vi-2/L-Z")


def squash(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s))


def to_lines(raw: str, keep_sup: bool) -> list[str]:
    body = raw[raw.find('id="jogszab"'):]
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    if not keep_sup:
        body = re.sub(r'<sup class="fnSup"[^>]*>.*?</sup>', "", body, flags=re.S)
    body = re.sub(r"<table.*?</table>", "\n[TÁBLÁZAT]\n", body, flags=re.S)
    body = re.sub(r"<(div|p|h1|h2|h3|li|tr|br)[^>]*>", "\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    text = re.sub(r"[^\S\n]+", " ", text)
    return [l.strip() for l in text.split("\n") if l.strip()]


def mentions(text: str, codes: list[str]) -> set[str]:
    """Zone codes a text refers to. "Lk-1/K" means Lk-1/K1, Lk-1/K2 but not Lk-1/KSZ1; "Lk" is not "Lke"."""
    found = set()
    for m in CODE_RE.finditer(norm(text)):
        mention = m.group(1) + m.group(2)
        if mention in ("K", "Kt", "Vt", "Vi") and not m.group(2):
            continue
        for c in codes:
            # Case-insensitive: the text has typos such as "Ln-T/Sz1".
            rest = c[len(mention):] if c.upper().startswith(mention.upper()) else None
            if rest is not None and (rest == "" or rest[0] in "-/" or rest[0].isdigit()):
                found.add(c)
    return found


def parse_units(plain: list[str], withsup: list[str]):
    """Paragraph units: a § with each (n) bekezdés and its points; headings tracked for scope."""
    units, chapter, chapter_no, section, para = [], "", "", "", None
    stop = next((i for i, l in enumerate(plain) if re.match(r"^1\.? melléklet", l)), len(plain))
    for i in range(stop):
        line, sup = plain[i], withsup[i]
        if re.match(r"^[IVXL]+\. Fejezet$", line):
            chapter, chapter_no = plain[i + 1], line.split(".")[0]
            continue
        bare = re.sub(r"\(.*?\)", "", line)
        if bare == bare.upper() and re.search(r"[A-ZÁÉÍÓÖŐÚÜŰ]{4}", bare):
            continue  # part/chapter titles ("MÁSODIK RÉSZ", "KERTVÁROSIAS LAKÓTERÜLET (Lke)")
        if re.match(r"^\d+(/[A-Z])?\. [A-ZÁÉÍÓÖŐÚÜŰ]", line) and "§" not in line[:12]:
            section = line
            continue
        m = re.match(r"^(\d+(?:/[A-Z])?)\. § ?(\((\w+)\))?\s*(.*)$", line)
        b = re.match(r"^\((\d+[a-z]?)\)\s*(.*)$", line)
        if m:
            para = m.group(1)
            ident = f"{para}. §" + (f" ({m.group(3)})" if m.group(3) else "")
            units.append({"id": ident, "chapter": chapter, "chapterNo": chapter_no, "section": section, "lines": [line], "sup": [sup]})
        elif b and para:
            units.append({"id": f"{para}. § ({b.group(1)})", "chapter": chapter, "chapterNo": chapter_no, "section": section,
                          "lines": [line], "sup": [sup]})
        elif units and para:
            units[-1]["lines"].append(line)
            units[-1]["sup"].append(sup)
    for u in units:
        u["text"] = " ".join(u.pop("lines"))
        u["quoteFull"] = " ".join(u.pop("sup"))
    # Drop repealed/empty paragraphs ("(3)" with nothing after it).
    return [u for u in units if len(re.sub(r"^\S+ §|\(\w+\)", "", u["text"]).strip()) > 3]


def main():
    key, html_path = sys.argv[1], sys.argv[2]
    raw = Path(html_path).read_text(encoding="utf-8")
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg_id = f"{key}-kesz"
    reg = regs["regulations"][reg_id]
    zone_types = json.loads((ROOT / "public/data" / reg["zoneTypes"]).read_text())
    codes = sorted(zone_types)
    scope = importlib.import_module(f"{key}_scope")

    plain, withsup = to_lines(raw, False), to_lines(raw, True)
    assert len(plain) == len(withsup), "footnote markers changed the line structure"
    units = parse_units(plain, withsup)

    doc = pymupdf.open(ROOT / "public" / reg["pdf"])
    pages = [squash(p.get_text()) for p in doc]

    out, missing = [], []
    for u in units:
        if u["id"] in scope.SKIP or any(u["id"].startswith(p) for p in scope.SKIP_PREFIX):
            continue
        own = mentions(u["text"], codes)
        override = scope.OVERRIDES.get(u["id"])
        if override is not None and "mode" in override:
            word = override["mode"]
            zones = sorted(c for c, z in zone_types.items() if re.fullmatch(scope.BUILT, c) and (
                word in z.get("buildingMode", {}).get("text", "") or z.get("buildingMode", {}).get("text") in ("---", "-")))
            kind = override["kind"]
        elif override is not None:
            zones, kind = override.get("zones"), override.get("kind")
            if isinstance(zones, str) and zones != "*":
                zones = sorted(c for c in codes if re.fullmatch(zones, c))
        elif own:
            zones, kind = sorted(own), "zone"
        else:
            inherited = mentions(u["section"], codes) or mentions(u["chapter"], codes)
            zones, kind = (sorted(inherited), "category") if inherited else ("*", "general")
        conditional = (override or {}).get("conditional", bool(CONDITIONAL_RE.search(u["text"])))
        flags = [p for p, rx in PARAM_WORDS.items() if re.search(rx, u["text"])] if kind not in ("general", "public") else []
        if override and "flags" in override:
            flags = override["flags"]

        # Quote: as much of the paragraph as fits on one page, verified against the PDF.
        words = u["quoteFull"].split()
        quote, page = None, None
        for n in (len(words), 60, 40, 25, 15, 10):
            q = " ".join(words[:n])
            hit = next((i + 1 for i, p in enumerate(pages) if squash(q) in p), None)
            if hit:
                quote, page = q, hit
                break
        if not quote:
            missing.append(u["id"])
            continue
        out.append({
            "id": u["id"], "section": u["section"], "chapter": u["chapter"], "text": u["text"],
            "kind": kind, "zones": zones, "conditional": conditional, "flags": flags,
            "note": (override or {}).get("note"),
            "cite": {"reg": reg_id, "page": page, "para": u["id"], "quote": quote},
        })

    if missing:
        sys.exit(f"quotes not found in the PDF: {', '.join(missing)}")
    path = ROOT / "public/data" / f"rules-{key}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    reg["rules"] = path.name
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")

    for r in out:
        z = r["zones"] if r["zones"] == "*" else (", ".join(r["zones"]) if len(r["zones"]) <= 6 else f"{len(r['zones'])} zones: {r['zones'][0]}…")
        print(f"{r['id']:<12} {r['kind']:<9} {'C' if r['conditional'] else ' '} {','.join(r['flags']):<28} {z} | {r['text'][:70]}")
    print(f"{len(out)} provisions, all quotes verified")


if __name__ == "__main__":
    main()
