# 22 — The structural sim, anchored + ensembled (the flagship, honestly)

_MODEL_ROADMAP.md's flagship: rebuild the per-lap field sim so it's **complex AND provably
not worse** than the rank model. This brief is the scaffold + the forward-chained proof of
the guarantee — and the honest finding that the first-cut physics adds no skill yet._

## The idea

The original mechanistic Monte Carlo (`engine/montecarlo.py`) **lost badly** forward-chained
(~31.7% vs ~63% top-pick): it predicts a high-dimensional intermediate (every car, every lap)
and integrates, so small per-lap biases compound, and physically-detailed sims are
over-confident. The roadmap's fix:

1. **Anchor** each car's race pace to its **Kalman strength** (the rank model's calibrated
   belief) instead of re-deriving pace — `structural_sim.strengths_to_pace_offsets`.
2. **Let the physics add structure** around that anchor (strategy, tyre deg, fuel, SC, weather).
3. **Ensemble** the sim's finishing distribution with the rank model's at a learned weight w:
   `ENSEMBLE(w) = (1-w)·anchor + w·sim`. At **w=0 it IS the rank model**, so a learned w can
   never do worse than the anchor — the physics only helps where it helps.

Modules: `app/models/structural_sim.py` (field sim seeded by Kalman + the blend primitives),
`app/models/validate_structural_sim.py` (the forward-chained proof).

## The forward-chained result (45 recent races, leak-free Kalman, actual grid + hazard DNF)

Win/podium/points **logloss** (lower better); top-pick / best-of-rest accuracy:

| w | win ll | podium ll | points ll | top% | bor% | |
|---|---|---|---|---|---|---|
| **0.0** | **0.131** | **0.244** | **0.464** | **0.333** | **0.40** | ANCHOR (rank model) |
| 0.15 | 0.135 | 0.247 | 0.466 | 0.267 | 0.333 | |
| 0.30 | 0.141 | 0.254 | 0.476 | 0.156 | 0.267 | |
| 0.50 | 0.152 | 0.272 | 0.506 | 0.133 | 0.178 | |
| 0.75 | 0.175 | 0.316 | 0.584 | 0.111 | 0.178 | |
| 1.0 | 0.510 | 0.820 | 1.713 | 0.089 | 0.178 | pure SIM |

**Two findings, both honest:**

1. **The guarantee holds.** The best ensemble weight is **w=0 on every market** — the blend is
   never worse than the anchor, by construction. And **pure sim (w=1) is catastrophic**
   (win logloss 0.51 vs 0.13; top-pick 9%), faithfully reproducing the documented history.
2. **The first-cut physics adds no skill.** Every w>0 *degrades* win/podium/points monotonically,
   so the learned weight wants none of the sim. Sweeping the pace-mapping scale
   (`PACE_S_PER_Z` ∈ {0.05…0.45 s/lap·z}) doesn't change this — the sim's finishing
   distributions are over-confident at every scale (a physical sim concentrates the top-10 on
   the pace order, so one DNF or midfield points-finish costs a huge logloss). This is exactly
   roadmap failure-mode #4 (more physics ≠ better-calibrated probabilities).

## Verdict — scaffold KEPT; the guarantee is the deliverable, the skill is v2

