"""Review plots on the plan itself: batches of plan crops for a reviewer (a person, or Claude reading
the images), and the answers kept in scripts/reviews/<key>.json, which plan_vector_parcels.py applies.

    python3 scripts/review_zones.py batches <key> [--sample N] [--crop-m M] [--out DIR]
        every plot flagged "zone-unclear", plus N random plots whose zone was found automatically
        (the sample measures how often the automatic zones are right). Writes DIR/batch-NN.png
        (6 numbered crops each: the plot outlined in orange on the plan) and DIR/batch-NN.json
        (crop number -> plot, the codes near it).
    python3 scripts/review_zones.py apply <key> answers.json
        answers: {"<hrsz>": {"zone": "<code>" | null, "outline": "ok" | "wrong" | "unsure"}, ...}
    python3 scripts/review_zones.py report <key>
        reviewed plots, and how many sampled automatic zones the review confirmed.

Then re-run `plan_vector_parcels.py <key> --zones-only` to publish the reviewed zones.
"""
import json
import random
import sys
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_georef as pg  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
CROP_M = 110      # each crop shows this many metres across, centred on the plot
CROP_PX = 520
PER_BATCH = 6     # 3 x 2 crops per image


def reviews_path(key):
    return ROOT / "scripts/reviews" / f"{key}.json"


def load_reviews(key):
    p = reviews_path(key)
    return json.loads(p.read_text()) if p.exists() else {}


def plots(key):
    import glob
    out = {}
    for f in glob.glob(str(ROOT / "public/data" / f"parcels-{key}" / "*.json")):
        for ft in json.loads(Path(f).read_text())["features"]:
            out[ft["properties"]["hrsz"]] = ft
    return out


class Sheets:
    """The cached sheet images with their fits: lng/lat -> sheet pixel."""

    def __init__(self, key):
        self.cfg = dcfg.load(key)
        fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
        self.local = pg.Local(*fit["local"])
        self.sheets = []
        for i, path in enumerate(dcfg.sheet_paths(self.cfg)):
            f = fit["sheets"][i] if i < len(fit["sheets"]) else {}
            if f.get("skipped") or f.get("coef") is None:
                continue
            with Image.open(path) as im:
                size = im.size
            model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
            frame = self.cfg["plan"].get("frames", [None] * (i + 1))[i] or [0, 0, *size]
            self.sheets.append((path, model.inverse(size), frame, size))
        self._open = {}

    def px(self, inv, lng, lat):
        return inv(np.column_stack(self.local.to_m(np.atleast_1d(lng), np.atleast_1d(lat))))

    def crop(self, geom):
        """The plan around a plot, from the sheet that shows it most centrally, with the plot outlined."""
        c = geom.representative_point()
        best = None
        for path, inv, frame, size in self.sheets:
            x, y = self.px(inv, c.x, c.y)[0]
            margin = min(x - frame[0], frame[2] - x, y - frame[1], frame[3] - y)
            if margin > 0 and (best is None or margin > best[0]):
                best = (margin, path, inv, x, y)
        if best is None:
            return None
        _, path, inv, x, y = best
        if path not in self._open:
            self._open.clear()
            self._open[path] = Image.open(path).convert("RGB")
        im = self._open[path]
        # pixels per metre on this sheet, measured around the plot
        a = self.px(inv, *self.local.to_ll(*(np.array(self.local.to_m(c.x, c.y)) + [CROP_M / 2, 0])))[0]
        half = max(40, abs(a[0] - x) + abs(a[1] - y))
        box = (int(x - half), int(y - half), int(x + half), int(y + half))
        out = im.crop(box).resize((CROP_PX, CROP_PX), Image.LANCZOS)
        k = CROP_PX / (2 * half)
        d = ImageDraw.Draw(out, "RGBA")
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for p in polys:
            ring = np.array(p.exterior.coords)
            pts = (self.px(inv, ring[:, 0], ring[:, 1]) - [box[0], box[1]]) * k
            d.polygon([tuple(q) for q in pts], fill=(255, 140, 0, 40))
            d.line([tuple(q) for q in pts] + [tuple(pts[0])], fill=(255, 110, 0, 255), width=4)
        return out


