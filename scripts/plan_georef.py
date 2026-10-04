"""Georeference scanned zoning-plan sheets, then cut map tiles and geolocate the zone labels.

1. Coarse: street names on a plan sit on their street. For every OCR'd street label we know which OSM
   street it belongs to, so we fit an affine pixel->metres transform by ICP with known correspondences.
2. Fine: at every OSM road intersection, search for the local shift that centres both crossing roads
   in the plan's yellow street bands, and fit a cubic polynomial (absorbs scan distortion) to those.
   References come from the basemap's own vector tiles, so the plan lines up with what users see.

Usage:
  python3 scripts/plan_georef.py xx sheet0.jpg:ocr0.json [sheet1.jpg:ocr1.json ...]
Writes public/tiles/<key>/, public/data/zone-labels-<key>.geojson and updates public/data/regulations.json.
"""
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree

import osm_ref

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scripts" / ".cache"
UA = "heszmap/0.1 (https://github.com/xlypton/heszmap)"

CONFIG = {
    "xx": {"reg": "xx-kesz", "district": 20, "district_query": "XX. kerület, Budapest", "minzoom": 13, "maxzoom": 18},
}

SUFFIXES = r"(utca|út|útja|tér|tere|köz|sor|fasor|körút|sétány|dűlő)"
STREET_RE = re.compile(rf"^(?P<name>[A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüű.\- ]*?)\s*(?P<suffix>{SUFFIXES})\b", re.U)
OCR_FIXES = [(r"ut[sc]a\b", "utca"), (r"utoa\b", "utca"), (r"\bUt\b", "út")]


# --- geometry helpers -------------------------------------------------------------------------

class Local:
    """Equirectangular metres around a reference point: accurate to well under a metre over a district."""

    def __init__(self, lng0: float, lat0: float):
        self.lng0, self.lat0 = lng0, lat0
        self.kx = 111_320 * math.cos(math.radians(lat0))
        self.ky = 110_540

    def to_m(self, lng, lat):
        return (np.asarray(lng) - self.lng0) * self.kx, (np.asarray(lat) - self.lat0) * self.ky

    def to_ll(self, x, y):
        return np.asarray(x) / self.kx + self.lng0, np.asarray(y) / self.ky + self.lat0


def nearest_on_polyline(p, segs):
    """segs: (n, 4) array of x1, y1, x2, y2. Returns the closest point on any segment and its distance."""
    a, b = segs[:, :2], segs[:, 2:]
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
    q = a + ab * t[:, None]
    d = np.hypot(*(q - p).T)
    i = int(d.argmin())
    return q[i], float(d[i])


