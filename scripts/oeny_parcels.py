"""Plot outlines with parcel numbers from the national land-registry map (OÉNY, Lechner), for any
municipality: replaces the plots plan_parcels.py traces from a scanned plan. Budapest districts on
the city GIS use fetch_btp_parcels.py instead.

    python3 scripts/oeny_parcels.py <key>             # fetch (cached), zone, write parcels-<key>/
    python3 scripts/oeny_parcels.py <key> --compare   # only report how it differs from the current plots

Run after plan_zones.py (pipeline.py does, for districts with plan.plots "oeny"), then hrsz_index.py.
- Each plot takes its zones from the zone cells in zones-<key>/ by share of its area, exactly as
  plan_parcels.py does (parcel_zones). Reviews in scripts/reviews/<key>.json apply by hrsz.
- Public spaces (obj_fels BC..: roads, squares, ditches) are flagged "street".
- builtM2: footprint of the land-registry buildings (hrsz:epulet) on the plot.
- Zone areas for the app's area selection are rebuilt along the plot lines into zone-plots-<key>/
  (regulations.json and registry/<key>.json point zoneAreas there); zones-<key>/ stays the input.
- Protected buildings in protected-<key>.geojson that were only geocoded move onto their plot.

!!! LICENCE NOT CLEARED (docs/data-sources.md, Permission register #3): the OÉNY map states no
!!! reuse licence. Peti allowed it for the proof of concept (2026-10-09). Before any public launch,
!!! get written permission from Lechner Tudásközpont (teradatszolgaltatas@lechnerkozpont.hu); until
!!! then the card credits "© Lechner Tudásközpont" on these plots. The data is not authoritative
!!! ("nem közhiteles"). Fetching is throttled in sources.py: never script OÉNY's hk-api.
"""
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import Polygon, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import sources  # noqa: E402
from plan_parcels import parcel_zones  # noqa: E402
from plan_vector_parcels import CELL, area_m2, coords  # noqa: E402
from shapely.geometry import box  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MIN_M2 = 5  # slivers of a neighbour's plot along the border of a cell
BORDER_SLOP = 0.003  # degrees, ~250 m
TOUCH = 0.000005  # ~0.4 m: neighbouring plots share a line, but not always to the last vertex
BIG_M2 = 10_000  # larger plots (fields, forest) are simplified to ~1 m instead of ~0.2 m


def municipality(key):
    """(regulations, regulation id, area the plan covers) of a district key."""
    cfg = dcfg.load(key)
    reg_id = dcfg.reg_id(cfg)
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())
    reg = regs["regulations"][reg_id]
    district_id = next(int(d) for d, v in regs["districts"].items() if reg_id in v["regulations"])
    fc = json.loads((ROOT / "public/data/districts.geojson").read_text())
    area = shape(next(f["geometry"] for f in fc["features"] if f["properties"]["id"] == district_id))
    if reg.get("plan", {}).get("area"):
        area = area.intersection(Polygon(reg["plan"]["area"][0]))
    return regs, reg_id, area


def oeny_layer(key, layer, area):
    cached = sources.CACHE / f"oeny-{layer}-{key}.geojson"
    if cached.exists():
        return json.loads(cached.read_text())["features"]
    feats = sources.oeny(layer, key, area)
    sources.write(f"oeny-{layer}", key, feats, f"Lechner Tudásközpont, OÉNY hrsz:{layer}")
    return feats


def oeny_plots(key, area):
    """The land-registry plots of the area: a plot on the border belongs to the side its inside
    point lies on, so neighbouring municipalities never share one."""
    feats = oeny_layer(key, "foldreszlet", area)
    plots = [(shape(f["geometry"]).buffer(0), f["properties"]) for f in feats]
    plots = [(g, p) for g, p in plots if not g.is_empty and area_m2(g) >= MIN_M2]
    # The settlement's KSH code: the one most plots inside the (OSM) boundary carry. Plots with that
    # code are kept up to BORDER_SLOP outside the boundary, since OSM and the registry differ a little.
    inside = Counter(p.get("ksh_kod") for g, p in plots if area.contains(g.representative_point()))
    ksh = inside.most_common(1)[0][0]
    near = area.buffer(BORDER_SLOP)
    out = [(g, p) for g, p in plots if p.get("ksh_kod") == ksh and near.contains(g.representative_point())]
    print(f"KSH {ksh}: {len(out)} plots ({sum(not area.contains(g.representative_point()) for g, _ in out)} just "
          f"outside the OSM boundary)")
    return out


