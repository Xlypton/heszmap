"""What the regulation TEXT says a zone is bounded by, for the card ("A rendelet szövege az övezet
határairól").

Peti (2026-11-02): show the zone's border description ("... által határolt") on the card, so a user
can compare the words with the area drawn on the map. Most KÉSZ texts leave a zone's extent to the
plan drawing (docs/onboarding/text-zone-survey.md), so what the text holds is mostly:

  extent  the zone itself is described by its bounding streets ("A Vi-1/Sz-3 jelű építési övezet a
          Kossuth Lajos utca – Ady Endre út – ... által határolt ... területek övezete"),
  part    a rule for a street-bounded part of the zone ("az Lk-2/SZ-8 építési övezet Vadrózsa utca –
          Hankóczy Jenő utca – Zilah utca – Herman Ottó utca által határolt területén ..."),
  plots   plots the text names as lying in the zone (text_zone_check.py statements, the same ones
          check Z8 compares with the map).

Only a chain of two or more named streets / plots / watercourses before "által határolt",
"közötti", "által közrezárt" is taken, followed by a word for an area (terület, tömb, telek ...),
so "between street A and B a lane must be built" is not shown as a border.

    python3 scripts/zone_borders.py <key> [--list]
    python3 scripts/zone_borders.py --all

Writes public/data/zone-borders-<key>.json:
    {"<code>": [{"kind": "extent"|"part"|"plots", "text": "...", "bounds": "...",
                 "hrsz": [...], "cite": {"reg", "page", "para", "quote"}}]}
({} when the text names none) and sets "zoneBorders" on the regulation in registry/<key>.json (run
registry.py build after).
Every area is reported, also the ones where the text names no border (NOTHING FOUND).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text_zone_check as tzc  # noqa: E402

ROOT, DATA = tzc.ROOT, tzc.DATA

UP = "A-ZÁÉÍÓÖŐÚÜŰ"
STREET = (r"(?:utc(?:a|ák|ája)|u\.|útja|utak|főút|útj?a?|tere?|közök?|sora?|körút|krt\.|rakpart|sétány|fasor|lejtő|dűlő|"
          r"park|liget|lépcső|patak|árok|Duna(?:-ág)?|vasútvonal|vasút|határa|telekhatár|hrsz[\w\.\-]*"
          r"(?:\s+(?:közterület|telek|ingatlan|közút|út|utca|árok))?|közterület|ingatlan|telek)")
# one named item: a capitalised word, a number or a "(12345)" plot, up to four more words, then a street
# word ("István király utca", "tervezett Köu-2 övezetű főút", "(52091/7) hrsz.-ú közterület")
STOP = r"(?:a|az|A|Az|és|által|valamint|ahol|kivéve|jelű|építési|övezet(?!ű)\w*|terület\w*|telk\w*|§|között\w*)(?![\w])"
CAP = r"[" + UP + r"\(\d][\w\.\-\(\)/]*"
ANY = r"(?!" + STOP + r")[\w\.\-\(\)/]+"
ITEM = (r"(?:(?:a|az|A|Az)\s+)?(?:(?:tervezett|felső|alsó)\s+)?" + CAP + r"\s+(?:" + ANY + r"\s+){0,4}?" + STREET + r"(?![\w])")
SEP = r"(?:\s*[–—-]\s*|\s*,\s*|\s+és\s+|\s+valamint\s+|\s+)"
CHAIN = re.compile(r"(" + ITEM + r"(?:" + SEP + ITEM + r")+)\s+(?:(?:által|által\s+körül)\s*(?:határolt|közrezárt|bezárt|lehatárolt|körbezárt)|közötti?|közé\s+eső)"
                   r"(,?(?:\s+[\w\-,\(\)]+){0,10}?\s+(?:terület\w*|tömb\w*|telk\w*|telek|ingatlan\w*|rész\w*|övezete\w*|közkert\w*|közpark\w*))")
# "... által határolt területe(i)" / "övezete" names the zone itself; "területén", "telkein" a part of it
WHOLE = re.compile(r"\b(?:területe|területei|területek\s+övezete|övezete|közkertek\s+területe)\b(?!n)", re.I)


def pdf_pages(pdf):
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return out.split("\f")


def squash(s):
    return re.sub(r"\s+", "", s)


def locate(pages, quote, near=""):
    """(page, quote as printed) for a quote taken from the de-hyphenated text: the PDF may break a
    line inside it with a hyphen ("Apáca utca -\nFerencesek"), which the viewer's search must see.
    Short quotes repeat, so a page that also holds `near` wins."""
    q = squash(quote)[:45]
    rx = re.compile(r"[\s\-]*".join(re.escape(c) for c in q))
    n = squash(near)[:30]
    hits = []
    for i, p in enumerate(pages):
        m = rx.search(p)
        if m:
            hits.append((i, re.sub(r"\s+", " ", m[0]).strip()))
    best = [h for h in hits if n in squash(pages[h[0]]) or (h[0] + 1 < len(pages) and n in squash(pages[h[0] + 1]))]
    i, printed = (best or hits or [(0, quote)])[0]
    return i + 1, printed


def codes_for(key):
    cfg = json.loads((ROOT / "districts" / f"{key}.json").read_text())
    reg_id = cfg.get("regulation", {}).get("reg") or f"{key}-kesz"
    regs = json.loads((DATA / "regulations.json").read_text())["regulations"]
    zt = (regs.get(reg_id) or {}).get("zoneTypes")
    if not zt or not (DATA / zt).exists():
        return reg_id, regs, None
    codes = sorted((c for c in json.loads((DATA / zt).read_text()) if len(c) >= 2 and not c.startswith("_")), key=len, reverse=True)
    return reg_id, regs, codes


def borders(key):
    reg_id, regs, codes = codes_for(key)
    if codes is None:
        return None
    alt = "|".join(re.escape(c) for c in codes)
    any_code = re.compile(r"(?<![\w/\-])(" + alt + r")(?![\w/\-])")
    out = {}
    seen = set()
    pages = {}
    for rid in sorted(r for r in regs if r == reg_id or r.startswith(reg_id + "-")):
        pdf = ROOT / "public" / regs[rid].get("pdf", "")
        if not regs[rid].get("pdf") or not pdf.exists():
            continue
        pg = pdf_pages(pdf)
        pages[rid] = pg
        parent = None
        for para in tzc.paragraphs("\f".join(pg)):
            para = para.replace("\f", " ")
            lettered = re.match(r"[a-z]{1,2}\)", para)
            found = any_code.findall(para)
            if found and para.rstrip().endswith(":") and len(set(found)) == 1:
                parent = found[0]
            elif not lettered:
                parent = None
            for m in CHAIN.finditer(para):
                # the sentence the chain is in: back to the last full stop, semicolon or list number
                head = para[max(0, m.start() - 300):m.start() + 1]
                cuts = list(re.finditer(r"[\.;]\s+(?=[" + UP + r"\(a-z])|\s\d{1,2}\.\s+(?=[" + UP + r"])", head))
                sent_start = m.start() + 1 - len(head) + (cuts[-1].end() if cuts else 0)
                window = para[sent_start:m.start()]
                own = sorted(set(any_code.findall(window))) if re.search(r"övezet", window) else []
                own = own or ([parent] if lettered and parent else [])
                if not own:
                    continue
                # "a Zkp-3 övezetbe és az X utca – ... által határolt területre": the area is named beside the zone
                if re.search(r"\bés\s+(?:az?\s+)?$", window):
                    continue
                # the item list must not be other zones ("Vi-2/45 és Vi-2/56 ... között"); a planned road
                # named by its zone ("tervezett Köu-2 övezetű főút") is a border item
                if any_code.search(re.sub(r"\S+\s+övezetű", "", m[1])):
                    continue
                tail = para[m.end(1):m.end() + 60]
                whole = (len(own) == 1 and bool(WHOLE.search(tail))
                         and not re.search(r"területén|területen|telkein|tömbben|\w+(?:ban|ben)\b", para[m.end(1):m.end()])
                         and not re.search(r"területén|területen|\bban\b|\bben\b", window[-150:]))
                text = para[sent_start:m.end() + 320]
                # to the end of the sentence; "a 21. §", "a III. ütem" do not end it
                cut = re.search(r"(?<=;)\s|(?<=[^\dIVX\s]\.)\s(?=[" + UP + r"\(])", text[m.end() - sent_start:])
                if cut:
                    text = text[:m.end() - sent_start + cut.start()]
                text = text.strip()
                page, quote = locate(pages[rid], para[sent_start:sent_start + 70], m[1])
                for code in own:
                    if (code, re.sub(r"\W", "", m[1])) in seen:
                        continue
                    seen.add((code, re.sub(r"\W", "", m[1])))
                    out.setdefault(code, []).append({
                        "kind": "extent" if whole else "part",
                        "text": text[:700],
                        "bounds": re.sub(r"^(?:\d{1,3}\s+)?(?:[Aa]z?\s+)?", "", m[1].strip()),
                        "cite": {"reg": rid, "page": page, "para": "határoló utcák", "quote": quote}})
    # plots the text puts in the zone (the Z8 statements), one entry per zone and sentence
    st = tzc.statements(key) or []
    for s in st:
        if not s.get("code"):
            continue
        doc = s["doc"]
        # a heading carried into its a), b) points is not on the same line
        page, quote = locate(pages[doc], s["quote"].split(" … ", 1)[-1][:70], s["hrsz"])
        if doc not in pages:
            continue
        items = out.setdefault(s["code"], [])
        same = next((e for e in items if e["kind"] == "plots" and e["text"] == s["quote"]), None)
        if same:
            if s["hrsz"] not in same["hrsz"]:
                same["hrsz"].append(s["hrsz"])
            continue
        items.append({"kind": "plots", "text": s["quote"], "hrsz": [s["hrsz"]],
                      "cite": {"reg": doc, "page": page, "para": "telkek az övezetben", "quote": quote}})
    order = {"extent": 0, "part": 1, "plots": 2}
    for v in out.values():
        v.sort(key=lambda e: order[e["kind"]])
    return reg_id, out


def run(key, show=False):
    r = borders(key)
    if r is None:
        return None
    reg_id, out = r
    p = DATA / f"zone-borders-{key}.json"
    reg_p = ROOT / "registry" / f"{key}.json"
    # written also when empty: the card then says the text describes no border for this zone
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    if reg_p.exists():
        reg = json.loads(reg_p.read_text())
        entry = (reg.get("regulations") or {}).get(reg_id)
        if entry is not None and entry.get("zoneBorders") != p.name:
            entry["zoneBorders"] = p.name
            reg_p.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n")
    if show:
        for code, items in sorted(out.items()):
            for e in items:
                extra = f" hrsz {', '.join(e['hrsz'])}" if e["kind"] == "plots" else f" [{e['bounds']}]"
                print(f"  {code:<16} {e['kind']:<6}{extra[:90]}  :: {e['text'][:140]}")
    return out


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    keys = sorted(p.stem for p in (ROOT / "registry").glob("*.json")) if "--all" in args else [a for a in args if not a.startswith("--")]
    for k in keys:
        if not (ROOT / "districts" / f"{k}.json").exists():
            continue
        out = run(k, "--list" in args)
        if out is None:
            print(f"{k}: SKIPPED, no zone table to match codes against")
        elif not out:
            print(f"{k}: NOTHING FOUND: the text names no street-bounded area or plot for any zone")
        else:
            n = {kind: sum(1 for v in out.values() for e in v if e["kind"] == kind) for kind in ("extent", "part", "plots")}
            print(f"{k}: {len(out)} zones: {n['extent']} extent, {n['part']} part, {n['plots']} plot lists")


if __name__ == "__main__":
    main()
