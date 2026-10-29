# Acceptance criteria: when a district or village may go live

Every municipality (Budapest district, KÉSZ area or village) must meet these criteria before it is
called live, and every re-ingest or pipeline change must keep meeting them. They collect what the
reviews of 2026-10-29 (zone assignment; zone and plot information), the onboarding standard of
2026-10-14 (plots and zone areas, not just plan tiles) and the alignment issue of 2026-10-29 (plan
overlay vs land-registry plot lines) found going wrong.

```sh
python3 scripts/check_district.py <key>            # the full table for one key
python3 scripts/check_district.py <key> --online   # also compare the regulation with njt.hu
python3 scripts/check_district.py --all            # one line per published key
```

The check reads only published files (public/data, public/pmtiles, registry/, scripts/plans,
scripts/reviews) with the Python standard library. Each criterion ends as **pass**, **warn**,
**FAIL**, **not measured** (the measurement or sign-off is missing) or **waived** (with a reason in
the district config). The verdict is *ready* only when nothing fails and nothing is unmeasured.
A key is live only when `check_district.py <key> --online --strict` exits 0.

## Where it sits in onboarding

1. Ingest the regulation (`ingest-kesz.mjs`, `extract_*.py`), then `scripts/validate_zones.py <key>`.
2. Plan pipeline (`pipeline.py <key>`: sheets, ocr, labels, georef, zones, parcels).
3. Plots and zone areas (`fetch_btp_parcels.py` + `plan_vector_parcels.py <key> --zones-only`, or OÉNY).
4. Align the plan to the plot lines (`plan_plotfit.py <key>`), then `pack_tiles.py <key> --from-tiles`.
5. Review: `review_zones.py batches <key> --sample 50`, read the crops, `apply`, rerun `--zones-only`.
6. `registry.py export <key>`, `registry.py build`, `hrsz_index.py`.
7. **`check_district.py <key> --online --strict`**. Fix or waive everything it reports, and add the
   three manual sign-offs (M1 to M3) to `districts/<key>.json`.
8. Commit. The PR's district acceptance job runs the check on every key the PR touches; a new key
   must pass it.

`pipeline.py <key>` ends with the check, so a run shows straight away what is still missing.

## The criteria

### Regulation text (R)

| Id | Criterion | Bar | Why |
|---|---|---|---|
| R1 | The regulation is in regulations.json with its PDF, `effectiveFrom` and njt link, and every district it covers lists it | all present | a tap only finds regulations its district lists |
| R2 | The text and annexes are the version in force on njt.hu (`--online`, `scripts/check_freshness.py`) | same version date, same annex sha256 | I, XIV and XVII were silently out of date on 2026-10-29 |

### Zone limits table (T)

| Id | Criterion | Bar | Why |
|---|---|---|---|
| T1 | Every zone has a citation; some zones have limits from the table | none uncited; warn above 20% without a table row | V shipped with all 13 zones "no table" |
| T2 | Values are plausible: percents 0–100, FAR ≤ 10, heights ≤ 120 m, no two numbers read as one ("45 75" → 4575), nothing marked by `validate_zones.py` | zero | XII-KVH coverage 4575%, XXI and XVII columns shifted |
| T3 | Every building zone has a max height, or a note that the plan sets it (`heightNote`) | warn | XIII has no height in any of 271 zones |

The card must show these values: T3 checks the data, the card's display is checked by M2.

### Plan overlay (P)

| Id | Criterion | Bar | Why |
|---|---|---|---|
| P1 | The plan is a packed PMTiles archive, chunks 0..n contiguous, size on disk = size in regulations.json, no loose `public/tiles` committed | exact | a rebuild on 2026-10-10 left 10 plans pointing at undeployed tiles |
| P2 | Every plan sheet is placed on the map, or listed in `acceptance.sheets_not_on_map` with why (legend, index sheet) | zero unplaced | an unplaced sheet is a hole in the overlay and in the zones |
| P3 | **The plan's plot lines lie on the land-registry plot outlines** (`scripts/plan_plotfit.py <key> --check`, per sheet) | median ≤ 1.0 m and 90th percentile ≤ 2.5 m on every sheet | the plan and the "Telekhatárok, hrsz" overlay must agree with each other better than with OpenStreetMap; zones are assigned by plot, so an offset moves plots across zone lines |

### Plots (L)

