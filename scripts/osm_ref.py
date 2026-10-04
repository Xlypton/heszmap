"""Reference geometry for aligning plans: building outlines and road centrelines from the same
OpenFreeMap (OpenMapTiles) vector tiles the app's basemap is drawn from, so the plan lines up with
what users see underneath it.
"""
import json
import math
import urllib.request
from pathlib import Path

import mapbox_vector_tile
import numpy as np

CACHE = Path(__file__).resolve().parent / ".cache"
TILEJSON = "https://tiles.openfreemap.org/planet"
Z = 14  # max zoom of the OpenMapTiles schema: full-detail geometry, 4096 units per tile
ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "minor", "service"}


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "heszmap/0.1"}), timeout=60) as r:
        return r.read()


def _tile_range(lng0, lat0, lng1, lat1):
    def tx(lng):
        return int((lng + 180) / 360 * 2 ** Z)

    def ty(lat):
        s = math.sin(math.radians(lat))
        return int((0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * 2 ** Z)

    return range(tx(lng0), tx(lng1) + 1), range(ty(lat1), ty(lat0) + 1)


def _to_lnglat(x, y, tx, ty, extent):
    n = 2 ** Z
    lng = (tx + x / extent) / n * 360 - 180
    merc_y = ty + 1 - y / extent  # MVT y grows downwards; mapbox_vector_tile flips it to grow upwards
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * merc_y / n))))
    return lng, lat


def fetch(bbox):
    """Returns (building rings, road lines) as lists of (n, 2) lng/lat arrays."""
    CACHE.mkdir(exist_ok=True)
    template = json.loads(_get(TILEJSON))["tiles"][0]
    buildings, roads = [], []
    xs, ys = _tile_range(*bbox)
    for tx in xs:
        for ty in ys:
            path = CACHE / f"ofm_{Z}_{tx}_{ty}.pbf"
            if not path.exists():
                path.write_bytes(_get(template.format(z=Z, x=tx, y=ty)))
            tile = mapbox_vector_tile.decode(path.read_bytes())
            for f in tile.get("building", {}).get("features", []):
                g = f["geometry"]
                polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]] if g["type"] == "Polygon" else []
                ext = tile["building"]["extent"]
                for poly in polys:
                    for ring in poly:
                        buildings.append(np.array([_to_lnglat(x, y, tx, ty, ext) for x, y in ring]))
            for f in tile.get("transportation", {}).get("features", []):
                if f["properties"].get("class") not in ROAD_CLASSES:
                    continue
                g = f["geometry"]
                lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]] if g["type"] == "LineString" else []
                ext = tile["transportation"]["extent"]
                for line in lines:
                    roads.append(np.array([_to_lnglat(x, y, tx, ty, ext) for x, y in line]))
    return buildings, roads


def densify(lines, local, step=0.5):
    """Points every `step` metres along polylines, in local metres."""
    out = []
    for ln in lines:
        x, y = local.to_m(ln[:, 0], ln[:, 1])
        for i in range(len(x) - 1):
            d = math.hypot(x[i + 1] - x[i], y[i + 1] - y[i])
            k = max(int(d / step), 1)
            t = np.arange(k) / k
            out.append(np.column_stack([x[i] + (x[i + 1] - x[i]) * t, y[i] + (y[i + 1] - y[i]) * t]))
    return np.vstack(out) if out else np.zeros((0, 2))


def named_roads(bbox):
    """Complete street geometry by name (all OSM ways of a street), from the transportation_name layer."""
    template = json.loads(_get(TILEJSON))["tiles"][0]
    out = {}
    xs, ys = _tile_range(*bbox)
    for tx in xs:
        for ty in ys:
            path = CACHE / f"ofm_{Z}_{tx}_{ty}.pbf"
            if not path.exists():
                path.write_bytes(_get(template.format(z=Z, x=tx, y=ty)))
            tile = mapbox_vector_tile.decode(path.read_bytes())
            layer = tile.get("transportation_name", {})
            for f in layer.get("features", []):
                name = f["properties"].get("name:hu") or f["properties"].get("name")
                g = f["geometry"]
                if not name or g["type"] not in ("LineString", "MultiLineString"):
                    continue
                lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
                for line in lines:
                    out.setdefault(name, []).append(np.array([_to_lnglat(x, y, tx, ty, layer["extent"]) for x, y in line]))
    return out
