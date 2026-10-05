"""Georeference a vector plan by matching its street network to OSM roads.

A plan's streets are corridors between plot lines (and regulation lines); an OSM road centre line,
placed correctly, runs inside such a corridor: a few metres from the lines on both sides, never on
a line, never out in empty paper. So:

  corridor score  G(p) = 1 where the distance from p to the plan's linework is 1.5–14 m, else 0
  fit score       S(T) = road length (OSM, transformed by T) on which G = 1

T is a similarity (scale, rotation, shift; plans have no shear). The search:
  - scale: from the plan's own "M = 1:2000" (and a few factors around it: PDFs are often
    printed to a different page size), or a wide sweep if none is printed;
  - rotation: a prior (e.g. from street names) ± a few degrees, else near north-up;
  - shift: for each scale and rotation, every shift at once by FFT cross-correlation;
then a local refinement of all four parameters on the continuous score.

No street names needed, so it works for village plans that name one or two streets.
"""
import math
import re

import cv2
import numpy as np
from scipy import ndimage, optimize
from scipy.signal import fftconvolve

CORRIDOR_M = (1.5, 14.0)  # a road centre line this far from the nearest plan line is in a corridor
COARSE_M = 2.0  # metres per pixel of the coarse search
CROSS_PENALTY = 3.0
INSIDE_M = 60  # within this distance of plan linework = inside the plan's drawn area


def nominal_scale(page_text: str):
    """m per PDF point from the plan's printed scale ("M = 1:2000", "M 1:2 000", "1:4000")."""
    m = re.search(r"\bM\s*=?\s*1\s*:\s*(\d{1,2}[ .]?\d{3})\b", page_text) or re.search(r"\b1\s*:\s*(\d{1,2}[ .]?\d{3})\b", page_text)
    if not m:
        return None
    denom = int(re.sub(r"\D", "", m.group(1)))
    return denom * 0.0254 / 72  # 1 pt = 1/72 inch on paper


def _raster_lines(lines, to_px, shape, width=1):
    img = np.zeros(shape, np.uint8)
    for ln in lines:
        p = to_px(np.asarray(ln))
        cv2.polylines(img, [np.round(p).astype(np.int32)], False, 1, width)
    return img


def corridor_map(plan_lines_pt, page_wh, m_per_pt, res):
    """G on a grid of `res` metres per pixel over the page (plan points scaled to metres)."""
    w, h = page_wh[0] * m_per_pt / res, page_wh[1] * m_per_pt / res
    shape = (int(h) + 1, int(w) + 1)
    lines = _raster_lines(plan_lines_pt, lambda p: p * m_per_pt / res, shape)
    dist = ndimage.distance_transform_edt(lines == 0) * res
    # Plot lines are dense (a plot every ~20 m), so most of a plan is within 14 m of a line: being
    # near lines proves little. What a wrong placement cannot avoid is crossing them: a road that
    # cuts across plots costs CROSS_PENALTY per pixel on a line.
    # Also, a bigger placement simply covers more OSM road: road inside the plan's drawn area but
    # not in a corridor counts against (-1), so the score is hits minus misses, not just hits.
    G = np.where(dist < INSIDE_M, -1.0, 0.0).astype(np.float32)
    G[(dist >= CORRIDOR_M[0]) & (dist <= CORRIDOR_M[1])] = 1.0
    G[dist < max(res, 0.8)] = -CROSS_PENALTY
    return G, dist


def _roads_raster(roads_m, theta, res):
    """OSM roads (local metres, y north) rotated by theta into page orientation (y down), rastered."""
    c, s = math.cos(theta), math.sin(theta)
    pts = [np.column_stack([c * r[:, 0] - s * r[:, 1], -(s * r[:, 0] + c * r[:, 1])]) for r in roads_m]
    allp = np.vstack(pts)
    lo = allp.min(0)
    shape = (int((allp[:, 1].max() - lo[1]) / res) + 2, int((allp[:, 0].max() - lo[0]) / res) + 2)
    img = _raster_lines(pts, lambda p: (p - lo) / res, shape)
    return img.astype(np.float32), lo


def _transform(params, m_per_pt0):
    """params = (log scale factor, theta, tx, ty): page point -> local metres (y north)."""
    lf, theta, tx, ty = params
    k = m_per_pt0 * math.exp(lf)
    c, s = math.cos(theta), math.sin(theta)
    # page (x right, y down) -> metres page-oriented (x, -y) -> rotate by -theta -> shift
    R = np.array([[c, s], [-s, c]])  # inverse of the rotation used for the roads raster
    A = np.zeros((3, 2))
    A[:2] = (k * R @ np.diag([1, -1])).T
    A[2] = [tx, ty]
    return A


