"""The plan's zone boundary lines, read from its own map tiles, for any plan.

Every published plan is a tile archive (public/pmtiles/<key>/, pack_tiles.py), whatever the source
looked like (vector PDF, scan, JPG annex). This reads every strongly coloured line on it, by hue
(red, orange, purple, ...) and style:

- dotted or dashed: small blobs of one size in evenly spaced, mostly straight chains (the dot size
  and spacing are learned from the plan; lettering, hatching and lone symbols do not chain);
- solid: long thin strokes.

Which kinds are the zone boundaries is set per plan from its legend (plan.boundary_lines, see
boundary_kinds()); the default is the red dotted övezethatár of Hungarian KÉSZ/HÉSZ plans. Running
the script prints every kind it found with its length, to pick from when onboarding a plan.

The kept lines are cached as scripts/plans/<key>-dotlines.geojson; plan_vector_parcels.py uses them
as walls (widened by REACH_M) and zone_line_check.py measures the zones against them.

    python3 scripts/plan_dotlines.py <key>      (re)read, cache, and list the line kinds
    python3 scripts/plan_dotlines.py <key> --preview <png> [--at=lat,lng]
                                                a picture of every kind found, to pick them from
"""
import io
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
WINDOW = 12        # tiles per side read at once (+1 tile margin each side)
MIN_CHAIN = 6      # dots in a line
MIN_KIND_LINKS = 15  # a kind of dot (size) counts as a line style when it makes this many links
MAX_GAP_CV = 0.35   # a line's dot spacing varies at most this much (std / mean)
MIN_STRAIGHT = 0.6  # ... and this share of its dots sit on a straight run
MAX_DASH_PX = 40   # a dash of a dashed line is at most this long
LINK = 2.6         # dots this many gaps apart are one line (a corner, one dot hidden under lettering)
EXTEND_GAPS = 2.5  # a loose end of a line is carried on this many dot gaps
REACH_M = 1.5      # wall half-width: plan vs land-registry plots sit ~1-3 m apart
# red: R strong, G and B well below it and about equal (orange and brown have G above B; salmon
# and pink fills have G, B above ~0.55 R)
SAT_MIN, VAL_MIN = 110, 70   # a strongly coloured pixel (OpenCV HSV, 0..255)
HUE_NAMES = ["red", "orange", "yellow", "lime", "green", "teal", "cyan", "azure", "blue", "violet", "purple", "magenta"]
STROKE_PX = 4        # a stroke is thin: area <= this x its length
MIN_STROKE_PX = 60   # ... and a solid line piece at least this long



class Archive:
    def __init__(self, key):
        from pmtiles.reader import MemorySource, Reader
        parts = sorted((ROOT / "public/pmtiles" / key).glob("*.bin"), key=lambda p: int(p.stem))
        if not parts:
            raise SystemExit(f"{key}: no tiles in public/pmtiles/{key}")
        self.reader = Reader(MemorySource(b"".join(p.read_bytes() for p in parts)))
        self.z = self.reader.header()["max_zoom"]

    def tiles(self):
        """(x, y) of every tile at the top zoom."""
        from pmtiles.reader import all_tiles
        return [(x, y) for (z, x, y), _ in all_tiles(self.reader.get_bytes) if z == self.z]

    def image(self, x0, y0, n):
        from PIL import Image
        out = np.full((n * 256, n * 256, 3), 255, np.uint8)
        hit = False
        for tx in range(x0, x0 + n):
            for ty in range(y0, y0 + n):
                b = self.reader.get(self.z, tx, ty)
                if b:
                    im = Image.open(io.BytesIO(b)).convert("RGBA")
                    a = np.asarray(im)
                    rgb = np.where(a[..., 3:] > 0, a[..., :3], 255)
                    out[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = rgb
                    hit = True
        return out if hit else None

    def to_ll(self, px, py):
        s = 256 * 2 ** self.z
        lng = px / s * 360 - 180
        lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * py / s))))
        return lng, lat

    def m_per_px(self, lat):
        return 40_075_016.7 * math.cos(math.radians(lat)) / (256 * 2 ** self.z)


SAT = SAT_MIN


