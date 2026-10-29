"""Register a georeferenced plan to the land-registry plot lines: the plan's own plot lines onto the
plot outlines the app shows (public/data/parcels-<key>/, OÉNY or BTP), instead of OSM streets and
buildings. A plan is drawn on the land-registry base map, so its plot lines and the registry
outlines should coincide; OSM is a few metres off in places (Csobánka: ~2-3 m).

    python3 scripts/plan_plotfit.py <key> [--check] [--sheets 0,2] [--shift-m 8]

For every fitted sheet in scripts/plans/<key>.json: chamfer distance from points along the registry
plot outlines to the plan's plot-line pixels, then a small similarity correction in metres (shift,
per 300 m block, then a smooth affine or quadratic field through the block shifts, added to the sheet's
own polynomial) that minimises it. Each sheet keeps its
correction only when the outlines clearly land closer to the plan lines. --check only reports.
Then: plan_georef.py <key> ... --reuse-fit (tiles and labels), pack_tiles, registry export/build
(pipeline --only georef does the first step).

Plot-line pixels: styles.plot_line, else styles.parcel_line (when it is a colour range), else
styles.building_line; each may be a list per sheet. Writes scripts/plans/<key>-plotfit.json.
"""
import glob
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.optimize import least_squares
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
import plan_georef as pg  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = pg.ROOT
CAP_M = 3.0  # outline points farther than this from a plan line are other drawing, not misfit
STEP_M = 1.0


def line_style(cfg, i):
    styles = cfg.get("styles", {})
    for k in ("plot_line", "parcel_line", "building_line"):
        s = styles.get(k)
        s = s[i] if isinstance(s, list) else s
        if s and ("min" in s or "max" in s):
            return s
    return {"max": [70, 70, 70]}


def registry_rings(key, local):
    """Outer rings of the app's plots in local metres."""
    rings = []
    for fn in sorted(glob.glob(str(ROOT / "public/data" / f"parcels-{key}" / "*.json"))):
        for f in json.loads(Path(fn).read_text())["features"]:
            if f["properties"].get("source") == "plan":
                continue  # traced from this plan: no independent evidence
            g = shape(f["geometry"])
            for poly in getattr(g, "geoms", [g]):
                r = np.asarray(poly.exterior.coords)
                x, y = local.to_m(r[:, 0], r[:, 1])
                rings.append(np.column_stack([x, y]))
    return rings


def outline_points(rings, lo, hi):
    out = []
    for r in rings:
        if r[:, 0].max() < lo[0] or r[:, 0].min() > hi[0] or r[:, 1].max() < lo[1] or r[:, 1].min() > hi[1]:
            continue
        for a, b in zip(r[:-1], r[1:]):
            n = max(int(math.hypot(*(b - a)) / STEP_M), 1)
            out.append(a + (b - a) * (np.arange(n) / n)[:, None])
    return np.vstack(out) if out else np.zeros((0, 2))


