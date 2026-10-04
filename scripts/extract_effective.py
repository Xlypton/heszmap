"""Build the effective-limits data for a district from the reviewed table in
scripts/rules/<key>_effective.py: resolve each paragraph to its verified citation and build the
geometry the app needs to evaluate location conditions (street lines, block polygons).

Usage: python3 scripts/extract_effective.py xx
Writes public/data/effective-<key>.json.
"""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "rules"))
import osm_ref  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def block_polygon(ring, roads):
    """The area enclosed by the bounding streets. Named street lines can stop a few metres short of an
    intersection, so buffer them slightly, take the enclosed hole, and grow it back."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    missing = [n for n in ring if n not in roads]
    if missing:
        sys.exit(f"streets not found: {missing}")
    for buf in (0.0001, 0.0002, 0.0003):  # ~8, 15, 23 m
        union = unary_union([LineString(l.tolist()).buffer(buf) for n in ring for l in roads[n] if len(l) > 1])
        polys = union.geoms if union.geom_type == "MultiPolygon" else [union]
        holes = [Polygon(h) for p in polys for h in p.interiors]
        if holes:
            # All faces the named streets enclose together (a street crossing the area splits it).
            block = unary_union([h.buffer(buf) for h in holes])
            block = max(block.geoms, key=lambda g: g.area) if block.geom_type == "MultiPolygon" else block
            return [[round(x, 7), round(y, 7)] for x, y in block.exterior.coords]
    sys.exit(f"{ring}: the streets do not enclose an area")


def street_lines(name, roads):
    if name not in roads:
        sys.exit(f"street not found: {name}")
    return [[[round(float(x), 7), round(float(y), 7)] for x, y in line] for line in roads[name]]


def main():
    key = sys.argv[1]
    eff = importlib.import_module(f"{key}_effective")
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg = regs["regulations"][f"{key}-kesz"]
    rules = {r["id"]: r for r in json.loads((ROOT / "public/data" / reg["rules"]).read_text())}
    zone_types = json.loads((ROOT / "public/data" / reg["zoneTypes"]).read_text())
    roads = osm_ref.named_roads([19.05, 47.40, 19.18, 47.47])

    def cite_of(para, zones):
        if para == "table":
            return zone_types[zones[0]]["buildingMode"]["cite"]
        if para not in rules:
            sys.exit(f"paragraph not found among the extracted provisions: {para}")
        return rules[para]["cite"]

    streets, blocks, overrides = {}, {}, []
    for o in eff.OVERRIDES:
        unknown = [z for z in o["zones"] if z not in zone_types]
        if unknown:
            sys.exit(f"unknown zones in {o['para']}: {unknown}")
        cond = o.get("condition")
        if cond and cond["type"] in ("along", "not-along", "parallel", "not-parallel"):
            streets.setdefault(cond["street"], street_lines(cond["street"], roads))
        if cond and cond["type"] == "block":
            bid = " – ".join(cond["ring"])
            blocks.setdefault(bid, block_polygon(cond["ring"], roads))
            cond = {"type": "block", "block": bid}
        overrides.append({**{k: v for k, v in o.items() if k not in ("para", "condition")},
                          "condition": cond, "cite": cite_of(o["para"], o["zones"])})

    meaning = [{**m, "cite": rules[m["para"]]["cite"]} for m in eff.HEIGHT_MEANING]
    out = {"heightMeaning": meaning, "overrides": overrides, "streets": streets, "blocks": blocks}
    path = ROOT / "public/data" / f"effective-{key}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    reg["effective"] = path.name
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(overrides)} overrides, {len(streets)} streets, {len(blocks)} blocks")


if __name__ == "__main__":
    main()
