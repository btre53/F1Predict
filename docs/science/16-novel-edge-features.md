# 16 — Novel Mechanistic Edge Features for Pre-Quali / Finishing-Order Prediction

A concrete, honest engineering brief for **mechanistic, generalizing** features that
improve **pre-quali** prediction and **finishing-order / props**, on **our** data
(FastF1, Jolpica, 168 races 2018–2026 in `laps.parquet`; full car telemetry +
`get_circuit_info()`; single-station per-session weather; Polymarket for comparison).

**The non-negotiable design rule (owner's bar).** No brand/identity features. We already
built and **rejected** a naive team×circuit affinity — `KalmanTrackModel` in
`backend/app/models/kalman.py` — which, forward-chained over 168 races, made *every*
metric worse, monotonically in `track_weight` (win log-loss 0.128 → 0.130 / 0.134 / 0.139
at w = 0.5 / 1.0 / 1.5). The diagnosis is recorded in that file: at ~5–8 visits/circuit a
team-circuit residual is dominated by race-day variance (SC/DNF/incidents), not stable
car-track suitability. **Every feature here must decompose brand → a measured car/driver/
track physical trait that a brand-new team (Audi/Cadillac) inherits from its measurements,
not its name.** Where a candidate is just an affinity in disguise, this brief says so.

**What is already settled (don't relitigate).** The pre-race **outright market is
efficient** (doc 07); the **in-play edge is null** after detrending (doc 13, a clean kill);
**telemetry driving-*style*** does **not** separate racecraft from the car at the reliable
grain (doc 12, |r| < 0.18 at n=152 driver-races); the **hazard DNF model is built** and
beats flat (doc 15). So this brief targets the one place left with headroom: a **smarter,
more track-aware pre-quali prior** and **better-calibrated props/finishing-order**, via
features that *generalize* across teams and seasons.

---

## Executive summary — ranked by (expected signal ÷ overfit-risk) on our 168 races

| # | Feature | Verdict | Signal ÷ overfit-risk | One-line mechanism |
|---|---|---|---|---|
| **1** | **Circuit overtaking-difficulty → a learned grid-vs-pace blend weight** | **Prototype first.** Strongest, lowest-risk. | **High** | One measured number per circuit (passing rate / grid→finish lock) decides how much qualifying should dominate the prediction *here*. Pre-quali it sets the variance of the finishing-order distribution. |
| **2** | **Car-DNA = corner-speed-band pace decomposition, projected onto a circuit's corner-band demand** | **Prototype second.** The owner's flagship idea — but must be regularized hard and validated as *incremental* over scalar pace. | **Medium-High** | Decompose each car's pace into low/med/high-speed-corner + straight-line factors from telemetry; a circuit is a *demand profile* over those bands; suitability = car factor · circuit demand. Generalizes by construction (a new team is its measured factors). |
| **3** | **Per-circuit SC/caution-likelihood from observable structural features → feeds the hazard/SC model** | **Build (small).** Dual-purpose (props + scenario realism). | **Medium-High** | SC rate is driven by *measurable* track structure (run-off, street-ness, pit-lane entry risk, lap-1 funnel) + weather, not the circuit's name. One regularized number/circuit + a weather term. |
| **4** | **Weather-conditioned finishing-order *variance* (not mean)** | **Test, expect modest.** | **Medium** | Rain/temperature don't reliably shift *who* wins, but they fatten the finishing-order distribution and lift DNF — so they should widen our predictive intervals and raise upset/podium-without-favourite props. |
| **5** | **Unsupervised circuit & car clustering → a *shrinkage backbone*, not a feature** | **Use as plumbing for #1/#2.** Gimmick if shipped as a standalone feature. | **Low-Medium** | Cluster circuits by corner-band/telemetry profile so a car's trait at an *unseen* track borrows strength from its *similar* tracks — a principled regularizer, not a new predictor. |
| 6 | **Standing-start launch / lap-1 position-change skill (grid-netted)** | **Test, niche.** | **Low-Medium** | First-lap places gained, netted vs grid slot, is a thin but *separable* driver trait that feeds finishing-order on lock-in circuits (interacts with #1). |

**Bottom line.** The single highest-leverage, lowest-overfit idea is **#1**: a *one-number-
per-circuit* overtaking-difficulty index that **tunes the grid↔pace blend and the spread of
the finishing-order distribution**. It is the mechanistic, generalizing replacement for the
rejected team×circuit affinity — it modulates *how confident* we are, not *who we favour by
name*. Build it first; build **#2 (Car-DNA)** second as the genuinely novel decomposition,
held to a strict incremental-calibration bar; fold **#3 (structural SC index)** into the
existing hazard model.

---

## 1. Circuit overtaking-difficulty index → learned grid-vs-pace blend

### Causal hypothesis (mechanistic, not brand)
The grid→finish correlation is **not** a property of any team; it is a property of the
**track's geometry**: passing requires a braking zone preceded by a long enough
acceleration zone (a DRS/slipstream straight) into a corner wide enough to hold two lines.
Where those are absent (Monaco, Hungaroring, Singapore), **track position is nearly
conserved**, so qualifying dominates and the finishing order is *low-variance given the
grid*. Where they're abundant (Spa, Shanghai, Bahrain, Baku straight) **pace can overcome
grid**, so qualifying matters less and the order is *high-variance*. Pole-to-win conversion
ranges from ~70%+ at Monaco to ~50% at high-overtaking tracks
([formula-1-bet](https://formula-1-bet.com/articles/f1-data-analytics-for-betting/)),
and the qualifying→finish relationship is known to be *moderated by overtaking difficulty*
([Weissbock & Mills 2025, arXiv 2507.10966](https://arxiv.org/pdf/2507.10966)). This
generalizes: a brand-new circuit is scored by its **measured passing rate**, and a new team
is unaffected — the index multiplies *everyone's* grid weight equally.

### Exactly how to compute it from our data
Three observable, leak-controllable proxies per circuit, each forward-chained (use only
prior runnings of that circuit; shrink to the global mean for first visits):

1. **Grid→finish rank lock** — Spearman ρ between `grid` and `finish_pos` across all dry,
   green-dominant runnings of the circuit. High ρ ⇒ hard to overtake. We already have
   `grid` (lap-1 position) and `finish_pos` in `build_feature_table()`
   (`backend/app/models/features.py`). This is the horse-racing **draw-bias** estimator
   (OLS/Spearman of fractional start vs finish rank), which the literature warns is only
   reliable past ~200 observations and degrades on small samples
   ([Stall Position Bias, ResearchGate](https://www.researchgate.net/publication/397305150_Stall_Position_Bias_in_British_Horse_Racing_A_Comparative_Analysis_Across_Distance_and_Course)) —
   hence heavy shrinkage below.
2. **On-track passing rate** — count position changes *not* explained by pit cycles. From
   `laps.parquet` we have per-lap `position`; a clean pass = a driver's `position`
   improving on a lap that is **not** a pit-out for them and **not** a pit-in for the car
   passed, during **green** (`track_status == "1"`) laps. Sum per race, normalize by
   (cars × racing laps), median over runnings. This is the mechanistic core (independent of
   the grid lock, which is partly a *pace-spread* artefact).
3. **Lap-1 churn** — mean |grid − position_after_lap1| across runnings. Captures
   start-line passing capacity specifically (funnel width into turn 1), which differs from
   steady-state passing.

Combine into one index per circuit:
`OT_difficulty = z(grid_finish_rho) − z(pass_rate) − z(lap1_churn)`, then **empirical-Bayes
shrink** toward the calendar mean by visit count: `OT* = OT · n/(n + k)` with `k ≈ 6`
(same shrinkage form as the rejected affinity, but applied to a *track-physics* number that
is the *same for all teams*, which is why it generalizes where the affinity didn't).

### How it enters the model (two uses)
- **Grid↔pace blend weight.** The Kalman predictor already exposes a `grid_weight` knob
  (`kalman.py`, `predict()`), today a flat scalar. Make it **circuit-scaled**:
  `grid_weight(circuit) = w0 · sigmoid(OT*)`. Hard-to-pass tracks lean on grid/quali;
  easy-to-pass tracks lean on pace. *Pre-quali*, the same index sets the **spread** of the
  Plackett-Luce / Monte-Carlo finishing-order distribution (tight at Monaco, wide at Spa) —
  this is the pre-quali track-specificity the current flat prior lacks.
- **Props.** Directly improves podium-without-favourite, top-6, and H2H calibration via the
  correct conditional variance.

### Forward-chained validation
Metric: **finishing-order log-loss / Plackett-Luce likelihood and grid-aware Brier** on
held-out races, forward-chained exactly as `hazard.forward_chain_eval()` does (fit OT* on
`seq < s`, score race `s`). **Baselines:** (a) flat `grid_weight` (current); (b) a *team×
circuit affinity* (the rejected model) to confirm the structural index does what the brand
proxy couldn't. Success = lower finishing-order log-loss *and* better-calibrated
podium/top-6 props, **monotone in conviction** (unlike the affinity, which degraded
monotonically).

### Overfit risk + regularization
**Low.** One number per circuit, heavily shrunk, *shared across all teams and seasons*
(track geometry is far more stable than car-track residuals — the 2022 aero reg-change is
the main regime break, [keberz](https://www.keberz.com/post/overtaking-in-formula-1-the-2022-season-update),
so estimate post-2022 separately or add a reg-era offset). The danger is using the
grid→finish lock *alone* (it's partly a pace-spread artefact); the passing-rate and lap-1
terms are the mechanistic anchors. Cap at ~1 free parameter (`w0`) tuned on a coarse grid.

### Honest signal-vs-noise verdict
**Signal.** This is the cleanest, most defensible idea in the brief. It is the *correct*
mechanistic form of "some tracks are different": it modulates **confidence**, applies
**equally to every team** (so it generalizes), and rests on a *track-stable* quantity rather
than a noisy per-team residual. Expect a small but real finishing-order/props improvement and
materially better pre-quali variance calibration.

---

## 2. Car-DNA: corner-speed-band pace decomposition × circuit corner-band demand

### Causal hypothesis (mechanistic, not brand)
This is the owner's flagship and the explicit anti-brand target: not "Ferrari is strong at
Monaco" but **"cars with higher minimum speed in low-speed corners + better traction out of
slow corners do better at street circuits."** Decompose each car's pace into **physically-
named factors** measured from telemetry: (i) **straight-line/drag** (speed-trap & top
speed), (ii) **high-speed-corner grip** (min speed in fast corners ≈ aero), (iii)
**low-speed-corner grip** (min speed in slow corners ≈ mechanical grip), (iv) **traction**
(speed gained / throttle-on time in the first ~100 m after a slow-corner apex), (v)
**braking** (deceleration gradient into heavy braking zones). A circuit is a **demand
profile** = the fraction of a lap spent in each band. **Suitability = car factor vector ·
circuit demand vector.** A new team inherits its rating from its *measured factors*, so this
generalizes by construction — exactly the AWS "Car Performance Scores" decomposition
([AWS F1 insights](https://aws.amazon.com/sports/f1/)), public-mirrored.

### Exactly how to compute it from our data
We already pull car telemetry and cache it (`backend/app/models/telemetry_signatures.py`,
which loads `get_car_data()` with Speed/Throttle/Brake/Gear/DRS) — extend that, don't start
fresh. The *missing* piece is **corner segmentation**, now feasible:

1. **Corner positions & speed-binning.** `session.get_circuit_info().corners` gives
   `Distance` along the lap for each corner (requires telemetry loaded for the Distance
   channel)
   ([FastF1 circuit_info](https://docs.fastf1.dev/circuit_info.html)). FastF1's corner
   list is **only geometry — it does not classify corner speed**, so we classify each corner
   by the **field-median minimum speed** in a window around its `Distance` on a fastest-lap
   telemetry trace: low (<≈130 km/h), medium (130–210), high (>≈210). The ~220 km/h corner/
   straight split is an established telemetry heuristic
   ([Radicalbit](https://radicalbit.medium.com/f1-modeling-an-interesting-use-case-for-telemetry-sports-bdfd0cef0801);
   [motorsport.com fastest/slowest turns](https://www.motorsport.com/f1/news/fastest-slowest-turns-f1-calendar/10572266/)).
2. **Per-car factor deltas vs field median** (per session, qualifying preferred — cleanest,
   low-fuel, one-lap): min corner speed by band, speed-trap (`speed_st`, already in
   `laps.parquet`), and a traction proxy = mean Δspeed over the 2–3 s after each slow-corner
   apex (from the speed trace). Teammate/field-net so the *driver* and session conditions
   partly cancel and the **car** factor is isolated.
3. **Reduce to 3–4 orthogonal factors** (PCA on the per-band delta matrix), physically named
   (power/drag, downforce, mechanical+traction, braking). Circuit demand = lap-distance
   share per band from `get_circuit_info()` + the fastest-lap trace.
4. **Suitability score** per car×circuit = factor vector · demand vector; forward-chained
   (factors estimated only from prior sessions, drifting like the Kalman car term).

### Forward-chained validation
This **must** clear a high bar because doc 10 §4 flagged the n≈85 overfit risk and the
rejected affinity proves the failure mode. Metric: does adding the suitability score to the
Kalman/PL prior *incrementally* lower **pre-quali** finishing-order log-loss vs the
**scalar-pace baseline**, forward-chained over 168 races? Cross-check it does **not**
collapse into the rejected team×circuit affinity (correlate the two; if suitability ≈
affinity, it adds nothing the affinity didn't — and the affinity was net-negative).

### Overfit risk + regularization
**Real, the highest in this brief.** Telemetry pulls are slow (~30 s/session) so the sample
is effectively *smaller* than 168 unless we batch-extract a season. Guardrails: **≤4
factors**, **physically pre-named** (no free latent dimensions), estimate factors with the
**same shrinkage/process-noise discipline as the Kalman car term**, and judge on
*incremental* calibration only — never on a pretty radar chart. The deepest trap: corner-
speed factors are themselves **car-and-driver confounded** (a faster car carries more speed
through every corner), so factors must be **shape-normalized** (e.g. each car's band profile
*relative to its own mean pace*) so we measure *where* a car is fast, not just *that* it's
fast — otherwise it's a scalar-pace proxy wearing five hats.

### Honest signal-vs-noise verdict
**Cautious signal; genuinely novel; the most likely to disappoint.** The mechanism is sound
and it is the *correct* decomposition of brand into physics, with real Explainer value
("this car gains 0.3 s in low-speed corners but loses 0.2 s on the straights here"). But the
88/12 car/driver split + slow telemetry + the affinity precedent mean the *incremental*
predictive lift over scalar pace may be small. **Prototype it, but pre-commit to killing it
if it doesn't beat scalar pace forward-chained** — and keep it as an Explainer feature even
if the predictive lift is marginal (label that honestly).

---

## 3. Per-circuit SC/caution-likelihood from structural features (feeds the hazard model)

### Causal hypothesis (mechanistic, not brand)
Safety-car probability is hugely circuit-dependent (~100% at Singapore vs ~10% at low-risk
tracks, [Axiora](https://www.axiorablogs.com/blog/probability-and-the-safety-car-the-statistics-of-f1-strategy);
[f1technical](https://www.f1technical.net/forum/viewtopic.php?t=26879)) — but the *cause* is
**measurable track structure**, not the circuit's identity: **walls close to the track with
little run-off** (a small error → a stranded car → SC), **narrow lap-1 funnel** (bunched-up
start contact), and **weather** (rain onset). These generalize: a new street circuit with
walls gets a high index from its *structure*, before it has any history.

### Exactly how to compute it from our data
- **Observed SC labels (free, in hand).** `track_status` containing 4/6/7 marks SC/VSC laps;
  the hazard model already computes `_sc_active_laps()` (`backend/app/models/hazard.py`).
  Label each race: any SC (binary) and #SC periods (count).
- **Structural predictors (one number/circuit, shared across teams):**
  (i) a **street-circuit / wall-proximity** proxy — minimal-run-off tracks have *higher
  lap-1 churn* and *lower passing rate*, both already computed in feature #1, so this reuses
  that telemetry-free structure; (ii) **lap-1 incident rate** = historical fraction of cars
  losing many places or DNF-ing on lap 1 (from `laps.parquet` lap-1 positions + Jolpica DNF
  cause); (iii) **pit-window clustering** as an in-race trigger (many cars pitting within a
  short lap window raises near-term SC odds via traffic/unsafe releases) — derivable from
  `is_pit_in` counts per lap.
- **Weather term:** `Rainfall` bool / `TrackTemp` from FastF1 session weather (single
  station, ~1 min — adequate for a *race-level* rain flag; doc 11), or Open-Meteo historical
  for a leak-free pre-race rain *probability*.
- **Model:** a small **Poisson/logistic** with circuit-structural fixed proxies + weather,
  empirical-Bayes shrunk to the calendar mean (mirrors the incident-factor multiplicative
  models in public F1 predictors,
  [DeepWiki F1 incidents](https://deepwiki.com/mehmetkahya0/f1-race-prediction/5.3-race-incidents-and-probability-models)).
  **Pre-register ≤4 terms.**

### Forward-chained validation
Predict P(any SC) per race, forward-chained; score Brier/log-loss vs (a) calendar base rate
and (b) a pure per-circuit historical SC rate (the brand-proxy baseline). The structural
model wins if it generalizes to held-out *circuits* better than the per-circuit rate —
e.g. predicting a *new* street circuit's SC risk from structure. Then feed the per-race SC
intensity into the hazard model's `is_sc_restart` pathway and the sim's SC count.

### Overfit risk + regularization
**Low-Medium.** SC is a near-Poisson shock (doc 10 warns against long-horizon SC
*forecasting* — that remains a trap). We are *not* forecasting "SC in next 10 laps"; we are
estimating a **race-level prior intensity** from structure, which is exactly the defensible
version. Keep terms few; the per-circuit history term must be shrunk hard (Singapore's ~100%
is real, but most circuits have <10 runnings).

### Honest signal-vs-noise verdict
**Signal, dual-purpose.** Improves props that hinge on chaos (podium-without-favourite,
points-finish for midfield, over/under SC) and scenario realism in the sim. The structural
framing is the generalizing, non-brand version of "Singapore always has a safety car."

---

## 4. Weather-conditioned finishing-order *variance* (not the mean)

### Causal hypothesis (mechanistic, not brand)
Doc 11 already established weather is **single-station, no sub-circuit resolution**, and that
there is no live weather edge. The salvageable, *mechanistic* claim is different and untested
in our data: **rain and extreme track temperature don't reliably change *who* is fastest, but
they fatten the finishing-order distribution** — more driver errors, more DNFs, more strategy
divergence (slick↔inter crossover) → higher upset rate. So weather should widen our
predictive *intervals* and lift *upset/podium-without-favourite* props, even though it adds
little to the *point* prediction.

### Exactly how to compute it from our data
- Label each race wet/mixed/dry from FastF1 `Rainfall` (any-true during race) + a TrackTemp
  band. (Open-Meteo historical for a leak-free *pre-race forecast* probability if we want a
  predictive, not just contemporaneous, signal — [Open-Meteo](https://open-meteo.com/en/docs/historical-forecast-api).)
- Measure, conditioned on the wet flag: (i) variance of `PGAE` (grid-netted finish residual,
  `racecraft.py`) — does it inflate in the wet? (ii) DNF rate (we have it via the hazard
  data); (iii) grid→finish ρ (does rain *break* the qualifying lock, interacting with #1?).
- If confirmed, weather enters as a **distribution-spread multiplier** (and a DNF-rate bump
  feeding the hazard model), **not** a driver/car-favouring term.

### Forward-chained validation
Compare the *calibration* (PIT/coverage of predictive intervals) and props log-loss with vs
without the wet-variance multiplier, forward-chained. The bar is **interval calibration and
upset-prop log-loss**, not point accuracy.

### Overfit risk + regularization
**Medium.** Wet races are rare (~10–15% of the sample), so the wet-variance estimate is
noisy — shrink it hard toward the dry variance and use a *single* multiplier, not per-driver
wet skill (which the small wet sample cannot support — a clear trap). A *driver* wet-skill
term is tempting and almost certainly overfits at our n; resist.

### Honest signal-vs-noise verdict
**Modest signal, correctly framed.** As a *who-wins* feature it's near-dead (doc 11). As a
**variance/DNF** feature it's plausibly real and cheap to test, and it's the honest use of
the data we have. Test it; expect a small props/calibration gain, mainly on upset markets.

---

## 5. Unsupervised circuit & car clustering → a shrinkage backbone (plumbing, not a feature)

### Causal hypothesis (mechanistic, not brand)
Don't ship a cluster label as a predictor (that's a fancy brand proxy — "Monaco-type tracks"
is just an alias). The *mechanistic* use is as a **borrowing-strength regularizer**:
circuits with similar **corner-band/telemetry profiles** (from #2) should share information,
so a car's measured trait at an *unseen* circuit is shrunk toward its average at *similar*
circuits rather than the global mean. Public work clusters F1 circuits into interpretable
groups — street (Baku/Miami/Marina Bay), fast-flowing (Spa/Suzuka/Silverstone), tight
high-downforce (Monaco/Hungaroring) — via k-means on corner/structure features with a
silhouette-chosen k
([dfamonteiro](https://dfamonteiro.com/posts/f1-clustering/);
[parttimeanalyst PCA](https://theparttimeanalyst.wordpress.com/2018/06/27/f1-circuit-cluster-analysis-part-1/)).

### Exactly how to compute it from our data
PCA/k-means on the **circuit corner-band demand vectors** built in #2 (and on
telemetry-free structure: passing rate, lap-1 churn, speed-trap distribution). Use the
cluster (or, better, the continuous PCA coordinates) to define a **similarity kernel** between
circuits; in #1 and #2, replace "shrink to global mean" with "shrink to similarity-weighted
mean over other circuits." Also cluster **race archetypes** (processional vs chaotic) from
SC count + lap-1 churn + DNF count to *interpret* and stress-test the sim, not to predict.

### Forward-chained validation
The backbone is validated *through* #1/#2: does similarity-weighted shrinkage beat
global-mean shrinkage in forward-chained finishing-order log-loss? No standalone metric —
that's the point.

### Overfit risk + regularization
**Low if used as plumbing, high if shipped as a label.** A hard cluster label invites
multiple-testing on "which cluster suits which car" — the affinity trap with extra steps.
Use **continuous** coordinates + a smooth kernel; never let the model fit a free coefficient
per cluster×team.

### Honest signal-vs-noise verdict
**Plumbing signal, standalone gimmick.** Valuable only as the regularizer that lets #1/#2
generalize to thin-sample circuits. Worth building *with* #2; not worth shipping alone.

---

## 6. Standing-start / lap-1 position-change skill (grid-netted) — niche

### Causal hypothesis
First-lap places gained, **netted against the grid slot** (P2 has more to gain than pole),
is a thin but plausibly *separable* driver+car launch trait (clutch/getaway + first-corner
positioning), distinct from steady-state pace. On lock-in circuits (#1) lap-1 is a large
share of all overtaking, so launch skill feeds finishing order there specifically.

### Compute / validate
Lap-1 gain = `grid − position_after_lap1` from `laps.parquet`; net vs an empirical
`E[lap1 gain | grid]` curve (PAVA, same as `racecraft.expected_finish_by_grid`); shrink per
driver. Forward-chained: does a driver's prior grid-netted lap-1 gain predict their next
race's lap-1 gain (a real skill has positive autocorrelation), and does adding it improve
finishing-order log-loss on high-OT-difficulty circuits?

### Overfit + verdict
**Low-Medium overfit** (one shrunk number/driver). **Weak-but-honest signal**; likely small
and partly car-driven (launch is power-unit + clutch dependent). Test only after #1; a useful
*interaction* term with the overtaking index, not a headline feature.

---

## Traps to avoid (pre-registered)

- **Brand/identity proxies in disguise.** A hard circuit-cluster label, a per-circuit
  historical SC *rate*, or a team×cluster coefficient are all the rejected affinity wearing a
  new coat. Always reduce to a **team-shared track-physics number** (#1, #3) or a
  **measured-trait projection** (#2) that a *new team inherits from its measurements*.
- **The team×circuit affinity is already dead** (`KalmanTrackModel`). Don't rebuild it; use
  it only as the *negative baseline* every new feature must beat.
- **Scalar-pace proxies in five hats.** Car-DNA factors must be **shape-normalized** (a car's
  band profile relative to its own mean pace) or they just re-encode "fast car," adding
  parameters and overfit without information.
- **Multiple testing across circuits/clusters.** With ~30 circuits and 4 corner bands, fishing
  for "factor f matters at track t" will find spurious hits. Pre-register the factor list,
  use shrinkage/similarity kernels (#5), and judge only *aggregate* forward-chained calibration.
- **Leakage / forward-chaining.** Every per-circuit and per-car estimate must use **only prior
  runnings** (fit on `seq < s`, score `s`), exactly like `hazard.forward_chain_eval()`. The
  2022 aero reg-change is a regime break for overtaking — estimate overtaking-difficulty
  post-2022 separately or add a reg-era offset.
- **Wet driver-skill terms.** Wet races are ~10–15% of the sample; a per-driver wet skill will
  overfit. Use weather as a **variance/DNF multiplier** only (#4).
- **Long-horizon SC *forecasting*.** Estimate a **race-level SC prior** from structure (#3);
  do **not** try to predict "SC in the next N laps" (near-Poisson noise, doc 10).
- **Single-station weather over-reach.** No sub-circuit / per-corner weather exists on free
  data (doc 11). Use weather only at race granularity.

---

## Top 2–3 to prototype first

1. **Overtaking-difficulty index → grid↔pace blend + finishing-order spread (#1).** Highest
   signal-to-overfit, fully on data we already have (`features.py` grid/finish + `laps.parquet`
   positions), one shrunk number/circuit shared across all teams. It is the **mechanistic,
   generalizing replacement** for the rejected affinity: it tunes *confidence*, not *brand
   favouritism*, and gives the flat pre-quali prior real track-specificity. Validate
   forward-chained against the flat-blend and the dead affinity baselines.

2. **Structural SC/caution index folded into the existing hazard model (#3).** Small, cheap,
   reuses `hazard.py` + `track_status`, dual-purpose (props + sim realism), and generalizes
   to new street circuits from structure rather than name.

3. **Car-DNA corner-band decomposition (#2)** — the owner's flagship and the genuinely novel
   one, but **held to a strict incremental-over-scalar-pace bar** and built *with* the
   similarity-shrinkage backbone (#5). Pre-commit to killing the predictive use if it doesn't
   beat scalar pace forward-chained; keep it as an Explainer feature regardless.

---

## Sources
- Internal: [07-polymarket-backtest.md](07-polymarket-backtest.md) (market efficient),
  [10-novel-approaches.md](10-novel-approaches.md) (car-DNA / hazard scouting),
  [11-inplay-latency-and-weather.md](11-inplay-latency-and-weather.md) (weather is
  single-station; no live edge), [12-telemetry-racecraft-validation.md](12-telemetry-racecraft-validation.md)
  (telemetry *style* doesn't separate racecraft), [13-inplay-wpa-backtest.md](13-inplay-wpa-backtest.md)
  (in-play edge null), [15-hazard-dnf-model.md](15-hazard-dnf-model.md) (hazard DNF built);
  `backend/app/models/kalman.py` (rejected `KalmanTrackModel` affinity),
  `backend/app/models/features.py`, `backend/app/models/hazard.py`,
  `backend/app/models/racecraft.py`, `backend/app/models/telemetry_signatures.py`.
- Qualifying predictive power, moderated by overtaking difficulty:
  [Weissbock & Mills 2025, arXiv 2507.10966](https://arxiv.org/pdf/2507.10966).
- Constructor-vs-driver variance / circuit-type modelling:
  [arXiv 2508.00200](https://arxiv.org/pdf/2508.00200),
  [Bayesian disentangling driver/constructor, arXiv 2203.08489](https://arxiv.org/pdf/2203.08489).
- Pole/overtaking conversion by circuit:
  [formula-1-bet data analytics](https://formula-1-bet.com/articles/f1-data-analytics-for-betting/),
  [keberz 2022 overtaking reg change](https://www.keberz.com/post/overtaking-in-formula-1-the-2022-season-update),
  [Value of pole position, ResearchGate](https://www.researchgate.net/publication/349900608_The_Value_of_Pole_Position_in_Formula_1_History).
- Draw-bias methodology (one-number-per-track, sample-size caveats):
  [Stall Position Bias in British Horse Racing](https://www.researchgate.net/publication/397305150_Stall_Position_Bias_in_British_Horse_Racing_A_Comparative_Analysis_Across_Distance_and_Course).
- FastF1 circuit info / corner segmentation (geometry only, no speed class):
  [FastF1 circuit_info](https://docs.fastf1.dev/circuit_info.html),
  [FastF1 core](https://docs.fastf1.dev/core.html),
  corner-speed heuristics [Radicalbit](https://radicalbit.medium.com/f1-modeling-an-interesting-use-case-for-telemetry-sports-bdfd0cef0801),
  [motorsport.com fastest/slowest turns](https://www.motorsport.com/f1/news/fastest-slowest-turns-f1-calendar/10572266/).
- Car-DNA / AWS Car Performance Scores (public mirror of telemetry factor decomposition):
  [AWS F1 insights](https://aws.amazon.com/sports/f1/),
  [AWS braking performance (Smedley)](https://www.formula1.com/en/latest/article/rob-smedley-explains-how-the-new-aws-braking-performance-graphic-works-and.3A8cnQLZGXFbMjCR2fFBnB).
- SC probability by circuit + incident-factor models:
  [Axiora SC statistics](https://www.axiorablogs.com/blog/probability-and-the-safety-car-the-statistics-of-f1-strategy),
  [f1technical SC-per-track](https://www.f1technical.net/forum/viewtopic.php?t=26879),
  [DeepWiki incident probability model](https://deepwiki.com/mehmetkahya0/f1-race-prediction/5.3-race-incidents-and-probability-models).
- Circuit clustering (interpretable groups, silhouette k):
  [dfamonteiro F1 clustering](https://dfamonteiro.com/posts/f1-clustering/),
  [parttimeanalyst PCA cluster](https://theparttimeanalyst.wordpress.com/2018/06/27/f1-circuit-cluster-analysis-part-1/).
- Weather APIs (leak-free pre-race forecast):
  [Open-Meteo historical-forecast](https://open-meteo.com/en/docs/historical-forecast-api),
  [Open-Meteo docs](https://open-meteo.com/en/docs).