def point_in_ring(p, ring) -> bool:
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, np.roll(ring, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def solve_affine(px, m):
    """Least-squares affine with m ≈ [px, 1] @ A, A is 3x2."""
    X = np.hstack([px, np.ones((len(px), 1))])
    A, *_ = np.linalg.lstsq(X, m, rcond=None)
    return A


# --- OSM street geometry via Nominatim (cached) -----------------------------------------------

def nominatim(params: dict) -> list:
    CACHE.mkdir(exist_ok=True)
    key = CACHE / ("nom_" + re.sub(r"\W+", "_", json.dumps(params, sort_keys=True, ensure_ascii=False))[:180] + ".json")
    if key.exists():
        return json.loads(key.read_text())
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({**params, "format": "json"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(30 * (attempt + 1))  # usage policy: back off when rate-limited
    key.write_text(json.dumps(data))
    time.sleep(1.5)
    return data


def street_segments(name: str, district_query: str, local: Local, bbox):
    hits = nominatim({"q": f"{name}, {district_query}", "polygon_geojson": 1, "limit": 10})
    segs = []
    for h in hits:
        if h.get("class") != "highway" or h["geojson"]["type"] not in ("LineString", "MultiLineString"):
            continue
        lines = h["geojson"]["coordinates"]
        for line in lines if h["geojson"]["type"] == "MultiLineString" else [lines]:
            pts = np.array(line)
            if not ((bbox[0] <= pts[:, 0]).all() and (pts[:, 0] <= bbox[2]).all() and (bbox[1] <= pts[:, 1]).all() and (pts[:, 1] <= bbox[3]).all()):
                continue
            x, y = local.to_m(pts[:, 0], pts[:, 1])
            xy = np.column_stack([x, y])
            segs.extend(np.hstack([xy[:-1], xy[1:]]))
    return np.array(segs) if segs else None


# --- OCR label parsing -------------------------------------------------------------------------

def centre(box):
    b = np.array(box, dtype=float)
    return b.mean(0)


def street_labels(ocr):
    out = []
    for l in ocr["labels"]:
        text = re.sub(r"\(.*?\)|\d", "", l["text"]).strip()
        for pat, rep in OCR_FIXES:
            text = re.sub(pat, rep, text)
        text = re.sub(rf"(\w){SUFFIXES}\b", r"\1 \2", text)  # "Csokonaiutca" -> "Csokonai utca"
        m = STREET_RE.match(text)
        if m and len(m["name"]) >= 3 and l["conf"] > 0.8:
            out.append((f"{m['name'].strip()} {m['suffix']}", centre(l["box"])))
    return out


def norm_code(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("‐", "-").replace("–", "-").upper()
    return s.translate(str.maketrans({"0": "O", "1": "I", "L": "I", "|": "I", " ": None, "5": "S"}))


def zone_labels(ocr, codes):
    by_norm = {}
    for c in codes:
        by_norm.setdefault(norm_code(c), set()).add(c)
    lookup = {k: next(iter(v)) for k, v in by_norm.items() if len(v) == 1}
    out = []
    for l in ocr["labels"]:
        tokens = l["text"].split()
        box = np.array(l["box"], dtype=float)
        start, total = 0, max(len(l["text"]), 1)
        for tok in tokens:
            pos = l["text"].find(tok, start)
            start = pos + len(tok)
            code = lookup.get(norm_code(tok))
            if code:
                # Split the text box proportionally to find this token's centre.
                f = (pos + len(tok) / 2) / total
                top = box[0] + (box[1] - box[0]) * f
                bottom = box[3] + (box[2] - box[3]) * f
                out.append((code, (top + bottom) / 2, l["conf"]))
    return out


# --- fitting -----------------------------------------------------------------------------------

def fit_sheet(labels, streets, init=None):
    named = [(n, p) for n, p in labels if streets.get(n) is not None]
    px = np.array([p for _, p in named])
    if len(px) < 6:
        raise SystemExit(f"only {len(px)} street labels matched OSM streets; cannot georeference")

    if init is None:
        # Start from street centroids: coarse, but correspondences are by name so ICP still converges.
        cs = {}
        for n, p in named:
            cs.setdefault(n, []).append(p)
        P = np.array([np.mean(v, 0) for v in cs.values()])
        M = np.array([streets[n][:, :2].mean(0) for n in cs])
        A = solve_affine(P, M)
    else:
        A = init

    keep = np.ones(len(px), bool)
    for it in range(40):
        m_pred = np.hstack([px, np.ones((len(px), 1))]) @ A
        targets, dists = [], []
        for (n, _), mp in zip(named, m_pred):
            q, d = nearest_on_polyline(mp, streets[n])
            targets.append(q)
            dists.append(d)
        dists = np.array(dists)
        cutoff = max(3 * np.median(dists[keep]), 8.0) if it > 3 else np.inf
        keep = dists < cutoff
        A_new = solve_affine(px[keep], np.array(targets)[keep])
        if np.abs(A_new - A).max() < 1e-6:
            break
        A = A_new
    res = dists[keep]
    scale = math.sqrt(abs(np.linalg.det(A[:2])))
    print(f"  fit: {keep.sum()}/{len(px)} street labels used, residual median {np.median(res):.1f} m, "
          f"90% {np.percentile(res, 90):.1f} m, scale {scale:.3f} m/px")
    return A, float(np.median(res))


# --- refinement against building outlines -----------------------------------------------------

class PolyModel:
    """Pixel -> local metres as a 2D polynomial (order 1 = affine). A scanned sheet is not perfectly
    affine (paper/scan distortion), so a low-order polynomial absorbs the bend."""

    def __init__(self, order, coef, centre, scale):
        self.order, self.coef, self.centre, self.scale = order, coef, centre, scale

    @staticmethod
    def terms(uv, order):
        u, v = uv[:, 0], uv[:, 1]
        cols = [u ** (i - j) * v ** j for i in range(order + 1) for j in range(i + 1)]
        return np.column_stack(cols)

    @classmethod
    def fit(cls, px, m, order, centre=None, scale=None):
        centre = px.mean(0) if centre is None else centre
        scale = px.std() if scale is None else scale
        coef, *_ = np.linalg.lstsq(cls.terms((px - centre) / scale, order), m, rcond=None)
        return cls(order, coef, centre, scale)

    @classmethod
    def from_affine(cls, A, centre, scale):
        # m = [px, 1] @ A, re-expressed in normalised coordinates.
        lin = A[:2] * scale
        const = A[2] + centre @ A[:2]
        return cls(1, np.vstack([const, lin]), centre, scale)

    def __call__(self, px):
        return self.terms((np.atleast_2d(px) - self.centre) / self.scale, self.order) @ self.coef

    def inverse(self, size):
        """Metres -> pixel, fitted on a dense grid over the sheet (order + 1 to keep it exact)."""
        g = np.stack(np.meshgrid(np.linspace(0, size[0], 60), np.linspace(0, size[1], 60)), -1).reshape(-1, 2)
        m = self(g)
        inv = PolyModel.fit(m, g, self.order + 2)
        err = np.abs(inv(m) - g).max()
        assert err < 0.5, f"inverse model error {err:.2f} px"
        return inv

    def to_json(self):
        return {"order": self.order, "coef": self.coef.tolist(), "centre": self.centre.tolist(), "scale": float(self.scale)}


def street_band_distance(im: Image.Image, step: int):
    """Distance (in reduced pixels) from each pixel to the edge of the plan's yellow street bands:
    largest along a band's centre line."""
    rgb = np.asarray(im.convert("RGB").reduce(step), dtype=np.int16)
    yellow = (rgb[..., 0] > 235) & (rgb[..., 1] > 225) & (rgb[..., 2] < 200) & (rgb[..., 2] > 100)
    yellow = ndimage.binary_closing(yellow, iterations=2)  # bridge text and lines printed on streets
    return ndimage.distance_transform_edt(yellow).astype(np.float32)


def road_intersections(roads, local):
    """Densified OSM road points (1 m), and one point per crossing of two differently oriented roads."""
    P, L, D = [], [], []
    for i, ln in enumerate(roads):
        x, y = local.to_m(ln[:, 0], ln[:, 1])
        for k in range(len(x) - 1):
            dx, dy = x[k + 1] - x[k], y[k + 1] - y[k]
            n = max(int(np.hypot(dx, dy)), 1)
            t = np.arange(n) / n
            P.append(np.column_stack([x[k] + dx * t, y[k] + dy * t]))
            L.append(np.full(n, i))
            D.append(np.full(n, np.arctan2(dy, dx) % np.pi))
    P, L, D = np.vstack(P), np.concatenate(L), np.concatenate(D)
    tree = cKDTree(P)
    pairs = tree.query_pairs(1.5, output_type="ndarray")
    ang = np.abs(D[pairs[:, 0]] - D[pairs[:, 1]])
    ang = np.minimum(ang, np.pi - ang)
    X = P[pairs[(L[pairs[:, 0]] != L[pairs[:, 1]]) & (ang > np.radians(50)), 0]]
    cells = {}
    for p in X:
        cells.setdefault((int(p[0] // 8), int(p[1] // 8)), p)
    return P, tree, np.array(list(cells.values()))


def match_intersections(model, size, dt, step, P, tree, X, rad=20, arm=30):
    """For each OSM intersection, find the local shift that best centres both crossing roads in the
    plan's street bands. Returns rows of (metres x, y, plan px x, y, shift px). Ambiguous matches
    (flat or multi-peaked score) are skipped."""
    H, W = dt.shape
    inv = model.inverse(size)
    offs = np.arange(-rad, rad + 1)
    out = []
    for c in X:
        cp = inv(c[None])[0] / step
        if not (2 * rad < cp[0] < W - 2 * rad and 2 * rad < cp[1] < H - 2 * rad):
            continue
        qi = np.round(inv(P[tree.query_ball_point(c, arm)]) / step).astype(int)
        sc = np.empty((len(offs), len(offs)))
        for a, oy in enumerate(offs):
            ys = np.clip(qi[:, 1] + oy, 0, H - 1)
            for b, ox in enumerate(offs):
                sc[a, b] = dt[ys, np.clip(qi[:, 0] + ox, 0, W - 1)].mean()
        a, b = np.unravel_index(sc.argmax(), sc.shape)
        if a in (0, 2 * rad) or b in (0, 2 * rad) or sc[a, b] < 3 or sc[a, b] < 2 * np.median(sc):
            continue
        others = np.ones_like(sc, bool)
        others[max(a - 4, 0):a + 5, max(b - 4, 0):b + 5] = False
        if sc[others].max() > 0.85 * sc[a, b]:
            continue
        out.append((c[0], c[1], (cp[0] + offs[b]) * step, (cp[1] + offs[a]) * step, np.hypot(offs[a], offs[b]) * step))
    return np.array(out)


def refine(model, im, roads_index, step=2, final_order=3):
    """Street intersections pin both axes (a single long street only pins one), so fit the plan to
    OSM intersections, raising the polynomial order as matches improve."""
    P, tree, X = roads_index
    dt = street_band_distance(im, step)
    m_per_px = math.sqrt(abs(np.linalg.det(np.array([[model.coef[1, 0], model.coef[1, 1]], [model.coef[2, 0], model.coef[2, 1]]])))) / model.scale
    for order in range(1, final_order + 1):
        M = match_intersections(model, im.size, dt, step, P, tree, X)
        print(f"  order {order}: {len(M)} intersections, offset median {np.median(M[:, 4]) * m_per_px:.2f} m, "
              f"90% {np.percentile(M[:, 4], 90) * m_per_px:.2f} m")
        px, m = M[:, 2:4], M[:, 0:2]
        keep = np.ones(len(M), bool)
        for _ in range(5):
            model = PolyModel.fit(px[keep], m[keep], order, model.centre, model.scale)
            r = np.hypot(*(model(px) - m).T)
            keep = r < max(3 * np.median(r[keep]), 1.0)
    M = match_intersections(model, im.size, dt, step, P, tree, X)
    print(f"  after: {len(M)} intersections, offset median {np.median(M[:, 4]) * m_per_px:.2f} m, "
          f"90% {np.percentile(M[:, 4], 90) * m_per_px:.2f} m")
    return model


# --- tiles ------------------------------------------------------------------------------------

def lnglat_to_tile_px(lng, lat, z):
    n = 256 * 2 ** z
    x = (lng + 180) / 360 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def tile_px_to_lnglat(x, y, z):
    n = 256 * 2 ** z
    lng = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lng, lat


def render_tiles(sheets, local, district_rings, out_dir: Path, minzoom, maxzoom):
    """sheets: list of (PIL image, PolyModel). Each output tile maps back to sheet pixels with an affine
    built from three tile corners: exact to a fraction of a pixel within one tile."""
    lngs = np.concatenate([r[:, 0] for r in district_rings])
    lats = np.concatenate([r[:, 1] for r in district_rings])
    bounds = [float(lngs.min()), float(lats.min()), float(lngs.max()), float(lats.max())]
    inv = [(im, model.inverse(im.size)) for im, model in sheets]
    count = 0
    for z in range(minzoom, maxzoom + 1):
        x0, y0 = lnglat_to_tile_px(bounds[0], bounds[3], z)
        x1, y1 = lnglat_to_tile_px(bounds[2], bounds[1], z)
        for tx in range(int(x0 // 256), int(x1 // 256) + 1):
            for ty in range(int(y0 // 256), int(y1 // 256) + 1):
                corners = [(tx * 256, ty * 256), ((tx + 1) * 256, ty * 256), (tx * 256, (ty + 1) * 256)]
                ll = [tile_px_to_lnglat(cx, cy, z) for cx, cy in corners]
                mx, my = local.to_m([c[0] for c in ll], [c[1] for c in ll])
                mask = Image.new("L", (256, 256), 0)
                draw = ImageDraw.Draw(mask)
                for ring in district_rings:
                    pts = [lnglat_to_tile_px(lng, lat, z) for lng, lat in ring]
                    draw.polygon([(px - tx * 256, py - ty * 256) for px, py in pts], fill=255)
                if not mask.getbbox():
                    continue
                tile = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
                for im, to_px in inv:
                    (u0, v0), (u1, v1), (u2, v2) = to_px(np.column_stack([mx, my]))
                    coeffs = ((u1 - u0) / 256, (u2 - u0) / 256, u0, (v1 - v0) / 256, (v2 - v0) / 256, v0)
                    part = im.transform((256, 256), Image.AFFINE, coeffs, resample=Image.BILINEAR, fillcolor=(0, 0, 0, 0))
                    tile.alpha_composite(part)
                tile.putalpha(Image.composite(tile.getchannel("A"), Image.new("L", (256, 256), 0), mask))
                if not tile.getchannel("A").getbbox():
                    continue
                path = out_dir / str(z) / str(tx) / f"{ty}.webp"
                path.parent.mkdir(parents=True, exist_ok=True)
                tile.save(path, "WEBP", quality=72, method=4)
                count += 1
        print(f"  zoom {z}: {count} tiles so far")
    return bounds


def main():
    key, pairs = sys.argv[1], sys.argv[2:]
    cfg = CONFIG[key]
    regs_path = ROOT / "public" / "data" / "regulations.json"
    regs = json.loads(regs_path.read_text())
    reg = regs["regulations"][cfg["reg"]]
    codes = json.loads((ROOT / "public" / "data" / reg["zoneTypes"]).read_text()).keys()

    districts = json.loads((ROOT / "public" / "data" / "districts.geojson").read_text())
    geom = next(f["geometry"] for f in districts["features"] if f["properties"]["id"] == cfg["district"])
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    rings = [np.array(p[0]) for p in polys]
    allpts = np.vstack(rings)
    bbox = [allpts[:, 0].min() - 0.01, allpts[:, 1].min() - 0.01, allpts[:, 0].max() + 0.01, allpts[:, 1].max() + 0.01]
    local = Local(float(allpts[:, 0].mean()), float(allpts[:, 1].mean()))

    _, roads = osm_ref.fetch(bbox)
    roads_index = road_intersections(roads, local)
    print(f"reference: {len(roads)} OSM road segments, {len(roads_index[2])} intersections")

    sheets, features, fits = [], [], []
    for pair in pairs:
        img_path, ocr_path = pair.split(":")
        ocr = json.loads(Path(ocr_path).read_text())
        labels = street_labels(ocr)
        names = sorted({n for n, _ in labels})
        print(f"{img_path}: {len(labels)} street labels, {len(names)} distinct streets")
        streets = {n: street_segments(n, cfg["district_query"], local, bbox) for n in names}
        print(f"  {sum(v is not None for v in streets.values())} streets found in OSM")
        A, _ = fit_sheet(labels, streets)
        im = Image.open(img_path).convert("RGBA")
        model = refine(PolyModel.from_affine(A, np.array(im.size) / 2, im.size[0] / 3), im, roads_index)
        sheets.append((im, model))
        fits.append({"sheet": Path(img_path).name, **model.to_json()})

        for code, p, conf in zone_labels(ocr, codes):
            mx, my = model(np.array(p))[0]
            lng, lat = local.to_ll(mx, my)
            features.append({"type": "Feature", "properties": {"code": code, "reg": cfg["reg"], "conf": conf},
                             "geometry": {"type": "Point", "coordinates": [round(float(lng), 7), round(float(lat), 7)]}})

    # Keep only labels inside the district (the sheets also show neighbouring areas and the legend).
    inside = [f for f in features if any(point_in_ring(f["geometry"]["coordinates"], r) for r in rings)]
    out_labels = ROOT / "public" / "data" / f"zone-labels-{key}.geojson"
    out_labels.write_text(json.dumps({"type": "FeatureCollection", "features": inside}, ensure_ascii=False))
    print(f"{len(inside)} zone labels inside the district ({len(features) - len(inside)} outside dropped)")

    tiles_dir = ROOT / "public" / "tiles" / key
    bounds = render_tiles(sheets, local, rings, tiles_dir, cfg["minzoom"], cfg["maxzoom"])

    (ROOT / "scripts" / "plans").mkdir(exist_ok=True)
    (ROOT / "scripts" / "plans" / f"{key}.json").write_text(json.dumps(
        {"local": [local.lng0, local.lat0], "sheets": fits}, indent=1) + "\n")

    reg["zoneLabels"] = out_labels.name
    reg["plan"] = {"tiles": f"tiles/{key}/{{z}}/{{x}}/{{y}}.webp", "bounds": bounds,
                   "minzoom": cfg["minzoom"], "maxzoom": cfg["maxzoom"]}
    regs_path.write_text(json.dumps(regs, ensure_ascii=False, indent=2) + "\n")
    print("updated regulations.json")


if __name__ == "__main__":
    main()
