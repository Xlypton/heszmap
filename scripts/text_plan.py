"""A regulation with no plan map, whose text alone says which plots are in which zone.

Budapest IX. 34/2003 (Merényi Gusztáv Kórház): njt publishes the decree text only, no plan annex,
but the text names the whole area as one plot (hrsz 38239) and puts it in one zone (K–EÜ/IX/1).
Such a plan is shown without plan tiles: its plots come from the city's plot layer
(fetch_btp_parcels.py), each takes the zone the text gives it, and the plan's area is those plots.

    python3 scripts/text_plan.py <key>

Config, districts/<key>.json:
  "plan": {"kind": "text", "plots": "btp", "zone_colour": false,
           "text_plots": [{"hrsz": "38239", "code": "K–EÜ/IX/1", "quote": "<the sentence naming the plot>"}],
           "note": "why the plan has no map"}
Each quote must be in the regulation's own PDF text (checked here), so every zone is cited.
Writes the zone labels (one per plot, at its inner point), the plan area and bounds in
regulations.json, then the plot and zone chunks (plan_vector_parcels.write, no zone lines).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from shapely import force_2d
from shapely.geometry import shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_fit  # noqa: E402
import plan_vector_parcels as pvp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    key = sys.argv[1]
    cfg = dcfg.load(key)
    plan = cfg["plan"]
    reg_id = dcfg.reg_id(cfg)
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg = regs["regulations"][reg_id]
    text = re.sub(r"\s+", "", subprocess.run(["pdftotext", str(ROOT / "public" / reg["pdf"]), "-"],
                                             capture_output=True, text=True, check=True).stdout)
    by_meb = {}
    for f in plan_fit.btp_plots(cfg)["features"]:
        by_meb.setdefault((f["properties"].get("meb") or "").strip(), []).append(force_2d(shape(f["geometry"])))
    plots, labels = [], []
    for tp in plan["text_plots"]:
        if re.sub(r"\s+", "", tp["quote"]) not in text:
            raise SystemExit(f"{tp['hrsz']}: quote not in the regulation text: {tp['quote']!r}")
        if tp["code"] not in json.loads((ROOT / "public/data" / reg["zoneTypes"]).read_text()):
            raise SystemExit(f"{tp['hrsz']}: zone {tp['code']} not in the zone table")
        found = by_meb.get(tp["hrsz"], [])
        if len(found) != 1:
            raise SystemExit(f"{tp['hrsz']}: {len(found)} plots with this number in the city's plot layer")
        g = found[0]
        plots.append((g, tp["hrsz"], False, round(pvp.area_m2(g))))
        p = g.representative_point()
        labels.append({"type": "Feature", "properties": {"code": tp["code"], "reg": reg_id, "conf": 1.0, "text": True},
                       "geometry": {"type": "Point", "coordinates": [round(p.x, 7), round(p.y, 7)]}})
        print(f"{tp['hrsz']}: {tp['code']}, {plots[-1][3]} m²")
    out = ROOT / "public/data" / f"zone-labels-{key}.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": labels}, ensure_ascii=False))
    reg["zoneLabels"] = out.name
    area = unary_union([p[0] for p in plots]).buffer(0)
    rings = [list(g.exterior.coords) for g in getattr(area, "geoms", [area])]
    x0, y0, x1, y1 = area.bounds
    # No tiles: the app draws no plan raster for a plan without "pmtiles"/"tiles".
    reg["plan"] = {"bounds": [round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)],
                   "minzoom": plan["minzoom"], "maxzoom": plan["maxzoom"], "textOnly": True,
                   "area": [[[round(x, 6), round(y, 6)] for x, y in r] for r in rings]}
    pvp.write(key, reg_id, reg, plots, [[] for _ in plots], lines=None)
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
