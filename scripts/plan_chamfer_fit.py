"""Place an image sheet with no usable street names or plot numbers on the BTP plot outlines, from one
hand-picked control point and a rough scale: a chamfer search (scale ±6%, rotation ±2°, shift ±40 m)
and least squares, then writes the saved fit (scripts/plans/<key>.json) for plan_georef.py --reuse-fit.

    python3 scripts/plan_chamfer_fit.py <key> <sheet> <px_x,px_y> <lng,lat> <m_per_px> <rot_deg> <frame x0,y0,x1,y1> <maxgrey>

Budapest XI. Lágymányosi-öböl KÉSZ 30/2016.: the only zone plan on njt is a 200 dpi A4 scan of the
consolidated sheet; one block corner (652,245 = 19.053417,47.468892) and 0.86 m/px (two features far
apart) were enough. The sheet's lines: dark pixels (max channel <= maxgrey) and the red zone borders,
which today's plot lines follow where the plan has been carried out."""
import sys, json, math, numpy as np
sys.path.insert(0, 'scripts')
from PIL import Image; from scipy import ndimage; from scipy.optimize import least_squares
from shapely.geometry import shape, box
import plan_georef as pg
Image.MAX_IMAGE_PIXELS = None
key, si = sys.argv[1], int(sys.argv[2]); P = np.array(sys.argv[3].split(','), float); LL = [float(v) for v in sys.argv[4].split(',')]
s0, r0 = float(sys.argv[5]), math.radians(float(sys.argv[6])); fr = [int(v) for v in sys.argv[7].split(',')]; mx = int(sys.argv[8])
cfg = json.load(open(f'districts/{key}.json')); roman = 'I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX XXI XXII XXIII'.split()[cfg['district'] - 1]
im = np.asarray(Image.open(f'scripts/.cache/{key}/sheet{si}.png').convert('RGB')).astype(int)
mask = (im.max(2) <= mx) | ((im[..., 0] > 140) & (im[..., 1] < 110) & (im[..., 2] < 120))
mask[:fr[1], :] = 0; mask[fr[3]:, :] = 0; mask[:, :fr[0]] = 0; mask[:, fr[2]:] = 0
dt = ndimage.distance_transform_edt(~mask).astype(np.float32)
geo = json.load(open('public/data/districts.geojson'))
dg = next(f['geometry'] for f in geo['features'] if f['properties']['id'] == cfg['district'])
allp = np.vstack([np.array(p[0]) for p in (dg['coordinates'] if dg['type'] == 'MultiPolygon' else [dg['coordinates']])])
local = pg.Local(float(allp[:, 0].mean()), float(allp[:, 1].mean()))  # the origin plan_georef uses
O = np.array(local.to_m(np.array([LL[0]]), np.array([LL[1]]))).ravel()
R = lambda t: np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
def to_m(p, prm):  # px -> local metres (y up)
    s, t, tx, ty = prm; u = np.column_stack([p[:, 0] - P[0], -(p[:, 1] - P[1])]) * s; return u @ R(t).T + [tx, ty] + O
def to_px(m, prm):
    s, t, tx, ty = prm; u = (m - [tx, ty] - O) @ R(t) / s; return np.column_stack([u[:, 0] + P[0], -u[:, 1] + P[1]])
corners = to_m(np.array([[fr[0], fr[1]], [fr[2], fr[3]]], float), [s0, r0, 0, 0])
lo, hi = corners.min(0) - 80, corners.max(0) + 80
g = json.load(open(f'scripts/.cache/btp/{roman}.geojson'))
pts = []
for f in g['features']:
    for poly in getattr(shape(f['geometry']), 'geoms', [shape(f['geometry'])]):
        r = np.asarray(poly.exterior.coords); x, y = local.to_m(r[:, 0], r[:, 1])
        if x.max() < lo[0] or x.min() > hi[0] or y.max() < lo[1] or y.min() > hi[1]: continue
        for a, b in zip(np.column_stack([x, y])[:-1], np.column_stack([x, y])[1:]):
            n = max(1, int(np.hypot(*(b - a)) / 1.0)); pts.append(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
M = np.vstack(pts); print(len(M), 'outline points')
def d(prm):
    q = to_px(M, prm); ok = (q[:, 0] > fr[0]) & (q[:, 0] < fr[2] - 1) & (q[:, 1] > fr[1]) & (q[:, 1] < fr[3] - 1)
    v = np.full(len(M), 8.0); v[ok] = ndimage.map_coordinates(dt, [q[ok, 1], q[ok, 0]], order=1) * prm[0]; return np.minimum(v, 8.0)
best = None
for s in np.arange(s0 * 0.94, s0 * 1.06, s0 * 0.01):
    for t in np.radians(np.arange(math.degrees(r0) - 2, math.degrees(r0) + 2.01, 0.5)):
        for tx in range(-40, 41, 4):
            for ty in range(-40, 41, 4):
                v = d([s, t, tx, ty])[::7].mean()
                if best is None or v < best[0]: best = (v, [s, t, tx, ty])
print('grid best', best[0], best[1][0], math.degrees(best[1][1]), best[1][2:])
sol = least_squares(d, best[1], x_scale=[s0 * 0.002, 0.0005, 0.5, 0.5], loss='soft_l1', f_scale=0.7)
dd = d(sol.x); inside = dd < 8
print('final: median %.2f m, %.0f%% within 1 m; m/px %.4f rot %.3f shift %.1f %.1f' % (np.median(dd[inside]), (dd[inside] < 1).mean() * 100, sol.x[0], math.degrees(sol.x[1]), *sol.x[2:]))
# PolyModel (order 1) for the saved fit
gx, gy = np.meshgrid(np.linspace(fr[0], fr[2], 10), np.linspace(fr[1], fr[3], 10)); G = np.column_stack([gx.ravel(), gy.ravel()])
h, w = im.shape[:2]
model = pg.PolyModel.fit(G, to_m(G, sol.x), 1, np.array([w, h], float) / 2, w / 3)
out = {"local": [local.lng0, local.lat0], "sheets": [{"sheet": f"sheet{si}.png", **model.to_json()}]}
json.dump(out, open(f'scripts/plans/{key}.json', 'w'), indent=1); print('wrote fit')
