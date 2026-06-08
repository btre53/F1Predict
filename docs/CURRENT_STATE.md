# Current State — F1Predict

_Last updated: 2026-06-08 (RESOLVED: ingest re-sourced on OpenF1+Jolpica; autonomous VPS cron LIVE)_

## ▶ RESOLVED (2026-06-08) — FastF1-free ingest; autonomous server-side auto-update (read first)

The datacenter-IP-block (below) is **solved by re-sourcing the ingest off FastF1's blocked
livetiming onto OpenF1 + Jolpica**, which the VPS CAN reach. The app now auto-updates itself
weekly, fully server-side — no GitHub, no residential machine, no proxy, free.

- **`app/etl/openf1_ingest.py`** (NEW): reproduces the exact `laps.parquet` schema from OpenF1
  (laps/stints/pit/position/race_control/drivers). Validated vs the FastF1 Monaco 2026 ingest:
  **sectors + speed-trap exact, lap time 1394/1415 exact, stint 100%, tyre_life 95% within 1 lap,
  compound 97.7%, position 98.5%.** tyre_life uses OpenF1's native age (red-flag splits cause a
  rare ±1-2 lap noise the deg model absorbs); track_status/is_accurate are approximated (~90%).
- **`calendar.py`**: season schedule from Jolpica (FastF1 fallback) → `next_race` works on the VPS.
  **`results.py`**: DNF classification from Jolpica `positionText`/`status` (98.7% DNF parity).
  **`refresh.py`**: completed-races via Jolpica, laps via OpenF1. `results.parquet` rebuilt.
  **119 tests pass** (+4 new in `test_openf1_ingest.py`). FastF1 kept as a fallback/telemetry path.
- **NOTE:** only FastF1's *livetiming* (laps, `session.results`) is datacenter-blocked; its
  `get_event_schedule` works from the VPS — so weather/polymarket (schedule-only) were left as-is.
- **AUTONOMOUS CRON LIVE on the VPS:** root crontab `23 8 * * 1 /usr/local/bin/f1-weekend-refresh`
  runs `app.etl.refresh` in the `f1-api-1` container (writes the persistent **f1data volume**) then
  `docker compose restart api`. Re-enabled the volume (it's now the live source of truth; git data
  is the seed). **Proven from the VPS:** OpenF1 1452 laps + Jolpica calendar/results all fetched
  server-side; the cron script ran clean (refresh exit 0, api restarted, site healthy at 169 races
  with Monaco overlay live). Logs: `/var/log/f1_refresh.log`. **First real run: Mon 2026-06-15**
  (after Barcelona R7, race 06-14) — it should ingest Barcelona with no intervention.
- **STILL TODO (the one remaining piece): the GPS track MAP** (`build_track_positions` /
  `build_track_outlines`) is still FastF1-based, so it won't auto-build for new races. Re-source it
  from OpenF1 `location` (x,y,z confirmed available) with a shared coordinate box so the eye-catching
  map auto-generates for every race (currently only 5 hand-built 2024 demos). Separable follow-up.

## ▶ CRITICAL FINDING (2026-06-08, now RESOLVED above) — F1 blocks datacenter IPs

**The post-race auto-pipeline (GitHub cron + VPS cron) does NOT work, by a hard constraint:
F1's live-timing CDN (livetiming.formula1.com) blocks DATACENTER IPs.** Confirmed empirically:
- Hetzner VPS → timing load fails (`DataNotLoadedError`, "Failed to load timing data").
- GitHub Azure runners → SAME failure (the scheduled + dispatched ingest both failed at the
  FastF1 schema-contract test, root cause = the timing load failing).