def current_plots(key):
    seen, out = set(), []
    for f in glob.glob(str(ROOT / "public/data" / f"parcels-{key}" / "*.json")):
        for ft in json.loads(Path(f).read_text())["features"]:
            g = shape(ft["geometry"]).buffer(0)  # traced outlines can self-touch
            if g.wkb not in seen:
                seen.add(g.wkb)
                out.append((g, ft["properties"]))
    return out


def compare(key, new):
    """How the land-registry plots differ from the plots the app serves now."""
    old = current_plots(key)
    tree = STRtree([g for g, _ in new])
    numbered = {p.get("hrsz") for _, p in new}
    agree = same_hrsz = 0
    for g, p in old:
        best = max(((new[j][0].intersection(g).area / new[j][0].union(g).area, j) for j in tree.query(g)), default=(0, None))
        if best[0] >= 0.8:
            agree += 1
            same_hrsz += p.get("hrsz") is not None and p["hrsz"] == new[best[1]][1].get("hrsz")
    old_n = sum(p.get("hrsz") is not None for _, p in old)
    print(f"now:  {len(old)} plots, {old_n} with hrsz, source {old[0][1].get('source', 'traced') if old else '-'}")
    print(f"OÉNY: {len(new)} plots, {sum(bool(p.get('hrsz')) for _, p in new)} with hrsz")
    print(f"{agree}/{len(old)} current plots match an OÉNY plot (IoU >= 0.8); "
          f"{same_hrsz}/{old_n} numbered ones carry the same hrsz; "
          f"{sum(p.get('hrsz') in numbered for _, p in old if p.get('hrsz'))}/{old_n} of their numbers exist in OÉNY")