def block_shifts(d, M, block_m, shift_m):
    """The shift (metres) that puts each block_m square's registry outlines onto the plan lines:
    [(centre, shift, points)] for the blocks with enough outline and a clear best shift."""
    step = max(0.5, shift_m / 16)  # least squares refines each block after the grid
    grid = np.arange(-shift_m, shift_m + 1e-6, step)
    cells = np.floor(M / block_m).astype(int)
    out = []
    for c in {tuple(v) for v in cells}:
        P = M[(cells == c).all(1)]
        if len(P) < 300:
            continue
        P = P[:: max(1, len(P) // 3000)]
        cost = lambda s: float(np.mean(np.minimum(d(P - s), CAP_M)))
        best = min((np.array([dx, dy]) for dx in grid for dy in grid), key=cost)
        sol = least_squares(lambda s: np.minimum(d(P - s), CAP_M), best, x_scale=0.5, loss="soft_l1", f_scale=0.7).x
        s = sol if cost(sol) <= cost(best) else best
        if np.hypot(*s) < shift_m and cost(s) < 0.9 * cost(np.zeros(2)) or cost(np.zeros(2)) < 1.0:
            out.append((P.mean(0), s, len(P)))
    return out


def fit_correction(blocks, m0, order):
    """A polynomial field (metres -> shift) through the block shifts, iteratively dropping outliers."""
    C = np.array([b[0] for b in blocks]) - m0
    S = np.array([b[1] for b in blocks])
    scale = max(float(np.abs(C).max()), 1.0)
    keep = np.ones(len(C), bool)
    for _ in range(4):
        coef, *_ = np.linalg.lstsq(pg.PolyModel.terms(C[keep] / scale, order), S[keep], rcond=None)
        res = np.hypot(*(pg.PolyModel.terms(C / scale, order) @ coef - S).T)
        keep = res < max(1.0, 2.5 * float(np.median(res)))
    return (lambda M: pg.PolyModel.terms(np.atleast_2d(M - m0) / scale, order) @ coef), res, keep


def fit_sheet(cfg, i, im, model, rings, shift_m, block_m=300):
    plan = cfg["plan"]
    rgba = pg.blank_sheet(plan, i, im.convert("RGBA"))
    alpha = np.asarray(rgba.getchannel("A"))
    rgb = np.asarray(rgba.convert("RGB"), dtype=np.int16)
    x0, y0, x1, y1 = pg.sheet_frame(plan, i, rgba) if plan.get("frames") else (0, 0, *rgba.size)
    lines = dcfg.mask(rgb, line_style(cfg, i)) & (alpha > 0)
    dt = ndimage.distance_transform_edt(~lines).astype(np.float32)
    inv = model.inverse(rgba.size)
    corners = model(np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float))
    M = outline_points(rings, corners.min(0) - 20, corners.max(0) + 20)
    if len(M) == 0:
        return None
    mpp = math.sqrt(abs(np.linalg.det(model.coef[1:3, :2]))) / model.scale
    q = inv(M)
    on = (q[:, 0] > x0 + 10) & (q[:, 0] < x1 - 10) & (q[:, 1] > y0 + 10) & (q[:, 1] < y1 - 10)
    on[on] &= alpha[q[on, 1].astype(int), q[on, 0].astype(int)] > 0
    # Only where the sheet draws plot lines at all (outside a partial plan's area it is blank).
    on[on] &= dt[q[on, 1].astype(int), q[on, 0].astype(int)] * mpp < 15
    M = M[on]
    if len(M) < 1000:
        return {"sheet": i, "skipped": f"only {len(M)} registry outline points on plan lines"}

    def d(P):
        """Distance (m) from registry points P, moved by the inverse of the correction, to a plan line."""
        qq = inv(P)
        return ndimage.map_coordinates(dt, [qq[:, 1], qq[:, 0]], order=1, mode="nearest") * mpp

    m0 = M.mean(0)
    blocks = block_shifts(d, M, block_m, shift_m)
    if len(blocks) < 3:
        return {"sheet": i, "skipped": f"only {len(blocks)} blocks with a clear shift"}
    # Affine with few blocks; a quadratic field (paper or scan stretch) with many.
    order = 2 if len(blocks) >= 15 else 1
    corr, res, keep = fit_correction(blocks, m0, order)
    sample = M[:: max(1, len(M) // 80000)]
    d0, d1 = d(sample), d(sample - corr(sample))
    moved = np.hypot(*corr(sample).T)
    rep = {"sheet": i, "points": int(len(sample)), "blocks": len(blocks), "blocksKept": int(keep.sum()), "order": order,
           "blockResidualMedianM": round(float(np.median(res[keep])), 2),
           "medianM_before": round(float(np.median(d0)), 2), "within1m_before": round(float((d0 < 1).mean()), 3),
           "p90M_before": round(float(np.percentile(d0[d0 < CAP_M], 90)), 2) if (d0 < CAP_M).any() else None,
           "matched_before": round(float((d0 < CAP_M).mean()), 3),
           "medianM_after": round(float(np.median(d1)), 2), "within1m_after": round(float((d1 < 1).mean()), 3),
           "movedMedianM": round(float(np.median(moved)), 2), "movedP95M": round(float(np.percentile(moved, 95)), 2),
           "movedMaxM": round(float(moved.max()), 2)}
    # A clear gain only, and no jump to a neighbouring plot line. The quadratic field may swing out at a
    # sheet corner with few plots (Csobánka 1:7000 overview: 16 m at one corner, 4.6 m median), so the
    # bar is on the 95th percentile of the move, not its maximum.
    rep["applied"] = bool(np.median(d1) < 0.95 * np.median(d0) and (d1 < 1).mean() > (d0 < 1).mean()
                          and np.percentile(moved, 95) < 1.5 * shift_m)
    # What a publish gate reads (scripts/check_district.py): the distances of the fit that is kept.
    # Registry lines the plan does not draw (CAP_M away from any plan line) are left out of the P90;
    # plotLineMatched is the share of outline points that are on a plan line at all.
    dk = d1 if rep["applied"] else d0
    rep["plotLineMedianM"] = round(float(np.median(dk)), 2)
    rep["plotLineP90M"] = round(float(np.percentile(dk[dk < CAP_M], 90)), 2) if (dk < CAP_M).any() else None
    rep["plotLineMatched"] = round(float((dk < CAP_M).mean()), 3)
    rep["_corr"] = corr
    return rep


def main():
    key = sys.argv[1]
    opt = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None
    check = "--check" in sys.argv
    only = [int(s) for s in opt("--sheets").split(",")] if opt("--sheets") else None
    cfg = dcfg.load(key)
    # plan.plotfit_shift_m: the largest offset searched, one number or one per sheet (an overview sheet
    # registered to a detail sheet can be off by more: Csobánka 1:7000, up to 14 m at its west edge).
    shift_cfg = cfg["plan"].get("plotfit_shift_m", 8)
    saved_path = ROOT / "scripts/plans" / f"{key}.json"
    saved = json.loads(saved_path.read_text())
    local = pg.Local(*saved["local"])
    rings = registry_rings(key, local)
    if not rings:
        raise SystemExit(f"no registry plots in public/data/parcels-{key}/")
    paths = dcfg.sheet_paths(cfg)
    reports = []
    for i, f in enumerate(saved["sheets"]):
        if f.get("skipped") or (only is not None and i not in only):
            continue
        path = next((p for p in paths if p.name == f["sheet"]), None)
        if path is None:
            print(f"sheet {i}: {f['sheet']} not rendered (pipeline --only sheets)")
            continue
        model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
        im = Image.open(path)
        shift_m = float(opt("--shift-m") or (shift_cfg[i] if isinstance(shift_cfg, list) else shift_cfg))
        rep = fit_sheet(cfg, i, im, model, rings, shift_m)
        if rep is None:
            continue
        if "skipped" in rep:
            print(f"sheet {i}: {rep['skipped']}")
            reports.append(rep)
            continue
        corr = rep.pop("_corr")
        print(f"sheet {i} ({f['sheet']}): {rep['blocksKept']}/{rep['blocks']} blocks, order {rep['order']}, block residual "
              f"{rep['blockResidualMedianM']:.2f} m; median {rep['medianM_before']:.2f} -> {rep['medianM_after']:.2f} m from a "
              f"plan plot line, within 1 m {rep['within1m_before']:.0%} -> {rep['within1m_after']:.0%}; moved median "
              f"{rep['movedMedianM']:.2f} m, max {rep['movedMaxM']:.2f} m{'' if rep['applied'] else '  (not applied)'}")
        reports.append(rep)
        if rep["applied"] and not check:
            g = np.stack(np.meshgrid(np.linspace(0, im.size[0], 40), np.linspace(0, im.size[1], 40)), -1).reshape(-1, 2)
            m = model(g)
            new = pg.PolyModel.fit(g, m + corr(m), max(model.order, rep["order"]), model.centre, model.scale)
            saved["sheets"][i] = {**f, **new.to_json()}
    # The report is written on --check too (with "applied" false), so the alignment can be gated on
    # without changing the fit; with --sheets only those sheets' entries are replaced.
    out = ROOT / "scripts/plans" / f"{key}-plotfit.json"
    old = {r["sheet"]: r for r in json.loads(out.read_text())} if out.exists() and only is not None else {}
    for r in reports:
        if check:
            r["applied"] = False
            if "medianM_before" in r:
                r["plotLineMedianM"], r["plotLineP90M"], r["plotLineMatched"] = r["medianM_before"], r["p90M_before"], r["matched_before"]
        old[r["sheet"]] = r
    out.write_text(json.dumps([old[k] for k in sorted(old)], indent=1) + "\n")
    if not check:
        saved_path.write_text(json.dumps(saved, indent=1) + "\n")
        print(f"updated {saved_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
