"""Nemzeti Jogszabálytár (njt.jog.gov.hu): every municipality's decrees, with annex PDFs.

The site has no public API; its search page is server-rendered at
/search/<fields>/<page>/<per page>, where <fields> is the colon-joined form that
/ajax/get_search_url.json returns for the search form's values.

    python3 scripts/njt.py search "helyi építési szabályzat" [--page N]
    python3 scripts/njt.py annexes 2015-26-SP-5Y269
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

NJT = "https://njt.jog.gov.hu"
UA = {"User-Agent": "Mozilla/5.0 (heszmap; +https://github.com/xlypton/heszmap)"}
CACHE = Path(__file__).resolve().parent / ".cache"


def _get(url: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def search_url(text: str, municipal=True, in_force=True, title_only=True, town="") -> str:
    form = {"szokereso": text, "csak_hatalyos": in_force, "pontos_szora": False, "csak_cimben": title_only,
            "relevancia": "", "onkormanyzati_kor": municipal, "evszam": "", "sorszam": "", "author_type": "",
            "gazette_state": "", "topic": "", "megye": "", "telepules_kibocsato": town, "modositok_kihagyasa": False}
    res = json.loads(_get(f"{NJT}/ajax/get_search_url.json", json.dumps(form).encode(), {"Content-Type": "application/json"}))
    return res["url"]


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def search(text: str, page=1, per_page=50, **kw) -> list[dict]:
    """[{id, issuer, title, inForce}] for one result page."""
    fields = urllib.parse.quote(search_url(text, **kw))
    page_html = _get(f"{NJT}/search/{fields}/{page}/{per_page}").decode()
    out = []
    for m in re.finditer(r'href="/?jogszabaly/([0-9]{4}-[0-9A-Za-z-]+)">(.*?)</a>.*?<p class="text-small">(.*?)</p>', page_html, re.S):
        if not any(o["id"] == m.group(1) for o in out):
            out.append({"id": m.group(1), "issuer": _text(m.group(2)), "title": _text(m.group(3))})
    return out


def annexes(doc_id: str) -> list[dict]:
    """The annex documents (/document/...) linked from a decree's consolidated text."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"njt-{doc_id}.html"
    if not path.exists():
        path.write_bytes(_get(f"{NJT}/jogszabaly/{doc_id}"))
    page = path.read_text(errors="replace")
    out = []
    for m in re.finditer(r'href="(/document/[^"]+)"[^>]*>(.*?)</a>', page, re.S):
        if not any(a["path"] == m.group(1) for a in out):
            out.append({"path": m.group(1), "url": NJT + m.group(1), "label": _text(m.group(2))})
    return out


def download(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_get(url))
    return dest


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "search":
        page = int(sys.argv[sys.argv.index("--page") + 1]) if "--page" in sys.argv else 1
        for r in search(sys.argv[2], page=page):
            print(r["id"], "|", r["issuer"], "|", r["title"])
    elif cmd == "annexes":
        for a in annexes(sys.argv[2]):
            print(a["url"], "|", a["label"])
