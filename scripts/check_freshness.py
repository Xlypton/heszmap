"""Is every regulation in the app still the version in force on njt.hu?

For each regulation in public/data/regulations.json with an njt.hu page (officialUrl .../jogszabaly/<id>):
  - the version in force now (the page's "hatályos" date) against the stored effectiveFrom,
  - every annex link we use (plan sheets, the limits table PDF) still on the page: an amendment that
    replaces an annex publishes it under a new document link,
  - for annex PDFs published as regulations of their own (<reg>-m2 …), their sha256 against the file now.
Run weekly by .github/workflows/freshness.yml, and before re-publishing a key.

    python3 scripts/check_freshness.py                 # every regulation
    python3 scripts/check_freshness.py xiv xvii        # the regulations of these keys (registry/<key>.json)
    python3 scripts/check_freshness.py --md out.md     # also write a Markdown report (for the issue)

Exits 1 when anything is out of date, 0 otherwise.
"""
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGS = ROOT / "public/data/regulations.json"
UA = {"user-agent": "heszmap/0.1 (+https://github.com/xlypton/heszmap)"}


def get(url: str) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def full_page(url: str) -> str:
    """The njt page with its lazily loaded text blocks (long decrees: the annex links are often in them),
    fetched the way scripts/ingest-kesz.mjs does."""
    page = get(url).decode("utf8", "replace")
    doc_id = url.rstrip("/").rsplit("/", 1)[-1]
    for m in re.finditer(r'<div id="([^"]+)" class="pH borderStart" data-show-order="(\d+)"(?: data-last-show-order="(\d+)")?', page):
        req = {"start": int(m[2]), **({"last": int(m[3])} if m[3] else {})}
        body = json.dumps({"documentId": doc_id, "data": [req]}).encode()
        r = urllib.request.Request("https://njt.jog.gov.hu/ajax/njtGetBlock.json", data=body, method="POST", headers={
            **UA, "content-type": "application/json; charset=utf-8", "x-requested-with": "XMLHttpRequest"})
        with urllib.request.urlopen(r, timeout=60) as resp:
            page += resp.read().decode("utf8", "replace")
    return page


def ymd(s: str | None) -> str | None:
    """'2026.10.23.' -> '2026-10-23'."""
    m = re.search(r"(\d{4})\.\s*(\d{2})\.\s*(\d{2})", s or "")
    return f"{m[1]}-{m[2]}-{m[3]}" if m else None


def page_state(page: str) -> tuple[str | None, set[str]]:
    """The date the shown (current) version is in force from, and the page's document links.
    (Versions coming into force later are listed only by njt's page script, so they are not seen here.)"""
    m = re.search(r'class="hataly"[^>]*>(.*?)</', page, re.S)
    now = ymd(html.unescape(m[1])) if m else None
    docs = set(re.findall(r'/document/[^"\'\s<>]+', html.unescape(page)))
    return now, docs


def config_annexes() -> dict[str, list[tuple[str, str]]]:
    """Per regulation id, the njt documents its key's pipeline reads (districts/<key>.json): plan sheets and
    the limits table PDF, as (what, path)."""
    out: dict[str, list[tuple[str, str]]] = {}
    for p in sorted((ROOT / "districts").glob("*.json")):
        cfg = json.loads(p.read_text())
        reg = (cfg.get("regulation") or {}).get("reg")
        if not reg:
            continue
        docs = [("szabályozási terv lap", a) for a in (cfg.get("plan") or {}).get("annexes", []) if isinstance(a, str)]
        if (cfg.get("zoneTablePdf") or {}).get("path"):
            docs.append(("határérték-táblázat", cfg["zoneTablePdf"]["path"]))
        out.setdefault(reg, []).extend(docs)
    return out


def regs_of(keys: list[str]) -> set[str]:
    out = set()
    for k in keys:
        frag = json.loads((ROOT / "registry" / f"{k}.json").read_text())
        out |= set(frag.get("regulations", {}))
    return out


def main(argv: list[str]) -> int:
    md_path = argv[argv.index("--md") + 1] if "--md" in argv else None
    keys = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--md")]
    regs = json.loads(REGS.read_text())["regulations"]
    wanted = regs_of(keys) if keys else set(regs)
    # Annex regulations belong to the regulation whose njt page links them (same decree).
    pages: dict[str, tuple] = {}
    used = config_annexes()
    problems: list[tuple[str, str]] = []
    for rid, r in regs.items():
        url = r.get("officialUrl") or ""
        if rid not in wanted or "/jogszabaly/" not in url:
            continue
        try:
            page = full_page(url)
        except Exception as e:
            problems.append((rid, f"njt.hu page could not be read ({e})"))
            continue
        now, docs = page_state(page)
        pages[rid] = (now, docs)
        stored = ymd(r.get("effectiveFrom"))
        if not now:
            problems.append((rid, "no version date on the njt.hu page"))
        elif stored != now:
            problems.append((rid, f"newer version on njt.hu: in force from {now} (the app has {stored})"))
        gone = []
        for a in r.get("annexes", []):
            path = re.sub(r"^https://njt\.jog\.gov\.hu", "", a["url"])
            if path.startswith("/document/") and path not in docs:
                gone.append(path)
                problems.append((rid, f"annex no longer linked on njt.hu (replaced?): {a['title']}"))
        for what, path in used.get(rid, []):
            if path.startswith("/document/") and path not in docs and path not in gone:
                gone.append(path)
                problems.append((rid, f"{what} no longer linked on njt.hu (replaced?): {path.rsplit('/', 1)[-1]}"))
        time.sleep(1)
    # Annex PDFs ingested as regulations of their own: the file itself.
    for rid, r in regs.items():
        url = r.get("officialUrl") or ""
        if rid not in wanted or "/document/" not in url or not r.get("sha256") or not url.endswith(".pdf"):
            continue
        try:
            sha = hashlib.sha256(get(url)).hexdigest()
        except Exception as e:
            problems.append((rid, f"annex PDF could not be read ({e})"))
            continue
        if sha != r["sha256"]:
            problems.append((rid, "annex PDF changed on njt.hu (sha256 differs)"))
        time.sleep(1)
    checked = len(pages)
    for rid, msg in problems:
        print(f"{rid}: {msg}")
    print(f"{checked} regulation pages checked, {len(problems)} problem(s)")
    if md_path:
        lines = ["Weekly check of the regulations in the app against njt.hu "
                 f"({time.strftime('%Y-%m-%d')}, `scripts/check_freshness.py`).", ""]
        if problems:
            lines += ["| Regulation | Problem |", "| --- | --- |"] + [f"| `{rid}` | {msg} |" for rid, msg in problems]
            lines += ["", "To update a key: re-run `node scripts/ingest-kesz.mjs <key>` (and its table step), review the "
                      "zone-types diff, then `python3 scripts/registry.py export <key>` and `build`."]
        else:
            lines.append("Everything matches.")
        Path(md_path).write_text("\n".join(lines) + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
