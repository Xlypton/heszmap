"""What a re-ingest changed in a key's zone limits: zones added or removed, and every value that changed,
against the committed version (or another git revision). Review this before publishing a re-ingest.

    python3 scripts/zone_diff.py xiv            # public/data/zone-types-xiv.json vs HEAD
    python3 scripts/zone_diff.py xiv HEAD~3
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def values(z: dict) -> dict[str, str]:
    return {f: p["text"] for f, p in z.items() if isinstance(p, dict) and "text" in p}


def main(key: str, rev: str = "HEAD") -> None:
    path = f"public/data/zone-types-{key}.json"
    try:
        old = json.loads(subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, check=True, text=True).stdout)
    except subprocess.CalledProcessError:
        old = {}
    new = json.loads((ROOT / path).read_text())
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    changed = []
    for code in sorted(set(new) & set(old)):
        a, b = values(old[code]), values(new[code])
        for f in sorted(set(a) | set(b)):
            if a.get(f) != b.get(f):
                changed.append(f"{code}.{f}: {a.get(f, '—')!r} -> {b.get(f, '—')!r}")
    print(f"{path} vs {rev}: {len(added)} zone(s) added, {len(removed)} removed, {len(changed)} value(s) changed")
    for c in added:
        print(f"  + {c}: {values(new[c])}")
    for c in removed:
        print(f"  - {c}")
    for c in changed:
        print(f"  ~ {c}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