def chunks(feats, out_dir):
    """Grid chunks like plan_vector_parcels.chunks, but a plot is stored only in the cells it
    actually touches: farmland, forest and long roads outside town span dozens of cells by bounding box."""
    for f in out_dir.glob("*.json") if out_dir.exists() else []:
        f.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = defaultdict(list)
    for f in feats:
        g = shape(f["geometry"])
        x0, y0, x1, y1 = g.bounds
        for ix in range(int(x0 // CELL[0]), int(x1 // CELL[0]) + 1):
            for iy in range(int(y0 // CELL[1]), int(y1 // CELL[1]) + 1):
                if g.intersects(box(ix * CELL[0], iy * CELL[1], (ix + 1) * CELL[0], (iy + 1) * CELL[1])):
                    cells[f"{ix}_{iy}"].append(f)
    for k, fs in cells.items():
        (out_dir / f"{k}.json").write_text(json.dumps({"type": "FeatureCollection", "features": fs}, separators=(",", ":")))
    return len(cells), sum(f.stat().st_size for f in out_dir.glob("*.json"))


def zone_areas(feats, key):
    """Zone areas for the app's area selection, drawn along land-registry plot lines: the plots of
    one zone that touch each other, merged. The plan's street cells (zones-<key>/) are kept too; that
    directory itself stays as it is, as the input of parcel_zones on the next run."""
    groups = defaultdict(list)
    for f in feats:
        zs = f["properties"]["zones"]
        # A public-space plot joins only when most of it lies in one zone (a square, a park, a
        # private road): a long street crosses several and would bridge the blocks on both sides.
        if zs and ("street" not in f["properties"]["check"] or zs[0]["share"] >= 0.6):
            groups[zs[0]["code"]].append((shape(f["geometry"]), zs[0]["status"]))
    out = []
    for code, plots in groups.items():
        tree = STRtree([g.buffer(TOUCH) for g, _ in plots])
        merged = unary_union([g.buffer(TOUCH) for g, _ in plots])
        for part in getattr(merged, "geoms", [merged]):
            members = [plots[j][1] for j in tree.query(part) if plots[j][0].representative_point().within(part)]
            status = "plan" if members.count("plan") * 2 > len(members) else "estimated"
            g = part.buffer(-TOUCH, join_style=2).simplify(0.000002)
            for poly in getattr(g, "geoms", [g]):
                if not poly.is_empty:
                    out.append({"type": "Feature", "properties": {"code": code, "status": status, "street": False},
                                "geometry": coords(poly)})
    # Plan cells the plots leave (mostly) uncovered stay as they are: street cells, railways, a zone
    # drawn over public space.
    covered = unary_union([shape(f["geometry"]) for f in out])
    seen, kept = set(), 0
    for f in glob.glob(str(ROOT / "public/data" / f"zones-{key}" / "*.json")):
        for ft in json.loads(Path(f).read_text())["features"]:
            g = shape(ft["geometry"])
            if g.wkb in seen or g.area == 0:
                continue
            seen.add(g.wkb)
            if ft["properties"]["street"] or g.intersection(covered).area < 0.5 * g.area:
                out.append(ft)
                kept += 1
    print(f"zone areas: {len(out) - kept} from plots, {kept} plan cells the plots leave uncovered")
    return out


def plot_points(key):
    """hrsz -> a point inside the plot, for every numbered plot the app serves for <key>."""
    return {p["hrsz"]: g.representative_point().coords[0] for g, p in current_plots(key) if p.get("hrsz")}


def place_protected(key):
    """Moves the protected buildings of protected-<key>.geojson (extract_tkr.py) that were only
    geocoded onto their plot, by the hrsz the TKR lists for them."""
    path = ROOT / "public/data" / f"protected-{key}.geojson"
    if not path.exists():
        return
    fc, at, moved = json.loads(path.read_text()), plot_points(key), 0
    for f in fc["features"]:
        p = f["properties"]
        if f["geometry"]["type"] != "Point" or p.get("source") == "hrsz" or not p.get("hrsz"):
            continue
        pt = next((at[h] for h in p["hrsz"].replace(",", " ").split() if h in at), None)
        if pt:
            f["geometry"]["coordinates"] = [round(pt[0], 7), round(pt[1], 7)]
            p.update(source="hrsz", approx=False)
            moved += 1
    path.write_text(json.dumps(fc, ensure_ascii=False))
    print(f"protected buildings: {moved} moved from a geocoded address onto their plot")


def built_m2(key, area, plots):
    """Footprint of the land-registry buildings on each plot (m²), or None before
    `oeny_layer(key, "epulet", ...)` has been fetched (it is fetched here when missing)."""
    buildings = [shape(f["geometry"]).buffer(0) for f in oeny_layer(key, "epulet", area)]
    if not buildings:
        return None
    tree = STRtree(buildings)
    out = []
    for g in plots:
        parts = [buildings[j].intersection(g) for j in tree.query(g)]
        out.append(round(sum(area_m2(x) for x in parts if not x.is_empty)))
    print(f"buildings: {len(buildings)}, on {sum(a > 0 for a in out)} plots")
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    key = sys.argv[1]
    regs, reg_id, area = municipality(key)
    plots = oeny_plots(key, area)
    if "--compare" in sys.argv:
        return compare(key, plots)

    zones = parcel_zones([g for g, _ in plots], key)
    built = built_m2(key, area, [g for g, _ in plots])
    rp = ROOT / "scripts/reviews" / f"{key}.json"
    reviews = json.loads(rp.read_text()) if rp.exists() else {}
    feats = []
    for k, ((g, p), zs) in enumerate(zip(plots, zones)):
        hrsz = p.get("hrsz") or None
        street = p.get("obj_fels", "").startswith("BC")  # BC..: roads, squares, ditches (BD..: ordinary plots)
        check = ["street"] if street else []
        r = reviews.get(hrsz) if hrsz else None
        if r and not street:
            check.append("reviewed")
            if r.get("zone"):
                zs = [{"code": r["zone"], "status": "plan", "share": 1.0}]
        feats.append({"type": "Feature", "properties": {
            "hrsz": hrsz, "areaM2": round(area_m2(g)), "check": check, "zones": zs, "source": "oeny",
            **({"builtM2": built[k]} if built else {})},
            "geometry": coords(g.simplify(0.000002 if area_m2(g) < BIG_M2 else 0.00001))})
    n_cells, size = chunks(feats, ROOT / "public/data" / f"parcels-{key}")
    print(f"{len(feats)} plots ({sum(bool(f['properties']['hrsz']) for f in feats)} with hrsz, "
          f"{sum('street' in f['properties']['check'] for f in feats)} public spaces, "
          f"{sum(bool(f['properties']['zones']) for f in feats)} in a zone), {n_cells} cells, {size / 1e6:.1f} MB")
    if regs["regulations"][reg_id].get("parcels", {}).get("dir") != f"parcels-{key}":
        print(f"note: regulations.json has no parcels entry for {reg_id}; add it in registry/{key}.json")

    place_protected(key)
    areas = zone_areas(feats, key)
    n_cells, size = chunks(areas, ROOT / "public/data" / f"zone-plots-{key}")
    print(f"zone areas: {n_cells} cells, {size / 1e6:.1f} MB")
    # The app selects zone areas from zone-plots-<key>/; shared files are assembled from registry/.
    entry = {"dir": f"zone-plots-{key}", "cell": list(CELL)}
    regs["regulations"][reg_id]["zoneAreas"] = entry
    (ROOT / "public/data/regulations.json").write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    frag_path = ROOT / "registry" / f"{key}.json"
    if frag_path.exists():
        frag = json.loads(frag_path.read_text())
        if reg_id in frag.get("regulations", {}):
            frag["regulations"][reg_id]["zoneAreas"] = entry
            frag_path.write_text(json.dumps(frag, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
