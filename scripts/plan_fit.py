"""Georeference a plan sheet whose scale is known: a CAD drawing exported as an image (Csobánka) or a
vector page. Such a sheet is an exact similarity of the national grid, so only the position, a small
rotation (grid north vs. true north) and a small scale correction are unknown.

1. Street names (OCR or text layer) are matched to the OSM streets of the settlement by name,
   accent-insensitively and with a tolerance for OCR errors.
2. Votes: every named label votes for the translations that put it on its street, for each rotation
   and scale on a small grid. Wrong matches scatter their votes; the right ones pile up. No starting
   guess is needed, and a single bad match cannot pull the fit.
3. The inliers of the best vote fix a least-squares similarity.
4. Checks (and optional refinement): road crossings centred in the plan's street bands (plan_georef.refine),
   and OSM building outlines against the plan's building lines (chamfer distance).

Every step prints its residual; fit_sheet() refuses a fit whose residual exceeds MAX_RESIDUAL_M.
"""
import difflib
import math
import unicodedata

import cv2
import numpy as np
from scipy import ndimage
from scipy.optimize import least_squares

import district as dcfg
import plan_georef as pg

SUFFIXES = {"utca", "ut", "utja", "ter", "tere", "koz", "sor", "fasor", "korut", "setany", "dulo", "arok", "lepcso", "lejto", "park"}
VOTE_CELL_M = 4.0
NEAR_STREET_M = 14.0  # a street name sits within this distance of the OSM centre line
MAX_RESIDUAL_M = 10.0


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isalpha() and not unicodedata.combining(c))


def osm_streets(named, local, area):
    """name -> (n, 4) segments in local metres, for the named OSM roads that touch the area polygon."""
    from shapely.geometry import LineString
    out = {}
    for name, lines in named.items():
        if not any(area.intersects(LineString(ln)) for ln in lines if len(ln) > 1):
            continue
        segs = []
        for ln in lines:
            x, y = local.to_m(ln[:, 0], ln[:, 1])
            xy = np.column_stack([x, y])
            segs.extend(np.hstack([xy[:-1], xy[1:]]))
        if segs:
            out[name] = np.array(segs)
    return out


def match_labels(labels, streets):
    """OCR'd text lines -> (street names it may be, label centre px). A label like "Szolo utca" matches
    "Szőlő utca" exactly after folding; "Hanfland" matches "Hanfland körút" by its base name; OCR slips
    ("Hanflang") are matched when one street is clearly the closest."""
    full = {n: fold(n) for n in streets}
    base = {}
    for n in streets:
        words = n.split()
        b = fold(" ".join(words[:-1])) if len(words) > 1 and fold(words[-1]) in SUFFIXES else fold(n)
        base.setdefault(b, []).append(n)
    out = []
    for l in labels:
        t = fold(l["text"])
        if len(t) < 5 or t in SUFFIXES:
            continue
        names = [n for n, f in full.items() if f == t] or base.get(t)
        if not names:
            # Strip a trailing (misread) suffix: "Kelta arok" -> "kelta".
            for suf in sorted(SUFFIXES, key=len, reverse=True):
                if t.endswith(suf) and len(t) - len(suf) >= 4 and t[: -len(suf)] in base:
                    names = base[t[: -len(suf)]]
                    break
        if not names:
            scores = sorted(((difflib.SequenceMatcher(None, t, k).ratio(), k) for k in list(base) + list(full.values())), reverse=True)
            if scores and scores[0][0] >= 0.86 and (len(scores) == 1 or scores[1][0] < scores[0][0] - 0.06):
                k = scores[0][1]
                names = base.get(k) or [n for n, f in full.items() if f == k]
        if names:
            out.append((tuple(sorted(set(names))), np.array(l["box"], float).mean(0), l["text"]))
    return out


def _rot(theta):
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


def to_metres(px, s, theta, t):
    """Plan pixels (x right, y down) -> local metres (x east, y north)."""
    u = np.column_stack([px[:, 0], -px[:, 1]])
    return s * u @ _rot(theta).T + t


