"""The area a partial KÉSZ plan regulates, read from the plan itself, written as plan.clip.

    python3 scripts/plan_area.py <key> <close_m> <note> <lng> <lat> [rail,<street name>,...]

With plan.area_line (a colour rule for the plan's own boundary line, e.g. XI. KÉSZ 1: 50% red dashes, district.py over_grey), the
area is a flood fill from the point (lng, lat) inside it, walled by: the line's dashes (small blobs of
that colour, max-pooled from full resolution and dilated by close_m), everything outside the district,
optionally the OSM railway lines / named streets the decree names as the boundary, and hand-drawn
walls (plan.area_walls_px) where the line has gaps. plan.area_seeds adds start points for pieces that
inner walls cut off; plan.area_fill_m closes inlets left by zone fills of the line's colour.
plan.area_line_blob = [min px, max px, max side px] keeps only dash-sized blobs at full resolution
(XI. KÉSZ 1, where a semi-transparent line rule also matches hatched fills); plan.area_line_gap_m
closes gaps up to that long where dashes hide under other symbols. Every flooded piece is kept
(clip.polygons when there are several).
Without plan.area_line: the coloured part of the sheet (zone fills), closed over streets; plan.area_colour
(a colour rule, at full size) for fills drawn as thin hatching, plan.area_open_m to drop narrow strips,
plan.area_walls_px / plan.area_cut_px (polygons) to cut off parts by hand.
Uses the saved fit (scripts/plans/<key>.json); run plan_georef.py again afterwards to clip tiles/labels.
Check the result: scripts/.cache/<key>-area.geojson."""
import json, sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from shapely.geometry import Polygon, shape
sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg
import plan_georef as pg
Image.MAX_IMAGE_PIXELS = None
W = str(Path(__file__).resolve().parent.parent) + '/'
key, close_m, note = sys.argv[1], float(sys.argv[2]), sys.argv[3]
cfg = dcfg.load(key)
fit = json.load(open(W + f'scripts/plans/{key}.json'))
local = pg.Local(*fit['local'])
polys = []
for i, (path, f) in enumerate(zip(dcfg.sheet_paths(cfg), fit['sheets'])):
    if f.get('skipped'):
        continue
    model = pg.PolyModel(f['order'], np.array(f['coef']), np.array(f['centre']), f['scale'])
    k = 4
    im = np.asarray(Image.open(path).convert('RGB').reduce(k), dtype=np.int16)
    sat = im.max(-1) - im.min(-1)
    col = (sat > 50) & (im.max(-1) > 90)
    fill = cfg['plan'].get('area_colour')  # zone fills drawn as thin hatching (XI. KÉSZ 8): a colour rule at full size, max-pooled
    if fill and not cfg['plan'].get('area_line'):
        full = dcfg.mask(np.asarray(Image.open(path).convert('RGB'), dtype=np.int16), fill).astype(np.uint8)
        H, Wd = im.shape[:2]
        full = np.pad(full, ((0, max(0, H * k - full.shape[0])), (0, max(0, Wd * k - full.shape[1]))))[:H * k, :Wd * k]
        col = full.reshape(H, k, Wd, k).max(axis=(1, 3)).astype(bool)
        del full
    line = cfg['plan'].get('area_line')  # the plan's own boundary line colour: {"min": [...], "max": [...]}
    if line:
        full = np.asarray(Image.open(path).convert('RGB'), dtype=np.int16)
        bf = dcfg.mask(full, line).astype(np.uint8)
        blob = cfg['plan'].get('area_line_blob')  # [min px, max px, max side px]: keep dash-sized blobs at full size
        if blob:
            n, lab, st, _ = cv2.connectedComponentsWithStats(bf, 8)
            ok = np.zeros(n, np.uint8)
            ok[1:] = (st[1:, 4] >= blob[0]) & (st[1:, 4] <= blob[1]) & (st[1:, 2] <= blob[2]) & (st[1:, 3] <= blob[2])
            bf = ok[lab]
            del lab
        H, Wd = im.shape[:2]
        bf = np.pad(bf, ((0, H * k - bf.shape[0]), (0, Wd * k - bf.shape[1])))
        b = bf.reshape(H, k, Wd, k).max(axis=(1, 3)).astype(np.uint8)  # max-pool: thin dashes survive
        del full, bf
        # The line is dashed: keep small blobs (dashes), not zone fills of the same colour.
        n, lab, stats, _ = cv2.connectedComponentsWithStats(b, 8)
        small = np.zeros(n, np.uint8); small[1:] = stats[1:, cv2.CC_STAT_AREA] < cfg['plan'].get('area_line_max_blob', 400)
        b = small[lab]
        r = max(1, int(close_m / (np.sqrt(abs(np.linalg.det(model(np.array([[1, 0], [0, 1], [0, 0]], float))[:2] - model(np.array([[0, 0]], float))))) * k)))
        b = cv2.dilate(b, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
        gap = cfg['plan'].get('area_line_gap_m')  # close gaps in the line up to this long (dashes hidden under fills)
        if gap:
            rg = int(gap / 2 / (close_m / r))
            b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rg + 1, 2 * rg + 1)))
        x, y = local.to_m(np.array([float(sys.argv[4])]), np.array([float(sys.argv[5])]))
        sx, sy = (model.inverse(Image.open(path).size)(np.column_stack([x, y]))[0] / k).astype(int)
        # Outside the district is wall too: the flood must not go round the plan's line through a
        # neighbouring district.
        geo = json.load(open(W + 'public/data/districts.geojson'))
        dpoly = shape(next(f['geometry'] for f in geo['features'] if f['properties']['id'] == cfg['district']))
        dring = np.array(dpoly.exterior.coords if dpoly.geom_type == 'Polygon' else max(dpoly.geoms, key=lambda p: p.area).exterior.coords)
        dx, dy = local.to_m(dring[:, 0], dring[:, 1])
        dpx = model.inverse(Image.open(path).size)(np.column_stack([dx, dy])) / k
        inside = np.zeros_like(b)
        cv2.fillPoly(inside, [np.round(dpx).astype(np.int32)], 1)
        b = np.maximum(b, 1 - inside)
        # Extra walls: OSM centre lines of named streets / railways that the decree names as the boundary
        # (argv[6]: "rail" and/or street names, comma separated), where the plan's line has gaps.
        if len(sys.argv) > 6:
            import osm_ref
            want = sys.argv[6].split(',')
            walls = []
            if 'rail' in want:
                walls += osm_ref.fetch(dpoly.bounds, road_classes={'rail'})[1]
            named = osm_ref.named_roads(dpoly.bounds)
            for n in want:
                walls += named.get(n, [])
            for ln in walls:
                ln = np.asarray(ln)
                if len(ln) < 2:
                    continue
                wx, wy = local.to_m(ln[:, 0], ln[:, 1])
                q = model.inverse(Image.open(path).size)(np.column_stack([wx, wy])) / k
                cv2.polylines(b, [np.round(q).astype(np.int32)], False, 1, 2)
        for x0, y0, x1, y1 in (cfg['plan'].get('area_walls_px') or {}).get(str(i), []):
            cv2.line(b, (x0 // k, y0 // k), (x1 // k, y1 // k), 1, 3)  # a gap in the plan's line, closed by hand
        free = (1 - b).copy()
        ff = np.zeros((free.shape[0] + 2, free.shape[1] + 2), np.uint8)
        inside_sheet = lambda px, py: 0 <= px < free.shape[1] and 0 <= py < free.shape[0]
        if inside_sheet(sx, sy) and free[sy, sx] == 1:  # several sheets: a seed counts on the sheets it falls on
            cv2.floodFill(free, ff, (int(sx), int(sy)), 2)
        for slng, slat in cfg['plan'].get('area_seeds', []):  # more seeds: pieces cut off by walls inside the area
            x2, y2 = local.to_m(np.array([slng]), np.array([slat]))
            px2 = (model.inverse(Image.open(path).size)(np.column_stack([x2, y2]))[0] / k).astype(int)
            if inside_sheet(px2[0], px2[1]) and free[px2[1], px2[0]] == 1:
                cv2.floodFill(free, np.zeros_like(ff), (int(px2[0]), int(px2[1])), 2)
        region = (free == 2).astype(np.uint8)
        import os
        if os.environ.get('DEBUGIMG'):  # walls black, flooded region green
            dbg = np.full(b.shape + (3,), 255, np.uint8); dbg[region == 1] = (150, 230, 150); dbg[b == 1] = (0, 0, 0)
            Image.fromarray(dbg).reduce(2).save(os.environ['DEBUGIMG'])
        region = cv2.dilate(region, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))  # back to the line's centre
        fill_m = cfg['plan'].get('area_fill_m')
        if fill_m:  # close inlets left by zone fills of the line's colour, then keep inside the district
            rf = int(fill_m / (close_m / r))
            region = cv2.morphologyEx(region, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rf + 1, 2 * rf + 1)))
            region &= inside
        for poly in (cfg['plan'].get('area_cut_px') or {}).get(str(i), []):  # parts known to be outside (another KÉSZ)
            cv2.fillPoly(region, [np.array(poly, np.int32) // k], 0)
        cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            print(f'sheet {i}: no seed inside the line')
            continue
        big = max(cv2.contourArea(c) for c in cnts)
        for c in cnts:  # every flooded piece (XI. KÉSZ 1: the railway corridor's walls split the area in two)
            if cv2.contourArea(c) < 0.02 * big:
                continue
            c = c[:, 0, :].astype(float) * k
            mx, my = model(c).T
            lng, lat = local.to_ll(mx, my)
            polys.append(Polygon(np.column_stack([lng, lat])).buffer(0))
        print(f'sheet {i}: boundary line, dilate {r} px, region {region.sum()} px')
        continue
    frame = (cfg['plan'].get('frames') or [None] * 99)[i]
    if frame:
        m = np.zeros_like(col); x0, y0, x1, y1 = [v // k for v in frame]; m[y0:y1, x0:x1] = True; col &= m
    mpp = np.sqrt(abs(np.linalg.det(model(np.array([[1, 0], [0, 1], [0, 0]], float))[:2] - model(np.array([[0, 0]], float))))) * k
    r = max(1, int(close_m / mpp))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    mask = cv2.morphologyEx(col.astype(np.uint8), cv2.MORPH_CLOSE, ker)
    ro = int(cfg['plan'].get('area_open_m', 0) / mpp) or r // 2  # plan.area_open_m: cut off strips narrower than twice this (road corridors drawn outside)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * ro + 1,) * 2))
    for x0, y0, x1, y1 in (cfg['plan'].get('area_walls_px') or {}).get(str(i), []):
        cv2.line(mask, (x0 // k, y0 // k), (x1 // k, y1 // k), 0, 3)  # cut off a strip drawn outside the area, by hand
    for poly in (cfg['plan'].get('area_cut_px') or {}).get(str(i), []):  # plan.area_cut_px: polygons (sheet px) known to be outside
        cv2.fillPoly(mask, [np.array(poly, np.int32) // k], 0)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)[:, 0, :].astype(float) * k
    mx, my = model(c).T
    lng, lat = local.to_ll(mx, my)
    polys.append(Polygon(np.column_stack([lng, lat])).buffer(0))
    print(f'sheet {i}: {mpp:.2f} m/px at 1/{k}, close {r} px, contour {len(c)} points')
geo = json.load(open(W + 'public/data/districts.geojson'))
dist = shape(next(f['geometry'] for f in geo['features'] if f['properties']['id'] == cfg['district']))
from shapely.ops import unary_union
area = unary_union(polys).intersection(dist).simplify(0.00003)
parts = [g for g in getattr(area, 'geoms', [area]) if g.geom_type == 'Polygon' and g.area > 0.02 * area.area]
print('bounds', [round(v, 4) for v in area.bounds], 'pieces', len(parts), 'points', sum(len(g.exterior.coords) for g in parts))
rings = [[[round(x, 7), round(y, 7)] for x, y in g.exterior.coords] for g in parts]
c = json.load(open(W + f'districts/{key}.json'))
c['plan']['clip'] = {"note": note, "keep": "inside", **({"polygon": rings[0]} if len(rings) == 1 else {"polygons": rings})}
open(W + f'districts/{key}.json', 'w').write(json.dumps(c, ensure_ascii=False, indent=2) + "\n")
json.dump({"type": "Feature", "properties": {}, "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}},
          open(W + f'scripts/.cache/{key}-area.geojson', 'w'))
