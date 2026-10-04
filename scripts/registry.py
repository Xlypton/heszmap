"""Per-municipality registry fragments, so municipalities can be onboarded in parallel.

public/data/regulations.json and public/data/districts.geojson are shared by every municipality;
editing them in parallel branches conflicts on every merge. Instead each municipality's entries
live in registry/<key>.json, and `build` assembles the shared files from them.

    python3 scripts/registry.py export <key>   # current shared files -> registry/<key>.json
    python3 scripts/registry.py build          # registry/*.json -> shared files (upsert, idempotent)

A fragment: {"features": [district boundary features], "regulations": {reg id: entry},
             "districts": {district id: {"status", "regulations": [...]}}}
What belongs to <key>: the district ids and regulation ids named in districts/<key>.json
("district": id or [ids], "regulations": [reg ids]; default "<key>-kesz"/"<key>-hesz").
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGS = ROOT / "public/data/regulations.json"
GEO = ROOT / "public/data/districts.geojson"
FRAG = ROOT / "registry"


def owned(key):
    cfg = json.loads((ROOT / "districts" / f"{key}.json").read_text())
    ids = cfg.get("district")
    ids = ids if isinstance(ids, list) else [ids] if ids is not None else []
    regs = cfg.get("regulations") or [r for r in (cfg.get("regulation", {}).get("reg"), f"{key}-kesz", f"{key}-hesz") if r]
    return [int(i) for i in ids], regs


def export(key):
    ids, reg_ids = owned(key)
    regs = json.loads(REGS.read_text())
    geo = json.loads(GEO.read_text())
    frag = {
        "features": [f for f in geo["features"] if f["properties"]["id"] in ids],
        "regulations": {r: regs["regulations"][r] for r in reg_ids if r in regs["regulations"]},
        "districts": {str(i): regs["districts"][str(i)] for i in ids if str(i) in regs["districts"]},
    }
    FRAG.mkdir(exist_ok=True)
    (FRAG / f"{key}.json").write_text(json.dumps(frag, ensure_ascii=False, indent=1) + "\n")
    print(f"registry/{key}.json: {len(frag['features'])} boundaries, {len(frag['regulations'])} regulations, "
          f"{len(frag['districts'])} district entries")


def build():
    regs = json.loads(REGS.read_text())
    geo = json.loads(GEO.read_text())
    for p in sorted(FRAG.glob("*.json")):
        frag = json.loads(p.read_text())
        for f in frag.get("features", []):
            geo["features"] = [g for g in geo["features"] if g["properties"]["id"] != f["properties"]["id"]] + [f]
        regs["regulations"].update(frag.get("regulations", {}))
        for i, entry in frag.get("districts", {}).items():
            # A Budapest district keeps the city-wide regulations it already lists.
            old = regs["districts"].get(i, {}).get("regulations", [])
            merged = entry["regulations"] + [r for r in old if r not in entry["regulations"]]
            regs["districts"][i] = {**regs["districts"].get(i, {}), **entry, "regulations": merged}
    geo["features"].sort(key=lambda f: f["properties"]["id"])
    REGS.write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    GEO.write_text(json.dumps(geo, ensure_ascii=False))
    print(f"built from {len(list(FRAG.glob('*.json')))} fragments: {len(geo['features'])} boundaries, "
          f"{len(regs['regulations'])} regulations")


if __name__ == "__main__":
    {"export": lambda: export(sys.argv[2]), "build": build}[sys.argv[1]]()