def vote(matches, streets, s0, extent, thetas, scales):
    """Hough voting over (rotation, scale, translation). Returns the best (s, theta, t, votes)."""
    x0, y0, x1, y1 = extent
    nx, ny = int((x1 - x0) / VOTE_CELL_M) + 1, int((y1 - y0) / VOTE_CELL_M) + 1
    # Each street (set) as the cells within NEAR_STREET_M of its centre line.
    cells = {}
    for names, _, _ in matches:
        if names in cells:
            continue
        img = np.zeros((ny, nx), np.uint8)
        for n in names:
            for x1s, y1s, x2s, y2s in streets[n]:
                p = ((np.array([[x1s, y1s], [x2s, y2s]]) - [x0, y0]) / VOTE_CELL_M).astype(np.int32)
                cv2.line(img, tuple(p[0]), tuple(p[1]), 1, 1)
        r = int(NEAR_STREET_M / VOTE_CELL_M)
        img = cv2.dilate(img, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
        iy, ix = np.nonzero(img)
        cells[names] = np.column_stack([ix * VOTE_CELL_M + x0, iy * VOTE_CELL_M + y0])
    px = np.array([p for _, p, _ in matches])
    best = None
    for k in scales:
        for th in thetas:
            v = to_metres(px, s0 * k, th, np.zeros(2))
            acc = np.zeros((ny, nx), np.int32)
            for (names, _, _), vi in zip(matches, v):
                t = cells[names] - vi
                ij = np.round((t - [x0, y0]) / VOTE_CELL_M).astype(np.int64)
                ok = (ij[:, 0] >= 0) & (ij[:, 0] < nx) & (ij[:, 1] >= 0) & (ij[:, 1] < ny)
                flat = np.unique(ij[ok, 1] * nx + ij[ok, 0])
                acc.ravel()[flat] += 1
            acc = ndimage.uniform_filter(acc.astype(np.float32), 3) * 9  # a peak can straddle cells
            j = int(acc.argmax())
            if best is None or acc.ravel()[j] > best[3]:
                t = np.array([j % nx, j // nx]) * VOTE_CELL_M + [x0, y0]
                best = (s0 * k, th, t, float(acc.ravel()[j]))
    return best


def street_residuals(matches, streets, s, theta, t):
    m = to_metres(np.array([p for _, p, _ in matches]), s, theta, t)
    res, tgt = [], []
    for (names, _, _), mp in zip(matches, m):
        segs = np.vstack([streets[n] for n in names])
        q, d = pg.nearest_on_polyline(mp, segs)
        res.append(d)
        tgt.append(q)
    return np.array(res), np.array(tgt)


def refine_labels(matches, streets, s, theta, t, tol=NEAR_STREET_M):
    """ICP on the inlier labels: label -> nearest point of its street; similarity by least squares."""
    for _ in range(30):
        res, tgt = street_residuals(matches, streets, s, theta, t)
        keep = res < tol
        if keep.sum() < 4:
            break
        px = np.array([p for _, p, _ in matches])[keep]

        def f(params):
            return (to_metres(px, params[0], params[1], params[2:]) - tgt[keep]).ravel()

        sol = least_squares(f, [s, theta, *t], x_scale=[s * 0.01, 0.002, 1, 1])
        if np.allclose(sol.x, [s, theta, *t], atol=1e-6):
            break
        s, theta, t = sol.x[0], sol.x[1], sol.x[2:]
        tol = max(min(tol, 3 * np.median(res[keep])), 6.0)
    res, _ = street_residuals(matches, streets, s, theta, t)
    return s, theta, t, res


def as_model(s, theta, t, size):
    """The similarity as plan_georef.PolyModel (order 1), the form every later step reads."""
    R = _rot(theta)
    # m = s R [x, -y] + t = [x, y] @ L + t, with L = s * [[R00, R10], [-R01, -R11]]
    L = s * np.array([[R[0, 0], R[1, 0]], [-R[0, 1], -R[1, 1]]])
    A = np.vstack([L, t])
    return pg.PolyModel.from_affine(A, np.array(size, float) / 2, size[0] / 3)


def chamfer(model, rgb, buildings, local, frame, style):
    """OSM building outlines vs. the plan's building lines: distance (m) from points along each OSM
    outline to the nearest plan line pixel. Returns the distances and the line distance transform."""
    lines = dcfg.mask(rgb, style).astype(np.uint8)
    dt = ndimage.distance_transform_edt(lines == 0).astype(np.float32)
    inv = model.inverse((rgb.shape[1], rgb.shape[0]))
    m_per_px = math.sqrt(abs(np.linalg.det(model.coef[1:3, :2]))) / model.scale
    pts = []
    for ring in buildings:
        x, y = local.to_m(ring[:, 0], ring[:, 1])
        for k in range(len(x) - 1):
            n = max(int(math.hypot(x[k + 1] - x[k], y[k + 1] - y[k]) / 0.5), 1)
            tt = np.arange(n) / n
            pts.append(np.column_stack([x[k] + (x[k + 1] - x[k]) * tt, y[k] + (y[k + 1] - y[k]) * tt]))
    if not pts:
        return np.zeros(0), dt, m_per_px
    m = np.vstack(pts)
    px = inv(m)
    x0, y0, x1, y1 = frame
    ok = (px[:, 0] > x0) & (px[:, 0] < x1 - 1) & (px[:, 1] > y0) & (px[:, 1] < y1 - 1)
    d = ndimage.map_coordinates(dt, [px[ok, 1], px[ok, 0]], order=1) * m_per_px
    return d, dt, m_per_px


def outline_points(buildings, local, step=1.0):
    out = []
    for ring in buildings:
        x, y = local.to_m(ring[:, 0], ring[:, 1])
        for k in range(len(x) - 1):
            n = max(int(math.hypot(x[k + 1] - x[k], y[k + 1] - y[k]) / step), 1)
            tt = np.arange(n) / n
            out.append(np.column_stack([x[k] + (x[k + 1] - x[k]) * tt, y[k] + (y[k + 1] - y[k]) * tt]))
    return np.vstack(out) if out else np.zeros((0, 2))


def to_px(params, m):
    """Inverse of to_metres for params [s, theta, tx, ty]."""
    u = (m - params[2:]) @ _rot(params[1]) / params[0]
    return np.column_stack([u[:, 0], -u[:, 1]])


def similarity_of(model, size):
    """[s, theta, tx, ty] closest to a PolyModel over the sheet."""
    g = np.stack(np.meshgrid(np.linspace(0, size[0], 15), np.linspace(0, size[1], 15)), -1).reshape(-1, 2)
    m = model(g)

    def f(p):
        return (to_metres(g, p[0], p[1], p[2:]) - m).ravel()

    m_per_px = math.sqrt(abs(np.linalg.det(model.coef[1:3, :2]))) / model.scale
    return least_squares(f, [m_per_px, 0.0, *m[0]]).x


def register_to_sheet(im, ref_im, ratio):
    """Sheet -> reference sheet pixels (2x3 affine), for two exports of the same drawing at different
    scales (the overview sheet shows the detail sheet's area too). ratio: reference px per sheet px.
    Template matching of edge images finds the overlap; ECC refines it to a fraction of a pixel."""
    def feat(g, sigma):
        e = cv2.Canny(g.astype(np.uint8), 40, 120).astype(np.float32)
        return cv2.GaussianBlur(e, (0, 0), sigma)

    a = np.asarray(ref_im.convert("L"), np.float32)
    b = np.asarray(im.convert("L"), np.float32)
    red = 4
    A = cv2.resize(a, None, fx=1 / ratio / red, fy=1 / ratio / red, interpolation=cv2.INTER_AREA)
    B = cv2.resize(b, None, fx=1 / red, fy=1 / red, interpolation=cv2.INTER_AREA)
    res = cv2.matchTemplate(feat(B, 1.5), feat(A, 1.5), cv2.TM_CCOEFF_NORMED)
    _, peak, _, loc = cv2.minMaxLoc(res)
    ox, oy = loc[0] * red, loc[1] * red
    W = np.array([[ratio, 0, -ox * ratio], [0, ratio, -oy * ratio]], np.float32)
    T, I = feat(b, 2.0), feat(a, 2.0 * ratio)
    Iw = cv2.warpAffine(I, W, (b.shape[1], b.shape[0]), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    mask = np.zeros(b.shape, np.uint8)
    mask[oy:oy + int(a.shape[0] / ratio), ox:ox + int(a.shape[1] / ratio)] = 1
    D = np.eye(2, 3, dtype=np.float32)
    cc, D = cv2.findTransformECC(T, Iw, D, cv2.MOTION_AFFINE,
                                 (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-7), mask, 5)
    W = (np.vstack([W, [0, 0, 1]]) @ np.vstack([D, [0, 0, 1]]))[:2]
    return W.astype(float), float(peak), float(cc)


def grid_guess(plan, i, im, rgb, done, buildings, local, frame, style):
    """Sheets of one plan series abut along their map frames. For a sheet that cannot be fitted on its
    own, try every fitted sheet's eight neighbouring frame positions; keep the one that puts the OSM
    buildings on the plan's building lines clearly better than any other (median < 3 m, and the
    runner-up at least 1.5 times worse)."""
    lines = dcfg.mask(rgb, style).astype(np.uint8)
    dt = ndimage.distance_transform_edt(lines == 0).astype(np.float32)
    fx0, fy0, fx1, fy1 = frame
    g = np.stack(np.meshgrid(np.linspace(fx0, fx1, 12), np.linspace(fy0, fy1, 12)), -1).reshape(-1, 2)
    M = outline_points(buildings, local)
    cands = []
    for d, prev in enumerate(done):
        if prev is None:  # a sheet left out
            continue
        im_d, model_d = prev
        dx0, dy0, dx1, dy1 = pg.sheet_frame(plan, d, im_d)
        for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            off = np.array([dx0 + sx * (dx1 - dx0) - fx0, dy0 + sy * (dy1 - dy0) - fy0], float)
            cand = pg.PolyModel.fit(g, model_d(g + off), 1, np.array(im.size, float) / 2, im.size[0] / 3)
            q = cand.inverse(im.size)(M)
            ok = (q[:, 0] > fx0) & (q[:, 0] < fx1 - 1) & (q[:, 1] > fy0) & (q[:, 1] < fy1 - 1)
            if ok.sum() < 500:
                continue
            m_per_px = math.sqrt(abs(np.linalg.det(cand.coef[1:3, :2]))) / cand.scale
            dd = ndimage.map_coordinates(dt, [q[ok, 1], q[ok, 0]], order=1) * m_per_px
            cands.append((float(np.median(dd)), d, sx, sy, cand))
    cands.sort(key=lambda c: c[0])
    # Two neighbours can predict the same place (the sheet is east of one and south of another): the
    # runner-up is the best candidate somewhere else (centre more than 10 m away).
    if cands:
        c0 = cands[0][4](np.array([[(fx0 + fx1) / 2, (fy0 + fy1) / 2]]))[0]
        cands = cands[:1] + [c for c in cands[1:] if np.hypot(*(c[4](np.array([[(fx0 + fx1) / 2, (fy0 + fy1) / 2]]))[0] - c0)) > 10]
    if not cands or cands[0][0] > 3.0 or (len(cands) > 1 and cands[1][0] < 1.5 * cands[0][0]):
        raise SystemExit(f"sheet {i}: no street names, and no neighbour position fits the buildings "
                         f"({[(round(c[0], 1), c[1], c[2], c[3]) for c in cands[:3]]})")
    med, d, sx, sy, cand = cands[0]
    print(f"  placed beside sheet {d} ({sx:+d}, {sy:+d}): buildings median {med:.2f} m (next best {cands[1][0] if len(cands) > 1 else float('nan'):.2f} m)")
    return cand, {"gridNeighbour": [d, sx, sy], "gridBuildingMedianM": round(med, 2)}


def fit_sheet(cfg, i, im, ocr, local, rings, bbox, roads_index, buildings, done=()):
    """The georeference of sheet i (a plan_georef.PolyModel) and a report of every check.
    done: [(image, model)] of the sheets fitted before, for a sheet registered to another one
    (plan.register_to[i]: an overview sheet without street names)."""
    import osm_ref
    from shapely.geometry import Polygon
    plan = cfg["plan"]
    dpi = plan.get("image_dpi") or (im.info.get("dpi") or (None,))[0]
    if not dpi or not plan.get("scales"):
        raise SystemExit("plan.scales (and the image's dpi, or plan.image_dpi) are needed for an image plan")
    s0 = plan["scales"][i] * 0.0254 / float(dpi)  # metres per pixel at the stated scale
    rgb = np.asarray(im.convert("RGB"), dtype=np.int16)
    alpha = np.asarray(im.getchannel("A"))
    frame = pg.sheet_frame(plan, i, im)
    report = {"sheet": i, "scale": plan["scales"][i], "mPerPxNominal": round(s0, 4)}
    # Only the settlement's own buildings: the sheet also shows the neighbours' land, without the base map.
    from shapely.geometry import Point
    settlement = Polygon(rings[0])
    buildings = [b for b in buildings if settlement.contains(Point(b[0]))]
    print(f"  scale 1:{plan['scales'][i]} at {float(dpi):.0f} dpi -> {s0:.3f} m/px")

    ref = (plan.get("register_to") or [None] * (i + 1))[i]
    matches = []
    if isinstance(ref, dict):
        # 1-3''. A sheet of another regulation's plan (same drawing base, e.g. two adjacent KÉSZ of one
        # district), already fitted: {"key", "sheet", "crop": [x0, y0, x1, y1] of THIS sheet}. The crop
        # (base map that both plans draw) is found in the other sheet; its fit then places this one.
        import json
        from PIL import Image
        rcfg = dcfg.load(ref["key"])
        saved = json.loads((pg.ROOT / "scripts" / "plans" / f"{ref['key']}.json").read_text())
        if [round(v, 9) for v in saved["local"]] != [round(local.lng0, 9), round(local.lat0, 9)]:
            raise SystemExit(f"sheet {i}: {ref['key']} was fitted in another local frame")
        f = saved["sheets"][ref["sheet"]]
        ref_model = pg.PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])
        other = Image.open(dcfg.sheet_paths(rcfg)[ref["sheet"]]).convert("RGB")
        x0c, y0c, x1c, y1c = ref["crop"]
        # metres per pixel here / metres per pixel there = crop px per other-sheet px (1 when alike)
        r_dpi = rcfg["plan"].get("image_dpi") or dpi
        ratio = (plan["scales"][i] / float(dpi)) / (rcfg["plan"]["scales"][ref["sheet"]] / float(r_dpi))
        # Fills and labels differ between the two plans; only the base map lines (ref["style"], e.g. the
        # blue plot lines) are compared.
        def lines(img):
            if not ref.get("style"):
                return img
            return Image.fromarray((dcfg.mask(np.asarray(img), ref["style"]) * 255).astype(np.uint8))
        if abs(ratio - 1) > 0.01:
            raise SystemExit(f"sheet {i}: register_to another plan needs the same scale and dpi")
        # Both plans are exports of the same base map at one scale: a translation. Normalised
        # cross-correlation of the line masks, coarse (1/4) then at full resolution around the peak.
        A = np.asarray(lines(other), np.float32) / 255
        B = np.asarray(lines(im.convert("RGB").crop((x0c, y0c, x1c, y1c))), np.float32) / 255
        red = 4
        sm = lambda g, k: cv2.GaussianBlur(cv2.resize(g, None, fx=1 / k, fy=1 / k, interpolation=cv2.INTER_AREA), (0, 0), 1.5)
        res = cv2.matchTemplate(sm(A, red), sm(B, red), cv2.TM_CCORR_NORMED)
        _, peak, _, (cx, cy) = cv2.minMaxLoc(res)
        x, y = cx * red, cy * red
        win = A[max(y - 12, 0):y + B.shape[0] + 12, max(x - 12, 0):x + B.shape[1] + 12]
        res2 = cv2.matchTemplate(cv2.GaussianBlur(win, (0, 0), 1.0), cv2.GaussianBlur(B, (0, 0), 1.0), cv2.TM_CCORR_NORMED)
        _, cc, _, (fx, fy) = cv2.minMaxLoc(res2)
        ox, oy = max(x - 12, 0) + fx, max(y - 12, 0) + fy
        Wi = np.array([[1.0, 0, ox], [0, 1.0, oy]])  # crop px -> other-sheet px
        g = np.stack(np.meshgrid(np.linspace(0, im.size[0], 15), np.linspace(0, im.size[1], 15)), -1).reshape(-1, 2)
        model = pg.PolyModel.fit(g, ref_model(np.column_stack([g - [x0c, y0c], np.ones(len(g))]) @ Wi.T), 1,
                                 np.array(im.size, float) / 2, im.size[0] / 3)
        params = similarity_of(model, im.size)
        print(f"  registered to {ref['key']} sheet {ref['sheet']}: match peak {peak:.2f}, fine {cc:.2f} at {ox},{oy}; rotation "
              f"{math.degrees(params[1]):+.3f}°, scale 1:{params[0] / s0 * plan['scales'][i]:.0f}")
        report.update({"registeredTo": ref, "matchPeak": round(peak, 3), "ecc": round(cc, 3)})
    elif ref is not None:
        # 1-3'. Overview sheet: register it to the detail sheet it overlaps, then use that one's fit.
        ref_im, ref_model = done[ref]
        W, peak, cc = register_to_sheet(im, ref_im, plan["scales"][i] / plan["scales"][ref])
        g = np.stack(np.meshgrid(np.linspace(0, im.size[0], 15), np.linspace(0, im.size[1], 15)), -1).reshape(-1, 2)
        model = pg.PolyModel.fit(g, ref_model(np.column_stack([g, np.ones(len(g))]) @ W.T), 1, np.array(im.size, float) / 2, im.size[0] / 3)
        params = similarity_of(model, im.size)
        print(f"  registered to sheet {ref}: match peak {peak:.2f}, ECC {cc:.2f}; rotation {math.degrees(params[1]):+.3f}°, "
              f"scale 1:{params[0] / s0 * plan['scales'][i]:.0f}")
        report.update({"registeredTo": ref, "matchPeak": round(peak, 3), "ecc": round(cc, 3)})
    else:
        # 1-3. Street names -> votes -> similarity.
        # Streets of the settlement and just around it (plan.street_buffer_deg: wider for a plan that
        # shows mostly its neighbours' streets, e.g. a small area on a district boundary).
        streets = osm_streets(osm_ref.named_roads(bbox), local, Polygon(rings[0]).buffer(plan.get("street_buffer_deg", 0.003)))
        labels = []
        for l in ocr["labels"]:
            cx, cy = np.array(l["box"], float).mean(0)
            if l["conf"] > 0.6 and 0 <= cy < alpha.shape[0] and 0 <= cx < alpha.shape[1] and alpha[int(cy), int(cx)] > 0:
                labels.append(l)
        matches = match_labels(labels, streets)
        print(f"  {len(matches)} OCR lines name one of {len(streets)} OSM streets of the settlement")
        if len(matches) < plan.get("min_street_labels", 6) or i in plan.get("force_grid", []):  # forest; or a sheet whose names mislead
            if not (plan.get("grid_fallback") and done):
                raise SystemExit(f"sheet {i}: only {len(matches)} street names matched; set plan.register_to or check the OCR")
            # A sheet without street names (forest, railway yard): placed next to a fitted sheet of the
            # same series, then refined on the buildings like any other.
            style = cfg.get("styles", {}).get("building_line", {"max": [70, 70, 70]})
            model, info = grid_guess(plan, i, im, rgb, done, buildings, local, frame, style[i] if isinstance(style, list) else style)
            params = similarity_of(model, im.size)
            matches = []
            report.update(info)
        else:
            xs, ys = local.to_m(rings[0][:, 0], rings[0][:, 1])
            pad = 1500
            extent = (xs.min() - pad - im.size[0] * s0, ys.min() - pad, xs.max() + pad, ys.max() + pad + im.size[1] * s0)
            # Search ranges (plan.rotation_search_deg / plan.scale_search: [from, to, step]) for plans not drawn
            # grid-north up or printed at another size than stated.
            ra, sa = plan.get("rotation_search_deg", [-1.5, 1.5, 0.25]), plan.get("scale_search", [0.97, 1.03, 0.01])
            s, theta, t, _ = vote(matches, streets, s0, extent, np.radians(np.arange(ra[0], ra[1] + 1e-6, ra[2])), np.arange(sa[0], sa[1] + 1e-6, sa[2]))
            s, theta, t, res = refine_labels(matches, streets, s, theta, t)
            inl = res < NEAR_STREET_M
            print(f"  street-name fit: {inl.sum()}/{len(res)} labels on their street, median {np.median(res[inl]):.1f} m, "
                  f"90% {np.percentile(res[inl], 90):.1f} m; rotation {math.degrees(theta):+.3f}°, scale 1:{s / s0 * plan['scales'][i]:.0f}")
            params = np.array([s, theta, *t])
            model = as_model(s, theta, t, im.size)
            report.update({"labelsMatched": len(matches), "labelsOnStreet": int(inl.sum()),
                           "labelResidualMedianM": round(float(np.median(res[inl])), 2)})
            if plan.get("grid_fallback") and done and (inl.sum() < max(4, 0.6 * len(res)) or np.median(res[inl]) > 5):
                print("  street-name fit weak: trying the neighbour positions")
                style = cfg.get("styles", {}).get("building_line", {"max": [70, 70, 70]})
                model, info = grid_guess(plan, i, im, rgb, done, buildings, local, frame, style[i] if isinstance(style, list) else style)
                params = similarity_of(model, im.size)
                matches = []
                report.update(info)

    # 4. OSM building outlines onto the plan's building lines (chamfer), similarity only.
    line_style = cfg.get("styles", {}).get("building_line", {"max": [70, 70, 70]})
    if isinstance(line_style, list):  # per sheet (an overview sheet draws the base map fainter)
        line_style = line_style[i]
    d0, dt, _ = chamfer(model, rgb, buildings, local, frame, line_style)
    print(f"  buildings: median distance to a plan line {np.median(d0):.2f} m, {(d0 < 1.0).mean():.0%} within 1 m")
    report["buildingMedianM_initial"] = round(float(np.median(d0)), 2)
    M = outline_points(buildings, local)
    x0, y0, x1, y1 = frame
    q = to_px(params, M)
    on = (q[:, 0] > x0 + 20) & (q[:, 0] < x1 - 20) & (q[:, 1] > y0 + 20) & (q[:, 1] < y1 - 20)
    on[on] &= alpha[q[on, 1].astype(int), q[on, 0].astype(int)] > 0
    M = M[on]
    if len(M) > 500:
        def f(p):
            qq = to_px(p, M)
            return np.minimum(ndimage.map_coordinates(dt, [qq[:, 1], qq[:, 0]], order=1, mode="nearest") * p[0], 3.0)

        sol = least_squares(f, params, x_scale=[params[0] * 0.002, 0.0005, 0.5, 0.5], loss="soft_l1", f_scale=0.7)
        shift = float(np.hypot(*(sol.x[2:] - params[2:])))
        model2 = as_model(sol.x[0], sol.x[1], sol.x[2:], im.size)
        d1, _, _ = chamfer(model2, rgb, buildings, local, frame, line_style)
        print(f"  building fit: moved {shift:.1f} m, rotation {math.degrees(sol.x[1]):+.3f}°, scale 1:{sol.x[0] / s0 * plan['scales'][i]:.0f}; "
              f"buildings median {np.median(d1):.2f} m, {(d1 < 1.0).mean():.0%} within 1 m")
        report.update({"buildingFitShiftM": round(shift, 2), "buildingMedianM": round(float(np.median(d1)), 2),
                       "buildingWithin1m": round(float((d1 < 1.0).mean()), 3)})
        if np.median(d1) < 0.95 * np.median(d0) and shift < 25:  # a clear gain only
            model, params = model2, sol.x
    report.update({"rotationDeg": round(math.degrees(params[1]), 4), "scaleFactor": round(float(params[0] / s0), 5)})

    # Independent checks: OSM road crossings against the centres of the plan's street bands, and the
    # street names again.
    if roads_index is not None and cfg.get("styles", {}).get("street"):
        try:
            banded = pg.refine(model, im, roads_index, final_order=1, style=cfg["styles"]["street"])
            g = np.stack(np.meshgrid(np.linspace(x0, x1, 20), np.linspace(y0, y1, 20)), -1).reshape(-1, 2)
            diff = np.hypot(*(banded(g) - model(g)).T)
            print(f"  street-band crossings fit differs from the final fit by median {np.median(diff):.1f} m, max {diff.max():.1f} m")
            report["streetBandFitDiffMedianM"] = round(float(np.median(diff)), 2)
        except Exception as e:  # too few crossings (an overview sheet)
            print(f"  street-band check skipped: {e}")
    checks = [report.get("buildingMedianM", report["buildingMedianM_initial"])]
    if matches:
        res, _ = street_residuals(matches, streets, params[0], params[1], params[2:])
        report["labelResidualMedianM_final"] = round(float(np.median(res[res < NEAR_STREET_M])), 2)
        checks.append(report["labelResidualMedianM_final"])
    # plan.max_building_median_m: a stricter bar for the buildings check than the general residual limit.
    if plan.get("max_building_median_m") and checks[0] > plan["max_building_median_m"]:
        raise SystemExit(f"sheet {i}: buildings median {checks[0]} m > {plan['max_building_median_m']} m; not georeferenced")
    if max(checks) > MAX_RESIDUAL_M:
        raise SystemExit(f"sheet {i}: residual {max(checks)} m > {MAX_RESIDUAL_M} m; not georeferenced")
    return model, report


