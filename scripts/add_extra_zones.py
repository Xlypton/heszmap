"""Add a district's "extraZones" (zones the limits table has no row for: parks, forests, roads, farmland)
to public/data/zone-types-<key>.json without re-running the whole ingest. Codes the plan prints but
the zone list lacks are dropped from the plan's labels, so their plots get no zone or a neighbour's.

    python3 scripts/add_extra_zones.py <key>

Reads "extraZones" {code: [name, quote]} from the config's "ingest" or "zoneTablePdf" (the same
entries ingest-kesz.mjs / ingest-pdf-zones.mjs read), checks each quote against the main regulation's
PDF the way they do (whitespace removed), and adds the zone with its citation. Existing zones stay.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import district as dcfg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def squash(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s))


def main():
    key = sys.argv[1]
    cfg = dcfg.load(key)
    reg = cfg["regulation"]["reg"]
    extra = {**cfg.get("ingest", {}).get("extraZones", {}), **cfg.get("zoneTablePdf", {}).get("extraZones", {})}
    pages = [squash(p.get_text()) for p in pymupdf.open(ROOT / "public/docs" / f"{reg}.pdf")]
    path = ROOT / "public/data" / f"zone-types-{key}.json"
    zones = json.loads(path.read_text())
    added, missing = [], []
    for code, e in extra.items():
        name, quote = e if isinstance(e, list) else (e, None)
        cite = None
        if quote:
            page = next((i + 1 for i, p in enumerate(pages) if squash(quote) in p), None)
            if not page:
                missing.append(code)
                continue
            cite = {"reg": reg, "page": page, "para": "szöveg", "quote": quote}
        if code not in zones:
            zones[code] = {"name": name, "category": name, "noTable": True, **({"cite": cite} if cite else {})}
            added.append(code)
    if missing:
        sys.exit(f"quotes not found in {reg}.pdf for: {', '.join(missing)}")
    path.write_text(json.dumps(zones, ensure_ascii=False, indent=1) + "\n")
    print(f"{key}: added {len(added)} zones ({', '.join(added)}), {len(zones)} in all")


if __name__ == "__main__":
    main()
