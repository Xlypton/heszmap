"""Run the plan pipeline for one district, from its config (districts/<key>.json).

    python3 scripts/pipeline.py xx [--from STEP] [--only STEP]

Steps (each reads the previous step's output; all colours and line styles come from the config):
  sheets   plan annexes -> sheet images (+ PDF text layer for vector pages)       plan_sheets.py
  ocr      OCR scanned sheets that have no text layer yet                         plan_ocr.py
  labels   re-read the zone codes (zone-code style)                                plan_zone_labels.py
  georef   fit sheets to OSM streets, cut map tiles (reuses a saved fit)          plan_georef.py
  zones    zone cells from boundaries, regulation lines, streets and labels       plan_zones.py
  parcels  plots, their zones and OSM checks                                      plan_parcels.py
The regulation text itself is ingested separately (scripts/ingest-kesz.mjs, extract_*.py).
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STEPS = ["sheets", "ocr", "labels", "georef", "zones", "parcels"]


def run(*args):
    print("$", " ".join(map(str, args)), flush=True)
    subprocess.run([sys.executable, *map(str, args)], check=True, cwd=ROOT)


def main():
    key = sys.argv[1]
    opt = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None
    steps = [opt("--only")] if opt("--only") else STEPS[STEPS.index(opt("--from") or "sheets"):]
    cfg = district.load(key)
    s = "scripts/"
    for step in steps:
        sheets = district.sheet_paths(cfg)
        ocr = [ROOT / "scripts/plans" / f"{key}-ocr-{i}.json" for i in range(len(sheets))]
        if step == "sheets":
            run(s + "plan_sheets.py", key)
        elif step == "ocr":
            for img, o in zip(sheets, ocr):
                if not o.exists():
                    run(s + "plan_ocr.py", img, o)
        elif step == "labels":
            run(s + "plan_zone_labels.py", key)
        elif step == "georef":
            fit = ROOT / "scripts/plans" / f"{key}.json"
            run(s + "plan_georef.py", key, *[f"{img}:{o}" for img, o in zip(sheets, ocr)], *(["--reuse-fit"] if fit.exists() else []))
        elif step == "zones":
            run(s + "plan_zones.py", key)
        elif step == "parcels":
            run(s + "plan_parcels.py", key)


if __name__ == "__main__":
    main()
