"""Plan tiles as one PMTiles archive per municipality, split into fixed-size chunk files.

Loose {z}/{x}/{y} tiles cost one static file each (a Worker deployment takes 20,000), which capped
the plans at zoom 17. One archive per municipality holds any zoom in a few files. Workers static
assets ignore HTTP Range requests, so the archive is cut into CHUNK-byte pieces
(public/pmtiles/<key>/<n>.bin) and the app reads byte ranges from those pieces (src/pmtiles.ts).

    python3 scripts/pack_tiles.py <key> [--maxzoom 18]
    python3 scripts/pack_tiles.py <key> --from-tiles     pack the loose tiles already in public/tiles/<key>/

Renders the tiles from the cached sheets (scripts/.cache/<key>/, plan_sheets.py) with the saved fit
(scripts/plans/<key>.json), packs them, removes public/tiles/<key>/ and points regulations.json at
the archive.
"""
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_georef as pg  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
CHUNK = 1 << 20  # 1 MiB: a screenful of tiles is a few chunks (the archive is in Hilbert order)


def main():
    key = sys.argv[1]
    opt = lambda k, default: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else default
    cfg = dcfg.load(key)
    plan_cfg = cfg["plan"]
    reg_id = dcfg.reg_id(cfg)
    regs_path = ROOT / "public/data/regulations.json"
    regs = json.loads(regs_path.read_text())
    plan = regs["regulations"][reg_id]["plan"]
    minzoom, maxzoom = plan_cfg["minzoom"], int(opt("--maxzoom", plan_cfg["maxzoom"]))

    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    local = pg.Local(*fit["local"])
    image_plan = plan_cfg.get("kind") == "image"
    sheets, frames = [], []
    for i, path in enumerate([] if "--from-tiles" in sys.argv else dcfg.sheet_paths(cfg)):
        f = fit["sheets"][i]
        if f.get("skipped"):
            continue
        im = Image.open(path).convert("RGBA")
        if image_plan:
            im = pg.blank_sheet(plan_cfg, i, im)
            frames.append(pg.sheet_frame(plan_cfg, i, im))
        sheets.append((im, pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])))
    if plan.get("area"):  # a regulation covering part of its district (plan_georef.py "clip")
        rings = [np.array(r) for r in plan["area"]]
    else:
        districts = json.loads((ROOT / "public/data/districts.geojson").read_text())
        geom = next(f["geometry"] for f in districts["features"] if f["properties"]["id"] == cfg["district"])
        rings = [np.array(p[0]) for p in (geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]])]

    with tempfile.TemporaryDirectory() as tmp:
        if "--from-tiles" in sys.argv:
            src = ROOT / "public/tiles" / key
            bounds, maxzoom = plan["bounds"], plan["maxzoom"]
        else:
            src = Path(tmp)
            bounds = pg.render_tiles(sheets, local, rings, src, minzoom, maxzoom, frames or None,
                                     first_wins=plan_cfg.get("overlap") == "first-wins", minify=image_plan)
        tiles = sorted((zxy_to_tileid(int(p.parts[-3]), int(p.parts[-2]), int(p.stem)), p)
                       for p in src.glob("*/*/*.webp"))
        buf = io.BytesIO()
        w = Writer(buf)
        for tid, p in tiles:
            w.write_tile(tid, p.read_bytes())
        w.finalize({
            "tile_type": TileType.WEBP, "tile_compression": Compression.NONE,
            "min_zoom": minzoom, "max_zoom": maxzoom,
            "min_lon_e7": int(bounds[0] * 1e7), "min_lat_e7": int(bounds[1] * 1e7),
            "max_lon_e7": int(bounds[2] * 1e7), "max_lat_e7": int(bounds[3] * 1e7),
            "center_zoom": minzoom, "center_lon_e7": int((bounds[0] + bounds[2]) / 2 * 1e7),
            "center_lat_e7": int((bounds[1] + bounds[3]) / 2 * 1e7),
        }, {"name": key, "attribution": "Szabályozási tervek: önkormányzati rendeletek mellékletei"})
    data = buf.getvalue()

    out = ROOT / "public/pmtiles" / key
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for n, at in enumerate(range(0, len(data), CHUNK)):
        (out / f"{n}.bin").write_bytes(data[at:at + CHUNK])
    shutil.rmtree(ROOT / "public/tiles" / key, ignore_errors=True)

    regs = json.loads(regs_path.read_text())  # re-read: another run may have changed it
    plan = regs["regulations"][reg_id]["plan"]
    plan.pop("tiles", None)
    plan.update({"pmtiles": f"pmtiles/{key}", "size": len(data), "chunk": CHUNK,
                 "bounds": bounds, "minzoom": minzoom, "maxzoom": maxzoom})
    regs_path.write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(tiles)} tiles, zoom {minzoom}-{maxzoom}, {len(data) / 1e6:.1f} MB in {-(-len(data) // CHUNK)} chunks")


if __name__ == "__main__":
    main()
