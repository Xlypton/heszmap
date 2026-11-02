"""Zone types for plans whose zone code *is* the limits table (Győr, GYÉSZ 4. melléklet).

Some older regulations print no limits table: every zone's code spells its limits out, position by
position, and an annex says what each position means. Győr (GYÉSZ, 1/2006.):

    building zone      Ln06/Z/35/50 – 095/125/03 – 14/45/007
                       role, FAR (0.1), building mode, max coverage %, min green %
                       – min height (0.1 m), max height (0.1 m), max storeys
                       – min plot width (m), min plot depth (m), min plot area (100 m²)
    non-building zone  Vízm00/S/05/90 – 036 – 1500
                       role, FAR (0.1), building mode, max coverage (0.1 %), min green %
                       – max height (0.1 m) – min buildable plot area (100 m²)

An empty position is not regulated; a letter (K, G, F) means a rule of the text sets it.

This script collects every code printed on the plan (the sheets' text layer, scripts/plans/<key>-ocr-N.json,
read by the same zone_labels() the georeference step uses), decodes it, and writes
public/data/zone-types-<key>.json with each value cited to the annex that defines the position.
Role names come from the regulation's own lists, found in the regulation PDF.

    python3 scripts/coded_zone_types.py <key> [--placed]   (--placed after georef: only codes placed on the map)

Config, districts/<key>.json "coded": {
    "pattern": regex a code must match (whole label),
    "roles": {role: [name, quote in the regulation PDF]},
    "modes": {letter: [name, quote]},
    "letters": {letter: [meaning, quote]},
    "building": quote for the building-zone layout, "nonBuilding": quote for the non-building layout,
    "annex": "4. melléklet", "notes": [[text, quote], ...]   notes shown on every zone,
    "bare": {   short codes with no limits spelled out (Győr city centre "Vt-T", "Lk/U-T"; squares "KTb")
        "t": [text, quote, para],          what a "-T" ending means (parameters set by the fitting-in rules)
        "roles": {role: [text, quote, para]}  roles also printed bare (roads, squares): the § that rules them
    }
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

B = re.compile(r"^(?P<role>.+?)(?P<far>\d\d|K|G)?/(?P<mode>[A-Z]*)/(?P<cov>\d+|[KGF])?/(?P<green>\d+|[KGF])?"
               r"-(?P<minh>\d+|[KG])?/(?P<maxh>\d+|[KG])?/(?P<lev>\d+|K)?"
               r"-(?P<w>\d+|K)?/(?P<d>\d+|K)?/(?P<a>\d+|K)?$")
N = re.compile(r"^(?P<role>.+?)(?P<far>\d\d|K|G)?/(?P<mode>[A-Z]*)/(?P<cov>\d+|[KGF])?/(?P<green>\d+|[KGF])?"
               r"-(?P<h>\d+|[KG])?-(?P<a>\d+|[KF])?$")


def squash(s):
    return re.sub(r"\s+", "", s)


def decode_bare(code, roles, modes, tnote, rnotes, cb=None):
    """A short code: role [FAR] [/mode] [-T] ("Vt-T", "Kegy18-T", "Vt/KE-T"), or a road or square role
    printed alone ("KTb", "KÖs"). With "-T" the parameters follow the fitting-in rules (tnote)."""
    body, t = (code[:-2], True) if code.endswith("-T") else (code, False)
    body, _, mode = body.partition("/")
    m = re.match(r"^(.+?)(\d\d)?$", body)
    role = m and m[1]
    if role not in roles or (mode and mode not in modes) or not (t or role in rnotes) or (not t and (mode or m[2])):
        return None
    name, rcite = roles[role]
    z = {"name": f"{name} ({code})", "category": name, "cite": rcite}
    if m[2]:
        v = round(int(m[2]) * 0.1, 2)
        z["maxFar"] = {"text": f"{v:g}".replace(".", ","), "num": v, "cite": {**cb, "para": f"{cb['para']} – {code}"} if cb else tnote["cite"]}
    if mode:
        z["buildingMode"] = {"text": mode + f" ({modes[mode][0]})", "num": None, "cite": modes[mode][1]}
    z["notes"] = [tnote] if t else []
    if role in rnotes:
        z["notes"].append(rnotes[role])
    return z


def main(key):
    cfg = dcfg.load(key)
    conf = cfg["coded"]
    reg = cfg["regulation"]["reg"]
    pdf = pymupdf.open(ROOT / "public" / "docs" / f"{reg}.pdf")
    pages = [squash(p.get_text()) for p in pdf]

    def cite(quote, para):
        q = squash(quote)
        page = next((i + 1 for i, t in enumerate(pages) if q in t), None)
        if not page:
            sys.exit(f"quote not found in {reg}.pdf: {quote!r}")
        return {"reg": reg, "page": page, "para": para, "quote": quote}

    annex = conf.get("annex", "4. melléklet")
    cb = cite(conf["building"], f"{annex} – építési övezetek jele")
    cn = cite(conf["nonBuilding"], f"{annex} – beépítésre nem szánt övezetek jele")
    roles = {r: (n, cite(q, "szerepkörök")) for r, (n, q) in conf["roles"].items()}
    modes = {m: (n, cite(q, "beépítési mód")) for m, (n, q) in conf["modes"].items()}
    letters = {l: (n, cite(q, "betű az övezeti jelben")) for l, (n, q) in conf["letters"].items()}
    notes = [{"text": t, "cite": cite(q, annex)} for t, q in conf.get("notes", [])]

    pat = re.compile(conf["pattern"])
    seen = {}
    for f in sorted((ROOT / "scripts/plans").glob(f"{key}-ocr-*.json"), key=lambda p: int(p.stem.rsplit("-", 1)[1])):
        for l in json.loads(f.read_text())["labels"]:
            t = l["text"].strip().replace("–", "-").replace(" ", "")
            if pat.match(t):
                seen[t] = seen.get(t, 0) + 1

    # --placed: only the codes the georeferenced zone labels hold (a code printed only outside the
    # municipality, on a sheet's overlap with its neighbour, is no zone of it)
    placed = set()
    if "--placed" in sys.argv:
        placed = {f["properties"]["code"] for f in json.loads((ROOT / "public/data" / f"zone-labels-{key}.geojson").read_text())["features"]}
        seen = {c: n for c, n in seen.items() if c in placed}
    out, bad = {}, []
    bare = conf.get("bare")
    if bare:
        tnote = {"text": bare["t"][0], "cite": cite(bare["t"][1], bare["t"][2])}
        rnotes = {r: {"text": t, "cite": cite(q, para)} for r, (t, q, para) in bare.get("roles", {}).items()}
        for f in sorted((ROOT / "scripts/plans").glob(f"{key}-ocr-*.json")):
            for l in json.loads(f.read_text())["labels"]:
                t = l["text"].strip().replace("–", "-").replace(" ", "")
                if t not in seen and decode_bare(t, roles, modes, tnote, rnotes):
                    seen[t] = 1
        if "--placed" in sys.argv:
            seen = {c: n for c, n in seen.items() if c in placed}
    for code in sorted(seen):
        if bare:
            z = decode_bare(code, roles, modes, tnote, rnotes, cb)
            if z:
                out[code] = z
                continue
        m = B.match(code)
        building = bool(m)
        m = m or N.match(code)
        role = m and next((r for r in sorted(roles, key=len, reverse=True) if m["role"] == r), None)
        if not m or not role:
            bad.append(code)
            continue
        name, rcite = roles[role]
        c = cb if building else cn
        para = c["para"]
        z = {"name": f"{name} ({code})", "category": name, "cite": rcite, "code_parts": "building" if building else "non-building"}
        notes_z = list(notes)

        def put(field, raw, scale=1.0, unit=""):
            if raw is None or raw == "":
                return
            if raw in letters:
                meaning, lc = letters[raw]
                z[field] = {"text": raw, "num": None, "cite": c}
                notes_z.append({"text": f"{raw}: {meaning}", "cite": lc})
                return
            v = int(raw) * scale
            v = round(v, 2)
            z[field] = {"text": f"{v:g}".replace(".", ",") + unit, "num": v, "cite": {**c, "para": f"{para} – {code}"}}

        put("maxFar", m["far"], 0.1)
        if m["mode"]:
            mode = modes.get(m["mode"])
            z["buildingMode"] = {"text": m["mode"] + (f" ({mode[0]})" if mode else ""), "num": None, "cite": mode[1] if mode else c}
        put("maxCoveragePct", m["cov"], 1.0 if building else 0.1)
        put("minGreenPct", m["green"])
        if building:
            put("minHeightM", m["minh"], 0.1)
            put("maxHeightM", m["maxh"], 0.1)
            if m["lev"]:
                notes_z.append({"text": f"Megengedett legnagyobb szintszám: {int(m['lev']) if m['lev'].isdigit() else m['lev']}", "cite": {**c, "para": f"{para} – {code}"}})
            put("minPlotWidthM", m["w"])
            if m["d"]:
                notes_z.append({"text": f"Telek megengedett legkisebb mélysége: {m['d']} m", "cite": {**c, "para": f"{para} – {code}"}})
            put("minPlotM2", m["a"], 100)
        else:
            put("maxHeightM", m["h"], 0.1)
            put("minBuildablePlotM2", m["a"], 100)
        for k in ("maxHeightM", "minHeightM"):
            if k in z:
                z[k]["label"] = "építménymagasság" if k == "maxHeightM" else "legkisebb építménymagasság"
        if notes_z:
            z["notes"] = notes_z
        del z["code_parts"]
        out[code] = z

    dest = ROOT / "public/data" / f"zone-types-{key}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    regs_path = ROOT / "public/data/regulations.json"
    regs = json.loads(regs_path.read_text())
    regs["regulations"][reg]["zoneTypes"] = dest.name
    regs_path.write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(out)} zone codes decoded, {len(bad)} labels not decoded" + (f": {bad[:30]}" if bad else ""))


if __name__ == "__main__":
    main(sys.argv[1])
