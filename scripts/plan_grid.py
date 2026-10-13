"""Place the sheets of a regular sheet grid that could not be fitted on their own (rural sheets with no
street names and few buildings), from the sheets that were.

A plan series drawn on one map projection is a grid: sheet (col, row) is the sheet at (0, 0) shifted by
col frame widths and row frame heights (Budapest XXIII.: SZT-1…31, 1:2000, abutting along their dashed
sheet boundaries, which are the configured frames). One affine map from grid-plan pixels to the local
metres is fitted to every fitted sheet at once; each fitted sheet's own fit is reported against it (a
check of the grid and of that sheet), and skipped sheets get the grid model.

Config: plan.grid = [[col, row], …] per sheet (from the plan's own sheet index), plan.grid_replace =
[sheet indices whose own fit disagrees with the grid and is replaced, e.g. a fit on few buildings].

    python3 scripts/plan_grid.py <key>     # then: plan_georef.py … --reuse-fit (pipeline --only georef)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402
from plan_georef import PolyModel  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAX_RESIDUAL_M = float(__import__("os").environ.get("GRID_MAX_RESIDUAL_M", 3.0))


def main(key):
    cfg = dcfg.load(key)
    plan = cfg["plan"]
    grid = plan["grid"]
    replace = set(plan.get("grid_replace", []))
    saved = ROOT / "scripts/plans" / f"{key}.json"
    fit = json.loads(saved.read_text())
    sheets = fit["sheets"]
    frames = plan["frames"]
    w = frames[0][2] - frames[0][0]
    h = frames[0][3] - frames[0][1]

    def to_grid(i, px):
        f = frames[i]
        c, r = grid[i]
        return px - np.array([f[0], f[1]]) + np.array([c * w, r * h])

    def model(f):
        return PolyModel(f["order"], np.array(f["coef"]), np.array(f["centre"]), f["scale"])

    # Sample points across each fitted sheet's frame.
    src, dst, own = [], [], {}
    for i, f in enumerate(sheets):
        if f.get("skipped") or f.get("gridPlaced") or i in replace:
            continue
        x0, y0, x1, y1 = frames[i]
        g = np.stack(np.meshgrid(np.linspace(x0, x1, 8), np.linspace(y0, y1, 8)), -1).reshape(-1, 2)
        own[i] = (g, model(f)(g))
        src.append(to_grid(i, g))
        dst.append(own[i][1])
    src, dst = np.vstack(src), np.vstack(dst)
    centre = src.mean(0)
    scale = float(src.std())
    G = PolyModel.fit(src, dst, 1, centre, scale)
    # Drop sheets far off the grid and refit, so one bad fit cannot pull the others.
    for _ in range(2):
        bad = []
        for i, (g, m) in own.items():
            res = np.hypot(*(G(to_grid(i, g)) - m).T)
            if np.median(res) > MAX_RESIDUAL_M:
                bad.append(i)
        if not bad:
            break
        keep = [i for i in own if i not in bad]
        G = PolyModel.fit(np.vstack([to_grid(i, own[i][0]) for i in keep]), np.vstack([own[i][1] for i in keep]), 1, centre, scale)
    m_per_px = np.sqrt(abs(np.linalg.det(G.coef[1:3]))) / G.scale
    print(f"grid model from {len(own)} fitted sheets: {m_per_px:.4f} m/px (1:{m_per_px / (0.0254 / 150):.0f})")
    for i, (g, m) in sorted(own.items()):
        res = np.hypot(*(G(to_grid(i, g)) - m).T)
        print(f"  sheet {i} (grid {grid[i]}): own fit vs grid median {np.median(res):.2f} m, max {res.max():.2f} m"
              + ("  ← off the grid" if np.median(res) > MAX_RESIDUAL_M else ""))
    for i, f in enumerate(sheets):
        if not (f.get("skipped") or f.get("gridPlaced") or i in replace):
            continue
        x0, y0, x1, y1 = frames[i]
        g = np.stack(np.meshgrid(np.linspace(x0, x1, 8), np.linspace(y0, y1, 8)), -1).reshape(-1, 2)
        m = PolyModel.fit(g, G(to_grid(i, g)), 1, np.array([(x0 + x1) / 2, (y0 + y1) / 2]), (x1 - x0) / 3)
        why = f.get("skipped") or f.get("gridReason") or "own fit replaced (plan.grid_replace)"
        sheets[i] = {"sheet": f["sheet"], **m.to_json(), "gridPlaced": grid[i], "gridReason": why}
        print(f"  sheet {i}: placed on the grid at {grid[i]}")
    saved.write_text(json.dumps(fit, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