def batches(key, sample, out_dir):
    ps = plots(key)
    reviewed = load_reviews(key)
    unclear = [h for h, f in ps.items() if "zone-unclear" in f["properties"]["check"] and h not in reviewed]
    auto = [h for h, f in ps.items() if f["properties"]["zones"] and "street" not in f["properties"]["check"]
            and "zone-unclear" not in f["properties"]["check"] and h not in reviewed]
    random.seed(1)
    picked = [(h, "unclear") for h in sorted(unclear)] + [(h, "sample") for h in random.sample(auto, min(sample, len(auto)))]
    reg_id = dcfg.reg_id(dcfg.load(key))
    reg = json.loads((ROOT / "public/data/regulations.json").read_text())["regulations"][reg_id]
    labels = [(f["properties"]["code"], Point(f["geometry"]["coordinates"]))
              for f in json.loads((ROOT / "public/data" / reg["zoneLabels"]).read_text())["features"]
              if f["properties"].get("reg", reg_id) == reg_id]
    ltree = STRtree([p for _, p in labels])
    sheets = Sheets(key)
    out_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=40)
    items, n = [], 0
    for h, why in picked:
        g = shape(ps[h]["geometry"])
        im = sheets.crop(g)
        if im is None:
            continue
        c = g.representative_point()
        near = sorted({labels[j][0] for j in ltree.query(c.buffer(150 / 111_000))},
                      key=lambda code: min(labels[j][1].distance(c) for j in range(len(labels)) if labels[j][0] == code))
        items.append((im, {"hrsz": h, "why": why, "auto_zone": (ps[h]["properties"]["zones"] or [{}])[0].get("code"),
                           "codes_nearby": near[:8]}))
    for b in range(0, len(items), PER_BATCH):
        chunk = items[b:b + PER_BATCH]
        sheet = Image.new("RGB", (CROP_PX * 3, CROP_PX * 2), "white")
        meta = {}
        for k, (im, info) in enumerate(chunk, 1):
            x, y = (k - 1) % 3 * CROP_PX, (k - 1) // 3 * CROP_PX
            sheet.paste(im, (x, y))
            d = ImageDraw.Draw(sheet)
            d.rectangle((x, y, x + 56, y + 52), fill="black")
            d.text((x + 14, y + 4), str(k), fill="white", font=font)
            d.rectangle((x, y, x + CROP_PX - 1, y + CROP_PX - 1), outline="black", width=2)
            meta[str(k)] = info
        n += 1
        sheet.save(out_dir / f"batch-{n:02d}.png")
        (out_dir / f"batch-{n:02d}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"{len(items)} plots ({len(unclear)} unclear, {len(items) - len(unclear)} sampled) in {n} batches in {out_dir}")


def apply(key, answers_path):
    reviews = load_reviews(key)
    answers = json.loads(Path(answers_path).read_text())
    ps = plots(key)
    for h, a in answers.items():
        props = ps.get(h, {}).get("properties", {})
        auto = (props.get("zones") or [{}])[0].get("code")
        reviews[h] = {"zone": a.get("zone"), "outline": a.get("outline", "unsure"), "auto_zone": auto,
                      "why": "unclear" if "zone-unclear" in props.get("check", []) else "sample", "date": date.today().isoformat(), "by": a.get("by", "claude")}
    p = reviews_path(key)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(dict(sorted(reviews.items())), ensure_ascii=False, indent=1) + "\n")
    print(f"{len(answers)} answers, {len(reviews)} reviewed plots in {p.relative_to(ROOT)}")


def report(key):
    r = load_reviews(key)
    sampled = [v for v in r.values() if v.get("why") == "sample" and v.get("zone")]
    agree = sum(v["zone"] == v["auto_zone"] for v in sampled)
    bad_outline = sum(v.get("outline") == "wrong" for v in r.values())
    print(f"{len(r)} reviewed; zone given for {sum(bool(v.get('zone')) for v in r.values())}; "
          f"automatic zone confirmed {agree}/{len(sampled)}; outline wrong: {bad_outline}")


if __name__ == "__main__":
    cmd, key = sys.argv[1], sys.argv[2]
    opt = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    if cmd == "batches":
        CROP_M = float(opt("--crop-m", CROP_M))
        batches(key, int(opt("--sample", 30)), Path(opt("--out", ROOT / "scripts/.cache" / key / "review")))
    elif cmd == "apply":
        apply(key, sys.argv[3])
    elif cmd == "report":
        report(key)
