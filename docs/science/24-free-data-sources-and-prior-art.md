# 24 — Free data sources & prior art (for the observable decomposition)

_Research scan (2026-06-03) for tying car/driver attributes to **observable data** instead of
generic claims. Goal: decompose the lumped strength into measurable components — (1) one-lap
pace, (2) clean-air race pace, (3) tyre deg, (4) reliability/DNF, (5) racecraft/overtaking,
(6) start, (7) strategy. Everything below is free + programmatic unless flagged._

## Free data sources beyond FastF1 / Open-Meteo

| Source | What it adds | Components | Cost / limits / gotchas |
|---|---|---|---|
| **Jolpica-F1** (`api.jolpi.ca/ergast/f1/`) | The **Ergast successor** (Ergast shut down early 2025; FastF1 already routes through it). Results, **pitstops**, laps, sprint, and the **`status`** endpoint = retirement *cause* codes (Engine/Gearbox/Collision/+1 Lap…) | (4) reliability via `status`; (7)/(3) pitstops; (1) quali | Free, no auth. **4 req/s, 500/hr** (HTTP 429); `limit` max 100 → paginate; cache/mirror locally |
| **OpenF1** (`openf1.org`) | **`intervals`** (gap to car ahead ~4s), **`location`** (x/y/z track position), **`stints`**, **`pit`**, **`starting_grid`**, **`race_control`** (flags/SC), telemetry ~3.7Hz, 2023+ | **(5) racecraft + dirty-air (real gaps!)**, (6) start (grid→lap1), (3)/(7) | **Free for historical** (anything >30min after a session). Live = €9.90/mo. 3 req/s, 30/min free. The unique value vs FastF1 is `intervals`/`location`/`starting_grid` |
| **F1DB** (github.com/f1db/f1db) | Most complete free historical DB 1950→ (drivers, constructors, **tyre manufacturers**, grids, fastest laps, pitstops). Ships SQLite/PG/MySQL dumps | priors for all | Free download; historical aggregates, not telemetry. Use as a **local backbone** so we don't hammer Jolpica |
| **Pirelli press** (press.pirelli.com) | Per-race **C1–C6 compound nomination** + set allocation | **(3) deg cross-race comparability** (FastF1 only gives relative SOFT/MED/HARD) | No API. ~24 rows/season → **hand-curate a lookup table** (highest ROI, trivial effort) |
| **FIA documents** (fia.com/documents) | Stewards' decisions, penalties, technical directives, grid drops | (5) racecraft (penalties), (7) grid penalties, DNF cross-check | No API. **Scraping only** (`fia-doc`, fia-f1-docs-bot) — fragile, unsanctioned ToS → best-effort, low-volume only |
| **F1 SignalR live feed** | Raw upstream feed | live timing | No auth but **proprietary, legally grey → don't consume directly; let FastF1/OpenF1 abstract it** |

**Skip:** betting/odds archives (no free programmatic source; aggregator ToS prohibits scraping; APIs paid), commercial F1 APIs (paid, no advantage over Jolpica+OpenF1+FastF1).

## Prior art worth mining (free, implementable)

