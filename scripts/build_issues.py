"""Collect every known data problem into public/data/issues.json (the Issues page and the card badge read it).

    python3 scripts/build_issues.py            # all published keys
    python3 scripts/build_issues.py xvi xx     # only these keys (others are kept from the old file)

Sources, nothing is typed in by hand:
  * the acceptance checks (scripts/check_district.py): every warning or failure becomes an issue
  * the district configs: rowCodeFix (fixed), duplicateRows (variant tables), and the reasons in
    acceptance.waive / text_zones_ok / line_crossings_ok / codes_not_on_plan ("worked around")
  * the regulation's planOutdated note

Status: open | worked-around | fixed. "worked-around" means a config entry explains it ("why").
An issue present in the previous file and gone now becomes "fixed" and stays listed. User reports
are not in this file; the page links to a pre-filled GitHub issue for them.

Kinds: source-typo, variant-tables, crossed-boundary, guessed-zone, no-boundary-lines, code-not-on-plan,
missing-citation, implausible-value, text-vs-map, text-not-read, plan-misaligned, plan-outdated,
unreviewed-plots, plots-without-zone, plots-missing, missing-height, no-table, table-highlight, area-gap.
Severity: wrong-answer (the card may show a wrong value or zone) | missing | uncertain | info.
Scope: "item" (one row) or "area" (a number with a map layer; never one row per plot).
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_district as cd  # noqa: E402

ROOT, DATA = cd.ROOT, cd.DATA
OUT = DATA / "issues.json"
PASS, WARN, FAIL, TODO, WAIVED = cd.PASS, cd.WARN, cd.FAIL, cd.TODO, cd.WAIVED

# check id -> (kind, severity) for the checks that stay one aggregate per area
AGG = {
    "Z1": ("no-boundary-lines", "uncertain"), "Z2": ("plots-without-zone", "missing"),
    "Z3": ("guessed-zone", "uncertain"), "Z4": ("unreviewed-plots", "uncertain"),
    "P2": ("plan-misaligned", "missing"), "P3": ("plan-misaligned", "uncertain"),
    "L2": ("plots-missing", "missing"), "L3": ("plots-missing", "missing"),
    "T3": ("missing-height", "missing"), "T4": ("table-highlight", "wrong-answer"),
}
ITEM_CHECKS = {"T1", "T2", "Z6", "Z7", "Z8"}  # split into rows below
SKIP = {"R1", "R2", "P1", "L1", "Z5"}  # R2 needs --online; Z5 is review progress, not a data problem


def issue(area, kind, subject, sev, note, status="open", why=None, source=None, found_by=None, scope="item", **extra):
    sid = f"{area}:{kind}:{subject}"
    d = {"id": sid, "area": area, "kind": kind, "severity": sev, "scope": scope, "note": note, "status": status}
    if why:
        d["why"] = why
    if source:
        d["source"] = source
    if found_by:
        d["found_by"] = found_by
    d.update(extra)
    return d


def cite_of(zt, code):
    c = (zt or {}).get(code, {}).get("cite") if isinstance((zt or {}).get(code), dict) else None
    return {k: c[k] for k in ("reg", "page", "para") if c and k in c} or None


def area_name(d):
    return d.cfg.get("name") or (d.reg or {}).get("title") or d.key


def collect(key):
    d = cd.District(key)
    res = {r["id"]: r for r in cd.check(key)}
    zt = d.zone_types() or {}
    acc = d.acc
    out = []
    A = key

    # Aggregates
    for cid, (kind, sev) in AGG.items():
        r = res.get(cid)
        if not r or r["status"] in (PASS, TODO):
            continue
        if cid == "Z2" and r["status"] == WARN:
            sev = "info"
        det = r["detail"]
        why = None
        status = "open"
        if r["status"] == WAIVED:
            det, _, why = det.partition(" -- waived: ")
            status = "worked-around"
        elif r["status"] == WARN and cid in ("Z3", "T3"):
            sev = "info" if cid == "Z3" else sev
        out.append(issue(A, kind, cid, sev, det, status, why, found_by=cid, scope="area", check=cid))

    # T1: uncited zones (rows) and zones without a table row (aggregate warning)
    r = res.get("T1")
    codes = [c for c in zt if not c.startswith("_")]
    for c in (c for c in codes if not (zt[c].get("cite") or {}).get("quote")):
        out.append(issue(A, "missing-citation", c, "missing", f"Zone {c} has no citation to the regulation text.",
                         found_by="T1", subject_zone=c))
    if r and r["status"] == WARN:
        out.append(issue(A, "no-table", "T1", "info", r["detail"], found_by="T1", scope="area", check="T1"))

    # T2: implausible values, one row per zone
    for c, z in zt.items():
        bad = [(f, v) for f, v in (z.items() if isinstance(z, dict) else []) if isinstance(v, dict) and v.get("check")]
        if bad:
            out.append(issue(A, "implausible-value", c, "wrong-answer",
                             f"{c}: " + "; ".join(f"{f} \"{v.get('text')}\" ({v['check']})" for f, v in bad[:3]) + (" ..." if len(bad) > 3 else ""),
                             found_by="T2", subject_zone=c, source=cite_of(zt, c), fields=[f for f, _ in bad]))

    # Z6: codes never read on the plan
    labels = (d.reg or {}).get("zoneLabels")
    if zt and labels and (DATA / labels).exists():
        seen = {f["properties"]["code"] for f in cd.load(DATA / labels)["features"]
                if f["properties"].get("reg", d.reg_id) == d.reg_id}
        waived = acc.get("codes_not_on_plan", {})
        gone = sorted(c for c in zt if not c.startswith("_") and c not in seen)
        todo = [c for c in gone if c not in waived]
        if todo:
            out.append(issue(A, "code-not-on-plan", "open", "uncertain",
                             f"{len(todo)} regulation codes never read on the plan: {', '.join(todo[:8])}{' ...' if len(todo) > 8 else ''}.",
                             found_by="Z6", codes=todo, source=cite_of(zt, todo[0])))
        if [c for c in gone if c in waived]:
            w = [c for c in gone if c in waived]
            out.append(issue(A, "code-not-on-plan", "listed", "info",
                             f"{len(w)} regulation codes are listed as not on the plan: {', '.join(w[:8])}{' ...' if len(w) > 8 else ''}.",
                             "worked-around", "; ".join(sorted({waived[c] for c in w}))[:300], found_by="Z6", codes=w))

    # Z7: crossings, grouped by zone code
    if res.get("Z7", {}).get("status") in (FAIL, WARN, PASS, WAIVED):
        zr, fresh = cd.zone_line_result(d)
        if zr and fresh and zr.get("linesFound"):
            ok = acc.get("line_crossings_ok", {})
            groups = {}
            for c in zr["crossings"]:
                k = f"{c['at'][0]:.5f},{c['at'][1]:.5f}"
                groups.setdefault((c["code"], k in ok), []).append((c, ok.get(k)))
            for (code, is_ok), items in sorted(groups.items()):
                items.sort(key=lambda x: -x[0]["m"])
                first = items[0][0]
                total_m = sum(i[0]["m"] for i in items)
                n = len(items)
                out.append(issue(
                    A, "crossed-boundary", code + (":checked" if is_ok else ""), "wrong-answer" if not is_ok else "info",
                    f"{code}: {n} zone area{'s' if n > 1 else ''} run across a red dotted boundary line "
                    f"(worst {first['m']} m, {round(total_m)} m in all).",
                    "worked-around" if is_ok else "open", "; ".join(sorted({i[1] for i in items if i[1]})) or None,
                    source=cite_of(zt, code), found_by="Z7", subject_zone=code, places=n,
                    at=[round(first["at"][0], 6), round(first["at"][1], 6)],
                    all_at=[[round(i[0]["at"][0], 6), round(i[0]["at"][1], 6)] for i in items[:20]]))

    # Z8: the text names a plot's zone and the map disagrees
    p = ROOT / "scripts/plans" / f"{key}-textzones.json"
    refs = acc.get("text_refs")
    if p.exists():
        st = cd.load(p)["statements"]
        if not st and not refs:
            out.append(issue(A, "text-not-read", "Z8", "info",
                             "The text reader found no plot named with its zone; how this regulation refers to zones is not recorded.",
                             found_by="Z8", scope="area", check="Z8"))
        zones = {}
        for pl in d.plots():
            if pl.get("hrsz"):
                zones.setdefault(pl["hrsz"], [z["code"] for z in pl.get("zones", [])])
        ok = acc.get("text_zones_ok", {})
        for s in st:
            z = zones.get(s["hrsz"])
            if z and not (set(s.get("codes") or [s["code"]]) & set(z)):
                said = f"zone {s['zone']} ({'/'.join(s['codes'])})" if s.get("zone") else s["code"]
                note = f"Plot {s['hrsz']} is {said} in the text, {'/'.join(z)} on the map."
                out.append(issue(A, "text-vs-map", s["hrsz"], "wrong-answer" if s["hrsz"] not in ok else "info", note,
                                 "worked-around" if s["hrsz"] in ok else "open", ok.get(s["hrsz"]),
                                 found_by="Z8", subject_plot=s["hrsz"]))

    # Waived checks that are not aggregates above (Z5, P1..): keep the reason visible
    for cid, why in acc.get("waive", {}).items():
        if cid in SKIP and cid != "Z5":
            out.append(issue(A, "area-gap", cid, "info", f"Check {cid} does not apply or is not possible here.",
                             "worked-around", why, found_by=cid, scope="area", check=cid))

    # Config: source typos fixed, variant tables
    ing = d.cfg.get("ingest", {})
    for fx in ing.get("rowCodeFix", []):
        code = fx["to"]
        out.append(issue(A, "source-typo", code, "wrong-answer",
                         f"The regulation prints the row of {code} under another code; read as {code}.",
                         "fixed", fx.get("why"), source=cite_of(zt, code), found_by="ingest",
                         subject_zone=code, fix=f"rowCodeFix in districts/{key}.json"))
    for code, why in ing.get("duplicateRows", {}).items():
        out.append(issue(A, "variant-tables", code, "missing",
                         f"{code} has several tables (variants); the card shows only the first.", "open", why,
                         source=cite_of(zt, code), found_by="ingest", subject_zone=code))

    po = (d.reg or {}).get("planOutdated")
    if po:
        out.append(issue(A, "plan-outdated", "plan", "uncertain",
                         f"The plan changed on {po.get('since')} ({po.get('what')}); the map layer and zone borders are still the old plan.",
                         found_by="regulations.json", scope="area"))
    return {"name": area_name(d), "reg": d.reg_id, "issues": out}


def main():
    keys = [a for a in sys.argv[1:] if not a.startswith("--")] or cd.published_keys()
    old = json.loads(OUT.read_text()) if OUT.exists() else {"areas": {}, "issues": []}
    today = date.today().isoformat()
    prev = {i["id"]: i for i in old["issues"]}
    areas, issues = dict(old.get("areas", {})), []
    for i in old["issues"]:
        if i["area"] not in keys:
            issues.append(i)
    for k in keys:
        got = collect(k)
        areas[k] = {"name": got["name"], "reg": got["reg"]}
        now = {i["id"] for i in got["issues"]}
        for i in got["issues"]:
            o = prev.get(i["id"])
            i["first_seen"] = o["first_seen"] if o else today
            i["last_seen"] = today
            if o and o.get("fixed_at") and i["status"] != "fixed":
                pass  # came back: no fixed_at
            if i["status"] == "fixed":
                i["fixed_at"] = (o or {}).get("fixed_at") or today
            issues.append(i)
        for o in old["issues"]:  # gone since the last run = fixed, kept in the history
            if o["area"] == k and o["id"] not in now:
                if o["status"] != "fixed":
                    o = {**o, "status": "fixed", "fixed_at": today, "why": o.get("why") or "no longer reported by the checks"}
                issues.append(o)
    issues.sort(key=lambda i: (i["area"], i["kind"], i["id"]))
    counts = {s: sum(i["status"] == s for i in issues) for s in ("open", "worked-around", "fixed")}
    OUT.write_text(json.dumps({"generated": today, "counts": counts, "areas": dict(sorted(areas.items())), "issues": issues},
                              ensure_ascii=False, separators=(",", ":")))
    print(f"{OUT.relative_to(ROOT)}: {len(issues)} issues {counts} in {len(keys)} areas, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
