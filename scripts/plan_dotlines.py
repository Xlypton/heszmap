"""The plan's red dotted zone boundary lines, read from its own map tiles, for any plan.

Every published plan is a tile archive (public/pmtiles/<key>/, pack_tiles.py), whatever the source
looked like (vector PDF, scan, JPG annex). Hungarian KÉSZ/HÉSZ plans draw the boundary between two
zones (övezethatár) as a red dotted line. This reads it with no per-plan settings:

1. Red pixels at the archive's top zoom, split into blobs.
2. A dot is a small, round, solid blob. The dot size and spacing are learned from the plan itself:
   the most common size among round red blobs, and the most common gap between them.
3. A boundary is a chain of such dots, evenly spaced: dots of about that size, each within ~2.6
   gaps of the next, at least MIN_CHAIN of them. Red lettering, red hatching and lone symbols are
   not chains of equal round dots.
4. Each pair of linked dots is a piece of wall; the walls widened by REACH_M are the lines
   plan_vector_parcels.write() never groups plots across, splits plots along, and never "sees"
   a zone code through.

The result is cached as scripts/plans/<key>-dotlines.geojson (lines, lng/lat) so the zone build and
check_district.py read the same lines.

    python3 scripts/plan_dotlines.py <key> [--debug <png>]   (re)read and cache the lines
"""
import io
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
WINDOW = 12        # tiles per side read at once (+1 tile margin each side)
MIN_CHAIN = 6      # dots in a line
MIN_KIND_LINKS = 40  # a kind of dot (size) counts as a line style when it makes this many links
MAX_GAP_CV = 0.35   # a line's dot spacing varies at most this much (std / mean)
MIN_STRAIGHT = 0.6  # ... and this share of its dots sit on a straight run
MAX_DASH_PX = 40   # a dash of a dashed line is at most this long
LINK = 2.6         # dots this many gaps apart are one line (a corner, one dot hidden under lettering)
EXTEND_GAPS = 2.5  # a loose end of a line is carried on this many dot gaps
REACH_M = 1.5      # wall half-width: plan vs land-registry plots sit ~1-3 m apart
# red: R strong, G and B well below it and about equal (orange and brown have G above B; salmon
# and pink fills have G, B above ~0.55 R)
RED = dict(r_min=90, gb_max=0.55, gb_diff=25)


def red_mask(rgb):
    """Red pixels, with a thin dark line drawn over a dot (a plot line crossing it) closed up, so
    the dot stays one round blob."""
    import cv2
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    m = ((r >= RED["r_min"]) & (np.maximum(g, b) <= RED["gb_max"] * r) & (np.abs(g - b) <= RED["gb_diff"])).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)).astype(bool)


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


def blobs(arc):
    """Every round, solid red blob: (px x, px y, area px) in global pixel coordinates."""
    import cv2
    have = set(arc.tiles())
    if not have:
        return np.zeros((0, 3))
    xs, ys = [t[0] for t in have], [t[1] for t in have]
    out = []
    for wx in range(min(xs), max(xs) + 1, WINDOW):
        for wy in range(min(ys), max(ys) + 1, WINDOW):
            if not any((x, y) in have for x in range(wx, wx + WINDOW) for y in range(wy, wy + WINDOW)):
                continue
            img = arc.image(wx - 1, wy - 1, WINDOW + 2)
            if img is None:
                continue
            m = red_mask(img).astype(np.uint8)
            n, _, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
            for i in range(1, n):
                x, y, w, h, a = stats[i]
                cx, cy = cent[i]
                # own the blob only in the window's core (the margin is the neighbour's core)
                if not (256 <= cx < 256 * (WINDOW + 1) and 256 <= cy < 256 * (WINDOW + 1)):
                    continue
                if a < 3 or a > 900:
                    continue
                round_ = max(w, h) <= 1.7 * min(w, h) and a >= 0.45 * w * h
                dash = max(w, h) <= MAX_DASH_PX and a <= 4 * math.hypot(w, h)  # a short thin stroke
                if not (round_ or dash):
                    continue
                out.append((cx + (wx - 1) * 256, cy + (wy - 1) * 256, a))
    return np.array(out, float).reshape(-1, 3)


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


def chains(pts, area):
    """The dotted (and dashed) lines among the small red blobs. A plan may draw more than one kind
    (a big-dot zone boundary, a fine-dot regulation line, a dash-dot line): every blob size common
    on the plan is tried, and each one that makes long even chains is kept.
    Returns (links as point pairs, dot size, gap px) with the size and gap of the main kind."""
    if len(pts) < MIN_CHAIN:
        return [], 0, 0
    bins = Counter(np.round(np.log(area) * 4))
    tried, found = set(), []
    for b, n in bins.most_common(12):
        if n < 3 * MIN_CHAIN:
            break
        size = math.exp(b / 4)
        links, gap = chain(pts, area, size)
        found.append((len(links), size, gap, links))
    if not found:
        return [], 0, 0
    found.sort(key=lambda f: -f[0])
    best = found[0][0]
    links = set()
    for n, size, gap, ls in found:
        if n >= max(MIN_KIND_LINKS, 0.1 * best):
            links |= set(ls)
    segs = [(pts[a], pts[b]) for a, b in links]
    return segs, found[0][1], found[0][2]


def read(key, debug=None):
    arc = Archive(key)
    b = blobs(arc)
    segs, size, gap = chains(b[:, :2], b[:, 2]) if len(b) else ([], 0, 0)
    feats = []
    for p, q in segs:
        lng, lat = arc.to_ll(np.array([p[0], q[0]]), np.array([p[1], q[1]]))
        feats.append([[round(float(lng[0]), 7), round(float(lat[0]), 7)], [round(float(lng[1]), 7), round(float(lat[1]), 7)]])
    lat0 = float(np.mean([f[0][1] for f in feats])) if feats else 47.5
    mpp = arc.m_per_px(lat0)
    info = {"zoom": arc.z, "blobs": int(len(b)), "dot_px": round(size, 1), "gap_m": round(float(gap * mpp), 2),
            "segments": len(feats), "length_m": round(sum(math.hypot(*(np.array(p) - np.array(q))) for p, q in segs) * mpp)}
    out = ROOT / "scripts/plans" / f"{key}-dotlines.geojson"
    out.write_text(json.dumps({"type": "Feature", "properties": info,
                               "geometry": {"type": "MultiLineString", "coordinates": feats}}, separators=(",", ":")))
    print(f"{key}: red dotted lines {info}")
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


if __name__ == "__main__":
    read(sys.argv[1])