def hue_bins(img):
    """Hue class (0..11, 30° each, 0 = red, 10 = purple) of the strongly coloured pixels, -1 elsewhere
    (white, greys, black, pale fills)."""
    import cv2
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    h, sat, val = hsv[..., 0].astype(np.int16), hsv[..., 1], hsv[..., 2]
    b = ((h + 7) // 15) % 12
    b[(sat < SAT) | (val < VAL_MIN)] = -1
    return b


def blobs(arc):
    """Every small coloured blob (a dot or a dash) and every long thin coloured stroke, by hue.
    Returns (blobs: array of (px x, px y, area px, hue), strokes: {hue: [polyline px]})."""
    import cv2
    have = set(arc.tiles())
    if not have:
        return np.zeros((0, 4)), {}
    xs, ys = [t[0] for t in have], [t[1] for t in have]
    out, strokes = [], {}
    for wx in range(min(xs), max(xs) + 1, WINDOW):
        for wy in range(min(ys), max(ys) + 1, WINDOW):
            if not any((x, y) in have for x in range(wx, wx + WINDOW) for y in range(wy, wy + WINDOW)):
                continue
            img = arc.image(wx - 1, wy - 1, WINDOW + 2)
            if img is None:
                continue
            hb = hue_bins(img)
            ox, oy = (wx - 1) * 256, (wy - 1) * 256
            for hue in np.unique(hb):
                if hue < 0:
                    continue
                # a thin dark line drawn over a dot (a plot line crossing it) closed up
                m = cv2.morphologyEx((hb == hue).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
                n, lab, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
                for i in range(1, n):
                    x, y, w, h, a = stats[i]
                    cx, cy = cent[i]
                    # own the blob only in the window's core (the margin is the neighbour's core)
                    if not (256 <= cx < 256 * (WINDOW + 1) and 256 <= cy < 256 * (WINDOW + 1)):
                        continue
                    if a < 3:
                        continue
                    thin = a <= STROKE_PX * math.hypot(w, h)
                    if a <= 900 and (max(w, h) <= 1.7 * min(w, h) and a >= 0.45 * w * h or max(w, h) <= MAX_DASH_PX and thin):
                        out.append((cx + ox, cy + oy, a, hue))  # a dot, or a dash
                    elif thin and max(w, h) >= MIN_STROKE_PX:
                        # a long thin stroke: its outline, simplified, stands for the line
                        piece = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
                        cs, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        for c in cs:
                            c = cv2.approxPolyDP(c, 1.5, True).reshape(-1, 2).astype(float)
                            if len(c) >= 2:
                                strokes.setdefault(int(hue), []).append(c + [x + ox, y + oy])
    return np.array(out, float).reshape(-1, 4), strokes


def chain(pts, area, size):
    """The dotted lines drawn with dots (or dashes) of about this size: (links, gap px)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    idx = np.flatnonzero(np.abs(np.log(area / size)) < 0.5)
    if len(idx) < MIN_CHAIN:
        return [], 0
    sub = pts[idx]
    tree = cKDTree(sub)
    nn = tree.query(sub, k=2)[0][:, 1]
    gap = Counter(np.round(nn * 2) / 2).most_common(1)[0][0]  # the most common spacing
    if gap <= 0:
        return [], 0
    ok = (nn <= LINK * gap) & (nn >= 0.5 * gap)
    sub, idx = sub[ok], idx[ok]
    if len(sub) < MIN_CHAIN:
        return [], gap
    pairs = np.array(sorted(cKDTree(sub).query_pairs(LINK * gap)), int).reshape(-1, 2)
    if not len(pairs):
        return [], gap
    # Each dot links to its two nearest dots at most: a line, not a mesh.
    dist = np.hypot(*(sub[pairs[:, 0]] - sub[pairs[:, 1]]).T)
    deg = np.zeros(len(sub), int)
    keep = []
    for k in np.argsort(dist):
        a, b = pairs[k]
        if deg[a] < 2 and deg[b] < 2:
            keep.append((a, b))
            deg[a] += 1
            deg[b] += 1
    pairs = np.array(keep, int).reshape(-1, 2)
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(sub), len(sub)))
    _, comp = connected_components(g, directed=False)
    big = {c for c, k in Counter(comp).items() if k >= MIN_CHAIN}
    # A line, not lettering or hatching cut into bits: evenly spaced dots (link lengths vary
    # little) that mostly run on straight (most dots have their two links nearly opposite).
    nbr = [[] for _ in range(len(sub))]
    for a, b in pairs:
        nbr[a].append(b)
        nbr[b].append(a)
    lens, turns = {}, {}
    for a, b in pairs:
        lens.setdefault(comp[a], []).append(np.hypot(*(sub[a] - sub[b])))
    for a in range(len(sub)):
        if len(nbr[a]) == 2 and comp[a] in big:
            u, v = sub[nbr[a][0]] - sub[a], sub[nbr[a][1]] - sub[a]
            cos = u @ v / (np.hypot(*u) * np.hypot(*v) + 1e-9)
            turns.setdefault(comp[a], []).append(cos < -0.85)  # within ~30° of straight
    good = {c for c in big if np.std(lens[c]) < MAX_GAP_CV * np.mean(lens[c])
            and np.mean(turns.get(c, [False])) >= MIN_STRAIGHT}
    return [(idx[a], idx[b]) for a, b in pairs if comp[a] in good], gap


def dot_kinds(pts, area):
    """The dotted (and dashed) line kinds among blobs of one hue: every blob size common on the
    plan is tried. Returns [(size, gap px, links as point pairs)] for sizes that make long even
    chains."""
    if len(pts) < MIN_CHAIN:
        return []
    bins = Counter(np.round(np.log(area) * 4))
    found = []
    for b, n in bins.most_common(12):
        if n < 3 * MIN_CHAIN:
            break
        size = math.exp(b / 4)
        links, gap = chain(pts, area, size)
        if len(links) >= MIN_KIND_LINKS:
            found.append((size, gap, [(pts[a], pts[b]) for a, b in links]))
    best = max((len(f[2]) for f in found), default=0)
    return [f for f in found if len(f[2]) >= 0.1 * best]  # not specks that happen to line up


def boundary_kinds(key):
    """Which line kinds are this plan's zone boundaries: districts/<key>.json plan.boundary_lines,
    a list of kind names or their start ("red dots", "purple solid", "orange dots 12px"), chosen
    from the plan's legend; by default the red dotted line of Hungarian KÉSZ/HÉSZ plans."""
    cfg = json.loads((ROOT / "districts" / f"{key}.json").read_text())
    return cfg.get("plan", {}).get("boundary_lines") or ["red dots"]


def read(key, debug=None):
    """Read every dotted, dashed and solid coloured line kind on the plan, keep the ones the plan
    uses as zone boundaries (boundary_kinds), cache them; print every kind found, so the right ones
    can be picked for a new plan."""
    global SAT
    if json.loads((ROOT / "districts" / f"{key}.json").read_text()).get("plan", {}).get("boundary_source") == "pdf":
        # a vector PDF plan: the exact lines from the PDF itself (plan_pdf_lines.py)
        import plan_pdf_lines
        return plan_pdf_lines.read(key)
    arc = Archive(key)
    # plan.line_saturation: a plan whose lines are pale at the tile zoom (thin anti-aliased dashes,
    # XII) is read with a lower saturation bar
    SAT = json.loads((ROOT / "districts" / f"{key}.json").read_text()).get("plan", {}).get("line_saturation", SAT_MIN)
    b, strokes = blobs(arc)
    to_ll = lambda p: [round(float(v), 7) for v in arc.to_ll(np.array(p[0]), np.array(p[1]))]
    kinds = []  # (name, hue, size, gap px, [segment px pairs])
    for hue in sorted(set(b[:, 3].astype(int))) if len(b) else []:
        sel = b[:, 3] == hue
        for size, gap, segs in dot_kinds(b[sel, :2], b[sel, 2]):
            kinds.append((f"{HUE_NAMES[hue]} dots {size:.0f}px", hue, size, gap, segs))
    for hue, polys in strokes.items():
        segs = [(c[k], c[(k + 1) % len(c)]) for c in polys for k in range(len(c))]
        if len(segs) >= MIN_KIND_LINKS:
            kinds.append((f"{HUE_NAMES[hue]} solid", hue, 0, 0, segs))
    want = boundary_kinds(key)
    lat0 = 47.5
    kept, report = [], []
    for name, hue, size, gap, segs in kinds:
        ll = [(to_ll(p), to_ll(q)) for p, q in segs]
        lat0 = ll[0][0][1]
        keep = any(name.startswith(w) for w in want)
        mpp = arc.m_per_px(lat0)
        report.append({"kind": name, "segments": len(segs), "length_m": round(sum(math.hypot(*(np.array(p) - np.array(q))) for p, q in segs) * mpp),
                       "gap_m": round(float(gap * mpp), 2), "kept": keep})
        if keep:
            kept.append((gap * mpp, ll))
    feats = [s_ for _, ll in kept for s_ in ll]
    gaps = [g for g, _ in kept if g]
    lat0 = float(np.mean([f[0][1] for f in feats])) if feats else lat0
    info = {"zoom": arc.z, "kinds": [r["kind"] for r in report if r["kept"]], "gap_m": round(float(np.median(gaps)), 2) if gaps else 5.0,
            "segments": len(feats), "length_m": sum(r["length_m"] for r in report if r["kept"]), "wanted": want, "all_kinds": report}
    if os.environ.get("KINDS_OUT", "1") != "0":  # every kind with its segments, for preview() (not committed)
        (ROOT / "scripts/plans" / f"{key}-kinds.json").write_text(json.dumps(
            [dict(r, segments=[(to_ll(p), to_ll(q)) for p, q in k[4]]) for r, k in zip(report, kinds)], separators=(",", ":")))
    out = ROOT / "scripts/plans" / f"{key}-dotlines.geojson"
    out.write_text(json.dumps({"type": "Feature", "properties": info,
                               "geometry": {"type": "MultiLineString", "coordinates": feats}}, separators=(",", ":")))
    print(f"{key}: zone boundary lines {info['kinds']} {info['length_m']} m")
    for r in sorted(report, key=lambda r: -r["length_m"])[:40]:
        print(f"    {'KEEP' if r['kept'] else '    '} {r['kind']:22s} {r['length_m']:7d} m" + (f"  dots every {r['gap_m']} m" if r['gap_m'] else ""))
    return info


def load(key, reach_m=REACH_M):
    """The cached lines, loose ends carried on, as wall polygons (lng/lat), merged; [] when there are none."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    p = ROOT / "scripts/plans" / f"{key}-dotlines.geojson"
    if not p.exists():
        read(key)
    f = json.loads(p.read_text())
    if not f["geometry"]["coordinates"]:
        return []
    from shapely import affinity
    from shapely.geometry import LineString, MultiLineString
    segs = f["geometry"]["coordinates"]
    lat = float(np.mean([s[0][1] for s in segs]))
    k = math.cos(math.radians(lat))
    # A dotted line seldom runs right up to the street edge or the line it meets: its last dot stops
    # up to a gap short, and a leak there joins the two zones. Each loose end is carried on in its
    # own direction by EXTEND_GAPS dot gaps (what it overshoots into a street does not matter).
    ends = Counter()
    for a, b in segs:
        ends[tuple(a)] += 1
        ends[tuple(b)] += 1
    ext = EXTEND_GAPS * (f["properties"].get("gap_m") or 5) / 111_000
    more = []
    for a, b in segs:
        for p, q in ((a, b), (b, a)):
            if ends[tuple(p)] == 1:
                v = np.array([(p[0] - q[0]) * k, p[1] - q[1]])
                n = np.hypot(*v)
                if n > 0:
                    v = v / n * ext
                    more.append([p, [p[0] + v[0] / k, p[1] + v[1]]])
    g = MultiLineString(segs + more)
    # metres -> degrees, widened in longitude for the latitude
    walls = affinity.scale(affinity.scale(g, k, 1, origin=(0, 0)).buffer(reach_m / 111_000, 4), 1 / k, 1, origin=(0, 0))
    walls = unary_union(walls)
    return list(getattr(walls, "geoms", [walls]))


def loose_ends(key, back=3):
    """The free ends of the lines: [(lng, lat, ux, uy)], u the unit direction the line runs out in
    (x in metres east, y north), taken over the last `back` dots."""
    p = ROOT / "scripts/plans" / f"{key}-dotlines.geojson"
    if not p.exists():
        return []
    segs = json.loads(p.read_text())["geometry"]["coordinates"]
    if not segs:
        return []
    adj = {}
    for a, b in segs:
        adj.setdefault(tuple(a), []).append(tuple(b))
        adj.setdefault(tuple(b), []).append(tuple(a))
    k = math.cos(math.radians(segs[0][0][1]))
    out = []
    for e, nb in adj.items():
        if len(nb) != 1:
            continue
        prev, cur = e, nb[0]
        for _ in range(back - 1):
            nxt = [q for q in adj[cur] if q != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
        v = np.array([(e[0] - cur[0]) * k, e[1] - cur[1]])
        n = np.hypot(*v)
        if n > 0:
            out.append((e[0], e[1], v[0] / n, v[1] / n))
    return out


def lines(key):
    """The cached lines (shapely MultiLineString, lng/lat) or None."""
    from shapely.geometry import shape
    p = ROOT / "scripts/plans" / f"{key}-dotlines.geojson"
    if not p.exists():
        return None
    f = json.loads(p.read_text())
    return shape(f["geometry"]) if f["geometry"]["coordinates"] else None





def preview(key, out, at=None, n=4):
    """A picture to pick a plan's boundary line kinds from: n x n top-zoom tiles around `at`
    (lng, lat; default: where the most kinds meet), the plan dimmed, every kind found drawn on it
    in its own colour with a numbered legend. Rerun read() first."""
    from PIL import Image, ImageDraw
    arc = Archive(key)
    f = json.loads((ROOT / "scripts/plans" / f"{key}-kinds.json").read_text())
    s = 256 * 2 ** arc.z
    px = lambda lng, lat: ((lng + 180) / 360 * s,
                           (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * s)
    kinds = sorted(f, key=lambda k: -k["length_m"])[:10]
    if at is None:  # the tile where the most kinds have segments
        count = Counter()
        for i, k in enumerate(kinds):
            for t in {tuple(int(v // 256) for v in px(*k["segments"][j][0])) for j in range(0, len(k["segments"]), 3)}:
                count[t] += 1
        (tx, ty), _ = count.most_common(1)[0]
    else:
        x, y = px(*at)
        tx, ty = int(x // 256), int(y // 256)
    x0, y0 = tx - n // 2, ty - n // 2
    img = arc.image(x0, y0, n)
    im = Image.fromarray((img * 0.55 + 255 * 0.45).astype(np.uint8))
    d = ImageDraw.Draw(im)
    pal = [(230, 0, 0), (0, 160, 0), (0, 0, 230), (230, 130, 0), (160, 0, 200), (0, 170, 170), (120, 70, 0), (230, 0, 160), (90, 90, 90), (0, 0, 0)]
    for i, k in enumerate(kinds):
        for a, b in k["segments"]:
            pa, pb = px(*a), px(*b)
            if x0 * 256 <= pa[0] < (x0 + n) * 256 and y0 * 256 <= pa[1] < (y0 + n) * 256:
                d.line([(pa[0] - x0 * 256, pa[1] - y0 * 256), (pb[0] - x0 * 256, pb[1] - y0 * 256)], fill=pal[i], width=3)
    leg = Image.new("RGB", (im.width, 22 * len(kinds) + 8), "white")
    dl = ImageDraw.Draw(leg)
    for i, k in enumerate(kinds):
        dl.rectangle((8, 8 + 22 * i, 28, 22 + 22 * i), fill=pal[i])
        dl.text((36, 8 + 22 * i), f"{k['kind']}  ({k['length_m']} m{', kept' if k['kept'] else ''})", fill="black", font_size=16)
    both = Image.new("RGB", (im.width, im.height + leg.height), "white")
    both.paste(im, (0, 0))
    both.paste(leg, (0, im.height))
    both.save(out)
    lng, lat = arc.to_ll(np.array((x0 + n / 2) * 256), np.array((y0 + n / 2) * 256))
    print(f"{out}: around {float(lat):.5f},{float(lng):.5f}")


if __name__ == "__main__":
    if "--preview" in sys.argv:
        i = sys.argv.index("--preview")
        at = next((tuple(map(float, a.split("=", 1)[1].split(",")))[::-1] for a in sys.argv if a.startswith("--at=")), None)
        preview(sys.argv[1], sys.argv[i + 1], at)
    else:
        read(sys.argv[1])
