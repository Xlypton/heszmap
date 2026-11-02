"""Re-cut a municipality's plot and zone-area chunks on plan.chunk_cell, without re-running
plan_vector_parcels.py (which also honours plan.chunk_cell). Workers deploy at most 20,000 static
files, and the default 0.004° x 0.003° grid gives a whole city thousands of chunks.

    python3 scripts/rechunk.py <key>     then: registry.py export <key>, registry.py build
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_vector_parcels as pvp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(key):
    cfg = dcfg.load(key)
    cell = tuple(cfg["plan"]["chunk_cell"])
    pvp.CELL = cell
    regs_path = ROOT / "public/data/regulations.json"
    regs = json.loads(regs_path.read_text())
    reg = regs["regulations"][dcfg.reg_id(cfg)]
    for field in ("parcels", "zoneAreas"):
        d = ROOT / "public/data" / reg[field]["dir"]
        seen, feats = set(), []
        for f in sorted(d.glob("*.json")):
            for ft in json.loads(f.read_text())["features"]:
                k = json.dumps(ft, sort_keys=True, separators=(",", ":"))
                if k not in seen:
                    seen.add(k)
                    feats.append(ft)
        n, size = pvp.chunks(feats, d)
        reg[field]["cell"] = list(cell)
        print(f"{d.name}: {len(feats)} features in {n} chunks, {size / 1e6:.1f} MB")
    regs_path.write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
