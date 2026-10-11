"""Read the amendment notes (lábjegyzetek) of each regulation PDF: which later decree inserted,
replaced or repealed a provision, and from when. njt.hu prints them as numbered notes, either at the
page foot or as endnotes; the provision's text carries the note number ("24. §28 (1)", "c)37 a ...").

Usage: python3 scripts/extract_notes.py [reg-id ...]   (default: every regulation with a PDF)
Writes public/data/notes-<reg-id>.json: {"37": "A 24. § (2) bekezdés c) pontját a ... rendelete 4. §-a ..."}.
The source viewer shows them on each paragraph's card.
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
# A note says how the text came about; numbered lines without these words are not notes (page
# numbers, table cells, list items).
KEYWORDS = re.compile(r"rendelet|törvény|megállapított|[Ii]ktatta|[Mm]ódosította|[Hh]atályon kívül|[Mm]egállapította|[Hh]atályos")
MAX_NOTE = 800


def notes(pdf: Path) -> dict[str, str]:
    lines = [ln.strip() for page in pymupdf.open(pdf) for ln in page.get_text().split("\n")]
    out: dict[int, str] = {}
    cur: list | None = None

    def close() -> None:
        if cur and KEYWORDS.search(cur[1]):
            out.setdefault(cur[0], re.sub(r"\s+", " ", cur[1]).replace("‐", "-").strip())

    for ln in lines:
        m = re.match(r"^(\d{1,3})(?:\s+(.*))?$", ln)
        # A new note starts with the next number in sequence (or 1 again, e.g. an annex's own notes).
        if m and (cur is None or int(m.group(1)) in (cur[0] + 1, 1)) and int(m.group(1)) not in out:
            close()
            cur = [int(m.group(1)), m.group(2) or ""]
        elif cur is not None and len(cur[1]) < MAX_NOTE:
            cur[1] += " " + ln
    close()
    return {str(k): v for k, v in sorted(out.items())}


def main() -> None:
    regs = json.loads((ROOT / "public/data/regulations.json").read_text())["regulations"]
    ids = sys.argv[1:] or [k for k, r in regs.items() if r.get("pdf")]
    for rid in ids:
        pdf = ROOT / "public" / regs[rid]["pdf"]
        found = notes(pdf)
        dest = ROOT / "public/data" / f"notes-{rid}.json"
        if found:
            dest.write_text(json.dumps(found, ensure_ascii=False, indent=0) + "\n")
        elif dest.exists():
            dest.unlink()
        print(f"{rid}: {len(found)} notes")


if __name__ == "__main__":
    main()
