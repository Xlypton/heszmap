"""Parcel-number search index for the app: hrsz -> a point inside the plot, per regulation.

    python3 scripts/hrsz_index.py          # every regulation with plots in regulations.json

Writes public/data/hrsz/<regulation id>.json ({"173037": [lng, lat], ...}). Rerun after the plots
of a municipality change (fetch_btp_parcels.py, oeny_parcels.py, plan_parcels.py).
"""
import glob
import json
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent


def main():
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())["regulations"]
    out_dir = ROOT / "public/data/hrsz"
    out_dir.mkdir(exist_ok=True)
    for reg_id, reg in sorted(regs.items()):
        if not reg.get("parcels"):
            continue
        index = {}
        for f in sorted(glob.glob(str(ROOT / "public/data" / reg["parcels"]["dir"] / "*.json"))):
            for ft in json.loads(Path(f).read_text())["features"]:
                h = ft["properties"].get("hrsz")
                if h and h not in index:
                    pt = shape(ft["geometry"]).buffer(0).representative_point()
                    index[h] = [round(pt.x, 6), round(pt.y, 6)]
        if index:
            (out_dir / f"{reg_id}.json").write_text(json.dumps(index, separators=(",", ":")))
        print(f"{reg_id}: {len(index)} parcel numbers")


if __name__ == "__main__":
    main()