def match(plan_lines_pt, page_wh, roads_lnglat, local, page_text="", theta_prior=None, log=print):
    """Returns (A: page pt -> local metres as 3x2 affine, info) or (None, info)."""
    roads_m = []
    for r in roads_lnglat:
        x, y = local.to_m(r[:, 0], r[:, 1])
        if len(x) >= 2:
            roads_m.append(np.column_stack([x, y]))
    if not roads_m or not plan_lines_pt:
        return None, {"ok": False, "why": "no roads or no plan lines"}
    nominal = nominal_scale(page_text)
    if nominal:
        scales = [nominal * 2 ** (k / 4) for k in range(-12, 5)]  # PDFs are often shrunk to fit a sheet
    else:
        scales = [0.05 * 2 ** (k / 4) for k in range(0, 26)]
    priors = [0.0] if theta_prior is None else [0.0, theta_prior, -theta_prior]
    thetas = np.unique(np.round(np.concatenate([np.radians(np.arange(-8, 8.1, 1.0)) + p for p in priors]), 4))
    best = (-1, None)
    for k in scales:
        G, _ = corridor_map(plan_lines_pt, page_wh, k, COARSE_M)
        for th in thetas:
            R, lo = _roads_raster(roads_m, th, COARSE_M)
            # Score of every shift: correlate the road raster with the corridor map.
            corr = fftconvolve(G, R[::-1, ::-1], mode="full")
            iy, ix = np.unravel_index(np.argmax(corr), corr.shape)
            score = corr[iy, ix] * COARSE_M
            if score > best[0]:
                # Road raster pixel (0,0) lands on G pixel (iy - R.h + 1, ix - R.w + 1).
                oy, ox = iy - R.shape[0] + 1, ix - R.shape[1] + 1
                best = (score, (k, th, lo, ox, oy))
    score, (k, th, lo, ox, oy) = best
    # Page point p (pt) -> page metres q = p*k (y down). A road point r_m maps to q via
    # q = rot(th)(r_m) flipped + (-lo) + (ox, oy)*res. Invert to get page -> local metres.
    shift = np.array([ox, oy]) * COARSE_M - lo  # q = Rf(r) + shift, Rf = rotate then flip y
    c, s = math.cos(th), math.sin(th)
    Rf = np.array([[c, -s], [-(s), -c]])  # r -> (c x - s y, -(s x + c y))
    Rinv = np.linalg.inv(Rf)
    # r = Rinv (q - shift) = Rinv (k p - shift)
    A = np.zeros((3, 2))
    A[:2] = (Rinv * k).T
    A[2] = -Rinv @ shift
    total = sum(np.hypot(*np.diff(r, axis=0).T).sum() for r in roads_m)
    log(f"  road match coarse: scale {k:.3f} m/pt, rotation {math.degrees(th):.1f}°, {score:.0f} m of road in corridors")
    A, fine = refine(A, plan_lines_pt, page_wh, roads_m, k)
    info = {"ok": True, "method": "road network", "m_per_pt": round(fine["m_per_pt"], 4),
            "rotation_deg": round(fine["rotation_deg"], 2), "nominal_m_per_pt": round(nominal, 4) if nominal else None,
            "road_in_corridor_m": round(fine["matched_m"]), "road_on_plan_m": round(fine["on_plan_m"]),
            "corridor_share": round(fine["matched_m"] / max(fine["on_plan_m"], 1), 3), "osm_road_m": round(total)}
    return A, info


def refine(A, plan_lines_pt, page_wh, roads_m, k, res=0.5):
    """Local optimisation of the similarity on a smooth version of the corridor score."""
    G, dist = corridor_map(plan_lines_pt, page_wh, k, res)
    smooth = ndimage.gaussian_filter(G, 2.0)
    inside = np.zeros_like(G)
    inside[:] = dist < INSIDE_M  # within the plan's drawn area
    samples = []
    for r in roads_m:
        seg = np.diff(r, axis=0)
        for a, d in zip(r[:-1], seg):
            n = max(int(np.hypot(*d) / 2), 1)
            samples.append(a + d * (np.arange(n)[:, None] / n))
    S = np.vstack(samples)
    Ainv0 = _inverse(A)

    def page_px(params, P):
        """local metres -> page px of the res grid, after a small similarity tweak of A^-1."""
        ds, dth, dx, dy = params
        c, s = math.cos(dth), math.sin(dth)
        Pm = (P - P.mean(0)) @ np.array([[c, -s], [s, c]]).T * math.exp(ds) + P.mean(0) + [dx, dy]
        p = np.hstack([Pm, np.ones((len(Pm), 1))]) @ Ainv0  # page points
        return p * k / res

    def cost(params, grid=smooth):
        q = page_px(params, S)
        v = ndimage.map_coordinates(grid, [q[:, 1], q[:, 0]], order=1, mode="constant")
        return -v.sum()

    x0 = np.zeros(4)
    r = optimize.minimize(cost, x0, method="Powell", options={"xtol": 1e-4, "ftol": 1e-6, "maxiter": 4000})
    params = r.x
    q = page_px(params, S)
    on = ndimage.map_coordinates(inside, [q[:, 1], q[:, 0]], order=0, mode="constant") > 0
    hit = ndimage.map_coordinates(G, [q[:, 1], q[:, 0]], order=0, mode="constant") > 0.5
    # (G < 0 on lines: those samples are not "in a corridor")
    # Rebuild A from the tweak: fit page->metres on the sample correspondences.
    P_page = q * res / k
    X = np.hstack([P_page, np.ones((len(P_page), 1))])
    A_new, *_ = np.linalg.lstsq(X, S, rcond=None)
    m_per_pt = math.sqrt(abs(np.linalg.det(A_new[:2])))
    rot = math.degrees(math.atan2(A_new[0, 1], A_new[0, 0]))
    return A_new, {"matched_m": float(hit.sum() * 2), "on_plan_m": float(on.sum() * 2), "m_per_pt": m_per_pt, "rotation_deg": rot}


def _inverse(A):
    """3x2 affine (p -> m) to its inverse (m -> p)."""
    M = np.vstack([A.T, [0, 0, 1]])  # [[a b tx],[c d ty],[0 0 1]] acting on (px, py, 1)
    Minv = np.linalg.inv(M)
    return Minv[:2].T