Per the project rules, this is **kept as the anchored+ensembled scaffold with a proven
guarantee**, not flipped into production (it doesn't beat the anchor). The honest read:

- **For who-wins / who-podiums / who-scores, the rank model is already at the ceiling**
  (finishing order is grid + car pace; brief 09). A field sim can't beat it on those — and now
  it provably won't *lose* to it either when ensembled.
- **The sim's real niche is the markets the rank model literally cannot produce**: lap-resolved
  **props** — pit-window timing, lead changes, "podium without the favourite", points-with-a-
  top-car-DNF, under/over-cut outcomes. Those need the per-lap detail; that's where v2 should
  score (and where the weather/SC variance terms actually pay).

## Update (2026-06-03) — diagnosed, and it was a BUG, not "physics adds no skill"

The "first-cut adds no skill" verdict above was wrong about the cause. Diagnosing per-race
(`app/models/diagnose_sim.py`) showed the sim agreed with the anchor's favourite only **35%** of
the time and was 60-65% confident vs reality's ~27%. Two fixes, both reality-grounded:

1. **Tyre double-count (the real bug).** The sim re-applied a per-team `deg_multiplier`
   (0.60-1.60, clamped) on top of the Kalman pace — but the Kalman strength already encodes race
   pace *including* tyre management (it's fit on finishing position). That term was large enough
   to override pace and crown the gentle-tyre teams (Ferrari/Aston) regardless of speed (LEC
   favourite from P15). Removing it (`team_deg=False`) → sim agrees with the anchor **100%**.
2. **Pace-scale calibration.** With pace × ~57 laps the field was too separated. Calibrating
   `PACE_S_PER_Z` 0.45→~0.15-0.18 brings the favourite win% to ~28% (reality).

After both, the **pure sim beats the rank model** forward-chained (win 0.121 vs 0.131, podium
0.228 vs 0.244, points 0.454 vs 0.466) and the ensemble wants **w≈0.75-1.0** — the opposite of
the original verdict. The sim's explicit grid/track-position + safety-car structure genuinely
adds calibration once it isn't swamped by the bug.

**Dirty-air / battling variance** (`montecarlo._apply_dirty_air`, opt-in): each lap a car within
~1s of the car ahead loses a stochastic chunk of time; a clear leader loses nothing
(self-limiting). The physically-honest source of finishing-order variance.

**MEASURED dirty-air curve** (`app/models/dirty_air.py`, `montecarlo._apply_dirty_air_curve`).
Per the owner's spec, dirty air is NOT a flat linear loss — so we measure it from OpenF1 gaps +
fuel/tyre-corrected lap-time excess over each car's clean-air baseline. The curve is sharply
**non-linear** (worse the closer you are): +1.15s in the 0–0.5s gap, +0.55s at 0.5–1s, +0.34s at
1–1.5s, fading to ~0 by 3s. And it's strongly **per-circuit** (0.15s → 2.0s): slipstream/straight
tracks shrug it off (Austria +0.15, Interlagos +0.24), high-speed-corner + can't-pass tracks bite
hardest (Qatar +1.84, Saudi +2.0, Spa +1.28, Monaco +1.72). It does **not** track raw top speed
(corr −0.14) — confirming it's the *type* of speed (aero corner vs straight slipstream), not raw
speed (owner's hypothesis, validated). Honest nuance: per-lap net never goes negative — the
straight tow helps within a lap but doesn't outweigh the corner loss over a full lap in this data.
Wired into the sim, the measured curve **improves the rest-of-field metrics** (vs no dirty-air):
**best-of-rest 0.42→0.51, points logloss 0.584→0.489**, top-pick 0.31→0.33, at a small win cost
(0.127→0.139) — exactly where dirty air operates (midfield battles in traffic). Still TODO from
OpenF1: start performance (grid→lap1).

### The deeper issue: the Kalman strength is a LUMP (double-counting audit)

The strength is fit on just two observations (quali gap, finish position), so it conflates pace,
tyre deg, reliability, racecraft, strategy and luck — and the sim re-adds several of them:

| Lumped in strength | Should come from (observable) | Sim double-counts? |
|---|---|---|
| One-lap pace | quali timesheets | partly (grid) |
| Clean-air race pace | un-trafficked, fuel/age-corrected race laps | — (the true anchor) |
| Tyre degradation | per-car stint slopes | **YES (fixed: team_deg off)** |
| Reliability / DNF | DNF history | **YES (strength depressed by DNFs + hazard applied)** |
| Racecraft | positions gained vs pace | partly (dirty-air) |
| Strategy / start | stint+pit data, lap-1 vs grid | partly |

**Decoupling experiment:** anchoring the sim on pure quali pace (deg-free, reliability-free) is
*worse* (win 0.125→0.132, points 0.588→0.690) — stripping to quali throws away real race-pace /
form signal. So decoupling means *replacing* the dirty "finish position" observation with a
**measured clean-air race pace**, not subtracting. That (plus per-car deg from stint slopes and
removing the reliability double-count) is the principled path to a fully observable sim with no
generic "team X is good on tyres" claims.

### Clean-air race-pace anchor — BUILT + validated (`app/models/clean_air_pace.py`)

Measured each car's clean-air race pace per race: fuel- and tyre-age-corrected (the same engine
`fuel_penalty` / `degradation_penalty` the sim uses), taking the fast quantile of green laps as
the unimpeded pace (a robust proxy for "gap-ahead > 1.5s" — true gap-based filtering is the
OpenF1-`intervals` upgrade). 2968 car-races, fully traceable to specific laps; no team labels.

Forward-chained validation (`validate_clean_air.py`, per-team EWMA belief):
- prior clean-air pace predicts finishing (Spearman **0.35**), is only moderately redundant with
  qualifying (corr **0.43**) → it carries **independent race-pace signal** (partial ~0.14).
- qualifying is still the stronger single signal (0.57); clean-air adds modestly.
- **As the sim's anchor** (quali + prior clean-air, realistic pace 0.30 + dirty-air): roughly
  break-even with the lumped Kalman — better on podium (0.280 vs 0.290) and points (0.561 vs
  0.570), slightly worse on win (0.150 vs 0.128).

Verdict: **the decoupling is viable at ~no predictive cost** — a clean, traceable anchor with no
tyre/reliability double-count and no "team X good on tyres" claims, roughly matching the lump.
The remaining win-gap is the crude per-team EWMA + hand-set weights; proper integration
(clean-air as a Kalman observation with car/driver split + fitted weights) should close it.

## v2 (the dedicated-session backlog)

- **Clean-air now MEASURED via OpenF1 `intervals`** (DONE — `app/etl/openf1.py`, free historical,
  79k laps / 72 races 2023+). Each lap is labelled clean/dirty from the real gap-to-car-ahead
  (>1.5s); `clean_air_pace.py` uses it where covered, proxy for pre-2023. Result: the measured
  clean-air pace gives the **same** predictive signal as the fast-quantile proxy (Spearman 0.36
  vs 0.35) — so it **validates the proxy** and makes the anchor traceable (no assumption). Still
  TODO: the measured **dirty-air penalty** (lap-time vs gap curve) and **start** (grid→lap1).
- **Clean-air as a Kalman observation** (not a side EWMA): swap the dirty "finishing position"
  observation for clean-air pace, with the car/driver split + fitted weights, and re-validate.
- ~~Clean-air race-pace anchor~~ (done, above). Original note kept for context:
- **Clean-air race-pace anchor (the big one).** Measure each car's race pace from un-trafficked
  (gap-ahead > ~1.5 s), fuel- and tyre-age-corrected race laps in `laps.parquet` → a pace signal
  free of deg/reliability/traffic. Anchor the sim on quali + this, and add deg/reliability/traffic
  separately from their own observables. Replaces the pace-scale fudge with a measured quantity
  and kills the remaining double-counts.
- **Remove the reliability double-count** — net the strength of past DNFs (or fit the anchor on
  classified pace only) so the hazard model isn't counting unreliability twice.
- **Per-car best-response strategy** inside the field (lift the Strategy Lab single-car
  optimiser to a Stackelberg field) — currently one optimal strategy is shared by all cars.
- **Score the prop markets**, not win/podium/points: pit-window, podium-without-fav, points,
  lead-lap distribution — judge the sim where physics has signal the rank model lacks.
- **MC the SC timing** from the structural SC intensity (#21) and apply the **weather variance**
  (#21/science/21) as a sim *mode* (the `rain_crossover` engine exists), widening prop intervals.
- **Calibrate the output** (temperature/variance) forward-chained before ensembling, so the
  sim's distributions aren't over-confident going into the blend.
- **Car-DNA (#22/science/19) as a cold-start prior** to seed the Kalman car term for a new
  team/car before any race.

The scaffold makes all of this safe to try: anything added is ensembled behind w, so the
worst case is always "no worse than the rank model."
