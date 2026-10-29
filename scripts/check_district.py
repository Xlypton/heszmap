"""Acceptance check for one onboarded municipality: is it good enough to go live?

    python3 scripts/check_district.py <key> [<key>...]   # one table per key
    python3 scripts/check_district.py --all               # one line per published key
    python3 scripts/check_district.py --changed <git rev>  # keys whose files differ from <rev>
    options: --online   also compare with njt.hu (scripts/check_freshness.py)
             --json     print the results as JSON
             --strict   exit 1 on "not measured" too, not only on a failure

The criteria and why each exists are in docs/onboarding/acceptance.md; the ids below (R1, Z5, ...)
are the ones used there. Every check reads only published files (public/data, public/pmtiles,
registry/, scripts/plans, scripts/reviews) with the standard library, so it runs anywhere, CI included.

A district config can waive a check, or record a manual sign-off, with a reason that the report shows:
    "acceptance": {"waive": {"Z2": "the south third is another KÉSZ (xi-sasad)"},
                   "sheets_not_on_map": {"0": "legend sheet"},
                   "codes_not_on_plan": {"Vi-2/SZ": "defined in the text, used by no plot"},
                   "signoff": {"M1": "2026-10-29 Peti: plan over plot lines at Kossuth tér, ..."}}
"""
import json
import re
import subprocess
import sys
from collections import Counter
from glob import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public/data"

# The bars. ZONE_ACCURACY_MIN: Peti, 2026-10-29 (docs/onboarding/acceptance.md, "Zone accuracy bar").
ZONE_SAMPLE_MIN = 50          # randomly sampled plots checked by eye on the plan (review_zones.py)
ZONE_ACCURACY_MIN = 0.90      # share of those whose automatic zone was right
PLOT_LINE_MEDIAN_MAX_M = 1.0  # plan plot lines vs land-registry plot outlines, per sheet
PLOT_LINE_P90_MAX_M = 2.5
PLOT_LINE_MATCHED_MIN = 0.5    # outline points within 3 m of a plan line (p90 is over those)
ZONED_MIN, ZONED_WARN = 0.80, 0.90  # building plots that have a zone at all
GUESSED_WARN = 0.20           # zoned building plots whose zone is a nearest-label estimate
UNCLEAR_OPEN_MAX = 0.02       # building plots still flagged zone-unclear and never reviewed
HRSZ_WARN = 0.90              # plots with a parcel number
NO_TABLE_WARN = 0.20          # zones with no row in the limits table

PASS, WARN, FAIL, TODO, WAIVED = "pass", "warn", "FAIL", "not measured", "waived"
MANUAL = {
    "M1": "plan overlay checked by eye over the plot lines at 3+ places, one at a sheet edge",
    "M2": "5 random cards compared with the official limits table",
    "M3": "every data source listed in the permission register (docs/data-sources.md)",
}


def load(p):
    return json.loads(Path(p).read_text())


class District:
    def __init__(self, key):
        self.key = key
        self.cfg = load(ROOT / "districts" / f"{key}.json")
        self.plan = self.cfg.get("plan", {})
        self.acc = self.cfg.get("acceptance", {})
        self.reg_id = self.cfg.get("regulation", {}).get("reg") or f"{key}-kesz"
        self.regs = load(DATA / "regulations.json")
        self.reg = self.regs["regulations"].get(self.reg_id)
        self._plots = None

    def zone_types(self):
        p = self.reg and self.reg.get("zoneTypes")
        return load(DATA / p) if p and (DATA / p).exists() else None

    def plots(self):
        """The published plots, keyed like scripts/reviews (hrsz, or "@lng,lat" for unnumbered ones)."""
        if self._plots is None:
            self._plots = []
            d = (self.reg or {}).get("parcels", {}).get("dir") or f"parcels-{self.key}"
            for f in sorted(glob(str(DATA / d / "*.json"))):
                for ft in load(f)["features"]:
                    if not ft["properties"].get("hrsz"):  # reviewed by a point inside it
                        ft["properties"]["_geom"] = ft["geometry"]
                    self._plots.append(ft["properties"])
        return self._plots

    def building_plots(self):
        return [p for p in self.plots() if "street" not in p.get("check", [])]

    def reviews(self):
        p = ROOT / "scripts/reviews" / f"{self.key}.json"
        return load(p) if p.exists() else {}