| Id | Criterion | Bar | Why |
|---|---|---|---|
| L1 | Plots and zone areas are linked in regulations.json and not empty | both | the onboarding standard: a tap highlights the plot and its zone. The same 2026-10-10 rebuild unlinked them for I, II, V, VI, VI-2, VIII, X, XIV |
| L2 | Every zone code on a plot exists in the zone table; plots carry parcel numbers | no unknown code; warn below 90% numbered | an unknown code gives an empty card |
| L3 | Parcel-number search index exists (`hrsz_index.py`) | present | the search found no parcel in 41 plans until 2026-10-29 |

### Zone of each plot (Z)

| Id | Criterion | Bar | Why |
|---|---|---|---|
| Z1 | The plan's zone boundaries are read: `plan.zone_lines` set, or zone areas from the plan's zone cells (OÉNY villages) | required | 41 plans assigned zones by nearest label only; nothing flagged their mistakes |
| Z2 | Building plots with a zone | fail below 80%, warn below 90% (waive with a reason where the rest is another KÉSZ) | XI KÉSZ 7 left 48% of plots without a zone |
| Z3 | Zoned plots whose zone is an estimate (`basis` block/near, or status estimated) | warn above 20% | estimates are where the errors are |
| Z4 | Plots flagged zone-unclear that nobody reviewed | at most 2% of building plots | II and X still had 2,000–3,000 unreviewed |
| Z5 | **Random sample review**: at least 50 plots picked at random among automatically zoned ones, read on the plan crop (`review_zones.py batches <key> --sample 50`) | at least **95%** right (see below) | the only measure of what users actually see; also the regression set for later pipeline changes (`EVAL_OUT`) |
| Z6 | Every code the regulation defines is read somewhere on the plan, or listed in `acceptance.codes_not_on_plan` with why | zero unexplained | a missed label silently hands its plots to the neighbour's code (62–100% of the time in the stress test) |

### Manual sign-offs (M)

Recorded in `districts/<key>.json` under `acceptance.signoff` as one line each: date, who, what was looked at.

| Id | What to do |
|---|---|
| M1 | Turn on the plan and the "Telekhatárok, hrsz" overlay and look at three places, one of them on a sheet edge: plot lines on top of each other, zone colours inside the right plots. |
| M2 | Open five random cards and compare each value with the official table; check the max height and the two-zone warning show where they should. |
| M3 | Every data source the key uses (plots, plan files from a municipal site) is a row in the permission register of `docs/data-sources.md`. Licensing is still not cleared: PoC only. |

## Waivers

A criterion that cannot be met for a good reason is waived in the district config, never by
changing a bar for everyone:

```json
"acceptance": {
  "waive": {"Z2": "the south third of the district is the xi-sasad KÉSZ"},
  "sheets_not_on_map": {"0": "legend sheet"},
  "codes_not_on_plan": {"KÖu-1": "defined in the text, the plan draws no such road"},
  "signoff": {"M1": "2026-10-29 Peti: Kossuth tér, Fő utca, sheet 3/4 edge"}
}
```

The report prints each waiver with its reason, so they stay visible.

## Zone accuracy bar (Z5): to be decided

Proposed: **95% on a sample of 50**, so at most 2 wrong zones in 50. With 48 of 50 right, the true
accuracy is above about 86% with 95% confidence; the bar mainly stops plans whose errors are
systematic (a missed label, an unread boundary). Alternatives: 90% (at most 5 wrong in 50) is
easier to reach on scanned plans; 98% only means something with a sample of 100 or more. The
constant is `ZONE_ACCURACY_MIN` in `scripts/check_district.py`.

## Status on 2026-10-29

`check_district.py --all` on the deploy branch: no key is ready yet. Most common gaps:

- P3 not measured anywhere until `plan_plotfit.py` lands and runs on every key.
- Z1: 40 of 50 plans read no zone boundary lines.
- Z5: only I, II and X have a 50-plot sample (100%, 98%, 96%); V (23/29), VI (28/28), XIV (40/40) need more.
- Z6: 42 plans have regulation codes never read on the plan (or not yet listed as unused).
- P2: 8 plans have unplaced sheets (II, IX, VIII, X, XIII, XV, XVI, XXII).
- T2: 5 plans have implausible values (IV-9, VIII, XII-DH, XII-KVH, XXI).
- Z4: II, X, VIII and IX-inner have 865–3,168 unreviewed unclear plots (II and X reviews were of the
  traced plots, before the switch to city GIS plots).
- L2: X, XIV and VI-2 have plot codes missing from the zone table (Kt-Fk/6, KÖu-2, Kt-kk/VI/1).
- Manual sign-offs M1 to M3: none recorded yet.

Fixed with the check itself: L1 (plots and zone areas relinked for I, II, V, VI, VI-2, VIII, X,
XIV) and L3 (parcel search built for 40 plans; VI-2's plots carry no numbers).
