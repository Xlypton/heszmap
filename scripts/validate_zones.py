"""Sanity checks on the zone limits read from the regulations (public/data/zone-types-*.json).

The citation check in the ingest scripts proves that a row is in the PDF, not that its values went into
the right fields: a table whose columns the parser misread still verifies. These checks catch the usual
symptoms (a percentage over 100, a 1 m height, two numbers read as one) and mark the value, so the card
shows it with a warning and the calculator leaves it out. Run on every build (registry.py build):

    python3 scripts/validate_zones.py                  # every zone-types file: mark values in place, report
    python3 scripts/validate_zones.py xvii xxi         # only these keys (zone-types-<key>.json)
    python3 scripts/validate_zones.py xvii --strict    # also exit 1 when any value is marked

A marked value gets "check": "<why, in Hungarian>" (its "num" is kept, the calculator skips it); a value that
passes loses any old mark.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public/data"

# Zones where buildings stand (building plots): heights, coverage and plot sizes must look like it.
BUILDING = re.compile(r"^(?:L[nkfe]?|Lke|Vt|Vi|Vk|G[kip]|Gksz|Gip|Üh|K-(?!Közl|KÖ))", re.I)
NOT_BUILDING = re.compile(r"^(?:KÖ|Kt|Zk|Zkp|ZKk|Zvp|E|V[fá]|M[áko]|K-Közl|K-T\b|K-Vke)|[-/](?:Zkk|Kk|Kp|Kt)$", re.I)

# Several numbers in one cell, not a thousands group ("10 000"): "45 75" (general / corner plot).
MERGED = re.compile(r"\d\s+\d")
THOUSANDS = re.compile(r"^\d{1,3}(?:[ .]\d{3})+\s*\**$")

PCT = ("maxCoveragePct", "minGreenPct", "maxUndergroundPct")


def problems(code: str, z: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    building = bool(BUILDING.match(code)) and not NOT_BUILDING.search(code)
    for f, p in z.items():
        if not isinstance(p, dict) or "text" not in p:
            continue
        t = p["text"].strip()
        if f != "buildingMode" and MERGED.search(t) and not THOUSANDS.match(t):
            out[f] = "A cellában több érték áll (pl. általános és saroktelek): nézd meg a táblázatban, melyik vonatkozik ide."
    num = lambda f: (z.get(f) or {}).get("num")
    for f in PCT:
        if f not in out and num(f) is not None and not 0 <= num(f) <= 100:
            out[f] = "Valószínűleg hibásan beolvasott érték (100%-nál több): ellenőrizd a táblázatban."
    for f in ("maxFar", "maxFarParking"):
        if f not in out and num(f) is not None and num(f) > 10:
            out[f] = "Valószínűleg hibásan beolvasott érték (szintterületi mutató 10 fölött): ellenőrizd a táblázatban."
    if building:
        if num("maxCoveragePct") is not None and 0 < num("maxCoveragePct") < 5 and "maxCoveragePct" not in out:
            out["maxCoveragePct"] = "Valószínűleg hibásan beolvasott érték (építési övezetben 5%-nál kisebb beépítettség): ellenőrizd a táblázatban."
        for f in ("maxHeightM",):
            if f not in out and num(f) is not None and 0 < num(f) < 3:
                out[f] = "Valószínűleg hibásan beolvasott érték (3 m-nél kisebb magasság): ellenőrizd a táblázatban."
        if "minPlotWidthM" not in out and num("minPlotWidthM") is not None and num("minPlotWidthM") > 150:
            out["minPlotWidthM"] = "Valószínűleg hibásan beolvasott érték (150 m-nél szélesebb telek): ellenőrizd a táblázatban."
        if "minPlotM2" not in out and num("minPlotM2") is not None and 0 < num("minPlotM2") < 50:
            out["minPlotM2"] = "Valószínűleg hibásan beolvasott érték (50 m²-nél kisebb telek): ellenőrizd a táblázatban."
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    keys = [a for a in argv if not a.startswith("--")]
    paths = [DATA / f"zone-types-{k}.json" for k in keys] if keys else sorted(DATA.glob("zone-types-*.json"))
    total = 0
    for path in paths:
        zones = json.loads(path.read_text())
        found = []
        for code, z in zones.items():
            bad = problems(code, z)
            for f, p in z.items():
                if not isinstance(p, dict) or "text" not in p:
                    continue
                if f in bad:
                    p["check"] = bad[f]
                    if MERGED.search(p["text"]) and not THOUSANDS.match(p["text"].strip()):
                        p["num"] = None  # what the ingest scripts' num() now gives: not one number
                    found.append(f"{code}.{f} = {p['text']!r}")
                else:
                    p.pop("check", None)
        new = json.dumps(zones, ensure_ascii=False, indent=1) + "\n"
        if new != path.read_text():
            path.write_text(new)
        if found:
            total += len(found)
            print(f"{path.name}: {len(found)} value(s) marked: {'; '.join(found[:8])}{' …' if len(found) > 8 else ''}")
    print(f"{total} value(s) marked for checking")
    return 1 if total and "--strict" in argv else 0


if __name__ == "__main__":
    sys.exit(main())