def inside(lng, lat, geom):
    """Point in a GeoJSON (Multi)Polygon, even-odd over all rings."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    hit = False
    for ring in (r for poly in polys for r in poly):
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > lat) != (y2 > lat) and lng < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
    return hit


def reviewed(plot, rv, points):
    if plot.get("hrsz"):
        return plot["hrsz"] in rv
    return any(inside(x, y, plot["_geom"]) for x, y in points)


def pct(a, b):
    return f"{a}/{b} ({a / b:.0%})" if b else f"{a}/0"


# --- R: regulation text --------------------------------------------------------------------------

def r1_regulation(d):
    if not d.reg:
        return FAIL, f"{d.reg_id} is not in regulations.json (registry.py export {d.key} && registry.py build)"
    pdf = d.reg.get("pdf")
    if not pdf or not (ROOT / "public" / pdf).exists():
        return FAIL, f"regulation PDF {pdf} missing"
    if not d.reg.get("effectiveFrom") or not d.reg.get("officialUrl"):
        return FAIL, "effectiveFrom or officialUrl missing"
    ids = d.cfg.get("district")
    ids = ids if isinstance(ids, list) else [ids] if ids is not None else []
    unlisted = [i for i in ids if d.reg_id not in d.regs["districts"].get(str(i), {}).get("regulations", [])]
    if unlisted:
        return FAIL, f"district {unlisted} does not list {d.reg_id}, so a tap there never finds it"
    return PASS, f"{d.reg.get('decree') or d.reg_id}, in force from {d.reg['effectiveFrom']}"


def r2_fresh(d, online):
    if not online:
        return TODO, f"retrieved {d.reg.get('retrievedAt') if d.reg else '?'}; run with --online to compare with njt.hu"
    script = ROOT / "scripts/check_freshness.py"
    if not script.exists():
        return TODO, "scripts/check_freshness.py not available yet"
    r = subprocess.run([sys.executable, str(script), d.key], cwd=ROOT, capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    return (PASS if r.returncode == 0 else FAIL), last or f"exit {r.returncode}"


# --- T: zone limits table ------------------------------------------------------------------------

def t1_table(d):
    zt = d.zone_types()
    if not zt:
        return FAIL, "no zone-types file"
    codes = [c for c in zt if not c.startswith("_")]
    no_table = [c for c in codes if zt[c].get("noTable")]
    uncited = [c for c in codes if not (zt[c].get("cite") or {}).get("quote")]
    if not codes or len(no_table) == len(codes):
        return FAIL, f"{len(codes)} zones, none with limits from the table"
    if uncited:
        return FAIL, f"{len(uncited)} zones without a citation: {', '.join(uncited[:5])}"
    if len(no_table) > NO_TABLE_WARN * len(codes):
        return WARN, f"{pct(len(no_table), len(codes))} zones have no table row"
    return PASS, f"{len(codes)} zones, {len(no_table)} without a table row"


VALUE_RULES = {  # field -> (min, max) on its parsed number
    "maxCoveragePct": (0, 100), "minGreenPct": (0, 100), "maxUndergroundPct": (0, 100),
    "maxFar": (0, 10), "maxHeightM": (0, 120), "minHeightM": (0, 120), "minPlotM2": (0, 1e7),
}
MERGED = re.compile(r"\d\s+\d(?!\d\d(?!\d))")  # "45 75" but not the thousands group "2 500"


def t2_values(d):
    """Suspicious values. scripts/validate_zones.py (when present) is the full rule set; it marks a
    value with "check". The rules here are the minimum that also runs without it."""
    zt = d.zone_types()
    if not zt:
        return FAIL, "no zone-types file"
    script = ROOT / "scripts/validate_zones.py"
    if script.exists():
        subprocess.run([sys.executable, str(script), d.key], cwd=ROOT, capture_output=True, text=True)
        zt = d.zone_types()  # it marks suspicious values in place ("check"), read below
    bad = []
    for code, z in zt.items():
        for field, v in z.items():
            if not isinstance(v, dict) or "text" not in v:
                continue
            n, lo_hi = v.get("num"), VALUE_RULES.get(field)
            if v.get("check"):
                bad.append(f"{code} {field}: {v['check']}")
            elif n is not None and MERGED.search(str(v["text"])):
                bad.append(f"{code} {field}: \"{v['text']}\" read as {n}")
            elif n is not None and lo_hi and not lo_hi[0] <= n <= lo_hi[1]:
                bad.append(f"{code} {field}: {n} outside {lo_hi[0]}-{lo_hi[1]}")
    if bad:
        return FAIL, f"{len(bad)} values: " + "; ".join(bad[:4]) + (" ..." if len(bad) > 4 else "")
    return PASS, "all values within range" + (" (validate_zones.py)" if script.exists() else "")


def t3_heights(d):
    zt = d.zone_types() or {}
    building = [c for c, z in zt.items() if isinstance(z, dict) and "maxCoveragePct" in z]
    # A cornice height counts too, and heightOnPlan is the note that the plan sets the height (ingest config).
    missing = [c for c in building if not any(k in zt[c] for k in ("maxHeightM", "maxCorniceM"))
               and not zt[c].get("heightOnPlan") and not zt[c].get("heightNote")]
    if missing:
        return WARN, f"{pct(len(missing), len(building))} building zones have no max height or note: {', '.join(missing[:4])}"
    return PASS, f"all {len(building)} building zones have a height"


# --- P: plan overlay -----------------------------------------------------------------------------

def p1_tiles(d):
    plan = (d.reg or {}).get("plan")
    if not plan:
        return FAIL, "no plan entry"
    if plan.get("tiles") or not plan.get("pmtiles"):
        return FAIL, "plan points to loose tiles, which are never deployed (pack_tiles.py, then export + build)"
    chunks = sorted(glob(str(ROOT / "public" / plan["pmtiles"] / "*.bin")))
    size = sum(Path(c).stat().st_size for c in chunks)
    names = sorted(int(Path(c).stem) for c in chunks)
    if not chunks or names != list(range(len(names))) or size != plan.get("size"):
        return FAIL, f"{len(chunks)} chunks, {size} bytes on disk vs size {plan.get('size')} in regulations.json"
    if list(ROOT.glob(f"public/tiles/{d.key}/*")) and _tracked(f"public/tiles/{d.key}"):
        return FAIL, f"public/tiles/{d.key} is committed (Workers asset limit)"
    return PASS, f"{len(chunks)} chunks, {size / 2**20:.1f} MiB, zoom {plan.get('minzoom')}-{plan.get('maxzoom')}"


def _tracked(path):
    r = subprocess.run(["git", "ls-files", path], cwd=ROOT, capture_output=True, text=True)
    return bool(r.stdout.strip())


def p2_sheets(d):
    p = ROOT / "scripts/plans" / f"{d.key}.json"
    if not p.exists():
        return FAIL, "no saved fit (scripts/plans/<key>.json)"
    sheets = load(p).get("sheets", [])
    waived = d.acc.get("sheets_not_on_map", {})
    off = [i for i, s in enumerate(sheets) if (s.get("skipped") or s.get("coef") is None) and str(i) not in waived]
    if off:
        return FAIL, f"{len(off)} of {len(sheets)} sheets not placed: {off[:8]} (place them, or list in acceptance.sheets_not_on_map)"
    return PASS, f"{len(sheets) - len(waived)} sheets placed" + (f", {len(waived)} not map sheets" if waived else "")


def p3_alignment(d):
    """Plan plot lines vs the app's plot outlines (scripts/plan_plotfit.py)."""
    p = ROOT / "scripts/plans" / f"{d.key}-plotfit.json"
    if not p.exists():
        return TODO, f"no {p.name}: run scripts/plan_plotfit.py {d.key} --check"
    rows = load(p)
    waived = d.acc.get("sheets_not_on_map", {})
    rows = [r for r in rows if str(r.get("sheet")) not in waived]
    bad = [f"sheet {r['sheet']}: {r['plotLineMedianM']:.1f}/{r['plotLineP90M']:.1f} m, {r.get('plotLineMatched', 1):.0%} matched" for r in rows
           if "plotLineMedianM" in r and (r["plotLineMedianM"] > PLOT_LINE_MEDIAN_MAX_M or r.get("plotLineP90M", 0) > PLOT_LINE_P90_MAX_M
                                          or r.get("plotLineMatched", 1) < PLOT_LINE_MATCHED_MIN)]
    unmeasured = [r.get("sheet") for r in rows if "plotLineMedianM" not in r]
    worst = max((r["plotLineMedianM"] for r in rows if "plotLineMedianM" in r), default=None)
    if bad:
        return FAIL, f"{len(bad)} sheets off the plot lines (median/p90, matched): " + "; ".join(bad[:4])
    if unmeasured:
        return TODO, f"{len(unmeasured)} sheets not measured (too few plot lines): {unmeasured[:8]}"
    return PASS, f"{len(rows)} sheets, worst median {worst:.2f} m"


