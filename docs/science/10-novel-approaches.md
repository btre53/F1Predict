# 10 — Novel Approaches: Research Brief

A scouting report on prediction/edge techniques **beyond** what F1Predict has already
built (rating systems, Plackett-Luce/Harville, Kalman pace-filter, quali/FP signal,
LightGBM-LambdaRank, strokes-gained/PGAE racecraft, mechanistic Monte Carlo sim — see
docs/science/08, 09). Every idea here is assessed against **our** reality: free data
only (FastF1, Jolpica/Ergast, Polymarket CLOB), **~85 effective races** (overfitting is
the enemy), and the honest finding that the **pre-race outright market is efficient**
(no edge there). The only plausible edges are **in-play/live**, **sub-markets/props**,
and exploiting that the **car ≈ 88%** of finishing-order variance.

---

## Executive summary — ranked shortlist

Ranked by `(promise × in-play fit × novelty) ÷ overfit-risk` on **our** data:

| # | Approach | Verdict | Why it ranks here |
|---|---|---|---|
| **1** | **In-play Win-Probability (WPA) from reconstructed race state, priced as a martingale** | **Build first.** | This is the *only* place a credible edge exists for us. Re-uses our existing MC sim as the "fair price" engine, re-seeded from live state. The martingale/no-arbitrage lens turns it into a clean trading signal vs Polymarket. |
| **2** | **Survival/hazard model for DNF (and for "next caution")** | **Build.** Genuinely novel for us; small, robust. | We currently sample DNF from a flat TUM rate. A Cox/discrete-time hazard makes DNF *lap- and context-dependent* — directly feeds finishing-position props (top-6/points/podium-without-favourite) and the in-play model. Low overfit risk if kept to ~3 covariates. |
| **3** | **Regime-switching (HMM/Markov) race-state layer for the in-play sim** | **Build, but as plumbing not a forecaster.** | The in-play WPA model *needs* a state classifier (green/SC/VSC/red/rain). Don't try to *predict* the regime far ahead (gimmick); do *detect* it fast and *condition* the sim on it. This is the live-state backbone for #1. |
| **4** | **Car-DNA factor decomposition from telemetry (speed-trap vs cornering vs braking)** | **Prototype as a feature, not a product.** | Novel — our telemetry is captured but unused. Strokes-gained-by-category analog. Promising as *interpretable features* for the pace model and the Explainer, and to predict which **track type** suits which car (props edge). Overfit risk is real at n≈85; keep it to 3-4 orthogonal factors. |
| **5** | **Time-rank duality (exponential ↔ rank-ordered logit) for fast car/driver split** | **Steal the trick.** Low effort, high rigor. | A 2024 *Economics Letters* result that makes disentangling driver-vs-car **far less data-intensive** — exactly our constraint. Drops into the PL/Harville back-end we already chose. |
| 6 | Particle filter for live state | **Defer.** | Theoretically the "right" live filter, but our Kalman + MC re-seed covers 90% of it at a fraction of the complexity. Only worth it if the state is genuinely non-Gaussian/multimodal and latency allows. |
| 7 | Optimal-stopping / DP + game-theory pit strategy | **Strategy-Lab feature, not an edge.** | Great for the interpretable Strategy Lab; not a market edge. Worth a scoped build for product, not for CLV. |
| — | Ensembling/stacking, Kelly sizing | **Use as discipline, not headline.** | Standard hygiene we should apply (Benter-blend is already stacking; Kelly for sizing any live bet). Not "novel," but non-negotiable. |

**Bottom line:** the through-line is **in-play**. Items 1-3 compose into one system:
*detect the regime fast (3) → re-seed the sim from live state, with hazard-driven DNF (2)
→ output a martingale-fair live win-prob and trade the gap vs the thin Polymarket (1).*
That is the single most promising, genuinely-novel direction for us.

---

## 1. In-play Win-Probability-Added (WPA), priced as a martingale

**Novelty (vs our work):** Our sim is a *pre-race* engine. We have never produced a
**live** win-probability that updates lap-by-lap from reconstructed race state, and we
have never framed it as a **tradeable** quantity against the market. This is new.