- This residential dev box → FastF1 loads fine (Monaco R = 1452 laps, winner ANT).
  (Aside: a raw `urllib` GET 403s even here — that's a User-Agent filter, a red herring;
  FastF1's own UA works from residential.)

**So the race-data FETCH can only run from a residential connection.** Neither GitHub nor the
VPS can ever ingest. Also note: GitHub's `schedule` trigger was independently unreliable — the
Monday 08:00 UTC cron fired ~4.5h late (12:36 UTC) and 0 on-time fires.

**Monaco WAS ingested + deployed (2026-06-08) by running `app.etl.refresh` on THIS dev box,**
then commit/push + SSH `git pull && up -d --build` to the VPS. Live now: 169 races, championship
recalibrated (ANT leads, 6 done), and the Monaco in-play overlay is live
(`/replay/inplay?circuit=Monaco&year=2026` → winner ANT, 78 laps, per-lap model vs market).

**Changes made this pivot (all pushed):**
- `ingest.yml`: removed the unreliable `schedule` (kept `workflow_dispatch`). It is now
  effectively OBSOLETE for ingest — GitHub can't fetch — but the `deploy` job + `EDGE_SSH_*`
  secrets still work for a manual SSH redeploy. **Decide next session:** delete it or keep as a
  redeploy-only button.
- `docker-compose.edge.yml`: the f1data volume was tried then REVERTED (it would shadow freshly-
  built image data; the VPS-ingest model it supported is dead). Orphan volume pruned.
- `live_capture.yml` (Barcelona weekend capture): the Polymarket price half works on GitHub
  runners (Polymarket isn't IP-blocked); the FastF1 live-timing half will FAIL there (same block)
  — that capture also needs a residential machine.

**OPEN — ongoing automation (pending owner decision):** server-side auto-ingest is impossible.
Realistic options: (1) a scheduled task on THIS PC (idempotent `refresh` catches up all missing
races → commit/push → SSH-deploy; best-effort, only runs when the PC is on); (2) manual one-shot
after each race; (3) a residential proxy so the VPS can fetch (more infra/cost). Recommended: (1).

## ▶ LATEST (2026-06-07) — Monaco post-race status + live-capture wired (superseded by the finding above)

**Monaco GP (round 6, Sun 2026-06-07) — data NOT ingested yet, by design.** The `ingest.yml`
cron runs **Mon 08:00 UTC** (tomorrow); it'll pull Monaco Q/R + practice, recalibrate, and
commit to the repo if tests pass. FastF1 already has the result (ANT win, HAM 2nd, HAD 3rd) so
the auto-ingest will succeed. **Caveat:** ingest commits to the *repo* only — the live VPS
(`f1.built-by-bobby.com`) won't show Monaco until a `git pull && docker compose up -d --build`
redeploy (no auto-deploy hook). Deployed heartbeat today still shows 168 races / latest 2026 R5.
**Monaco was NOT dogfood-captured** (no `live_*.csv`, no timing file) — the live SignalR replay
is unrecoverable; the Polymarket price curve is still backfillable from CLOB `prices-history`.

**NEW — automated race-weekend capture** (`.github/workflows/live_capture.yml` +
`app/etl/capture_preflight.py`), so we don't miss the record again (Barcelona is next, round 7,
race Sun 2026-06-14 13:00 UTC):
- Self-healing scheduled Action, same ethos as `ingest.yml`. Two best-effort records published
  as **build artifacts** (the raw files are gitignored scratch → not committed): Polymarket price
  drift (`live_capture`) + FastF1 live timing (`live_timing`).
- Crons tuned to a EUROPEAN weekend (Sat 13:00/13:40, Sun 11:00/12:40 UTC). `capture_preflight`
  resolves the upcoming race from the FastF1 schedule and **no-ops unless the race is within 30h**,
  so the weekly crons are safe to leave on. `workflow_dispatch` for manual/non-EU races.
- `live_capture.py` refactored: `--gp` takes comma-separated aliases (tries `barcelona,spanish` —
  Polymarket's 2026 slug isn't known until they open the market ~2-3 days out) + `--minutes` cap
  for unattended runs. Back-compat `slugs_for` kept. **115 tests pass, 1 skipped.**
- **TO ACTIVATE: must commit + push `live_capture.yml` to `main`** (scheduled Actions only run
  from the default branch). Then optionally fire it via "Run workflow" to smoke-test the plumbing.

**NEW — auto-redeploy + automatic (b) in-play backfill (the post-race pipeline is now fully
hands-off → site).** Both flow through the Mon 08:00 UTC `ingest.yml`:
- **Auto-redeploy** (`ingest.yml` `deploy` job): after the data commit, SSHes to the edge VPS and
  runs `cd /opt/deploy/f1 && git pull --ff-only && docker compose -f docker-compose.edge.yml up -d
  --build`. Gated on `commit.outputs.changed == 'true'` (a no-op weekend never rebuilds). **Needs
  3 repo secrets: `EDGE_SSH_KEY` (private key in the VPS authorized_keys), `EDGE_SSH_HOST`,
  optional `EDGE_SSH_USER` (default root).** Assumes deploy dir `/opt/deploy/f1` + the edge compose
  — confirm those on the VPS. This fixes the "repo updated but site stale" gap.
- **(b) automatic in-play price curve** (`inplay_probe.fetch_year` + year-aware `build_overlay`,
  wired into `refresh.py`): every weekend refresh pulls the new race's CLOB winner-price curve
  (reuses `season_winner_markets`, slug-drift-robust) and rebuilds `inplay_overlay.json`. Verified
  end-to-end on Monaco 2026 (slug `f1-monaco-grand-prix-winner-2026-06-07` resolves; 20 drivers /
  7800 pts). Overlay JSON is now keyed **`<year>-<circuit>`** (was bare circuit); `replay.inplay_overlay`
  looks up year-aware with a bare-circuit fallback; the 2024 backtest races were regenerated to the
  new keys. Frontend already passes `(circuit, year)` → 2026 races surface automatically once the
  curve lands. **115 backend tests pass, 1 skipped; frontend builds (315KB).**
- **NET:** after Monday's cron, the live site auto-shows Monaco results/standings/companion AND the
  Monaco model-vs-market in-play overlay, with no manual step. (Monaco itself gets backfilled by
  that same run.)
- **SHIPPED (2026-06-08):** all of the above pushed to `main` (`af5dc79`); both Actions are active
  on GitHub. Deploy secrets `EDGE_SSH_KEY` (dedicated ed25519, public half in the VPS root
  authorized_keys) + `EDGE_SSH_HOST` set; `EDGE_SSH_USER` unset → defaults to root. VPS deploy
  assumptions verified live: `/opt/deploy/f1` is a git checkout that pulls non-interactively;
  containers `f1`/`f1-api-1`/`f1-db-1` run under compose project `f1`. The Mon 08:00 UTC ingest is
  the first end-to-end test (ingest → backfill → commit → SSH redeploy). Caveat: the CI deploy key
  has effective root on the shared edge VPS (docker group) — inherent to push-based deploy.

## ▶ SESSION CLOSE-OUT / NEXT-SESSION HAND-OFF (read first)

**RELEASED to `main` (HEAD `bc5c959`) — `mechanistic-features` synced + pushed. 115 tests pass, 1 skipped.**
**+ Model Replay sandbox** (`7fa8a33`): interactive "pick a past race + a model → forward-chained prediction vs actual" on the FINDINGS page.
**+ Visual-critic QA pass** (`bc5c959`): fixed FINDINGS card width-collapse (5★), StrategyLab blank lap-time chart (5★, optimize now populates the top strategy's profile), Championship tie-sort (4★, secondary by exp_points), lap times now M:SS.ddd (`charts.lapTime`), Explainer 3-letter team codes. Critic artifacts (Predictor/Explorer loader/idle captures) + transient Markets vig triaged out.
Production predictor probabilities UNCHANGED (calibrated rank model); all new work is additive.
**Deploy = on the VPS host** per `docs/DEPLOY.md` (`git pull && docker compose up -d --build`); Docker isn't on the dev box so the container build runs on the host. main == the deployed checkpoint.

**LATEST (HEAD ca42eb0) — companion view, perceived-perf, and a deep model-vs-market study:**
- **RACE COMPANION view** (`2eb3519`): `GET /companion/props` + COMPANION tab — the upcoming race's
  Polymarket props with OUR model beside the de-vigged market (winner/podium/pole/safety-car priced;
  rest market-only). `polymarket.event_devig` + `discover_f1_markets`/`classify_f1_market` catalog.
- **F1-circuit loader** (`9d4ff89`): `TrackLoader.tsx` (SMIL animation) on the slow tabs. App was
  already SPA + debounced + cache-warmed (no Streamlit-style reloads); this is perceived-perf polish.
- **Held-up asymmetry** (`beb52db`, brief 30): backmarkers yield to much-faster cars → per-lap
  held-up penalty shrinks with the pace mismatch. Opt-in in the position sim. **Best mechanistic
  result yet**: win-ll 0.178→**0.160**, top-pick 35.6→**37.8%**, "fast car from the back" recovery
  podium-ll 0.321→**0.299** (small podium/pts cost). `held_up_asymmetry=True`.
- **Brief 30 — model-vs-market divergence taxonomy** (the portfolio piece): the P20 experiment
  (Monaco 0% / Bahrain 8.9% — model is circuit-aware), 8 systematic divergence drivers, mapped onto
  the ranking-model literature (Harville=Gumbel/PL [what we use], Henery=Normal, Lo-Bacon-Shone λ).
- **Temperature-from-market + Lo-Bacon-Shone — both HONEST NEGATIVES** (`ca42eb0`): our temperature
  is already market-calibrated (γ≈1.05 → T≈0.476 vs our 0.5); λ=1 (plain PL) is best on podium (no
  favourite-longshot bias present). **Conclusion: our distribution is well-calibrated at every level;
  the residual market gap is information/ranking, not distributional** (converges with brief 29).
  Primitives kept (`probability.temper`/`fit_market_gamma`/`strengths_to_probs_lbs`), neither wired.

**Market-gap audit (brief 29) — the honest closing finding:** we are at the **free-data ceiling**.
The production Kalman already uses the two signals that matter (prior-race pace + the real quali
grid incl. penalties); the only unused free signal, this-weekend practice pace, is noise as we can
measure it (FP long-run corr 0.06 with quali) and not even testable on the priced races (FP ingested
~45% of 2025, 0% of 2026). Residual market edge is structural (fuel-corrected internal pace,
setup/upgrade intel, crowd sentiment — data we lack). No free lever found; framed as open problems
for collaboration. The pitch is final: calibrated, transparent, competitive, **no edge**.

**THIS SESSION (HEAD 7b443e9) — all of the next-session backlog #1–#7 cleared:**
1. **CHAMPIONSHIP page DONE** (`b…fe22b83`): `GET /championship` + `POST /championship/simulate`
   (interactive sandbox), `components/Championship.tsx` (2nd nav tab), de-vigged Polymarket title
   column. Rebuilt results.parquet to 2026 (standings fix). Honest: model ANT 87% vs market 51%.
2. **Pole-market backtest DONE** (`d060585`): `validate_quali_market.py` + `GET /markets/quali-backtest`.
   **No edge** — market pole Brier 0.039 vs model 0.045 over **n=23** (found via tag enumeration,
   both pole slug formats). brief 27.
3. **General Polymarket F1 market discovery DONE** (`b885588`): `classify_f1_market` +
   `discover_f1_markets` + `GET /markets/f1-catalog` — the companion-mode prop index (43 open
   markets across 13 types). The reusable foundation the owner asked for (props + Benter market-find).
3b. **RACE COMPANION view DONE** (`2eb3519`): `GET /companion/props` + `components/Companion.tsx`
   (COMPANION tab) — the upcoming race's props with OUR model beside the de-vigged market, outcome
   by outcome. Prices winner/podium (Kalman), pole (quali model), safety car (SC prior); lists the
   rest market-only. `polymarket.event_devig` (exclusive vs binary vs single Yes/No de-vig).
   Verified live on Monaco (pre-quali divergences shown honestly). The companion-mode build is done.
4. **Benter decision DONE** (`02256c5`): surfaced as a **Blend column** in the vs-market panel only
   (Brier 0.0509 — beats model, behind market; calibration aid, not edge). Not wired into the
   default predictor. brief 23.
5. **Straight-line defence + 2026 era gate DONE** (`7b443e9`, brief 28): measured straight-line
   index (team corr 0.82, predicts passing z=2.4) wired opt-in into the position sim — **neutral on
   order accuracy, kept OFF**; 2026 active-aero global threshold ×0.85 (shrunk prior); energy-
   override model designed + deferred to 2026 data. Formula E: prior data unusable, methods transferable.
6. **RETRAIN-GAP FIX** (`1922a49`): `refresh.py` now rebuilds **results.parquet** on ingest — it
   was the one production artifact the weekend refresh skipped, so the hazard model + championship
   standings used to lag a race. Continual-update pipeline is now complete.

**NEXT SESSION — candidate work (all additive, none blocking):**
- **Model Replay sandbox — DONE** (`7fa8a33`): `replay_predict.py` → `data/model_replay.json`
  (40 races × 4 models, forward-chained), `GET /models/replay`, `ModelReplay.tsx` at the top of the
  FINDINGS page (race dropdown + model pills + verdict banner + field table + who-believed-in-the-
  winner). v2 ideas if revisited: expose more validated toggles (net_dnf, sim_weight, straight_line,
  era, λ) as switches; rebuild the artifact in `refresh.py` (left manual — the precompute is heavy).
- **Companion view v2** — base shipped. Extends: model H2H from the finish distribution
  (P(A ahead of B)); driver fastest-lap proxy; live price refresh; pre-quali→post-quali auto-switch.
- **Season-sim polish:** sprint/fastest-lap points in `season_sim` (currently top-10 only); a
  per-constructor sandbox.
- **Position-sim v2 (brief 28):** per-pair straight-line using the *actual* car-ahead's top speed
  (we approximate with field-relative z); build the 2026 energy-override reservoir model once a
  season of 2026 data exists to fit it.
- **Deploy** — merge `mechanistic-features` → main (everything tested + pushed; nothing blocks).

**Model-vs-market (honest, the consistent finding):** win Brier 0.054 vs market 0.049; pole Brier
0.045 vs 0.039; title model 87% vs market 51% on the leader. Well-calibrated, competitive,
transparent — **no edge** at any zoom level (lap / race / season / pole). That's the honest pitch.

## SESSION SUMMARY (2026-06-03, earlier) — the decoupling arc

The sim went from "very wrong" to physically grounded; every car/driver attribute now ties to
observed data. Fixed the tyre double-count → decoupled the lumped Kalman strength into MEASURED
components (clean-air pace, measured dirty-air curve, per-car deg, reliability via net_dnf, official
Jolpica grid, start perf) → built the **position-resolution sim** (top-pick 0.47→0.53, best-of-rest
0.31→0.49) → re-anchored on clean-air pace → **qualifying model** (Spearman 0.68) → **season
simulator**. Plus weather points-widening (shipped), OpenF1/Jolpica/Pirelli data, the JOURNEY page,
and honest negatives (Pirelli absolute compound, strength-scaled dirty-air, teammate orders).

## SESSION SUMMARY (2026-06-03) — the decoupling deep-dive

**Done (14 backlog items + the website write-up):** the sim went from "very wrong" to physically
grounded, and every car/driver attribute now ties to observed data (no team-label assumptions, no
double-counts). In order of the arc:
- **Weather-as-variance** (science/21): points-only wet widening (not DNF/win). Wired + UI.
- **Structural sim diagnosed + fixed** (science/22): root bug was a per-team tyre `deg_multiplier`
  double-counting on top of Kalman pace (crowned Ferrari/Aston regardless of speed). Removed it +
  calibrated pace → the anchored+ensembled sim now beats the rank model.
- **Decoupling the lumped Kalman strength into MEASURED components:** clean-air race pace
  (`clean_air_pace.py`, OpenF1-backed), measured non-linear per-circuit **dirty-air curve**
  (`dirty_air.py`), **reliability** net out of pace (`net_dnf`, now production default), **per-car
  tyre deg** from own stints (`tyre_deg_car.py`, reproducible), **official starting grid** (Jolpica,
  not lap-1), **start performance** (`start_perf.py`).
- **Benter** market blend (science/23): calibration tool, not an edge.
- **Free data sources** integrated/researched (science/24): OpenF1 (gaps, free historical),
  Jolpica (grid+status), Open-Meteo (weather); Pirelli table in progress.
- **Honest negatives kept:** prop-market scoring — sim doesn't beat the rank model on
  finishing-order joint props (#14); start-shuffle variance neutral (#12); tyre warm-up undecidable
  on free data (#13).
- **In-app write-up:** FINDINGS tab gained an animated weather panel + interactive ensemble slider;
  `docs/journey_notes.md` is the full Act 1→6 narrative + metrics section for the website journey.

**Current state:** **88 tests pass, 1 skipped.** All committed + pushed to branch
`mechanistic-features` through `17f5974`. **All backlog items #6–#23 complete** (#24 is the one v2
follow-up). Production predictor probabilities are UNCHANGED (rank model); the sim is opt-in ensemble.

**#16 — DONE.** `predict_race_kalman(sim_weight=…)` / env `F1P_SIM_WEIGHT` blends the physics sim's
distribution into the rank model via the ensemble guarantee. Default 0.0 (rank model is
better-calibrated); >0 trades calibration for order accuracy. Fail-safe.

**JOURNEY page — DONE.** New `frontend/src/components/Journey.tsx` (JOURNEY tab): the 8-act story
+ metrics + final scorecard, from `docs/journey_notes.md`. Builds + verified live.

**Why the sim trails on win/podium (researched, MODEL_ROADMAP + task #23):** the sim applies noise
at field-average magnitude, over-dispersing the FRONT (a rating model is implicitly heteroskedastic
and nails dominant cars). Fix path = strength-dependent dirty-air + car-dependent overtake threshold
(top-speed/DRS) + heteroskedastic noise + team reliability — only pays on a clean-air-anchored sim.

**#18 Pirelli table — DONE (honest negative).** Sourced 2022–26 C1–C6 nominations (94 races); the
absolute compound does NOT track in-race deg (C5/C6 lowest — softer compounds run at low-deg tracks
in short stints); relative compound is cleaner. Kept as a sourced artifact, NOT wired. Surfaced on
the FINDINGS page.

**#15 Stackelberg field strategy — DONE (honest negative).** Per-car deg-driven stop plans on the
lumped anchor HURT (re-introduce the deg double-count); only pay on a clean-air anchor. Opt-in, off.

**FINAL forward-chained comparison (45 races, sim = pace 0.30 + measured dirty-air):** the rank
model and the sim SPLIT — **rank model wins calibration** (win/pod/pts logloss 0.131/0.244/0.471),
**sim wins order accuracy** (top-pick 0.356 vs 0.333, best-of-rest 0.49 vs 0.38). Ship the rank
model for probabilities; the sim is the texture/props engine. (journey_notes Act 8.)

**Recovered cleanly from a laptop crash (2026-06-03):** working tree was clean, all work was
already pushed; 88 tests pass, frontend builds, ports free. No loss.

**Task #23 — DONE (honest negative + explainability win, brief 25).** Tested "strong cars lose less
in dirty air, scale the wake by strength": the data says the OPPOSITE — a fast car loses ~1.3 s/lap
stuck in traffic (held up by a slower car) vs ~0.5 s for a slow car. So the per-lap fix is rejected
(points the wrong way). The explainability win — *why track position is gold* — is surfaced on
FINDINGS + JOURNEY Act 9. `dirty_air.strength_dependent_dirty_air()`, +1 test.

**Next priorities (all future/optional — nothing blocks deploy):** (1) **task #24** — track-position
PERSISTENCE (a clean-air leader is near-unpassable) is the real win/podium lever; needs an
overtake-threshold model + first an overtake-event-detection probe (do strong cars *clear* traffic
faster?). Only pays on a clean-air-anchored sim; (2) deploy (merge `mechanistic-features` → main);
(3) rest of the v2 backlog in MODEL_ROADMAP.

**Key gotchas/decisions this session:**
- **pace_scale × dirty-air interact:** with measured dirty-air ON the sim wants `pace_scale≈0.30`,
  not the `0.18` default (which was calibrated before dirty-air). Use 0.30 when wiring #16.
- **`net_dnf=True` is now the production Kalman default** (reliability lives only in the hazard model).
- **"grid" is now the official Jolpica grid** in the feature table (was lap-1 position; matched only
  30%). hazard.py still uses lap-1 grid (defensible for first-lap-contact DNF risk) — intentional.
- Network artifacts (OpenF1/Jolpica/Open-Meteo) are rate-limited + cached to parquet/json; rebuilt
  incrementally by `refresh.py` on ingest. Fetch caches (`*_cache.json`, `benter_collect.json`) gitignored.
- Stale uvicorn can squat port 8000 (new routes 404) — kill via `Get-NetTCPConnection -LocalPort 8000`.

## Latest session (cont.) — OpenF1 measured clean-air (free historical)
- **OpenF1 intervals upgrade DONE (`app/etl/openf1.py`, free, no auth).** Labels each 2023+ race
  lap clean/dirty from the real gap-to-car-ahead (`intervals` endpoint) aligned to laps via
  `date_start`/`lap_duration`: **79k laps / 72 races → `data/openf1_clean_laps.parquet`**.
  Rate-limited (2.1s/req, 429 backoff), cached. `clean_air_pace.py` uses the MEASURED clean flag
  where covered (1318 rows), fast-quantile proxy pre-2023 (1632). **Result: measured clean-air
  gives the same predictive signal as the proxy (Spearman 0.36 vs 0.35) → validates the proxy +
  makes the anchor traceable.** 3 OpenF1 tests; NaN-on-null-tyre_life fixed. Committed+pushed (fc2ecb8).
- **Remaining OpenF1 unlocks (task #20):** measured dirty-air penalty (lap-time vs gap regression
  to replace the assumed `loss_s`) + start performance (official grid→lap1). **Task #19:** the
  feature table's "grid" is end-of-lap-1 position (post-start) — swap in the official starting grid
  (FastF1 `results.GridPosition` / OpenF1 `starting_grid` / Jolpica) to stop folding start perf into grid.
- NOTE for deploy/cron: OpenF1 build is network+rate-limited (~6min, all years force-rebuild); not
  yet wired into `refresh.py` (would need an incremental per-new-race fetch). 71 tests pass, 1 skip.

## Latest session (cont.) — Benter + sim diagnosis/decoupling + data-source research
- **Benter market-blend — DONE (`docs/science/23`, `validate_benter.py`, +3 tests).** Equal
  model+market blend beats both in-sample (0.161 vs model 0.177 / market 0.166 → the model
  carries independent signal) but out-of-sample beats our model (0.175) not the market (0.174)
  on 23 priced races. Calibration tool, not a market edge. `benter_blend` validated; recommended
  surface = a model·market·blend column in Markets (not wired into the default predictor).
- **Diagnosed why the structural sim was "very wrong" (`diagnose_sim.py`) — it was a BUG.**
  The sim re-applied a per-team tyre `deg_multiplier` (0.6–1.6) on top of Kalman pace, which
  already encodes tyre management → it crowned gentle-tyre teams (Ferrari/Aston) regardless of
  speed (sim-fav matched anchor only 35%). Fix (`team_deg=False`) → 100% agreement. Then
  calibrated `PACE_S_PER_Z` 0.45→0.18 (favourite 60%→~28%). **The sim now BEATS the rank model**
  forward-chained (win 0.121 vs 0.131, pod 0.228 vs 0.244); ensemble wants w≈0.75–1.0. Brief 22
  rewritten with the full diagnosis.
- **Dirty-air/battling variance (`montecarlo._apply_dirty_air`, opt-in, +1 test).** Per-lap loss
  for cars within ~1s of the car ahead, scaled by overtaking difficulty; clear leader loses
  nothing (self-limiting). The physically-grounded variance source (owner's brainstorm).
- **Clean-air race-pace decoupling — BUILT + validated (`clean_air_pace.py`, `validate_clean_air.py`,
  +3 tests, `data/clean_air_pace.parquet` 2968 car-races).** Measures each car's fuel- and
  tyre-age-corrected clean-air pace from green laps (fast-quantile proxy), fully traceable. Prior
  clean-air pace predicts finish (Spearman 0.35), partly independent of quali (corr 0.43). As the
  sim anchor (quali+clean-air, realistic pace) ≈ break-even with the lumped Kalman (better pod/pts,
  worse win) → **decoupling viable at ~no predictive cost**, value is traceability + no double-count.
- **Double-count audit (brief 22):** tyre (FIXED), reliability (still doubled — strength depressed
  by DNFs + hazard applied → task #10), grid/strategy/start (minor). The Kalman strength is a LUMP
  (fit on quali+finish); decoupling = replace the dirty "finish" observation with measured clean-air
  pace, NOT strip to quali (which loses signal: win 0.125→0.132).
- **Free data-source + prior-art research (`docs/science/24`, via subagent).** Jolpica (Ergast
  successor; `status` endpoint = DNF causes), **OpenF1 `intervals`/`location` free historical =
  true gap-based clean-air + dirty-air + start** (biggest unlock, task #17), Pirelli C1–C6 table
  (task #18), F1DB backbone, Heilmeier/TUMFTM + state-space tyre papers validate our recipe.
- **Task backlog #10–#18** tracks every idea from this deep-dive (reliability decouple, per-car
  deg from stints, more variance sources, tyre warm-up, prop-market scoring, Stackelberg field
  strategy, wire sim into predictor, OpenF1 upgrade, Pirelli table). **70 tests pass, 1 skipped.**
  NOT yet committed.

## Latest session — model improvement (weather lane + structural-sim flagship)
Picked up the parked `docs/MODEL_ROADMAP.md` hobby. Owner's steer: do the flagship structural
sim **and** add weather. Both delivered; **61 backend tests pass (+9 new), 1 skipped.**

- **Weather-as-variance — DONE, KEPT (points-only), `docs/science/21`.**
  - ETL `app/etl/weather.py` → `data/weather.parquet` (168 races): race-window precipitation
    from the **Open-Meteo ERA5 archive** (free, leak-free; `precipitation_probability` isn't
    archived historically so realized precip is the honest stand-in). Windowed to the race's
    local start hour via the FastF1 schedule. **Cross-checked 13/14 vs FastF1 trackside
    `Rainfall`** (`crosscheck_fastf1`). `refresh.py` rebuilds it on ingest.
  - Forward-chained validation `app/models/validate_weather.py`. **Honest findings:** (a) **DNF
    multiplier dead** — wet 9.16% vs dry 9.26% (modern reliability + SC running); (b) **win/podium
    spread rejected** — the wet favourite is already calibrated (baseline wet win ll 0.128 <
    dry 0.129); (c) **points (top-10) is over-confident in the wet** (wet 0.558 vs dry 0.530) and
    a wet-only points widening fixes exactly that gap → **0.517**, monotonic, at zero cost.
  - **Wired:** `predict_kalman(weather_spread=True, rain=None)` widens ONLY the points market in
    the wet via a 2nd PL pass (`T_points = T·(1+0.5·wet)`); win/podium/distribution untouched.
    `RaceSimResult.rain_prob`/`wet` surfaced on `/predict/race`; new **`GET /circuits/weather`**.
    For a live upcoming race pass `rain=<forecast>` (no ERA5 row exists yet → defaults dry).
- **Structural sim, anchored + ensembled — SCAFFOLDED, guarantee proven, `docs/science/22`.**
  - `app/models/structural_sim.py`: seeds the existing vectorized field MC (`engine/montecarlo`)
    from **Kalman strengths** (the anchor), runs strategy/tyre/fuel/SC physics, returns per-driver
    finishing distributions; `blend_distributions((1-w)·anchor + w·sim)` is the Benter-style
    ensemble (w=0 = rank model → can't be worse).
  - `app/models/validate_structural_sim.py` forward-chains it over 45 recent races. **Result:
    best ensemble w=0 on every market** (guarantee holds — never worse than the anchor); **pure
    sim (w=1) catastrophic** (win ll 0.51, reproducing the documented "loses badly"); **first-cut
    physics adds no win/podium/points skill** at any pace scale (roadmap failure-mode #4). Kept as
    the scaffold; **v2 = score the lap-resolved PROP markets the rank model can't produce**
    (pit-window, podium-without-fav, lead-laps) + per-car best-response strategy + calibrate-
    before-blend. The ensemble makes all v2 safe (anything added sits behind w).
  - Tests: `test_weather.py` (5), `test_structural_sim.py` (4, incl. the w=0==anchor guarantee).
  - Docs updated: `MODEL.md` (bake-off row + findings), `MODEL_ROADMAP.md` (weather done, sim
    status).
- **In-app write-up — DONE (engaging, animated).** Extended the FINDINGS tab
  (`frontend/src/components/Methodology.tsx`) with a "Shipped this season" section:
  - **Animated rain panel** (CSS `@keyframes pwrain`) — the honest weather verdicts (DNF dead /
    win-podium calibrated / points kept) + the strikethrough 0.558→**0.517** headline + the
    dry/wet points-logloss spread bars + a **live wettest-races feed** from `GET /circuits/weather`.
  - **Interactive "ensemble guarantee" slider** — drag w 0→1 and the three logloss bars grow
    green→red, flipping the verdict from "the floor — can never score worse" (ANCHOR) to
    "catastrophic — the model that historically lost badly" (PURE SIM). Sweep data hardcoded
    from brief 22's validation.
  - Plus 2 new findings cards, an **Open questions** panel (props/per-car strategy/forecast/
    quali-model/energy-tyre/Benter), briefs 21+22 added. New CSS in `styles/pitwall.css`;
    `api.ts` gained `circuitWeather()`/`WeatherRow`. **Frontend builds (274KB); verified live
    via Playwright (rain animates, slider drives the bars, 0 console errors).**
  - **DEPLOY TOMORROW.** Verified locally: fresh API on :8000 serves all 34 routes incl.
    `/circuits/weather`; frontend dev clean. Gotcha hit this session: a stale uvicorn held :8000
    (new route 404'd) — killed PID via `Get-NetTCPConnection -LocalPort 8000` then restarted.
  - **Branch:** `mechanistic-features` (not committed yet this session). Untracked new files:
    `app/etl/weather.py`, `app/models/{structural_sim,validate_structural_sim,validate_weather}.py`,
    `tests/test_{weather,structural_sim}.py`, `docs/science/{21,22}.md`, `data/weather.parquet`
    (+ `weather_cache.json`).



## Latest session (cont.) — #22 car-DNA corner-band — built, validated, KEPT as Explainer-only
- **Built the car-DNA corner-band decomposition** (task #22, brief 16 §2, the flagship
  anti-brand idea): `app/models/car_dna.py` — decompose qualifying telemetry into
  shape-normalized corner-speed-band factors (low/med/high/straight) × per-circuit demand;
  suitability = car DNA · circuit demand (leave-one-circuit-out). 2024 sample, 12 circuits,
  238 car-circuits, cached to `data/car_dna.parquet` (telemetry ~10s/session). `GET /cars/dna`.
- **Verdict** (writeup **`docs/science/19`**): the decomposition is **real + interpretable**
  (Monaco 0% straight / Monza 55%; McLaren+VER strong in slow corners, Alpine/Sauber on
  straights — correct for 2024) but **ZERO incremental predictive lift over scalar pace**
  (corr with quali deviation −0.01). The crux: naive shape-normalization (÷ lap-mean) is
  scalar pace in disguise (corr 0.92); a cross-band demean fixed it (0.92→0.18), and once
  honestly purged of pace, the corner-band fit predicts ~nothing. Exactly brief 16 §2's
  "most likely to disappoint" prediction.
- **KEPT as Explainer-only** (owner's keep-it bar): NOT wired into the predictor (no lift,
  would add overfit risk); served at `/cars/dna` as honest portfolio content. **41 backend
  tests pass** (3 new in `test_car_dna.py`; the scalar-pace-removal guard is the key test).
- **v2** (brief 19): multi-season sample, traction/braking sub-factors (not yet measured),
  validate on race pace, tie telemetry to tyre-deg/lap-time physics (the deterministic-engine
  lane — a dedicated research pass, now running, see below).

## Latest session (cont.) — #23 Polymarket probs on the track viewer — DONE
- **Built the in-play overlay** (task #23): `app/etl/inplay_backtest.build_overlay()` →
  `data/inplay_overlay.json` (per-lap model vs de-vigged Polymarket win-prob for the 11 2024
  races with in-play curves), `replay.inplay_overlay()` + **`GET /replay/inplay`**,
  `frontend` Explorer leaderboard now shows **MODEL · MARKET · Δ** columns per driver as the
  replay scrubs (+ honest caption). Reuses the validated brief-13 live-MC + market alignment.
- **Verified in the running app** (Playwright): Singapore 2024 leaderboard renders the columns
  (NOR leader model 89% / market 50% / Δ +39 at lap 1; drivers without a market curve show —).
  The model's early over-confidence on the on-track leader vs the illiquid market is the
  documented brief-13 behavior, shown transparently (it's a companion, NOT a betting edge;
  wall-clock alignment approximate). **42 backend tests pass** (1 new); frontend builds (253KB).
- Overlay covers the 11 inplay 2024 races (British, Dutch, Italian, Azerbaijan, Singapore, US,
  Mexico, São Paulo, Las Vegas, Qatar, Abu Dhabi); other races hide the columns gracefully.
- LIVE pricing note (owner Q): `/markets/live` uses **Gamma `outcomePrices`** (last/mid), the
  historical overlay uses **CLOB `prices-history`** (midpoint). For true top-of-book live we'd
  hit CLOB `/book` (best bid/ask). See answer in chat; not yet wired (no execution edge anyway).

## Latest session (cont.) — Live Polymarket pricing fixed to CLOB order book (accuracy)
- **Root-caused the "demo-killer" price mismatch**: `/markets/live` read **Gamma `outcomePrices`**
  (a stale last/mid), not the order book. Now reads the **CLOB book** (`POST /books` batch) and
  prices each outcome robustly (`polymarket._book_price`): tight two-sided book → midpoint
  (matches Polymarket, e.g. LEC 0.32/0.33→0.325); **one-sided or spread >0.10 → last trade, then
  Gamma** (owner's caution: never a meaningless mid across a gap). Carries bid/ask/spread/source.
- **Re-added the live panel** (dropped in the redesign) to the Markets tab: per-outcome implied%,
  price, bid–ask, and a liquidity-source badge (mid/last/est), polled ~5s, LIVE/snapshot label +
  vig. Verified in-app (Playwright): Monaco winner ● LIVE 9% vig, LEC 30%; pole 33% vig.
- Refreshed `data/markets_snapshot.json` to the new shape. **46 backend tests pass** (4 new in
  `test_markets.py` for the book-price fallback logic). Frontend builds (255KB). On branch
  `mechanistic-features` (#23 + this not yet merged to main).
- **v2 (task #9):** CLOB WebSocket push instead of polling — deferred (market moves in <8% of
  minutes; polling is fine; WS adds reconnect/async state vs the low-maintenance ethos).

## Latest session (cont.) — visual review (Sonnet) + fixes
- Ran `/visual-critic` with a **Sonnet** subagent over all 7 tabs (harness bootstrapped in
  `.test-harness/`, report at `.test-harness/AI_REVIEW_REPORT.md`): 21 findings (2×5★, 5×4★).
- **Fixed the real ones:** (5★) Predictor blank = cold-start → **warm the model caches on a
  startup thread** (`main.py`); (5★/4★) Explorer all-dash sectors + single-dot map + 404 noise
  = it defaulted to an uncached race → **default the Explorer to a GPS-cached race (Bahrain
  2024)** + made `/replay/track`+`/replay/positions` return **200+null instead of 404** (no
  console errors); (4★) Scenario bar encoding → **"shorter is faster" captions** on the cost
  DuelBars; (4★) StrategyLab −39.3s cover value → **sign-convention note**; table headers
  9.5→10.5px. Verified in-app (Playwright): Predictor renders, Explorer lands on Bahrain with
  real map/sectors/best-lap + zero console errors.
- **Triaged out (not bugs):** the "orphaned ┌ bracket" is the intentional 2-corner panel frame
  (`.pw-panel::before/::after`); most "9px illegible table" findings are fullPage-screenshot
  scaling (real `td`=13px). Remaining low-pri nits (LIVE-SOON nav styling, calibration n=,
  per-team chart height) left for later. **52 backend tests pass; frontend builds.**

## Earlier this session — #15 + #18 + live pricing v2 (#9) all DONE
- **#15 Methodology & Findings tab** — new "FINDINGS" tab (`Methodology.tsx`): the bake-off
  table (every model + verdict), the headline findings, and the LIVE mechanistic indices from
  the API (overtaking + SC bars, tyre-degradation table, car-DNA). Verified in-app.
- **#18 Polymarket 2025/26 history** — `season_winner_markets()` resolves each race's real
  slug across format drift (year-verified), extending the model-vs-market backtest 11→23 races.
  Also switched the backtest from the stale mechanistic sim to the **forward-chained Kalman**
  (leak-free, post-quali): honest result model Brier 0.054 vs market 0.049, top-pick 39% vs 52%.
- **#9 Live pricing v2 (CLOB WebSocket)** — `app/etl/clob_ws.py`: an optional background task
  streams the upcoming race's CLOB order books → in-memory cache; `/markets/live` reads it
  (`source=ws`, no per-request REST) and **`/markets/stream` (SSE)** pushes it to the browser
  (Markets uses EventSource, falls back to polling). Gated by `F1P_LIVE_WS_ENABLED` (default
  OFF → REST book path, deploy stays low-maintenance). Verified end-to-end against live Monaco
  (44 books cached, source=ws, SSE emits). nginx tuned for SSE; `websockets` dep added.
- **52 backend tests pass; frontend builds (265KB).** All committed on `mechanistic-features`.

## Earlier — model work parked; pivot to DEPLOY + #15 + #18
- **Model improvement is now a post-deploy hobby, not a blocker.** Parked all model ideas +
  open questions (incl. the ambitious structural-sim "why flawed / how to fix" design) in
  **`docs/MODEL_ROADMAP.md`**. Wrote the canonical **`docs/MODEL.md`** (current model + every
  model tested in the bake-off + the honest findings) — the deploy-time doc + source for #15.
- **Quali-grid fusion shipped** (foundational, validated): the Predictor now fuses the real
  qualifying grid when available (`use_quali`, auto-fetch via `fetch_quali_gaps`), activating
  feature #20's grid weight in production. Pre→post gain: best-of-rest 0.32→0.44, podium ll
  0.27→0.21. PRE/POST-QUALI badge in the UI. Deterministic roster tie-break. 52 tests pass.
- **Deploy readiness — DONE (artifacts):** added `frontend/Dockerfile` + `frontend/nginx.conf`
  (SPA serve + `/api` proxy to api:8000), `.env.example`, `Caddyfile` (TLS entrypoint), a
  `caddy` service in `docker-compose.yml` (DOMAIN unset → :80, set → auto-HTTPS), and
  `docs/DEPLOY.md` runbook. Untracked 17 root screenshot PNGs (`/*.png` in .gitignore; kept on
  disk). Backend imports clean (32 routes); frontend builds. **`docker compose config` / build
  must be verified ON THE HOST** (Docker isn't installed in this dev box). The app is
  self-contained (ships the committed parquet artifacts; no DB/network needed to predict).
- **STILL TO DO:** (2) **#15 Methodology page** — render MODEL.md + briefs + the new endpoints
  (/circuits/overtaking, /circuits/safety-car, /cars/dna, /tyres/degradation, /circuits/qss);
  (3) **#18 Polymarket 2025/26 history**; then verify docker build on host + final deploy.
- Commits on `mechanistic-features`; quali fusion (`4d699c9`) + model docs + deploy artifacts
  NOT yet merged to main (merge once #15/#18 land or as a checkpoint).

## Earlier this session — deep-research processed + engine upgrades built (task #8)
- **Wrote `docs/science/20`** — the full deep-research report (3 tiers, 2 implementable on free
  FastF1; equations, sources, refuted claims, open questions) + the build plan. Permanent
  reference; publishable in #15.
- **A. Per-compound tyre degradation re-fit on 2022+ stint residuals** (`app/etl/tyre_degradation.py`
  → `data/tyre_degradation.json`, `GET /tyres/degradation`). Age-binned medians (per-lap residuals
  are swamped by ±2.9s traffic noise) fit to Heilmeier's 4 closed forms, AIC-selected. **Finding:
  the LOG form is NOT best for the ground-effect era** (SOFT/MEDIUM→linear, HARD→quadratic) —
  Heilmeier's 2014–19 result doesn't carry to 2022+. Observed in-race deg is gentle/managed.
  Documented artifact + cross-check; not yet wired into the sim's per-circuit 3-phase model.
- **B. QSS corner/braking on the driven line** (`app/engine/qss.py` → `data/qss_profiles.json`,
  `GET /circuits/qss`). Curvature from fastest-lap X/Y + empirical g-g envelope + forward-backward
  velocity profile. **Validation: tracks the speed-trace SHAPE (corr 0.80–0.92) but overestimates
  pace ~20–30%** (Monaco qss 49.6s vs 70.1s actual) — 10Hz X/Y under-resolves tight corners. A
  corner/straight decomposition + Explainer tool, NOT a lap-time predictor on free data. Honest.
- **Tier 3 (physics wear)** stays un-calibratable (needs slip/load/tyre-temp we lack). `refresh.py`
  re-fits degradation on ingest. **50 backend tests pass** (4 new in `test_laptime_physics.py`:
  recovers a known quadratic, median kills outliers, curvature of a circle = 1/r, QSS slows in
  corners). On branch `mechanistic-features`. NOT yet merged to main.

## Deep research COMPLETE — superseded by the section above
- The deep-research workflow finished (`wf_b688145f-d7e`, 103 agents). Headline: deterministic
  F1 lap-time/tyre modeling has **3 tiers, 2 implementable on free FastF1** — (1) lap-wise additive
  sims (Heilmeier/TUMFTM: quali pace + race-pace gap + fuel-mass term + per-compound closed-form
  tyre-age degradation, re-fittable on FastF1 stint residuals); (2) min-lap-time optimal control
  (Perantoni-Limebeer) + QSS forward-backward velocity profiles over a GGV envelope where
  min-curvature ≈ min-time (curvature is a telemetry INPUT we have); (3) physics wear/grip
  (Reye energy law, MF-evo, Pacejka) — needs slip/load/tyre-temp we LACK. Recommendation: keep
  base+fuel+3-phase, **re-fit per-compound degradation on FastF1**, add telemetry corner/braking
  terms via a QSS velocity profile on a min-curvature line. Full result in the task output file.
  TODO: write up as docs/science/20 + scope the engine upgrade (task #8).

## Deep-research lane (superseded by the COMPLETE section above)
- Owner's steer: telemetry is better aimed at a **deterministic physics engine** (lap-time,
  tyre deg, corner arcs) than at a market edge (the edge lane is concluded null, briefs 07–19).
  Launched a **deep-research workflow** (`wf_b688145f-d7e`, background) to survey implementable
  prior art (Heilmeier 2020, Perantoni & Limebeer 2014, Pacejka, OpenLAP, TUMFTM trajectory
  opt; thermal/energy tyre-wear laws) and split implementable-on-free-FastF1 vs needs-unavailable
  data (we lack tyre temps/loads/slip/fuel). Task #8 tracks processing it → docs/science/20 +
  scoped engine upgrades. Watch with `/workflows`.

## Repo / branch state (this session)
- **#20 committed + MERGED to main + pushed** (`a2d416d`). **#21 + #22 committed + MERGED to
  main + pushed** (`bcbc14b`). Current branch **`mechanistic-features`** (= main, both on GitHub).
  main is the live, tested checkpoint (41 backend tests pass). Remaining backlog: #23 (Polymarket
  on track viewer), #15 (Methodology page — would surface /circuits/overtaking, /circuits/safety-car,
  /cars/dna), #18 (2025/26 Polymarket history). Structured task list is live in-session (TaskList).

## Earlier this session (cont.) — #21 structural SC index — built, validated, KEPT for ordering
- **Built the structural safety-car index** (task #21, brief 16 §3): `app/models/sc_index.py`
  — race-level P(any SC) from measurable track structure (street-ness via low passing rate +
  high lap-1 churn, reusing `overtaking_proxies.parquet`) + a wet flag + EB-shrunk per-circuit
  rate, forward-chained. SC label = track_status ∈ {4,6,7} via `hazard._sc_active_laps`.
- **Forward-chained verdict** (writeup **`docs/science/18`**): **nothing beats the base rate**
  (structure logloss 0.6335 vs base 0.6298; count MAE tie) — SC is a near-Poisson race-day
  shock (converges with doc 10). **But the cross-sectional structure is real** (per-circuit
  SC-rate ~ passing-rate r=−0.39, n_periods r=−0.43): Baku 0.79 / Jeddah 0.78 high, Hungary
  0.63 low — correct ordering.
- **KEPT for the ordering** (owner's keep-it bar): wired as the Predictor's per-circuit SC
  prior (`RaceSimResult.sc_probability`, was hardcoded **0.0**; Monaco 0.73, Baku 0.79, Hungary
  0.63), served at **`GET /circuits/safety-car`** for the Explainer. Honestly NOT an edge — the
  prior sits within base-rate noise; value is realism + interpretability. `refresh.py` refits it
  on ingest. **38 backend tests pass** (4 new in `test_sc_index.py`). On branch
  `mechanistic-features` (off main); **#21 NOT yet committed** as of this line — committing next.
- **v2** (brief 18): a-priori geometry from `get_circuit_info()` for never-raced circuits
  (shared pull with #22), rain *forecast* not a contemporaneous flag, feed SC count into the sim.

## Earlier this session (#20 overtaking-difficulty index — built, forward-chain-validated, KEPT, MERGED to main)
- **Built the mechanistic, brand-agnostic overtaking-difficulty index** (task #20, brief 16 §1):
  `app/models/overtaking.py` — ONE track-physics number/circuit (grid→finish Spearman lock +
  green on-track passing rate + lap-1 churn), forward-chained + empirical-Bayes shrunk, wet
  runnings excluded. `data/overtaking_proxies.parquet` holds the raw per-running inputs.
  Face validity: Monaco tops (+2.36), Spa/Bahrain/Baku correctly low. Known wart: Hungaroring
  ranks mid/low because lap-1 churn reads its chaotic start as "easy to pass" (v2 fix noted).
- **Forward-chained validation** (`app/models/validate_overtaking.py`, `KalmanOTModel` in
  `kalman.py`) — full writeup **`docs/science/17`**. **Reframed per owner: scored on
  best-of-rest / podium, NOT win** (VER 23/24 dominance makes win near-trivial). Findings:
  grid-awareness itself lifts best-of-rest 0.380→0.466 + podium ll 0.246→0.204; **OT-scaling
  ≈ the best matched flat grid weight** (within ~1-race noise) but **beats the rejected
  affinity decisively** (best-of-rest 0.436 vs 0.325). The per-circuit spread is
  calibration-neutral in aggregate but gives correct per-circuit variance.
- **VERDICT: KEPT, not killed** (owner's call: mechanistic features stay in the modeling
  conversation as portfolio pieces even when they don't beat a tuned baseline; note v2, don't
  bin). Wired in: **Predictor** uses a per-circuit spread (`predict_race_kalman(circuit_spread=
  True)`, `T=t0·exp(−0.2·index)`) — Monaco favourite 17.8%→24.3%, Spa/Bahrain→~15% (pre-quali
  the flat prior gave every circuit an identical 17.8% fav). **`GET /circuits/overtaking`**
  exposes the index for the Explainer. `refresh.py` rebuilds the proxies + busts caches (incl.
  `_ot_index`, `_proxy_table`, `_fitted`) on ingest. **34 backend tests pass** (5 new in
  `test_overtaking.py`); frontend untouched (Explainer wiring of the index is #15's job).
- **v2 ideas** (in brief 17): split lap-1 churn from steady-state passing (the Hungaroring fix),
  true gap-based pass attribution, per-era estimates as the modern sample grows, similarity-
  shrinkage backbone for thin circuits, per-circuit grid weight once the Predictor fuses a real
  quali grid (it currently runs pre-quali only — grid_weight is inert there).

## Earlier session (track-affinity experiment + Scenario Runner expand + mechanistic-features research)
- **Track-affinity: built, validated, REJECTED** (`KalmanTrackModel` in `kalman.py`, commit 2ce9181).
  Forward-chained over 168 races it made every metric worse (win logloss 0.128→0.139). Kept as a
  documented negative; NOT wired in. The honest lever stays qualifying.
- **Scenario Runner expanded + restyled to pitwall** (cc13f8d): 5 scenarios now (safety car,
  undercut, cover-vs-extend, 1-vs-2-stop fork, rain crossover). New `strategy.rain_crossover`,
  `/scenario/stop-fork` + `/scenario/rain-crossover`. Deleted dead `CoverExtendPanel.tsx`. 27 tests.
- **Mechanistic edge-feature research** (`docs/science/16`, 225348d): ranked anti-brand features —
  #1 **overtaking-difficulty index** (per-circuit shrunk grid→finish lock + passing rate + lap-1
  churn; tunes Kalman grid_weight + per-circuit spread — the principled replacement for the rejected
  affinity), #2 structural SC index (into hazard.py), #3 car-DNA corner-band decomposition (telemetry,
  highest overfit, must beat scalar pace or kill). Task #20 tracks the build-first one.
- **Track viewer DONE** (#19, 995fe4b): real GPS outlines (`/replay/track`), real sector times in
  `/replay/race`, per-car X/Y `/replay/positions` + multi-car TrackMap (20 team-coloured dots on the
  real outline; graceful single-dot fallback for uncached races). Position cache built for 5 demo
  2024 GPs (data/track_positions.json ~4MB; regenerable via `build_track_positions --year/--circuit`).
  Verified visually (Bahrain 2024). 29 tests pass.
- **Research follow-ups queued** (tasks #20-23): overtaking-difficulty index (build-first), structural
  SC index, car-DNA corner-band, and Polymarket probs on the track viewer (we already hold 2024
  in-play curves in `data/inplay_probe.json` for the replay overlay).
- Worktree isolation is unavailable in this env, so parallel CODE agents aren't safe — builds run
  sequentially (#14 done → #19 now); only read-only/doc agents run truly parallel.

## Earlier this session (Kalman Predictor + 2026 data catch-up + next-race auto-select)
- **FIXED the stale Predictor.** Root cause: it used `drivers.json` = `calibrate_drivers()` =
  a flat all-time POOLED mean (Perez/Red-Bull, VER dominant — the 2024 grid). Replaced with a
  time-local **Kalman car+driver** model: `app/models/predict_kalman.py` forward-chains the
  filter over all races, roster from the latest season, moved drivers inherit the new car
  (car+driver split), PL sampling + hazard DNF → full distribution. `/predict/race` now uses it.
  Temperature 0.5 (forward-chained calibrated). Pre-quali spread is honestly tight (~18% fav),
  sharpens once a quali grid is fused. The OLD mechanistic `engine/predict.predict_race` + the
  bake-off models were always proper (car/driver, forward-chained) — only the Predictor *tab*
  was wired to the naive pooled sim. That's fixed.
- **Data caught up to 2026.** FastF1 HAS 2026 (my earlier "no" was a bad query — name mismatch +
  `.results` vs `.laps`). Ran `app.etl.refresh`: archive now 2018–2026, **168 R races**, 2025
  complete + 2026 R1–5. Roster is the **real 2026 grid**: Audi, Cadillac, HAM→Ferrari, ANT→
  Mercedes, **PER→Cadillac** (correct, not stale). Recalibrated 36 circuits.
- **Next-race auto-select** (no scraping): `/calendar/next` from the FastF1 schedule; the
  Predictor defaults to the upcoming race (Monaco, round 6) with a "NEXT" affordance.
- **Calibration robustness** (exposed by fuller/sparser data): `_slope` drops non-finite rows +
  catches LinAlgError (fixed the SVD crash that aborted the post-ingest recalibrate); per-circuit
  tyre fit falls back to the seed curve when degradation isn't monotone after warm-up.
- Committed on branch `maintainability-and-resilience` (fe7a33f). 24 tests pass.

## Earlier this session (pushed to GitHub + maintainability/resilience + pitwall redesign)
- **On GitHub:** private repo **github.com/btre53/F1Predict**, one root repo (backend+frontend+docs).
  `main` has the initial commit; current work is on branch **`maintainability-and-resilience`**.
- **Maintainability + live-resilience layer (committed on the branch).** Live features kept but made
  robust + observable (the user's call: live service, low-maintenance via graceful degradation):
  - `/markets/live` is **live-first with a committed snapshot fallback** (`data/markets_snapshot.json`).
    Discovery derives the upcoming race's slugs from the FastF1 schedule (robust to Polymarket slug
    drift); falls back to the snapshot when the feed is down/off-season. New `fetch_f1_markets_live`,
    `next_race_event_slugs`, snapshot helpers in `polymarket.py`. Verified it pulls Monaco live.
  - **`/health/data`** heartbeat (latest ingested race + snapshot age) = observability.
  - **Scheduled GitHub Action `ingest.yml`** = the robust weekend cron (refresh→test→commit only if
    green; self-healing, auto-reverting). `refresh.py` also refits the hazard cache + snapshot.
  - **CI `ci.yml`** (pytest + frontend build), **FastF1 schema-contract test** (gated to ingest),
    root **README** (honest-findings story), **.gitattributes**.
- **Pitwall redesign INTEGRATED (uncommitted — diff shown, awaiting OK).** Dropped in the
  `design_handoff_pitwall` `src/**` (5 components replaced + `charts/` + `pitwall.css`), fonts +
  `data-theme=dark` in index.html, the 3 optional `ReplaySlot` sector fields in `api.ts`. Re-added
  the Scenario Runner tab. **Build green, bundle 744→246 KB, runs with no console errors** (verified
  via Playwright — Strategy Lab renders fully with live data). Handoff folder + zip gitignored.

## Prior session (Scenario Runner headline feature + hazard wiring + Monaco capture)
- **Scenario Runner BUILT — the new headline feature (6th tab).** The "anti-AWS": transparent,
  calibrated strategy calls instead of a black-box probability. New engine `safety_car_decision()`
  in `strategy.py` (pit-now-under-SC vs stay-out — captures the real nuance: pit only if a stop was
  due soon; fresh tyres → stay) + `/scenario/safety-car` endpoint + schemas + 2 unit tests.
  Frontend `components/ScenarioRunner.tsx` (SC centerpiece + undercut + cover/extend as selectable
  scenarios), wired into `App.tsx`. 24 backend tests pass; frontend builds; endpoint verified 200.
- App is now **6 working tabs**. Remaining before launch: deploy (Docker/Caddy/Hetzner) + the
  `fetch_f1_markets` 2026-slug fix.

## Earlier this session (hazard DNF + wiring + Monaco capture infra + MM verdict)
- **Hazard DNF WIRED into the production sim.** `engine/predict.py` calls
  `hazard.apply_to_grid(grid, year=2025, total_laps=...)` (fail-safe lazy import to dodge the
  engine→models→etl→engine cycle), so the Predictor now uses per-driver DNF (pole ~2% vs P20
  ~16%) instead of flat 0.08. 22 tests pass. (Backtests still use flat DNF — research artifacts.)
- **Props/CLV test DROPPED** — every edge thread is null; modeling-exploration arc CONCLUDED.
  Remaining work is deploy/polish + the (unbuilt) scenario runner.
- **Hazard DNF model DONE** (`app/models/hazard.py`, `app/etl/results.py`, `data/results.parquet`,
  brief 15). Discrete-time logistic hazard, forward-chained over 90 races, **beats the flat 0.08
  baseline** (per-race P(DNF) logloss 0.337 vs 0.399). Grid (+2.18) + first-lap (+1.42) dominate;
  pole 2.7% vs P20 19.4% DNF. `race_dnf_prob()` is a drop-in for the sim's flat `dnf_prob` (wiring
  into `montecarlo.py` is the next step). team_prior ~nil (collinear with grid).
- **Pre-race T-12h edge test: NULL.** Early line ≈ closing line (Brier 0.096 vs 0.095; median move
  0.008/driver). T-12h is post-quali, so the market already has our only signal. No timing edge.
- **Polymarket MM verdict: negative-to-zero EV for retail** (brief 14, agent). `sports_fees_v2`
  exists (maker rebate 25% of a ≤0.75% taker fee) but rewards are UNFUNDED on F1 markets and
  adverse selection on a news-gapping binary dominates. The +EV path is *taking* on a real model
  edge (>fee), not making. Don't build an MM bot.
- **Monaco 2026 capture infra DONE** (Monaco is **this Sun 2026-06-07 13:00 UTC**): `app/etl/
  live_capture.py` (Polymarket winner/pole/SC/constructor → CSV, smoke-tested live) +
  `app/etl/live_timing.py` (FastF1 SignalR recorder for replay). Runbook: `docs/MONACO_DOGFOOD.md`.
  NOTE: 2026 is the OOS lockbox — capture/dogfood only, do NOT train on it. `fetch_f1_markets`
  needs a 2026-slug-format fix (discovery missed the new `f1-…-2026-06-07` slugs).

## This session (in-play step 1 + research)
- **Telemetry → racecraft validation DONE (the decisive free gate).** New code:
  `app/models/racecraft_signatures.py` (lap-level, no API) + `app/models/telemetry_signatures.py`
  (sub-lap car telemetry, 8-race sample → `data/telemetry_sig.parquet`). Full writeup:
  **`docs/science/12-telemetry-racecraft-validation.md`**. **Result = AMBER, leaning negative
  on the paid-telemetry premise:** racecraft is a *real* skill (teammate-netted quali↔PGAE
  r≈0, so it's NOT just one-lap pace), but at lap resolution it surfaces almost only as a
  **race-pace delta** (r≈−0.3 per-race / −0.5 per-driver) that is **confounded with clean air**
  (gaining positions → faster laps; effect vs cause unresolved). Tyre-mgmt, consistency, traffic
  carry ~nothing. Sub-lap telemetry style carries ~nothing at the reliable n=152 grain (the
  apparent per-driver hits are traffic-exposure artifacts). **A paid live-telemetry feed would
  mostly re-derive race pace + position we already get free from lap timing → low marginal value.**
- **Two research briefs added:** `10-novel-approaches.md` (in-play WPA-as-martingale is the one
  credible edge; + survival/hazard DNF; + time-rank-duality car/driver split) and
  `11-inplay-latency-and-weather.md` (undercut latency-arb & weather ideas: signals backtestable,
  live execution infeasible, sector-weather premise dead; salvage as decision-support).
- **In-play step 2 DONE — PASS.** `app/etl/inplay_probe.py` (→ `data/inplay_probe.json`)
  pulled the CLOB `prices-history` curve at 1-min fidelity across the race window for all 11
  2024 winner markets. **All 11/11 move in-play**; the winner's price climbs gradually mid-race
  every time (median +0.675; São Paulo VER 0.075→0.99 over ~3h; British HAM event-jump). 2402
  real moves over ~31k points. **An in-play benchmark exists.** Caveat: it's the price curve,
  not executable depth (thin liquidity) — and repricing may lag on-track events (= the edge).
- **In-play step 3 DONE — NULL (the edge thesis is killed, cheaply).** Built the WPA backtest:
  `app/etl/inplay_backtest.py` (state reconstruction → vectorized live win-prob MC →
  Polymarket alignment → calibration + lead-lag), → `data/inplay_backtest.json`, writeup
  `docs/science/13-inplay-wpa-backtest.md`. Live prob is **well-calibrated** (Brier ~0.048,
  comparable to the market) but **does NOT lead it**: the detrended increment cross-correlation
  is flat at every lag (≈0, n=6824). The headline CLV (+0.46) was common-trend co-convergence —
  the reverse placebo was +0.36. Structural: a lap-completion engine lags real-time ~90s. This
  converges with briefs 11 (latency-arb inexecutable) and 12 (telemetry low-value): **three
  threads, one negative — no exploitable in-play edge, do not pay for OpenF1.**
- **Net direction:** the in-play *trading* thesis is closed. Surviving value: (a) ship the live
  win-prob as a calibrated race-companion OVERLAY (engagement, "anti-AWS"); (b) pivot modeling
  to PROPS/sub-markets + a survival/hazard DNF model (brief 10 §2), the lane still plausibly
  holding edge. Telemetry stays an Explainer-only feature.

## Where we are
The 5-tab app + mechanistic sim are built. We then **pivoted into a serious modeling
exploration** to find a better, validated F1 predictor. **Read `docs/TODO.md` and
`docs/science/09-modeling-bakeoff.md` first** — they hold the live plan and the panel
synthesis. Quick facts:
- **The mechanistic Monte Carlo sim loses badly** (forward-chained top-pick 31.7%; the
  market beats it 18% vs 36%). It's been superseded by the bake-off models for prediction.
- **Model bake-off** (`backend/app/models/`): a shared forward-chained, calibration-first
  harness scoring a **baseline (grid+quali)**, a **PL-Glicko rating**, a **Kalman
  pace-filter**, and **LightGBM**. On the fair 80-race sample (2018–19 + 2023–25):
  **all cluster ~63% top-pick** and barely beat the 10-line grid+quali baseline.
  **The signal is the grid/qualifying** — the panel's core warning, proven. Grid-awareness
  was the key fix for the rating/Kalman models.
- **Best-of-rest + PGAE eval lenses** added — the *winner* is ~trivial (pole); the real
  variance is the rest-of-field. **Racecraft rating** (`racecraft.py`, strokes-gained
  analog, car-netted) sanity-passes (HAM top, ALB high). Validated as a metric, not a
  better prediction *target* (it's a reparameterization — see `docs/science/strokes`).
- **No edge vs the pre-race outright market** (confirmed). Edge, if any, is **in-play +
  props** — the current direction (see TODO "Immediate next").
- **Telemetry is captured but UNUSED** (`speed_st`); deliberate v1 deferral.
- **Cron wired in**: `app.etl.refresh` + APScheduler in `app/main` (off by default,
  `F1P_REFRESH_ENABLED`). Same `model.update(race)` hook is the per-race retrain.
- 6 research briefs in `docs/science/` (live-data, prior-art, AWS, historical-data/odds,
  strokes-gained) + 09 (bake-off plan). Data backfill 2018→2025 still staging across the
  FastF1 500-calls/hour limit (a self-resuming loop is running).

## Working tabs (5 of 6)
- **Strategy Lab** — optimizer + undercut + Stackelberg cover/extend; manual strategy
  builder (calibrated) + lap-time profile chart; delta-first metric.
- **Predictor** — 10k-sim Monte Carlo, win/podium/points + finishing-position heatmap.
- **Explorer** — animated historical race replay (real data, position tower + scrub).
- **Markets** — calibration backtest (46 races, Brier/log-loss/calibration plot, per-race
  table, vs grid baseline) + live Polymarket de-vig panel (read-only/paper).
- **Explainer** — curated in-app explanation of every model (8 cards + math drill-downs).
- (Live still "soon".)
- 22 backend tests pass. **Data: 24 circuits, 46 races (2023–24) + 37k FP1/FP2 laps
  (`practice.parquet`), free sources only.**
- **Per-team tyre management** calibrated (`team_tyres.json`, `/api/tyres/teams`):
  McLaren/Mercedes gentle ×0.60, Haas/Sauber harsh ×1.3–1.6; applied per-driver in
  the Monte Carlo via `GridEntry.deg_multiplier`.
- Active build chunk + sequencing tracked in **docs/TODO.md** (FP/per-team done;
  forward-chaining backtest + interactive explainer + real Polymarket backtest next).

## Key backtest finding (act on this)
The model is **overconfident on its top picks**: it predicts ~92% win for its
favourite but the favourite wins ~61% of the time, and it only *ties* the naive
grid-favourite baseline on win Brier. Outright-win is grid-dominated; the real edge
(if any) is in podium/points and live in-race repricing. Fix: temper win
probabilities / raise `FORM_SIGMA_S` in montecarlo. This is the honest gate result —
no evidence yet to justify paying for live data.

## Hard constraint: cost-neutral
The project must run on **free data**. The only paid option on the table is the
OpenF1 live tier (~€10/mo), and it is **deferred indefinitely** — needed only for
true live in-race ingestion, and only justified if a **zero-cost backtest** (our
model probabilities vs historical Polymarket prices + de-vigged bookmaker lines)
shows a real edge that covers the cost. Everything built so far and the next
several phases need **no paid data**. Keep any paid/live path behind a flag,
default OFF. See the Markets phase notes in ROADMAP.md.

## What this is
A portfolio-grade F1 race prediction / replay / strategy-evaluation web app, to be
deployed on a small Hetzner VPS. Built from the original research doc
(`F1Predict_ Stochastic Race Simulation Engine.md`), validated and corrected by
independent research (see `docs/science/`).

## What's done
- **Research + science docs** (`docs/science/01-04`): lap-time model, race strategy,
  data sources/2026 regs, and a point-by-point validation of the original doc.
  These double as the future in-app Explainer content.
- **Roadmap** (`docs/ROADMAP.md`): 6 tabs, 8 phases, seeded parameters.
- **Backend** (`backend/`, FastAPI + uv, Python 3.12):
  - `app/engine/params.py` — calibrated parameters (TUM-seeded), era/compound enums.
  - `app/engine/tyres.py` — three-phase degradation + bounded SLSQP calibration.
  - `app/engine/physics.py` — deterministic baseline (base + fuel + tyre).
  - `app/engine/noise.py` — positively-skewed (skew-normal) execution noise.
  - `app/engine/strategy.py` — **Strategy Lab core**: fast vectorized `RaceModel`
    scorer, coarse-grid + refine optimizer, undercut calc, Stackelberg cover/extend.
  - `app/api/` — `/api/health`, `/strategy/evaluate`, `/strategy/optimize`,
    `/strategy/undercut`.
  - `app/db/schema.sql` — era-partitioned Postgres schema.
  - 9 passing smoke tests (`uv run pytest`).
- **Frontend** (`frontend/`, Vite + React + TS + Tailwind v4):
  - Dark broadcast-style F1 UI, 6-tab shell (Strategy Lab live; others "soon").
  - Strategy Lab: circuit + max-stops controls, ranked strategy cards with tyre
    timeline bars, undercut calculator with debounced sliders.
- **Infra**: `docker-compose.yml` (db + api + web), `backend/Dockerfile`, `.env.example`.
- **Phase 1 ETL (done)** — real data now drives the Strategy Lab:
  - `app/etl/fastf1_client.py` — load a session → normalized Polars frame (pandas→Polars at the edge).
  - `app/etl/ingest.py` — batch backfill → `data/laps.parquet` (15.8k laps, 5 circuits, 2023–24 FP2/FP3/R).
  - `app/etl/calibrate.py` — fuel-correct + stint-relative residuals → per-circuit base lap + 3-phase
    tyre θ-params → `data/calibration.json`.
  - `app/engine/calibration_store.py` + `GET /api/circuits` + `circuit_name` on `/strategy/optimize`.
  - UI loads calibrated circuits and shows a "CALIBRATED FROM REAL DATA" badge.
  - Verified: Bahrain base 1:31.6, avg race pace 1:34.6/lap, realistic SOFT deg ~0.05 s/lap.

## Key design decisions (from user feedback)
- **Headline metric = delta to optimal + avg lap time**, NOT absolute race time
  (users think in deltas/lap times). See `delta_to_best_s`, `avg_lap_s`.
- **Speed matters for sliders**: optimizer rewritten to a precomputed `RaceModel`
  (base+fuel is constant across strategies; only tyre wear + pit loss differ) →
  ~157ms for a 66-lap 2-stop search (was 23s). Sliders debounced ~90ms.
- **Fuel-amplified tyre wear** (`WEAR_FUEL_SENSITIVITY=0.30`): heavy car wears tyres
  faster, so the optimizer realistically runs **softs late**. Breaks the
  order-degeneracy that made permutations tie.

## Gotchas
- **`uvicorn --reload` does not reliably hot-reload on this Windows setup** and its
  reloader parent respawns stale workers. To restart the API cleanly: kill the
  python process holding port 8000 (find via `Get-NetTCPConnection -LocalPort 8000`,
  then `Stop-Process`), then start `uv run uvicorn app.main:app --port 8000` WITHOUT
  `--reload`. An orphaned socket can show a dead PID as the listener — kill the
  parent uv-python process to free it.
- **Vite dev binds IPv6 `::1` only** → use `http://localhost:5173` (not 127.0.0.1)
  for Playwright/curl.
- Fast optimizer scorer vs full per-lap `evaluate_strategy` differ by <1s (the
  scorer uses stint-average fuel for the wear multiplier). Rankings are
  self-consistent; absolute totals differ slightly by design.
- No DB is required yet — the engine runs on calibrated params from Parquet. ETL
  (FastF1 → Postgres) is a later phase.
- **Measuring timed UI behaviour via Playwright is unreliable** — tool-call latency
  means many real seconds pass between a `sleep` and a snapshot, so the browser
  keeps animating. The Explorer playback looked "too fast" but was correct at
  450ms/lap (verified via in-page `console.log` of elapsed/lap). Verify timing with
  in-page logs, not wall-clock sleeps. Playback uses a wall-clock-derived lap
  (`startLap + floor(elapsed/speed)`) so it's immune to timer stacking / StrictMode.

## How to run
- Backend: `cd backend && uv run uvicorn app.main:app --port 8000`
- Frontend: `cd frontend && npm run dev` → http://localhost:5173
- Tests: `cd backend && uv run pytest`
- ETL (offline): `uv run python -m app.etl.ingest` then `uv run python -m app.etl.calibrate`
  - Full calendar: `uv run python -m app.etl.ingest --seasons 2023 2024` (race sessions only)
  - One event: `uv run python -m app.etl.ingest 2024 Monaco`
  - Backtest (after calibrate): `uv run python -m app.etl.backtest` → `data/backtest.json`
  - FastF1 cache lives in `backend/.cache/fastf1`; artifacts in `backend/data/`.

## Next priorities (see docs/TODO.md)
Modeling arc is concluded (all edge threads null). The work now is product + ship:
1. **Commit the pitwall redesign** to the branch (diff shown, awaiting user OK ± deleting the 6
   dead component files: StintBar/LapTimeChart/LapTimeBuilder/StrategyBuilder/TeamTyreOverlay/
   TyreSandbox.tsx — superseded by `charts/Charts.tsx`).
2. **Restyle the Scenario Runner to pitwall** (it works but is still in old Tailwind styling) and
   **expand it** (#14): rain crossover, VSC-vs-SC, 1-vs-2-stop fork, dirty-air. Deterministic.
3. **Methodology & Findings page** (#15) — render the docs/science briefs in-app (honest showcase).
4. **Optional backend fidelity patches** (`design_handoff_pitwall/backend_patch/`): `real_sectors.md`
   (~5 lines in `replay.py` → true sector times) and `track_outline.md` (FastF1 GPS circuit outlines
   + `/replay/track` endpoint). Frontend already prefers real data when present; falls back otherwise.
5. **Deploy** (Hetzner + Caddy + the scheduled-ingest Action). Merge branch → main first.

## Gotchas (this session)
- **Repo structure:** ONE root git repo (an abandoned empty `backend/.git` was moved to
  `../_f1predict_backend_empty_git_backup`). Don't re-init inside backend/.
- **Polymarket 2026 slugs** changed format to `f1-<race>-grand-prix-<market>-<YYYY-MM-DD>` (old
  `<race>-grand-prix-winner` is 2024/25). `next_race_event_slugs()` derives them from the schedule;
  if a race name mismatches Polymarket's, add it to `_SLUG_ALIASES` in `polymarket.py`.
- **Pitwall + Tailwind coexist:** new components use `pw-*` classes (pitwall.css via App.tsx);
  ScenarioRunner still uses Tailwind (index.css via main.tsx). Both stylesheets load. Don't remove
  index.css until ScenarioRunner is restyled.
- **`design_handoff_pitwall/` + `claude design.zip`** are gitignored reference material (on disk for
  reference, not committed).
