# Onboarding batch budapest-2: Budapest IX–XVI (triage, 2026-10-04)

Sources: njt.jog.gov.hu search (municipal decrees in force; njt ids end in `5Y<issuer>`: IX 258 … XVI 265,
Főváros 4191), each decree's consolidated text (all lazily loaded blocks fetched, see below) and its annex
files, probed with `plan_probe.py`.

City-wide, applies everywhere alongside the district rules: **FRSZ**, Budapest főváros rendezési szabályzata,
3/2026. (II. 12.) Főv. Kgy. rendelet (`2026-3-SP-5Y4191`, in force from 2026-02-14; replaces 5/2015. (II. 16.),
which older district texts still cite). Duna-parti építési szabályzatok (DÉSZ, Főv. Kgy.) cover the Danube
banks and are excluded from the district KÉSZ: IX → 50/2018. (XII. 10.) (`2018-50-SP-5Y4191`, V/IX/XXI),
XI → 21/2024. (V. 8.) (`2024-21-SP-5Y4191`, I/II/XI), XIII → 36/2018. (X. 30.) (`2018-36-SP-5Y4191`).
XIV: the Városliget is under the Főv. Kgy. Városligeti építési szabályzat (VÉSZ), not the district KÉSZ.

**njt pitfall (fixed in `ingest-kesz.mjs`):** long decrees arrive with part of their text not loaded; njt's
page script fetches each block from `/ajax/njtGetBlock.json` on scroll. Without loading them the XIII KÉSZ
stops at § 73 and has no annexes; X misses 2. melléklet tables 9–36. `ingest-kesz.mjs` now loads every block.

| Dist. | Regulation(s) in force (njt id) | Coverage | Zone limits table | Plan on njt | Status |
|---|---|---|---|---|---|
| X Kőbánya | KÉSZ 16/2020. (XI. 26.) `2020-16-SP-5Y259` (+ two 2003/2006 partial KÉSZ still listed as in force, last changed 2006/2016, superseded in practice) | whole district | in text, 2. melléklet (36 tables) | 13 PNG sheets (`/picture/`, 200/300 dpi, 1:2000), + 4 védelmi sheets | in progress (first) |
| XIII | KÉSZ 14/2021. (VI. 29.) `2021-14-SP-5Y262` | whole district except DÉSZ area | in text, 3. melléklet (≈20 tables) | 12 colour raster PDFs (one JPEG, 10807×8091 px, 300 dpi, 1:2000), sheet grid rotated | next: raster pipeline as XX |
| XIV Zugló | Zugló építési szabályzata 11/2021. (III. 26.) `2021-11-SP-5Y263` | whole district except VÉSZ | in text, 3. melléklet | one 38-page PDF (39 MB), vector with a text layer (zone codes readable), raster basemap | todo: vector path |
| XV | KÉSZ 17/2018. (VI. 26.) `2018-17-SP-5Y264` | whole district | **annex PDF** (2. melléklet), not in text | 1. melléklet: one 202 MB PDF, 20 sheets 1:2000 | todo: needs a PDF-table ingest |
| XVI | KÉSZ 21/2018. (VII. 6.) `2018-21-SP-5Y265` | whole district | **annex PDF** (2. melléklet), not in text | 1. melléklet: 23-page PDF (51 MB), raster pages, no text layer | todo: needs a PDF-table ingest + OCR |
| XI Újbuda | 11 partial KÉSZ, together the whole district: 30/2016 `2016-30`, 11/2017 `2017-11`, 8/2017 `2017-8`, 16/2018 `2018-16`, 25/2018 `2018-25`, 26/2018 `2018-26`, 43/2018 `2018-43`, 30/2020 `2020-30`, 1/2021 `2021-1`, 36/2021 `2021-36`, 41/2023 `2023-41` (all `-SP-5Y260`) | each by bounding streets | mostly in annex PDFs (2. melléklet); only 2017-8 has tables in text | vector PDFs with text layers (zone codes readable), 1–9 files each | todo: needs per-area regulation choice in the app + PDF tables |
| XII Hegyvidék | KVSZ 14/2005. (VIII. 10.) `2005-14-SP-5Y261` (rest of district) + KÉSZ 1/2018 `2018-1`, 23/2018 `2018-23`, 26/2020 Észak-Hegyvidék `2020-26`, 18/2021 Alkotás u. `2021-18`, 35/2021 Kissvábhegy `2021-35`, 36/2021 Dél-Hegyvidék `2021-36` | KVSZ for what the KÉSZ do not cover | in text (all) | KVSZ: **no plan on njt** (only a small image); KÉSZ: A3 multi-page PDFs (37–78 p.), vector without text, or single vector sheets | todo; KVSZ plan must come from hegyvidek.hu |
| IX Ferencváros | KÉSZ 20/2026. (VII. 16.) `2026-20` (Vámház krt–Üllői út–Déli körvasút, replaces Belső-/Középső-Ferencváros, Malmok, Vágóhíd u. KÉSZ), KÉSZ 22/2017 UNIX `2017-22`, 1/2019 Kvassay `2019-1`, + 10 older KSZT/KÉSZ 2002–2012 (`2002-15`, `2002-19`, `2002-21`, `2003-34`, `2003-37`, `2003-41`, `2004-38`, `2005-17`, `2010-20`, `2012-20`; all `-SP-5Y258`) | partial; Külső-Ferencváros residential areas (e.g. Gloriett-like blocks) need checking | in text for the KÉSZ; old KSZT partly none | 2026 KÉSZ: 8 PNG sheets + overview; old KSZT: small A4/A3 scans (poor) | todo |

Order of work (population, then feasibility): XI is the largest but needs per-area regulation choice in
the app and PDF tables, so X and XIII (district-wide, tables in text, plans readable) go first, then XIV.

## Progress

(updated as municipalities are finished)