**Promise & in-play fit:** This is *the* edge thesis. The pre-race outright market is
efficient (~0.95 corr), but **in-play markets are thin and slow**: industry/punditry
consensus is that odds "can reflect outdated information for **60-90 seconds** after a
safety car / incident" and that books lag 30-60s on majors
([f1bettips](https://f1bettips.com/f1-live-betting-tactics/),
[grandprix247](https://www.grandprix247.com/2025/12/14/formula-1-racing-on-the-track-isnt-chaotic-youll-learn-to-understand-it-by-paying-attention-to-real-world-performance/)).
Polymarket's F1 race-winner market exists 2024+ but is **thin** — which cuts both ways:
thin = exploitable mispricing *and* hard to get size on. The realistic deliverable is a
**CLV signal** (did our live prob lead the market?), not fantasy profit.

**The martingale lens (borrowed from in-play football pricing):** Gerrard et al.,
*Risk-Neutral Pricing and Hedging of In-Play Football Bets*
([arXiv 1811.03931](https://arxiv.org/pdf/1811.03931)), show in-play bet prices should be
a **martingale between information events**, jumping only on goals (for us: SC/VSC, rain
onset, DNF of a contender, a pit cycle resolving). The practical implications for us:
- **Fair price = E[win | current state]** under the "physical" measure; our MC sim,
  re-seeded from live state, *is* that expectation engine.
- **Between events the fair price should drift smoothly**; **at an event it should jump**.
  If the market jumps *late* (the documented 60-90s lag), the window between our jump and
  the market's jump is the edge. Pre-register: measure our prob's lead time vs Polymarket
  around timestamped race-control events.
- **No-arbitrage discipline:** sum of de-vigged YES must be ~1; our live probs must be a
  proper distribution (the sim guarantees this).

**Concrete sketch on our data:**
1. **State reconstruction** (offline replay for backtest; OpenF1/SignalR for true live —
   deferred): from FastF1 lap data we already have per-lap **position, gap, tyre age,
   compound, pit events, track status**. Build `live_state(lap)` in Polars.
2. **Re-seed the existing MC sim** at lap *L*: fix track positions and gaps to the
   observed state, set each car's remaining-pace from the Kalman/PL estimate *adjusted for
   observed in-race form*, apply the regime (item 3) and hazard DNF (item 2), simulate the
   **remaining** laps 10k times → live win/podium/points probs.
3. **Backtest vs Polymarket CLOB** `prices-history` (we already ingest this in
   `app/etl/polymarket.py`). For each 2024-25 race with coverage, align our lap-indexed
   live probs to price timestamps; around each race-control event, compute **lead/lag** and
   **CLV** (our prob at t vs market price at t+Δ). Pre-register Δ and the event list.

**Honest verdict: signal, but gated.** The *mechanism* (slow thin market + a fast fair-
price engine) is the most defensible edge we have. The *risk*: Polymarket liquidity may be
too thin to realize it, and true live needs paid OpenF1/SignalR. So **build the offline-
replay CLV backtest first** (free, leak-controllable). If our live prob demonstrably leads
the market around cautions on 2024-25 replays, *that result alone* justifies the ~€10/mo
live feed. If it doesn't lead, we've cheaply killed the only edge thesis — also a win.

**Sources:** [in-play football martingale pricing (arXiv 1811.03931)](https://arxiv.org/pdf/1811.03931);
[state-space in-game betting sentiment + VAEP (arXiv 2202.10085)](https://arxiv.org/pdf/2202.10085);
[VAEP framework, KU Leuven](https://dtai.cs.kuleuven.be/sports/vaep/);
[F1 in-play lag, f1bettips](https://f1bettips.com/f1-live-betting-tactics/);
SIG/Nellie Analytics in-game quant unit ([Market Making in Sports Betting](https://navnoorbawa.substack.com/p/market-making-in-sports-betting-how)).

---

## 2. Survival / hazard model for DNF and time-to-event

**Novelty (vs our work):** Real and useful. Today the sim samples DNFs from a **flat,
literature-derived rate** (TUM 2014-19). A survival model makes the DNF hazard
**lap-varying and covariate-dependent** — and the same machinery gives **time-to-next-
caution** and (stretch) **time-to-overtake**. We have never modeled reliability/attrition
as a hazard.

**Promise & in-play fit:** High signal-to-effort. DNFs are a *huge* driver of prop
outcomes (top-6, points-finish, podium-without-favourite) and of in-play swings — a
contender retiring is exactly the kind of jump the WPA model (item 1) must price. A
discrete-time hazard is also trivially **live-updatable**: each completed lap that a car
survives updates its conditional survival.

**Concrete sketch on our data:**
- **Event data from Jolpica:** results include a `status` field (Finished / +N Laps /
  Accident / Engine / Gearbox / Collision / Hydraulics …). Code each car-race as
  censored (finished) or event-at-lap-*k* (DNF), with cause class (mechanical vs
  collision — they have different covariates).
- **Discrete-time hazard (cleaner than Cox at n≈85):** logistic regression of
  `P(DNF on lap k | survived to k)` on a *tiny* covariate set to avoid overfit:
  `lap_fraction` (early-race collision risk vs late-race mechanical), `is_SC_restart`
  (restarts spike incidents), `grid_position`/`pack_density` (midfield = more contact),
  `team_reliability_prior` (constructor random effect, regularized — car dominates here
  too), and maybe `track_attrition_rate`. Fit in `statsmodels`/`scikit-survival`/`lifelines`
  on Polars→numpy. **Pre-register the covariate list; ≤5 terms.**
- **Plug into the sim:** replace the flat DNF draw with `hazard(lap, covariates)`; the
  cause class routes to "instant retire" vs "limp to garage." Feeds props directly and
  the live model's jump intensity.
- **Validation:** forward-chained Brier/log-loss on per-race DNF counts and identities;
  compare calibration vs the flat-rate baseline. Watch out: F1 reliability has a strong
  **era trend** (modern cars finish far more often) — include season as a smooth term or
  fit era-relative.

**Honest verdict: signal.** Cheap, robust if kept small, and it improves *two* products at
once (props + in-play). The trap is over-parameterizing per-driver/per-component on 85
races — resist; regularize hard toward the constructor mean.

**Sources:** [Cox proportional hazards overview, GeeksforGeeks](https://www.geeksforgeeks.org/data-science/cox-proportional-hazards-model/);
[scikit-survival predictions guide](https://scikit-survival.readthedocs.io/en/stable/user_guide/understanding_predictions.html);
[Reliability prediction via Cox PH (d-nb)](https://d-nb.info/1026053943/34);
[Proportional hazards model, Wikipedia](https://en.wikipedia.org/wiki/Proportional_hazards_model).
(No public F1-DNF survival model found — a genuine gap we'd be filling.)

---

## 3. Regime-switching (HMM / Markov-switching) race-state layer

**Novelty (vs our work):** Our sim *samples* safety cars from empirical distributions but
has no notion of a **latent race regime** that you **infer from data and condition on**.
That inference step is new for us.

**Promise & in-play fit:** Essential *plumbing* for item 1, but a **gimmick if mis-aimed.**
The honest distinction:
- **Gimmick:** trying to *forecast* "will there be a safety car in the next 10 laps" far
  ahead from telemetry. Cautions are near-Poisson shocks; long-horizon prediction is mostly
  noise and will overfit on 85 races.
- **Signal:** a fast **state classifier/filter** that decides *right now* which regime the
  race is in (Green / SC / VSC / Red / Wet) and lets every downstream rate (deg, pace
  spread, hazard, overtake prob) **switch** to regime-specific values. Under SC the field
  compresses, pit-loss collapses, deg pauses — conditioning on the regime is where the value
  is, and it's exactly what makes the in-play fair price jump correctly.

**Concrete sketch on our data:**
- **Observed regime, mostly:** FastF1 `track_status` and race-control messages give SC/VSC/
  red/green almost directly, and rain via `Weather` (`Rainfall`, `TrackTemp`). So this is
  largely a **conditioning layer over an observed state**, not a hard latent-state inference
  problem — which is good (less to overfit).
- **Where the HMM earns its keep:** the *grey zones* — "is this a degrading-tyre regime or a
  wet-track regime?", "has the race entered a high-attrition phase?" Fit a small
  **Gaussian-HMM** (`hmmlearn`) on per-lap features (field-median lap delta, lap-time
  variance across field, pit-rate) with 3-4 states to *label historical laps* with a regime;
  use those labels to estimate **regime-conditional** deg/pace/hazard params for the sim.
- **Transition matrix** estimated from labeled laps gives the sim realistic regime dynamics
  (SC→green→maybe-another-SC), replacing hand-set durations.

**Honest verdict: signal as plumbing, gimmick as a forecaster.** Build it as the
state-conditioning backbone of the in-play sim (item 1). Do **not** market a "safety-car
predictor."

**Sources:** [Regime-switching IDM for car-following (arXiv 2506.14762)](https://arxiv.org/pdf/2506.14762);
[HMM for crash prediction (arXiv 2212.12011)](https://arxiv.org/pdf/2212.12011);
[HMM regime detection (QuantConnect)](https://www.quantconnect.com/docs/v2/research-environment/applying-research/hidden-markov-models);
[asset-independent regime-switching (arXiv 2107.05535)](https://arxiv.org/pdf/2107.05535).

---

## 4. Car-DNA: factor decomposition of car performance from telemetry

**Novelty (vs our work):** New. Our pace estimates are **scalar** (one pace number per
car/driver). We have never decomposed performance into **interpretable factors** —
straight-line/power vs high-speed-aero vs low-speed-mechanical vs braking vs tyre-handling.
This is the golf strokes-gained-by-category analog and the public mirror of **AWS's Car
Performance Scores** (F1 derives power/aero/braking/tyre breakdowns from telemetry:
[AWS F1 insights](https://aws.amazon.com/sports/f1/),
[Rob Smedley on AWS braking performance](https://www.formula1.com/en/latest/article/rob-smedley-explains-how-the-new-aws-braking-performance-graphic-works-and.3A8cnQLZGXFbMjCR2fFBnB)).
Our telemetry (`speed_st` traps + full FastF1 speed/throttle/brake/gear/DRS traces) is
**captured but unused** — this is the obvious thing to do with it.

**Promise & in-play fit:** Promising as **interpretable features**, not as a standalone
predictor. The car is 88% of variance — a *decomposed* car signal could (a) predict which
**track type** suits which car (a props edge: H2H and top-6 on power tracks vs downforce
tracks), (b) feed the pace model with richer-than-scalar inputs, and (c) power a genuinely
impressive **Explainer** ("Ferrari gains 0.3s in low-speed corners but loses 0.2s on the
straights here"). In-play relevance is indirect (better priors), not direct.

**Concrete sketch on our data:**
1. **Segment the track by corner type.** FastF1 gives distance-aligned speed traces and a
   circuit corner list. Classify each track segment as straight / high-speed corner
   (>~220 km/h) / low-speed corner / braking zone — the 220 km/h corner-vs-straight split is
   a known telemetry heuristic
   ([Radicalbit F1 telemetry](https://radicalbit.medium.com/f1-modeling-an-interesting-use-case-for-telemetry-sports-bdfd0cef0801)).
2. **Per car/session, compute factor deltas vs field median:** speed-trap speed (power/drag),
   min-corner-speed in high-speed corners (aero), min-corner-speed in low-speed corners
   (mechanical grip), braking distance/decel from speed-trace gradient
   ([AWS braking method](https://www.formula1.com/en/latest/article/rob-smedley-explains-how-the-new-aws-braking-performance-graphic-works-and.3A8cnQLZGXFbMjCR2fFBnB)),
   and a tyre/deg slope we already estimate.
3. **Reduce to 3-4 orthogonal factors** (PCA on the per-segment deltas;
   [PCA on F1 telemetry](https://theparttimeanalyst.wordpress.com/2018/06/27/f1-circuit-cluster-analysis-part-1/)).
   Express each circuit as a **factor-demand profile** (Monza = power-heavy; Monaco =
   low-speed + braking). Predicted suitability = car factor profile · circuit demand.
4. **Use as features** in the PL/Kalman pace model and as Explainer content; **backtest the
   suitability score's incremental value** on track-specific props, forward-chained.

**Honest verdict: signal as a feature, gimmick if oversold.** At n≈85 the overfit risk is
real — keep to **3-4 factors**, regularize, and judge it strictly on *incremental* prop
calibration over the scalar-pace baseline, not on a pretty chart. The Explainer value alone
(portfolio appeal) may justify it even if the predictive lift is marginal — but label that
honestly.

**Sources:** [AWS F1 insights](https://aws.amazon.com/sports/f1/);
[AWS Braking Performance (Smedley)](https://www.formula1.com/en/latest/article/rob-smedley-explains-how-the-new-aws-braking-performance-graphic-works-and.3A8cnQLZGXFbMjCR2fFBnB);
[How F1 insights are powered by AWS](https://dev.to/aws-builders/how-formula-1-insights-are-powered-by-aws-3ndb);
[F1 telemetry corner-zone split (Radicalbit)](https://radicalbit.medium.com/f1-modeling-an-interesting-use-case-for-telemetry-sports-bdfd0cef0801);
[F1 circuit cluster analysis / PCA](https://theparttimeanalyst.wordpress.com/2018/06/27/f1-circuit-cluster-analysis-part-1/);
[driver behavior modeling with F1 telemetry](https://f1briefing.com/driver-behavior-modeling-with-f1-telemetry/).

---

## 5. Time-rank duality — a cheaper car/driver split

**Novelty (vs our work):** A specific, citable *technique* we haven't used. Fry, Brighton &
Fanzon (2024, *Economics Letters* 237), *Faster identification of faster Formula 1 drivers
via time-rank duality* ([arXiv 2312.14637](https://arxiv.org/abs/2312.14637),
[code](https://www.silviofanzon.com/F1-Paper-Code/)) prove an **equivalence** between (a) a
probabilistic model where finishing *times* are exponential and (b) **econometric modelling
of the ranks** (the rank-ordered/Plackett-Luce family we already adopted). Equating the two
race-winning-probability expressions yields equivalent parametrizations and a **much less
data-intensive** way to disentangle **driver vs car** effects — and that small-sample
efficiency is *exactly* our binding constraint.

**Promise & in-play fit:** It's a back-end upgrade, not a live model. It drops straight into
the PL/Harville stack from doc 09 and gives a more **statistically efficient** car/driver
split on ~85 races (their headline: cleanly recovers that Verstappen/Alonso outperform their
cars). Better driver-vs-car separation improves *every* downstream prob, including the
in-play prior.

**Concrete sketch on our data:** Implement the exponential-times parametrization alongside
our PL fit (their R code is the reference; port to Polars/numpy). Cross-check that both give
the same win probs (the duality is the unit test). Use the time-domain form to get fast,
low-variance driver offsets and car strengths to seed the Kalman/PL pace model, then proceed
through discounted-Harville + Benter blend exactly as planned.

**Honest verdict: signal, low-risk.** Cheap, rigorous, peer-reviewed, and aimed squarely at
our small-sample problem. Easy yes as part of building the pace back-end.

**Sources:** [arXiv 2312.14637](https://arxiv.org/abs/2312.14637);
[Economics Letters listing](https://ideas.repec.org/a/eee/ecolet/v237y2024ics016517652400154x.html);
[author code + data](https://www.silviofanzon.com/F1-Paper-Code/).

---

## 6. Particle filter (Sequential Monte Carlo) for live state — defer

**Novelty/promise:** A particle filter is the "correct" Bayesian filter for a **nonlinear,
non-Gaussian, multimodal** live state (positions, gaps, tyre, regime) — strictly more
general than our Kalman filter
([Particle filter, Wikipedia](https://en.wikipedia.org/wiki/Particle_filter);
[SMC unified review](https://www.annualreviews.org/doi/10.1146/annurev-control-042920-015119)).

**Why defer:** For in-play F1 our state is *largely observed* (positions, gaps, tyre age,
track status come straight from timing) — the hard part is the *forward* simulation, which
our MC sim already does. Re-seeding the MC sim from the observed live state (item 1) is a
particle-filter-in-spirit at a fraction of the engineering and tuning cost, and far less
likely to be fiddly under latency. Revisit **only** if we find the live posterior is
genuinely multimodal (e.g. "undercut works vs doesn't" branching) in a way the MC re-seed
can't capture.

**Verdict: defer / over-engineering for now.**

---

## 7. Optimal-stopping / DP + game-theory pit strategy — product, not edge

**Novelty/promise:** Pit timing as **optimal stopping / dynamic programming**, and the rival
interaction as a **zero-sum Stackelberg game** (leader decides first each lap), is well-posed
and recent: Optimizing Pit Stop Strategies in F1 with DP + Game Theory (*EJOR* 319(3), 2024,
[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0377221724005484),
[summary](https://ideas.repec.org/a/eee/ejores/v319y2024i3p908-919.html)). Notable finding:
**maximizing win-probability (not gap) makes optimal play more risk-taking**, and racing
strategically vs a naive rival lifts win odds **>15%**. Heilmeier's VSE (FFNN+LSTM) and recent
RL pit-strategy work ([Frontiers/PMC deep-learning pit support](https://pmc.ncbi.nlm.nih.gov/articles/PMC12626961/),
[Explainable RL for F1 strategy, arXiv 2501.04068](https://arxiv.org/html/2501.04068v1)) are
adjacent.

**Why it's not our edge:** It optimizes *the team's* decision; it doesn't price the *market*.
Its real home is the **Strategy Lab / Explainer** ("optimal vs actual undercut window"), where
it's a strong, interpretable, portfolio-grade feature. The undercut/overcut and SC-pit
mechanics also *inform* the in-play sim's transitions.

**Verdict: build for the product, don't expect CLV from it.**

---

## Gimmicks / traps to avoid

- **A long-horizon "safety-car predictor."** Cautions are near-Poisson shocks; predicting them
  many laps ahead from telemetry on 85 races is noise-fitting. *Detect and condition*, don't
  *forecast* (item 3).
- **Per-driver/per-component reliability params.** 85 races can't support a hazard model with
  dozens of driver×component terms. Regularize hard to the constructor mean (item 2).
- **>4 telemetry factors / a deep net on telemetry.** The 88/12 car/driver split and tiny
  sample mean a fancy telemetry model will memorize sessions. Keep Car-DNA to 3-4 orthogonal,
  physically-named factors and judge on *incremental* calibration (item 4).
- **Claiming an outright-market edge.** Settled: the pre-race outright is efficient (~0.95
  corr). Any "we beat the line" result is leakage or in-sample. Our honest targets are CLV
  in-play and prop calibration.
- **Reading the Polymarket pre-race as live.** Gamma `startDate` = market-open, not race-start;
  thin liquidity means single trades move the price. Use Jolpica race-start time and last
  `t ≤ start` (already handled in `app/etl/polymarket.py`) — and don't mistake a thin-book
  wobble for signal.
- **Live-data leakage in the in-play backtest.** When replaying 2024-25 to test WPA lead/lag,
  the re-seed must use *only* information available at lap *L* (no end-of-race pace, no future
  weather). This is the same forward-chaining discipline as doc 09, applied within a race.
- **RL pit-strategy as a betting edge.** It's a planning tool; it doesn't price the market.
  Ship it in the Strategy Lab, not as an alpha claim.
- **Particle-filter gold-plating.** Don't build SMC machinery when an MC re-seed from observed
  state suffices (item 6).

---

## Closing recommendation — what to prototype next (ordered)

1. **In-play WPA + offline-replay CLV backtest (items 1+3, with item 2 folded in).**
   The whole edge thesis lives here, and it's testable **for free** today: reconstruct
   `live_state(lap)` from FastF1, re-seed the existing MC sim under the detected regime with
   a hazard-driven DNF, produce lap-indexed live win probs, and measure **lead/lag and CLV
   vs the Polymarket CLOB** around timestamped race-control events on 2024-25. If our prob
   leads the market into cautions, that single result justifies the ~€10/mo OpenF1 live feed.
   If not, we've cheaply falsified the only edge thesis — equally valuable.
2. **Survival/hazard DNF model (item 2)** as the first concrete upgrade *inside* step 1, and
   independently as a **props** improver (top-6 / points / podium-without-favourite). Small,
   robust, dual-purpose. Pre-register ≤5 covariates; regularize to the constructor mean.
3. **Time-rank-duality car/driver split (item 5)** when building the PL/Kalman pace back-end —
   a cheap, peer-reviewed, small-sample-friendly upgrade that improves the prior feeding both
   the pre-race props and the in-play seed.

Car-DNA telemetry factors (item 4) and the DP/game-theory pit optimizer (item 7) are the next
**product/Explainer** investments (portfolio appeal, track-suitability props) but should not be
expected to produce market edge on their own. The particle filter (6) stays deferred.
