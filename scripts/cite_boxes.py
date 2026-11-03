#!/usr/bin/env python3
"""Highlight boxes for cited quotes whose text is hidden under a picture of the table.

The source viewer highlights a quote by finding it in the PDF's text layer. That fails silently when
an amendment pasted a picture of the new table over the old table's text (Budapest XVIII. KÉSZ m2,
2. melléklet p. 7: the Vi-2 table): the text is still there, so the quote is found, but the old rows
sit at other heights than the rows of the picture, and the highlight lands on another row
(Vi-2/N's highlight sat on Vi-2/KI).

For every cited quote this finds the quote's characters and checks whether a picture painted after
them covers them. For those it maps the quote's row onto the picture: the rules between table rows
are found in both the text-only rendering and the picture, the two sequences of rows are aligned by
content (rows can be added or removed by the amendment), and the quote's row in the picture gives the
box. The viewer draws these boxes instead of the text-layer highlight (public/data/cite-boxes.json).

Rows that are only in the picture (no text at all: config "handRows" with "scanned": true) can give
their box by hand: "box": [x0, y0, x1, y1] in PDF points, y up, as this script prints them.

  python3 scripts/cite_boxes.py            # all regulations; writes public/data/cite-boxes.json
  python3 scripts/cite_boxes.py --check    # report only

The report lists every quote that sits under a picture, how it was mapped, and the quotes that could
not be mapped (with the reason), so no affected highlight is skipped silently.
"""
import argparse
import collections
import glob
import json
import re
import sys
import unicodedata

import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from pdfminer.layout import LTChar, LTContainer, LTImage

OUT = 'public/data/cite-boxes.json'
Z = 4  # render scale, px per PDF point


def squash(s: str) -> str:
    return ''.join(unicodedata.normalize('NFC', s).split())


def collect_cites() -> dict:
    """(reg, page) -> set of quotes, from every cite in the published data."""
    cites = collections.defaultdict(set)

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get('quote'), str) and isinstance(o.get('page'), int) and 'reg' in o:
                cites[(o['reg'], o['page'])].add(o['quote'])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for f in sorted(glob.glob('public/data/*.json')):
        if f.endswith('cite-boxes.json'):
            continue
        walk(json.load(open(f)))
    return cites


def hand_boxes() -> list:
    """Boxes given by hand in districts/*.json (zoneTablePdf.handRows[].box)."""
    out = []
    for f in sorted(glob.glob('districts/*.json')):
        t = json.load(open(f)).get('zoneTablePdf') or {}
        for r in t.get('handRows', []) + t.get('rows', []):
            if isinstance(r, dict) and r.get('box'):
                out.append((t['reg'], r['page'], r['quote'], r['box']))
    return out


def flatten(o, out):
    for c in o:
        if isinstance(c, (LTChar, LTImage)):
            out.append(c)
        if isinstance(c, LTContainer):
            flatten(c, out)


def rules(a: np.ndarray) -> list:
    """Horizontal table rules in a greyscale crop: (top px, bottom px, left px, right px)."""
    dark = a < 140
    rows = np.where(dark.mean(1) > 0.6)[0]
    groups = []
    for r in rows:
        if groups and r - groups[-1][-1] <= 2:
            groups[-1].append(r)
        else:
            groups.append([r])
    out = []
    for g in groups:
        cols = np.where(dark[g].any(0))[0]
        out.append((g[0], g[-1], cols.min(), cols.max()))
    return out


def bands(a: np.ndarray):
    """Table rows between consecutive rules: list of (top px, bottom px), and the table's x extent."""
    rs = rules(a)
    if len(rs) < 3:
        return [], None
    left = int(np.median([r[2] for r in rs]))
    right = int(np.median([r[3] for r in rs]))
    return [(rs[i][1] + 1, rs[i + 1][0]) for i in range(len(rs) - 1) if rs[i + 1][0] - rs[i][1] > 4], (left, right)


def norm_band(a, band, ext, w=600, h=24):
    import cv2
    crop = a[band[0]:band[1], ext[0]:ext[1] + 1]
    v = cv2.resize(crop, (w, h), interpolation=cv2.INTER_AREA).astype(float)
    v -= v.mean()
    n = np.linalg.norm(v)
    return v / n if n else v


