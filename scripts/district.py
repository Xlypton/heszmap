"""Per-district configuration: districts/<key>.json, merged over DEFAULTS.

Everything the plan pipeline needs to know about one municipality's plan lives there: where the
regulation and its plan annexes are, how to turn the annexes into sheet images, and how the plan
draws each element ("styles"). Styles start from the plan's own legend (plan_legend.py) and can be
corrected by hand; the defaults are the conventions most Hungarian plans follow.

A style is a colour rule evaluated on RGB pixels (int16 arrays):
  min / max      per-channel bounds, e.g. yellow street fill
  tint           {"channel": 0|1|2, "min": n}: that channel exceeds the mean of the other two by n
  margin         {"channel": c, "min": n}: that channel exceeds the max of the other two by n
  others_max     the two other channels stay below this
  lum_max        mean of the channels below this (paper is ~250)
"""
import copy
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "scripts" / ".cache"

DEFAULTS = {
    "plan": {"dpi": 300, "minzoom": 13, "maxzoom": 18},
    "styles": {
        # Parcel lines: thin, dark blue-tinted (the national cadastral base map convention).
        "parcel_line": {"tint": {"channel": 2, "min": 18}, "lum_max": 235},
        # Zone codes: bold saturated blue lettering ("Építési övezet, övezet jele").
        "zone_code": {"margin": {"channel": 2, "min": 90}, "others_max": 90},
        # Zone boundary ("Építési övezet, övezet határa") and regulation line: red.
        "zone_boundary": {"min": [171, 0, 0], "max": [255, 109, 109], "pattern": "dots", "join_px": 7, "thin_px": 2},
        "regulation_line": {"min": [181, 0, 0], "max": [255, 119, 119]},
        # Public roads: yellow fill.
        "street": {"min": [226, 216, 0], "max": [255, 255, 199]},
    },
}


def _merge(a, b):
    out = copy.deepcopy(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(key: str) -> dict:
    cfg = json.loads((ROOT / "districts" / f"{key}.json").read_text())
    cfg = _merge(DEFAULTS, cfg)
    cfg["key"] = key
    return cfg


def work_dir(key: str) -> Path:
    d = WORK / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def sheet_paths(cfg: dict) -> list[Path]:
    """The sheet images plan_sheets.py made from the plan annexes (one per sheet)."""
    d = work_dir(cfg["key"])
    return sorted(d.glob("sheet*.png")) + sorted(d.glob("sheet*.jpg"))


def mask(rgb: np.ndarray, style: dict) -> np.ndarray:
    """Pixels matching a colour rule (see the module docstring)."""
    rgb = rgb.astype(np.int16)
    m = np.ones(rgb.shape[:2], bool)
    if "min" in style:
        m &= (rgb >= np.array(style["min"])).all(-1)
    if "max" in style:
        m &= (rgb <= np.array(style["max"])).all(-1)
    for rule, use_max in (("tint", False), ("margin", True)):
        if rule in style:
            c = style[rule]["channel"]
            o = [i for i in range(3) if i != c]
            other = np.maximum(rgb[..., o[0]], rgb[..., o[1]]) if use_max else (rgb[..., o[0]] + rgb[..., o[1]]) / 2
            m &= (rgb[..., c] - other) > style[rule]["min"]
    if "others_max" in style:
        c = (style.get("margin") or style.get("tint"))["channel"]
        o = [i for i in range(3) if i != c]
        m &= np.maximum(rgb[..., o[0]], rgb[..., o[1]]) < style["others_max"]
    if "lum_max" in style:
        m &= rgb.mean(-1) < style["lum_max"]
    return m
