"""The plan's fill colour inside each plot, as a check on its zone (plan_vector_parcels.py).

Plans fill each kind of zone with its own colour (forest green for Ek, light green for Ev, white for
housing, ...). No legend is read: the colours are learned from the plots whose code is printed on
them. A colour that, on those plots, nearly always goes with one kind of zone (the code's letters
before the first "-" or "/": Ek, Ev, Má, Lke, ...) is then a check on every other plot: a plot whose
guessed or enclosed zone is of another kind is wrong, whatever its block said.

The colours come from the plan's own tiles (public/pmtiles/<key>/, pack_tiles.py) at zoom ZOOM.
"""
import io
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ZOOM = 17          # ~1.1 m per pixel in Budapest: enough for a fill colour, few tiles
MIN_PLOTS = 12     # a colour is learned from at least this many printed plots
MIN_PURITY = 0.9   # ... nearly all of one kind of zone
MIN_COVER = 0.5    # a plot "has" a colour when it fills this share of its sampled pixels
INSET_M = 1.5      # sample inside the plot, away from its lines


def kind(code):
    return re.split(r"[-/]", code, maxsplit=1)[0]


class Tiles:
    def __init__(self, key):
        from pmtiles.reader import MemorySource, Reader
        parts = sorted((ROOT / "public/pmtiles" / key).glob("*.bin"), key=lambda p: int(p.stem))
        self.reader = Reader(MemorySource(b"".join(p.read_bytes() for p in parts))) if parts else None
        self.cache = {}

    def tile(self, x, y):
        if (x, y) not in self.cache:
            b = self.reader.get(ZOOM, x, y)
            self.cache[(x, y)] = np.asarray(Image.open(io.BytesIO(b)).convert("RGBA")) if b else None
            if len(self.cache) > 4000:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[(x, y)]


def px(lng, lat):
    s = 256 * 2 ** ZOOM
    return (lng + 180) / 360 * s, (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * s


def colour_bin(rgb):
    return tuple(int(c) >> 4 for c in rgb)


def plot_colour(tiles, g):
    """The colour bin filling most of the plot (None: no single colour, or no plan here)."""
    inner = g.buffer(-INSET_M / 111_000)
    if inner.is_empty:
        inner = g.representative_point().buffer(0.5 / 111_000)
    x0, y1 = px(*inner.bounds[:2])
    x1, y0 = px(*inner.bounds[2:])
    w, h = int(x1) - int(x0) + 1, int(y1) - int(y0) + 1
    if w * h > 250_000:
        return None
    mask = Image.new("L", (w, h))
    d = ImageDraw.Draw(mask)
    for poly in getattr(inner, "geoms", [inner]):
        d.polygon([(px(*q)[0] - int(x0), px(*q)[1] - int(y0)) for q in poly.exterior.coords], fill=1)
    m = np.asarray(mask, bool)
    if m.sum() < 4:
        return None
    counts = Counter()
    for ty in range(int(y0) // 256, int(y1) // 256 + 1):
        for tx in range(int(x0) // 256, int(x1) // 256 + 1):
            t = tiles.tile(tx, ty)
            if t is None:
                continue
            # The part of this tile under the mask.
            ax0, ay0 = max(tx * 256, int(x0)), max(ty * 256, int(y0))
            ax1, ay1 = min(tx * 256 + 256, int(x0) + w), min(ty * 256 + 256, int(y0) + h)
            if ax0 >= ax1 or ay0 >= ay1:
                continue
            sub = t[ay0 - ty * 256:ay1 - ty * 256, ax0 - tx * 256:ax1 - tx * 256]
            sm = m[ay0 - int(y0):ay1 - int(y0), ax0 - int(x0):ax1 - int(x0)] & (sub[..., 3] > 0)
            pix = sub[sm][:, :3].astype(int)
            pix = pix[pix.sum(1) > 300]  # not the dark lines and lettering
            counts.update(map(colour_bin, pix))
    total = sum(counts.values())
    if total < 4:
        return None
    b, n = counts.most_common(1)[0]
    return b if n >= MIN_COVER * total else None


def learn(colours, codes, printed):
    """colour bin -> kind of zone, from the printed plots: only colours that nearly always go with
    one kind."""
    seen = defaultdict(Counter)
    for c, code, p in zip(colours, codes, printed):
        if p and c is not None and code:
            seen[c][kind(code)] += 1
    out = {}
    for c, ks in seen.items():
        k, n = ks.most_common(1)[0]
        if sum(ks.values()) >= MIN_PLOTS and n >= MIN_PURITY * sum(ks.values()):
            out[c] = k
    return out, seen