def align(old, new, sim):
    """Needleman-Wunsch over two row sequences: old row index -> new row index (or None)."""
    gap = -0.3
    n, m = len(old), len(new)
    S = np.zeros((n + 1, m + 1))
    S[:, 0] = gap * np.arange(n + 1)
    S[0, :] = gap * np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            S[i, j] = max(S[i - 1, j - 1] + sim[i - 1, j - 1], S[i - 1, j] + gap, S[i, j - 1] + gap)
    pair = {}
    i, j = n, m
    while i and j:
        if S[i, j] == S[i - 1, j - 1] + sim[i - 1, j - 1]:
            pair[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif S[i, j] == S[i - 1, j] + gap:
            i -= 1
        else:
            j -= 1
    return pair


class CoveredPage:
    """A page whose picture covers text: the rows of the text-only rendering mapped onto the picture."""

    def __init__(self, pdf: pdfium.PdfDocument, page: int, image_bbox):
        pg = pdf[page - 1]
        self.H = pg.get_height()
        full = np.array(pg.render(scale=Z, grayscale=True).to_pil().convert('L'))
        # The same page without its pictures shows the text where the text layer puts it.
        for o in [o for o in pg.get_objects() if o.type == 3]:
            pg.remove_obj(o)
        pg.gen_content()
        bare = np.array(pg.render(scale=Z, grayscale=True).to_pil().convert('L'))
        l, b, r, t = image_bbox
        self.x0, self.y0 = int(l * Z), int((self.H - t) * Z)
        x1, y1 = int(r * Z), int((self.H - b) * Z)
        self.old = bare[self.y0:y1, self.x0:x1]
        self.new = full[self.y0:y1, self.x0:x1]
        self.old_rows, self.old_ext = bands(self.old)
        self.new_rows, self.new_ext = bands(self.new)
        self.pair, self.sim = {}, None
        if self.old_rows and self.new_rows:
            o = [norm_band(self.old, r, self.old_ext) for r in self.old_rows]
            n = [norm_band(self.new, r, self.new_ext) for r in self.new_rows]
            self.sim = np.array([[float((a * c).sum()) for c in n] for a in o])
            self.pair = align(o, n, self.sim)

    def picture_only_rows(self):
        """Rows of the picture with no row of text under them (added by the amendment): PDF boxes."""
        taken = set(self.pair.values())
        (nl, nr) = self.new_ext or (0, 0)
        return [[round(float(self.x0 + nl) / Z, 1), round(float(self.H - (b + self.y0) / Z), 1),
                 round(float(self.x0 + nr) / Z, 1), round(float(self.H - (t + self.y0) / Z), 1)]
                for j, (t, b) in enumerate(self.new_rows) if j not in taken]

    def box(self, chars):
        """PDF box [x0, y0, x1, y1] (y up) of the quote's row in the picture, or a reason why not."""
        if not self.old_rows:
            return None, 'no table rules found under the picture'
        if not self.new_rows:
            return None, 'no table rules found in the picture'
        cy = np.mean([(self.H - (c.y0 + c.y1) / 2) * Z for c in chars]) - self.y0
        row = next((i for i, (t, b) in enumerate(self.old_rows) if t <= cy <= b), None)
        if row is None:
            return None, 'quote is not inside a table row'
        j = self.pair.get(row)
        if j is None:
            return None, 'row was dropped from the picture (no matching row)'
        score = self.sim[row, j]
        if score < 0.35:
            return None, f'best matching row is too different (similarity {score:.2f})'
        (ol, orr), (nl, nr) = self.old_ext, self.new_ext
        fx = lambda x: nl + (x * Z - self.x0 - ol) * (nr - nl) / (orr - ol)
        x0 = fx(min(c.x0 for c in chars)) - 1.5 * Z
        x1 = fx(max(c.x1 for c in chars)) + 1.5 * Z
        # A quote that runs to the table's last column: the box runs to the picture's right edge
        # (the pictured columns are not exactly where the old ones were).
        if orr - (max(c.x1 for c in chars) * Z - self.x0) < 0.1 * (orr - ol):
            x1 = max(x1, nr - 1 * Z)
        top, bot = self.new_rows[j]
        pt = lambda px_x, px_y: (round(float(px_x + self.x0) / Z, 1), round(float(self.H - (px_y + self.y0) / Z), 1))
        (bx0, by0), (bx1, by1) = pt(x0, bot), pt(x1, top)
        return [bx0, by0, bx1, by1], f'old row {row + 1} -> picture row {j + 1} (similarity {score:.2f})'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='report only, do not write ' + OUT)
    ap.add_argument('--reg', action='append', help='only these regulations')
    args = ap.parse_args()

    regs = json.load(open('public/data/regulations.json'))['regulations']
    cites = collect_cites()
    boxes = collections.defaultdict(dict)
    stats = collections.Counter()
    problems = []
    pdfs = {}
    for (reg, page), quotes in sorted(cites.items()):
        if args.reg and reg not in args.reg:
            continue
        path = regs.get(reg, {}).get('pdf')
        if not path:
            continue
        stats['quotes'] += len(quotes)
        if path not in pdfs:
            pdfs[path] = pdfium.PdfDocument('public/' + path)
        pdf = pdfs[path]
        if page > len(pdf):
            continue
        # Most pages have no picture at all: skip the slow layout analysis for them.
        if not any(o.type == 3 for o in pdf[page - 1].get_objects()):
            continue
        with pdfplumber.open('public/' + path, pages=[page]) as pl:
            seq = []
            flatten(pl.pages[0].layout, seq)
        flat, owner = '', []
        for i, o in enumerate(seq):
            if isinstance(o, LTChar):
                for ch in squash(o.get_text()):
                    flat += ch
                    owner.append(i)
        images = [(i, o.bbox) for i, o in enumerate(seq) if isinstance(o, LTImage)]
        order = {id(o): i for i, o in enumerate(seq)}
        covered_pages = {}
        for q in sorted(quotes):
            at = flat.find(squash(q))
            if at < 0:
                continue  # not in the text of this page (a scanned row, or the quote runs on): nothing to move
            chars = [seq[k] for k in sorted(set(owner[at:at + len(squash(q))]))]
            # A picture painted after the text and over it hides the text: the text layer is not what is seen.
            over = None
            for i, bb in images:
                inside = [c for c in chars if i > order[id(c)] and bb[0] <= (c.x0 + c.x1) / 2 <= bb[2] and bb[1] <= (c.y0 + c.y1) / 2 <= bb[3]]
                if len(inside) > len(chars) / 2:
                    over = bb
            if not over:
                continue
            stats['covered'] += 1
            key = tuple(round(v, 1) for v in over)
            if key not in covered_pages:
                covered_pages[key] = CoveredPage(pdf, page, over)
            box, why = covered_pages[key].box(chars)
            if box:
                boxes[reg].setdefault(str(page), {})[q] = box
                stats['mapped'] += 1
                print(f'{reg} p{page}: {q[:40]!r}: {why} -> {box}')
            else:
                problems.append(f'{reg} p{page}: {q[:60]!r}: {why}')
        for cp in covered_pages.values():
            for b in cp.picture_only_rows():
                print(f'{reg} p{page}: picture row with no text under it (a hand row\'s "box"?): {b}')

    for reg, page, quote, box in sorted(set((r, p, q, tuple(b)) for r, p, q, b in hand_boxes())):
        box = list(box)
        if args.reg and reg not in args.reg:
            continue
        boxes[reg].setdefault(str(page), {})[quote] = box
        stats['hand'] += 1
        print(f'{reg} p{page}: {quote[:40]!r}: box given by hand -> {box}')

    print(f"\n{stats['quotes']} cited quotes checked; {stats['covered']} hidden under a picture, "
          f"{stats['mapped']} mapped onto it; {stats['hand']} boxes given by hand.")
    if args.check:
        # The published boxes must be the ones computed now, or the viewer draws stale ones.
        try:
            saved = json.load(open(OUT))
        except FileNotFoundError:
            saved = {}
        for reg, pages in boxes.items():
            for page, qs in pages.items():
                for q, b in qs.items():
                    if saved.get(reg, {}).get(page, {}).get(q) != b:
                        problems.append(f'{reg} p{page}: {q[:60]!r}: box not in {OUT} (run scripts/cite_boxes.py)')
    if problems:
        print(f'{len(problems)} NOT mapped (the viewer would highlight the wrong place):')
        for p in problems:
            print('  ' + p)
    if not args.check:
        out = {reg: dict(sorted(pages.items(), key=lambda kv: int(kv[0]))) for reg, pages in sorted(boxes.items())}
        if args.reg:
            try:
                old = json.load(open(OUT))
            except FileNotFoundError:
                old = {}
            old.update(out)
            out = dict(sorted(old.items()))
        text = json.dumps(out, ensure_ascii=False, indent=1)
        text = re.sub(r'\[\s+([-\d.]+),\s+([-\d.]+),\s+([-\d.]+),\s+([-\d.]+)\s+\]', r'[\1, \2, \3, \4]', text)
        with open(OUT, 'w') as f:
            f.write(text + '\n')
        print(f'wrote {OUT}')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