| Source | Year | The idea to mine |
|---|---|---|
| **State-space tyre-deg model** (arXiv 2512.00640) | 2025 | **Directly our problem, uses FastF1.** Bayesian state-space: lapTime = f(fuel mass, **latent tyre pace**), pit = state reset. The latent state IS our clean-air-pace-minus-deg (components 2+3) in one estimator. Caution: they found **per-compound deg not statistically distinct** — matches our brief 08A "keep but flag" finding |
| **Heilmeier / TUMFTM race-simulation** (MDPI 2076-3417/10/21/7805; `TUMFTM/race-simulation`) | 2018–20 | The canonical decomposition: `lap = base(car,driver) + fuel(linear) + deg(age) + pit_loss`, deg fit **per driver** on **fuel-corrected residuals** (log if rich, linear if sparse). This is exactly our `clean_air_pace.py` correction recipe — validates the method + gives reference params |
| **Bayesian driver/constructor split** (Ingram blog; JQAS hierarchical ROL) | 2021–23 | Separate latent driver vs car ratings; **~64–88% of result variance is the car**. Use as a **regularizer** so bottom-up components don't double-count the car |
| **RAPM driver/constructor** (arXiv 2508.00200) | 2025 | Regression-only (time-decayed ridge) alternative to the Bayesian split — cheaper |
| **Qualifying predictive power** (arXiv 2507.10966) | 2025 | Ordinal logit grid→finish: quantifies how much one-lap pace translates → a defensible weight for the quali feature (we use quali heavily) |
| **Tyre-energy deg** (arXiv 2501.04067) | 2025 | Deg driven by sliding energy ≈ f(speed, lat-accel, throttle, brake) — proxy from FastF1 telemetry → physics-flavoured deg tied to telemetry rows (our roadmap open-Q1) |
| **Stackelberg pit-stop game** (ScienceDirect S0377221724005484; Frontiers AI 2025) | 2024–25 | Undercut as a leader-commits/follower-responds game — the game-theoretic undercut feature (we already have a first cut in `strategy.cover_or_extend`) |
| **Optimal tyre management** (ScienceDirect S2405896320318577) | 2020 | grip = f(wear, **temperature**) with a thermal window → justifies a **track-temp × compound** deg interaction (we have track temp from Open-Meteo + FastF1) — our roadmap open-Q5 |

**Overtaking/dirty-air (component 5):** no strong free academic model on timing data (rigorous work is CFD or AWS-proprietary). **Build it ourselves from OpenF1 `intervals`/`location`**: empirically fit the lap-time penalty vs gap-to-car-ahead (<1s = dirty air) and overtake-success vs gap/pace-delta. Data-row-traceable — exactly what our `_apply_dirty_air` approximates today (it would replace the proxy with measured values).

Meta-resource: `subinium/awesome-f1` (vetted free APIs/datasets).

## Highest-value, lowest-effort shortlist (for OUR decomposition)

1. ~~**Pirelli C1–C6 lookup table** — makes tyre-deg comparable across races.~~ **DONE, premise
   FAILED (task #18).** Sourced 2022–26 nominations (`data/pirelli_compounds.json`, 94 races). But
   the absolute C-number does NOT track in-race deg (C5/C6 show the *lowest* — softer compounds run
   at low-deg tracks in short managed stints); the **relative** compound is cleaner (SOFT 0.087 vs
   HARD/MED ~0.037 s/lap²). Matches the state-space paper + brief 08A. Kept as a sourced artifact,
   NOT wired into deg. Honest negative.
2. **OpenF1 `intervals` + `location` + `starting_grid`** (free, historical) — true gap-based **clean-air** (upgrade `clean_air_pace.py` from the fast-quantile proxy) and **dirty-air** (upgrade `_apply_dirty_air` from proxy to measured) and **start** performance. Biggest single unlock.
3. **Jolpica `status` endpoint** — retirement causes → reliability decoupling. → task #10.
4. **Heilmeier per-driver fuel-corrected deg** — validates/improves `clean_air_pace.py`; reference params to check against. → task #11.
5. **F1DB local backbone** — priors without rate-limit risk.
6. **Driver/car split as a regularizer** (Ingram/RAPM) — keep bottom-up components from double-counting the car (which is ~64–88% of variance).

## How this maps to our tasks

- The whole scan **validates the decoupling architecture** (brief 22): the state-space + Heilmeier papers are doing exactly the clean-air-pace + per-driver deg decomposition we built.
- **OpenF1 `intervals`/`location`** is the upgrade path for both `clean_air_pace.py` (true gap-based clean-air, replacing the fast-quantile proxy) and `_apply_dirty_air` (measured dirty-air penalty). New task.
- **Jolpica `status`** → the reliability double-count fix (task #10) with real causes.
- **Pirelli table + Heilmeier** → per-car deg from observed stints (task #11).
