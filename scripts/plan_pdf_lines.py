"""The zone boundary lines of a vector PDF plan, read from the PDF itself (exact, no tile pixels).

For plans with plan.boundary_source "pdf" (Győr, Pécs): plan_dotlines.read() calls this instead of
reading the tiles. Every sheet with a georef fit is read for the paths in the plan's line colours:

- a dot is a tiny path, or a cluster of tiny paths (Pécs draws each dot as dozens of micro strokes;
  Győr as one zero-length path with a round cap); dots are chained per size like plan_dotlines.py
  (evenly spaced, mostly straight), one sheet at a time;
- a solid line is a longer path (or a long cluster of micro strokes), kept as its segments.

Kinds are named "<#rrggbb> <width>pt dots <size>pt" and "<#rrggbb> <width>pt solid"; plan.boundary_lines
picks them by prefix as for tile kinds (e.g. "#fa4f14 0.99pt dots"). Output is the same
scripts/plans/<key>-dotlines.geojson (and -kinds.json) plan_dotlines.py writes, so walls, loose ends,
zone_line_check.py and the preview work unchanged.

    python3 scripts/plan_pdf_lines.py <key>            (normally run through plan_dotlines.py <key>)
    python3 scripts/plan_pdf_lines.py <key> --select   re-pick kinds after editing plan.boundary_lines
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_dotlines as pdl  # noqa: E402
import plan_georef as pg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TINY_PT = 1.5     # a path at most this long is a piece of a dot
JOIN_PT = 0.6     # pieces this close are one dot (or one micro-stroked line)
MAX_DOT_PT = 6.0  # a cluster wider than this is a line drawn in micro strokes, not a dot
MIN_SOLID_PT = 8.0  # a solid line piece is at least this long


def colours(cfg):
    """The colours to read: plan.boundary_colours [[r,g,b], ...], else those of plan.zone_lines."""
    cs = cfg["plan"].get("boundary_colours") or [x[0] for x in cfg["plan"].get("zone_lines", []) if isinstance(x, list)]
    return [tuple(c) for c in cs] or [(1.0, 0.0, 0.0)]


def hexc(c):
    return "#" + "".join(f"{round(v * 255):02x}" for v in c)


def sheet_pages(cfg):
    """(annex path, page number) for each sheet, in plan_sheets.py order."""
    out = []
    for ref in cfg["plan"]["annexes"]:
        ref = ref if isinstance(ref, str) else ref["path"]
        import pymupdf
        doc = pymupdf.open(dcfg.work_dir(cfg["key"]) / "annex" / Path(ref).name)
        for page in doc:
            if cfg["plan"].get("pages") and page.number + 1 not in cfg["plan"]["pages"]:
                continue
            out.append((str(doc.name), page.number))
    return out


def read_sheet(args):
    """One sheet: {kind: [segments in page points]} and {kind: dot gap pt}."""
    path, pno, cols = args
    import pymupdf
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    page = pymupdf.open(path)[pno]
    tiny, solid = defaultdict(list), defaultdict(list)  # style -> [(x, y, extent)] / [segment]
    for d in page.get_drawings():
        c = d.get("color")
        if not c:
            continue
        col = next((k for k in cols if np.allclose(c, k, atol=0.03)), None)
        if col is None:
            continue
        st = (hexc(col), round(d.get("width") or 0, 2))
        r = d["rect"]
        if max(r.width, r.height) <= TINY_PT:
            tiny[st].append((r.x0, r.y0, r.x1, r.y1))
            continue
        for it in d["items"]:
            if it[0] == "l":
                solid[st].append((tuple(it[1]), tuple(it[2])))
            elif it[0] == "c":
                solid[st].append((tuple(it[1]), tuple(it[4])))
            elif it[0] == "re":
                q = it[1]
                solid[st] += [((q.x0, q.y0), (q.x1, q.y0)), ((q.x1, q.y0), (q.x1, q.y1)),
                              ((q.x1, q.y1), (q.x0, q.y1)), ((q.x0, q.y1), (q.x0, q.y0))]
    out, gaps = defaultdict(list), {}
    for st, rects in tiny.items():
        rc = np.array(rects)
        ctr = (rc[:, :2] + rc[:, 2:]) / 2
        pairs = np.array(sorted(cKDTree(ctr).query_pairs(JOIN_PT)), int).reshape(-1, 2)
        g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(ctr), len(ctr)))
        _, comp = connected_components(g, directed=False)
        order = np.argsort(comp)
        bounds = np.flatnonzero(np.diff(comp[order])) + 1
        dots, sizes = [], []
        for grp in np.split(order, bounds):
            x0, y0 = rc[grp, 0].min(), rc[grp, 1].min()
            x1, y1 = rc[grp, 2].max(), rc[grp, 3].max()
            ext = max(x1 - x0, y1 - y0)
            if ext > MAX_DOT_PT:  # a line drawn in micro strokes: its pieces in order along it
                p = ctr[grp]
                ax = np.argmax(p.max(0) - p.min(0))
                p = p[np.argsort(p[:, ax])]
                solid[st] += [(tuple(p[k]), tuple(p[k + 1])) for k in range(len(p) - 1)
                              if np.hypot(*(p[k + 1] - p[k])) < 2 * JOIN_PT]
                continue
            dots.append(((x0 + x1) / 2, (y0 + y1) / 2))
            sizes.append(ext + st[1])  # a zero-length round-capped dot is as wide as its stroke
        if len(dots) < pdl.MIN_CHAIN:
            continue
        pts, size = np.array(dots), np.array(sizes)
        area = size ** 2
        seen = set()  # neighbouring size bins share dots: each link once
        for sz, gap, segs in sorted(pdl.dot_kinds(pts, area), key=lambda f: -len(f[2])):
            k = f"{st[0]} {st[1]}pt dots {round(math.sqrt(sz) * 2) / 2:.1f}pt"
            for a, b in segs:
                a, b = tuple(map(float, a)), tuple(map(float, b))
                if (a, b) not in seen and (b, a) not in seen:
                    seen.add((a, b))
                    out[k].append((a, b))
            gaps.setdefault(k, gap)
    for st, segs in solid.items():
        L = sum(math.dist(a, b) for a, b in segs)
        if L >= MIN_SOLID_PT:
            out[f"{st[0]} {st[1]}pt solid"] += segs
    return pno, dict(out), gaps, tuple(page.rotation_matrix)


def read(key):
    cfg = dcfg.load(key)
    fit = json.loads((ROOT / "scripts/plans" / f"{key}.json").read_text())
    local = pg.Local(*fit["local"])
    import pymupdf
    zoom = cfg["plan"]["dpi"] / 72
    cols = colours(cfg)
    jobs = [(p, n, cols) for i, (p, n) in enumerate(sheet_pages(cfg))
            if i < len(fit["sheets"]) and fit["sheets"][i].get("coef") is not None]
    idx = [i for i, _ in enumerate(sheet_pages(cfg)) if i < len(fit["sheets"]) and fit["sheets"][i].get("coef") is not None]
    kinds = defaultdict(list)  # name -> [segment lng/lat]
    gapm = defaultdict(list)
    with ProcessPoolExecutor(int(os.environ.get("JOBS", os.cpu_count() or 2))) as ex:
        for i, (pno, segs, gaps, rot) in zip(idx, ex.map(read_sheet, jobs)):
            f = fit["sheets"][i]
            model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
            mat = pymupdf.Matrix(rot) * pymupdf.Matrix(zoom, zoom)

            def ll(pts):
                px = np.array([tuple(pymupdf.Point(x, y) * mat) for x, y in pts])
                x, y = local.to_ll(*model(px).T)
                return np.column_stack([x, y])
            for k, s in segs.items():
                a = ll([p for p, _ in s])
                b = ll([q for _, q in s])
                kinds[k] += [[[round(float(v), 7) for v in p], [round(float(v), 7) for v in q]] for p, q in zip(a, b)]
                if k in gaps:
                    m = (np.hypot((a[:, 0] - b[:, 0]) * local.kx, (a[:, 1] - b[:, 1]) * local.ky))
                    gapm[k].append(float(np.median(m)))
            print(f"  sheet {i}: " + ", ".join(f"{k} {len(s)}" for k, s in sorted(segs.items(), key=lambda t: -len(t[1]))[:4]), flush=True)
    want = pdl.boundary_kinds(key)
    report, feats, gaps = [], [], []
    for name, segs in kinds.items():
        L = sum(math.hypot((p[0] - q[0]) * local.kx, (p[1] - q[1]) * local.ky) for p, q in segs)
        keep = any(name.startswith(w) for w in want)
        g = float(np.median(gapm[name])) if gapm.get(name) else 0
        report.append({"kind": name, "segments": len(segs), "length_m": round(L), "gap_m": round(g, 2), "kept": keep})
        if keep:
            feats += segs
            if g:
                gaps.append(g)
    info = {"source": "pdf", "kinds": [r["kind"] for r in report if r["kept"]], "gap_m": round(float(np.median(gaps)), 2) if gaps else 5.0,
            "segments": len(feats), "length_m": sum(r["length_m"] for r in report if r["kept"]), "wanted": want,
            "all_kinds": sorted(report, key=lambda r: -r["length_m"])}
    (ROOT / "scripts/plans" / f"{key}-kinds.json").write_text(json.dumps(
        [dict(r, segments=kinds[r["kind"]]) for r in report], separators=(",", ":")))
    (ROOT / "scripts/plans" / f"{key}-dotlines.geojson").write_text(json.dumps(
        {"type": "Feature", "properties": info, "geometry": {"type": "MultiLineString", "coordinates": feats}}, separators=(",", ":")))
    print(f"{key}: zone boundary lines (from the PDF) {info['kinds']} {info['length_m']} m")
    for r in info["all_kinds"][:40]:
        print(f"    {'KEEP' if r['kept'] else '    '} {r['kind']:34s} {r['length_m']:7d} m" + (f"  dots every {r['gap_m']} m" if r['gap_m'] else ""))
    return info


def select(key):
    """Re-pick the kept kinds from the cached -kinds.json after plan.boundary_lines changed (no re-read)."""
    want = pdl.boundary_kinds(key)
    kinds = json.loads((ROOT / "scripts/plans" / f"{key}-kinds.json").read_text())
    p = ROOT / "scripts/plans" / f"{key}-dotlines.geojson"
    f = json.loads(p.read_text())
    for k in kinds:
        k["kept"] = any(k["kind"].startswith(w) for w in want)
    keep = [k for k in kinds if k["kept"]]
    gaps = [k["gap_m"] for k in keep if k["gap_m"]]
    f["properties"].update(kinds=[k["kind"] for k in keep], wanted=want, segments=sum(len(k["segments"]) for k in keep),
                           length_m=sum(k["length_m"] for k in keep), gap_m=round(float(np.median(gaps)), 2) if gaps else 5.0,
                           all_kinds=sorted([{a: b for a, b in k.items() if a != "segments"} for k in kinds], key=lambda r: -r["length_m"]))
    f["geometry"]["coordinates"] = [s for k in keep for s in k["segments"]]
    p.write_text(json.dumps(f, separators=(",", ":")))
    (ROOT / "scripts/plans" / f"{key}-kinds.json").write_text(json.dumps(kinds, separators=(",", ":")))
    print(f"{key}: kept {f['properties']['kinds']}")


if __name__ == "__main__":
    select(sys.argv[1]) if "--select" in sys.argv else read(sys.argv[1])