# --- L: plots ------------------------------------------------------------------------------------

def l1_linked(d):
    missing = [f for f in ("parcels", "zoneAreas") if not (d.reg or {}).get(f)
               or not glob(str(DATA / d.reg[f]["dir"] / "*.json"))]
    if missing:
        return FAIL, f"{' and '.join(missing)} not linked in regulations.json or empty, so a tap highlights nothing"
    return PASS, f"{d.reg['parcels']['dir']}, {d.reg['zoneAreas']['dir']}"


def l2_plots(d):
    ps = d.building_plots()
    if not ps:
        return FAIL, "no building plots"
    numbered = sum(bool(p.get("hrsz")) for p in ps)
    src = Counter(p.get("source", "traced") for p in ps).most_common(1)[0][0]
    zt = d.zone_types() or {}
    unknown = Counter(z["code"] for p in d.plots() for z in p.get("zones", []) if z.get("code") not in zt)
    if unknown:
        return FAIL, f"zone codes on plots but not in the zone table (the card shows nothing): {', '.join(list(unknown)[:6])}"
    if numbered < HRSZ_WARN * len(ps):
        return WARN, f"only {pct(numbered, len(ps))} plots have a parcel number (source {src})"
    return PASS, f"{len(ps)} building plots from {src}, {numbered / len(ps):.0%} numbered"


