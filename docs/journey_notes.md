# The model journey — notes for the website write-up

_Raw material for a visitor-facing "how we built this model" story: from the first naive sim,
through the bake-off, to the decoupling deep-dive we're doing now — and the metrics that judged
every step. Bullet notes; to be turned into prose + visuals later. Newest learnings at the bottom._

## Act 1 — the naive start
- We began with a **mechanistic Monte Carlo**: simulate every car's lap times (pace + fuel +
  tyre + pit stops), rank by total race time. The intuitive "physical" model.
- It **lost badly** forward-chained (~31.7% top-pick vs the market's ~36%). Lesson #1: a detailed
  physical sim that predicts a high-dimensional intermediate (every car, every lap) compounds
  small errors and is over-confident — more physics ≠ better probabilities.

## Act 2 — the bake-off (let the data pick the model)
- Built a **forward-chained, calibration-first harness**: for each race in time order, predict
  using only strictly-prior races, score, then fold the result in. Leak-free by construction.
- Tested: grid+quali **baseline**, **PL-Glicko** rating, **Kalman** car+driver pace filter,
  **LightGBM** ranker, the mechanistic sim, and a team×circuit **affinity**.
- Result: they all cluster ~63% top-pick and barely beat a 10-line grid+quali baseline.
  **The signal is the grid / qualifying.** The **Kalman won** (best-calibrated, online, interpretable).
- Affinity was **rejected** (overfit at ~6 visits/circuit); kept as a documented negative.

## Act 3 — the honest negatives (what doesn't work, kept on the record)
- **No edge vs the pre-race market** (it's efficient). **No in-play edge** (our live prob is
  calibrated but lags the market ~90s). **No timing edge** at T-12h. **Market-making is -EV.**
- **Telemetry driving-style doesn't separate racecraft** from the car at a reliable grain.
- We keep every negative — the honesty IS the product (the "anti-AWS": every number explainable).

## Act 4 — mechanistic, brand-agnostic features (track physics, not brand bias)
- **Overtaking-difficulty index** (#20): one track number → per-circuit finishing spread + grid weight.
- **Structural safety-car prior** (#21): caution likelihood from street-ness (realism, not edge).
- **Hazard DNF model**: per-driver retirement risk (grid/first-lap/era) beats a flat 8%.
- **Car-DNA corner bands**: interpretable but not predictive over scalar pace (Explainer-only).
- **Weather-as-variance** (science/21): rain doesn't raise DNF and the wet favourite is already
  calibrated — but it scrambles WHO SCORES, so we widen only the points market in the wet.

## Act 5 — the decoupling deep-dive (where we are now)
- **The flagship sim, rebuilt right:** anchor it to the Kalman pace + **ensemble** so a learned
  weight can never make it worse than the rank model. The guarantee is proven forward-chained.
- **Found the bug that made the old sim "very wrong":** it re-applied a per-team tyre multiplier
  on top of Kalman pace (which already includes tyre management) → it crowned gentle-tyre teams
  regardless of speed. Removing it + calibrating the pace scale → the sim now beats the rank model.
- **The core idea:** the Kalman "strength" is a LUMP (fit on quali + finish) that conflates pace,
  tyre deg, reliability, racecraft, strategy. We're **decoupling it into measured components**,
  each traceable to observed data — never a generic "Team X is good on tyres" claim:
  - **Clean-air race pace** — fuel/tyre-corrected pace on un-trafficked laps (OpenF1 gaps).
  - **Dirty-air penalty** — MEASURED non-linear curve (worse the closer you are; +1.15s glued →
    0 by 3s), strongly per-circuit (slipstream tracks shrug it off; high-speed-corner / can't-pass
    tracks bite hardest) — it's the *type* of speed, not raw speed.
  - **Per-car tyre deg** — MEASURED from each car's own fuel-corrected stint slopes (not a team
    label). Proven a reproducible property (prior→next Spearman 0.305), ~±0.1 s/lap/lap spread —
    a real, modest effect, traceable to specific stints.
  - **Reliability** — DECOUPLED (`net_dnf`): a retirement no longer drags down the car's *pace*
    strength; reliability lives only in the hazard DNF model. Forward-chained calibration-neutral
    (the double-count was real but small) → adopted as the cleaner, more correct model.
  - **Grid** — we used to call "grid" the lap-1 timing-line position, which is *post-start* — it
    only matches the official grid 30% of the time (mean 1.7-place shuffle baked in). Swapped in
    the OFFICIAL grid (Jolpica, penalties applied); the lap-1 delta is now its own thing →
  - **Start performance** = official grid − lap-1 position. A big lap-1 shuffle (2.7 places std)
    but only a weak persistent driver skill (Spearman 0.13) — mostly variance, small per-driver
    bias (STR/MAG good starters, BOT/GRO poor — face-valid).
- **Free data that makes it traceable:** FastF1, Open-Meteo (weather), **OpenF1** (real gap-to-car-
  ahead, free historical), Jolpica (DNF causes). Prior art (Heilmeier/TUMFTM, state-space tyre
  models) validates the recipe.

## The metrics — how we judged every step (give this its own section on the site)
- **Forward-chained, leak-free**: predict each race from only its past; never sees the future.
- **Calibration-first**: a single temperature tuned on win log-loss; report **Brier + log-loss +
  reliability** for win / podium / points.
- **Best-of-the-rest accuracy**: predict P2 with the actual winner removed — the high-variance
  signal that matters given one car's dominance (the winner is near-trivial = pole).
- **Top-pick accuracy**, **per-race DNF log-loss** (vs a flat rate), and **vs the market** (Brier).
- For the sim specifically: judge on **best-of-rest / podium / points / props**, not who-wins.

## Act 6 — what the sim is (and isn't) good for
- We scored the sim on **prop markets** (`validate_props.py`): head-to-head matchups and
  podium-without-the-favourite. Honest result: the sim does **not** beat the rank model on these —
  they're still "who finishes where" questions, and the rank model is at the ceiling there.
- The sim's *measured* edge is the **marginal midfield** (best-of-rest 0.42→0.51, points
  0.584→0.489 with the dirty-air curve). The genuinely sim-unique markets — **who leads at lap k,
  pit-window timing, lead changes** — need lap-by-lap state we haven't exposed yet (future work).
- Takeaway for the site: a sim doesn't beat a calibrated rank model at picking the order; its job
  is the *texture* of the race (midfield variance, strategy, what-ifs) that a rank model can't show.
- **Variance sources (#12) — the honest lesson:** we tried adding a calibrated start/T1 shuffle
  (measured at ~2.7 places). For a sim that outputs *finishing order* it's NEUTRAL — absorbed into
  the global variance level. Only **structured** variance adds information: **dirty-air**
  (position-dependent, per-circuit) does; an unstructured start jitter doesn't (it'd only matter
  for lap-1-position props). Also found: pace-scale and dirty-air interact — with dirty-air on,
  the sim wants pace_scale ~0.30 (the 0.18 default was calibrated before dirty-air existed).

## Act 7 — a premise that failed honestly (good for the story)
- We sourced Pirelli's real C1–C6 nominations (94 races, 2022–26) to make tyre deg "comparable
  across races." Expected: softer absolute compound → faster deg. **It didn't hold** — C5/C6 show
  the *lowest* in-race deg, because softer compounds are nominated at low-deg tracks (Monaco, Imola)
  and run in short managed stints. The plain *relative* compound (soft degrades fastest) is the
  cleaner in-race signal. We kept the table as a sourced artifact but did NOT wire it — a good
  example of testing a plausible idea, finding it doesn't help, understanding *why*, and saying so.

## Act 8 — the final scorecard (give this the closing section on the site)
- **Stackelberg / per-car field strategy (#15):** we let each car best-respond with its own stop
  plan, driven by measured per-car deg. On the current (lumped-Kalman) anchor it HURTS — adding an
  explicit per-car deg term re-introduces the double-count (the strength already contains deg). It
  would only pay on a fully decoupled clean-air anchor — and even then, for who-finishes-where the
  rank model is at the ceiling. Kept as opt-in, default off. The honest lesson again: you can't
  bolt physical components onto the lumped strength without double-counting.
- **Final forward-chained comparison (45 recent races, the best sim config = pace 0.30 + measured
  dirty-air):** the two models SPLIT the trophies —
  - **Rank model** wins **calibration**: win/podium/points logloss 0.131 / 0.244 / 0.471.
  - **Structural sim** wins **order accuracy**: top-pick 0.356 vs 0.333, and **best-of-rest 0.49 vs
    0.38** (the high-variance rest-of-field metric that matters given one car's dominance).
  - The **ensemble** tunes between calibration and accuracy; the guarantee holds (never worse than
    the rank model on logloss).
- **The closing line:** the physics never beat the calibrated rank model on *probabilities* — but
  the decoupling made the sim genuinely better at *ordering the midfield*, and every number now
  ties to observed data (clean-air pace, measured dirty-air, official grid, per-car deg, reliability
  in the hazard model only). Calibration + transparency over a false edge — the anti-AWS, proven.

## Act 9 — why the leader checks out (and why the sim can't quite match it)
- We chased the last gap: the physics sim trails the rank model on WIN/PODIUM. Research said
  "stronger cars shrug off dirty air — scale the wake by strength." We tested it on the data and
  found the OPPOSITE: a fast car stuck in traffic loses **1.3 s/lap** vs a slow car's 0.5 s/lap —
  because it's being **held up**, and pace-mismatch dwarfs the aero effect.
- So the naive fix was rejected — but it handed us the cleanest explanation of the whole sport:
  **track position is gold because being stuck costs a fast car ~1.3 s every lap.** That's why
  qualifying dominates finishing order, why the leader sprints into clean air, and why the rank
  model (which bakes in "fast cars start ahead and stay ahead") edges the sim at the very front.
- The honest open lever: the sim shuffles the clean-air leader backwards too easily; the real fix
  is track-position *persistence* (a leader with a pace cushion is near-unpassable), a bigger change
  we've scoped but not built. A good note to end on — we know exactly what's left and why.

## Act 10 — re-anchoring the sim on clean pace (the prerequisite for the real fix)
- To fix the win/podium gap we need the sim's "pace surplus" to be PURE pace, not the lumped
  Kalman strength (which secretly contains deg/reliability/traffic — adding physics on top
  double-counts, as #15 showed). So we built a decoupled **clean-air anchor**: quali pace +
  forward-chained prior clean-air race pace (`clean_anchor.py`).
- Effect (measured): the clean anchor identifies the fast car far better — **top-pick 0.31 → 0.51**
  — but the *current* sim over-disperses it (worse log-loss). That's expected and is the whole
  point: the anchor gives a clean, sharp pace signal; the **position-resolution model** (next) is
  what converts it into a calibrated distribution by making the clean-air leader near-unpassable.

## Performance ledger — every change and its measured effect (forward-chained)
_The honest scoreboard. "→" is before→after; all leak-free / forward-chained._

| Change | Metric | Effect | Verdict |
|---|---|---|---|
| Weather: widen points in the wet | wet points log-loss | 0.558 → **0.517** | KEPT (points-only) |
| Fix tyre deg double-count | sim favourite vs anchor agreement | 35% → **100%** | KEPT (was a bug) |
| Calibrate pace scale (0.45→0.18) | sim favourite win% | 60% → **~28%** | KEPT |
| Measured dirty-air curve | best-of-rest / points ll | 0.42→**0.51** / 0.584→**0.489** | KEPT |
| net_dnf (reliability → hazard only) | win/podium/points ll | calibration-neutral | KEPT (cleaner) |
| Per-car tyre deg | prior→next reproducibility | Spearman **0.305** (real) | measured; hurts on lumped anchor |
| Official starting grid (vs lap-1) | grid contamination removed | 1.7-place start shuffle | KEPT (correctness) |
| Pirelli absolute compound | in-race deg comparability | no gain (C5/C6 lowest deg) | REJECTED (honest) |
| Strength-scaled dirty-air | per-lap traffic penalty | strong cars lose MORE (1.3s/lap) | REJECTED; → "track position is gold" |
| Start-shuffle variance | finishing-order ll | neutral (absorbed) | opt-in, off |
| Sim ensemble into predictor (#16) | production probabilities | unchanged (default off) | wired, opt-in |
| Re-anchor sim on clean pace | top-pick | 0.31 → **0.51** (ll worse pending #2) | foundation for position model |
| Position-resolution sim (#24) | top-pick / best-of-rest | 0.47→**0.53** / 0.31→**0.49** | best ordering engine; calibration still rank model's |
| **Final scorecard** | — | rank model wins calibration; sim wins order accuracy (best-of-rest 0.49 vs 0.38) | ship rank model + sim for texture |
| Season sim vs Polymarket title | drivers' title odds | model **87%** vs market **51%** on the leader | no edge; model over-extrapolates the standings leader |
| Pole model vs Polymarket (23 races) | pole Brier / top-pick | 0.045 vs **0.039** / 26% vs **30%** | no edge (even the most predictable session); market better-calibrated |
| Per-car straight-line defence (sim) | pass-rate vs sl_z | +0.094 logit (z=2.4); sim order-acc neutral | mechanism REAL (kept opt-in); doesn't lift sim accuracy |
| 2026 era gate (active aero) | global pass threshold | ×0.85 (shrunk prior) | wired; energy-override designed, deferred to 2026 data |
| Held-up asymmetry (backmarkers yield) | win-ll / top-pick / recovery | 0.178→**0.160** / 35.6→**37.8%** / recov-ll 0.321→**0.299** | KEPT (opt-in) — best mechanistic win/top-pick result; small podium/pts cost |

## Act 11 — making track position real (the position-resolution sim)
- The fix we'd scoped for the win/podium gap: stop ranking cars by total time (which lets a faster
  car pass for free) and instead make **track position a state** — each lap you only pass the car
  ahead if you're enough faster (`p = σ(k·(pace surplus − threshold))`, the Michelin overtaking
  curve), harder at hard-to-pass circuits. A clean-air leader with a pace cushion becomes
  near-unpassable (at Monaco, a fast pole car wins ~92%).
- Result: it's the **best ordering engine we've built** — beats the rank model on both top-pick
  (0.47→0.53) and best-of-rest (0.31→0.49). The honest catch: locking the order also makes the
  *probabilities* over-confident, so the rank model still wins calibration (points/podium log-loss).
  First cut over-locked (points ll blew up to 1.27); loosening the threshold fixed most of it.
- The clean ending: **rank model for calibrated probabilities, position sim for the order and the
  lap-resolved props** (who-leads-lap-k, pit windows) it's uniquely able to produce. Two engines,
  each best at its job — exactly what the whole journey has been pointing at.

## Act 12 — zooming out to the whole season (the championship simulator)
- Every engine so far answers *one race*. The season sim aggregates them: take the real current
  standings, then Monte-Carlo every remaining race from the same pre-quali pace model + hazard DNF
  we already validate per race, award points, repeat 20k times → per-driver and per-constructor
  **title odds**, expected points, P(top-3). Low overfit by construction — it invents no new model,
  it just compounds predictions we've already scored.
- **Interactive sandbox** (the point of the page): nudge a driver's pace (±z) or hand them extra
  DNFs and the whole title race re-simulates live. Giving the 2026 leader (ANT, +51 pts) eight
  late-season retirements collapses his odds 87% → 7% and hands the title to his team-mate — the
  kind of "what if" a static odds table can't answer.
- **The honest market column.** We pull the de-vigged Polymarket drivers'- and constructors'-
  champion outrights and sit them beside our numbers. The story is the same as every other market
  test: **no edge.** But the *shape* of the disagreement is instructive — our model puts the leader
  at 87% where the market says 51%. The sim faithfully extrapolates a measured 51-point pace lead;
  the market prices in the long-season unknowns a pace model can't see (upgrades, form swings,
  a mid-season regulation tweak). It's the per-race "over-confident on the favourite" finding,
  scaled up to a whole championship — surfaced transparently rather than hidden.
- Clean ending for the arc: the project now predicts at every zoom level — a lap (replay/props),
  a race (rank model + position sim), and a **season** (this) — and at every level the verdict is
  the same honest one: well-calibrated, transparent, no alpha over an efficient market.

## Visual ideas for the site
- The bake-off table (done, in FINDINGS). The ensemble slider (done). The animated rain (done).
- NEW: the dirty-air curve (penalty vs gap, with a per-circuit selector — slipstream vs high-speed).
- NEW: a "decomposition" diagram — the lumped strength fanning out into measured components.
- NEW: a forward-chaining animation (the train moving race by race, never looking ahead).