def l3_search(d):
    if not (DATA / "hrsz" / f"{d.reg_id}.json").exists():
        return FAIL, "no parcel-number search index (python3 scripts/hrsz_index.py)"
    return PASS, f"hrsz/{d.reg_id}.json"


# --- Z: zone of each plot ------------------------------------------------------------------------

def z1_boundaries(d):
    if d.plan.get("zone_lines"):
        return PASS, f"zone_lines {str(d.plan['zone_lines'])[:40]}"
    if d.plan.get("plots") == "oeny":
        return PASS, "zone areas from the plan's zone cells (plan_zones.py)"
    return FAIL, "the plan's zone boundary lines are not read (plan.zone_lines): plots take the nearest label"


def z2_zoned(d):
    ps = d.building_plots()
    zoned = sum(bool(p.get("zones")) for p in ps)
    if not ps:
        return FAIL, "no building plots"
    share = zoned / len(ps)
    return (FAIL if share < ZONED_MIN else WARN if share < ZONED_WARN else PASS), f"{pct(zoned, len(ps))} building plots have a zone"


def z3_guessed(d):
    zs = [p["zones"][0] for p in d.building_plots() if p.get("zones")]
    guessed = sum(z.get("basis") in ("block", "near") if "basis" in z else z.get("status") == "estimated" for z in zs)
    return (WARN if zs and guessed > GUESSED_WARN * len(zs) else PASS), f"{pct(guessed, len(zs))} zones are estimates"


def z4_unclear(d):
    ps, rv = d.building_plots(), d.reviews()
    points = [tuple(map(float, k[1:].split(","))) for k in rv if k.startswith("@")]
    open_ = [p for p in ps if "zone-unclear" in p.get("check", []) and not reviewed(p, rv, points)]
    flagged = sum("zone-unclear" in p.get("check", []) for p in ps)
    ok = len(open_) <= UNCLEAR_OPEN_MAX * max(len(ps), 1)
    return (PASS if ok else FAIL), f"{len(open_)} unclear plots never reviewed ({flagged} flagged, {len(ps)} plots)"


def z5_sample(d):
    s = [v for v in d.reviews().values() if v.get("why") == "sample" and v.get("zone")]
    agree = sum(v["zone"] == v.get("auto_zone") for v in s)
    if len(s) < ZONE_SAMPLE_MIN:
        return TODO, (f"{agree}/{len(s)} sampled plots confirmed; need {ZONE_SAMPLE_MIN} "
                      f"(review_zones.py batches {d.key} --sample {ZONE_SAMPLE_MIN - len(s)} --max-unclear 0)")
    return (PASS if agree >= ZONE_ACCURACY_MIN * len(s) else FAIL), f"{pct(agree, len(s))} sampled zones right (bar {ZONE_ACCURACY_MIN:.0%})"


def z6_codes(d):
    zt, labels = d.zone_types(), (d.reg or {}).get("zoneLabels")
    if not zt or not labels or not (DATA / labels).exists():
        return FAIL, "no zone labels"
    seen = {f["properties"]["code"] for f in load(DATA / labels)["features"]
            if f["properties"].get("reg", d.reg_id) == d.reg_id}
    waived = d.acc.get("codes_not_on_plan", {})
    missing = sorted(c for c in zt if not c.startswith("_") and c not in seen and c not in waived)
    if missing:
        return FAIL, (f"{len(missing)} regulation codes never read on the plan: {', '.join(missing[:6])}"
                      + (" ..." if len(missing) > 6 else "") + " (fix the labels, or list in acceptance.codes_not_on_plan)")
    return PASS, f"every code read on the plan ({len(waived)} listed as not on it)"


CHECKS = [
    ("R1", "Regulation linked, PDF and version date", r1_regulation),
    ("R2", "Regulation current on njt.hu", None),
    ("T1", "Zone limits table, every zone cited", t1_table),
    ("T2", "Zone values plausible", t2_values),
    ("T3", "Max height shown for building zones", t3_heights),
    ("P1", "Plan overlay packed and deployable", p1_tiles),
    ("P2", "Every plan sheet placed", p2_sheets),
    ("P3", "Plan aligned to the plot lines", p3_alignment),
    ("L1", "Plots and zone areas linked", l1_linked),
    ("L2", "Plots numbered, zone codes known", l2_plots),
    ("L3", "Parcel-number search", l3_search),
    ("Z1", "Zone boundaries read from the plan", z1_boundaries),
    ("Z2", "Building plots with a zone", z2_zoned),
    ("Z3", "Zones that are estimates", z3_guessed),
    ("Z4", "Unclear plots reviewed", z4_unclear),
    ("Z5", "Random sample review score", z5_sample),
    ("Z6", "Every regulation code found on the plan", z6_codes),
]


def check(key, online=False):
    d = District(key)
    out = []
    for cid, title, fn in CHECKS:
        try:
            status, detail = r2_fresh(d, online) if cid == "R2" else fn(d)
        except Exception as e:  # a broken input is a failure of that check, not of the run
            status, detail = FAIL, f"{type(e).__name__}: {e}"
        if status in (FAIL, TODO, WARN) and cid in d.acc.get("waive", {}):
            status, detail = WAIVED, f"{detail} -- waived: {d.acc['waive'][cid]}"
        out.append({"id": cid, "title": title, "status": status, "detail": detail})
    for cid, title in MANUAL.items():
        s = d.acc.get("signoff", {}).get(cid)
        out.append({"id": cid, "title": title, "status": PASS if s else TODO, "detail": s or "not signed off"})
    return out


def verdict(results):
    st = {r["status"] for r in results}
    return "not ready" if FAIL in st else "incomplete" if TODO in st else "ready"


def published_keys():
    return sorted(p.stem for p in (ROOT / "registry").glob("*.json"))


def changed_keys(rev):
    names = subprocess.run(["git", "diff", "--name-only", rev, "--"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    keys = set()
    for n in names:
        m = re.match(r"(?:districts|registry|scripts/reviews)/([^/]+)\.json$|public/(?:data/(?:parcels|zones)|pmtiles)[-/]([^/]+)/", n)
        if m:
            keys.add(m.group(1) or m.group(2))
    return sorted(k for k in keys if (ROOT / "registry" / f"{k}.json").exists())


def main():
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    if "--all" in flags:
        keys = published_keys()
    elif "--changed" in flags:
        keys = changed_keys(args[args.index("--changed") + 1])
    else:
        keys = [a for a in args if not a.startswith("--")]
    if not keys:
        print("{}" if "--json" in flags else "no keys" if "--changed" in flags else __doc__)
        return 0
    report = {k: check(k, "--online" in flags) for k in keys}
    if "--json" in flags:
        print(json.dumps({k: {"verdict": verdict(r), "checks": r} for k, r in report.items()}, ensure_ascii=False, indent=1))
    elif len(keys) > 1 and "--changed" not in flags:
        ids = [r["id"] for r in next(iter(report.values()))]
        mark = {PASS: ".", WAIVED: "w", WARN: "!", FAIL: "X", TODO: "?"}
        print(f"{'key':14} {'verdict':11} {' '.join(i[:2] for i in ids)}")
        for k, r in report.items():
            print(f"{k:14} {verdict(r):11} {' '.join(mark[x['status']].center(2) for x in r)}")
        print("\n. pass  ! warning  X fail  ? not measured / not signed off  w waived")
    else:
        for k, r in report.items():
            print(f"\n{k}: {verdict(r)}")
            for x in r:
                print(f"  {x['id']} {x['status']:12} {x['title']}: {x['detail']}")
    bad = {FAIL, TODO} if "--strict" in flags else {FAIL}
    return 1 if any(x["status"] in bad for r in report.values() for x in r) else 0


if __name__ == "__main__":
    sys.exit(main())
