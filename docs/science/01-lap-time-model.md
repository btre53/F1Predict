# 01 — The Lap-Time Model

How F1Predict turns physics and statistics into a single predicted lap time.

---

## 1. Lap-time decomposition

We model an observed race lap time as an additive sum of an interpretable physics
baseline, a machine-learned residual, and irreducible execution noise:

```
t_lap(driver d, lap k) = f_physics(state)  +  g_ML(features)  +  ε
```

- `f_physics` — deterministic, well-understood effects (fuel mass, gross tyre
  trend, base circuit pace).
- `g_ML` — a gradient-boosted model (LightGBM) that learns the *systematic but
  hard-to-physically-model* leftover (corner-specific traffic, driver style,
  micro track-evolution, weather transitions).
- `ε` — random lap-to-lap "execution noise" (driver mistakes, lock-ups, traffic).

This "physics baseline + stochastic noise" split is the canonical backbone of
every published F1 race simulator (Heilmeier/TUM). Inserting a learned residual
`g_ML` between them is a legitimate **gray-box / residual-learning** pattern — a
design choice, not a settled convention, but well supported.

**How we separate deterministic from residual:** take race/long-run laps, remove
the two dominant confounders first — **fuel burn and tyre age** — by regression;
what remains is car/driver pace offsets plus residual noise.

> **Explainer:** *A car's lap time is mostly predictable physics: heavy fuel and
> worn tyres make it slower in known ways. We model those directly, let a
> statistical layer learn the leftover patterns, then treat whatever remains as
> random "execution noise." Stripping out the predictable parts is what lets us
> compare a driver's true pace fairly.*

Sources: [TUMFTM/race-simulation](https://github.com/TUMFTM/race-simulation),
[Heilmeier et al. 2020](https://www.mdpi.com/2076-3417/10/12/4229),
[State-Space Tyre Degradation, arXiv 2512.00640](https://arxiv.org/html/2512.00640v1).

---

## 2. Fuel-corrected lap time

Added fuel mass slows the car roughly linearly. Industry rule of thumb:
**~0.3 s/lap per 10 kg ≈ 0.03 s/kg**, in a 0.025–0.040 band, track-dependent.

```
fuel_mass(lap) ≈ fuel_start − burn_per_lap × lap
t_fuel(lap)    = k_fuel × fuel_mass(lap)              # k_fuel ≈ 0.03 s/kg

# Fuel-correct an observed lap to zero-fuel-equivalent pace:
t_corrected = t_observed − k_fuel × fuel_mass(lap)
```

| Parameter | Typical | Units | Notes |
|---|---|---|---|
| Fuel sensitivity `k_fuel` | 0.030 (0.025–0.040) | s/kg | ≈0.3 s per 10 kg; track-dependent |
| Max race fuel | 110 | kg | 2019–2025 ceiling; **~70 kg in 2026** |
| Fuel burn per lap | ~1.5–2.2 (avg ~1.6–1.8) | kg/lap | higher on long-lap tracks (Spa, Silverstone) |
| Total start fuel penalty | ~3.0–3.3 | s/lap | 110 kg × 0.03 |

⚠ **Correction:** the original doc's global `k_fuel`, `burn_per_lap`, and
`base_lap` constants are fine *as averages* but should be **circuit-specific**.

> **Explainer:** *An F1 car starts a race carrying up to ~100 kg of fuel and
> burns it off, getting lighter and faster — worth roughly 0.03 seconds per lap
> per kilogram. To compare true pace fairly we "fuel-correct" lap times by adding
> back what the heavy fuel cost, revealing how the tyres are actually wearing.*

---

## 3. Tyre degradation — the three-phase curve

A stint has three regimes: **(1) thermal warm-up** (cold tyre underperforms until
it reaches its window), **(2) linear wear** (steady grip loss), **(3) the cliff**
(sharp nonlinear collapse). Our phenomenological model is one basis function per
regime:

```
t_deg(age) =  θ1·exp(−θ2·age)               # Phase 1: warm-up, decays away
            + θ3·age                         # Phase 2: linear wear
            + θ4 / (1 + exp(−θ5·(age−θ6)))   # Phase 3: logistic cliff
```

| Quantity | Typical | Units |
|---|---|---|
| Soft vs Hard pace delta | ~0.6–1.0 | s/lap |
| Medium vs Hard delta | ~0.3–0.6 | s/lap |
| Hard deg rate (linear `θ3`) | ~0.05 | s/lap |
| Medium deg rate | ~0.05–0.06 | s/lap |
| Soft deg rate | ~0.08–0.15+ | s/lap |
| Optimal slick temp window | ~90–110 | °C |

⚠ **Correction / caveat:** the 6-parameter form is scientifically sound but
**over-parameterized for typical data** — clean long-runs rarely extend past the
cliff, so `θ4–θ6` are weakly identified. **Fit it with priors/regularization** (a
Bayesian or bounded fit) and **fall back to linear/log when data is sparse**
(Heilmeier's own guidance). Hotter tracks accelerate deg and bring the cliff
earlier.

**Fitting procedure:** take FP long runs → fuel-correct each lap → regress
fuel-corrected lap time on tyre age per compound. Slope = linear deg rate;
intercept vs reference compound = pace delta; late-stint upturn = cliff.

> **Explainer:** *New tyres start slightly slow until they heat into their grip
> window, then lose time steadily as they wear — about 0.05 s/lap for a hard —
> until they hit a "cliff" and fall apart over a couple of laps. Softer tyres are
> faster but cliff sooner; hotter tracks speed up the decline. We learn each
> tyre's wear curve from practice long runs.*

---

## 4. Driver execution noise — why it's skewed

⚠ **Correction:** the original doc samples symmetric Gaussian noise. Use a
**positively-skewed t-distribution** instead. Drivers are given target lap times;
a clean lap clusters near target, but errors are asymmetric — you can lose a lot
of time (lock-up, traffic, going off) but you essentially **cannot go much faster
than the optimal lap**. So the residual has a short left tail and a long right
(slow) tail; the heavy `t`-tails capture occasional big blips.

| Parameter | Value | Units |
|---|---|---|
| Per-lap execution σ | ~0.20–0.35 (driver-specific) | s |
| Distribution | skewed-t (positive skew), df≈2 | — |
| Inflate in traffic/wet | yes | — |

Empirically the skewed-t beats a symmetric baseline (RMSPE 1.082 vs 1.520; CRPS
0.202 vs 0.324 in the state-space paper). The doc's ~350 ms σ is realistic *once
traffic/wet/mistakes are folded in*; clean-lap σ is closer to ~0.2–0.3 s.

> **Explainer:** *Drivers make mistakes, but the mistakes are lopsided — you can
> lose a second locking up a brake, but you can't gain a second over a perfect
> lap. So we add randomness that's "skewed": small losses common, occasional big
> ones, almost never a freakishly fast lap.*

---

## 5. Separating driver skill from car performance

Results are dominated by the car: Bayesian analyses attribute ~**85–88%** of
result variance to the constructor. We use a hierarchical additive latent model:

```
pace_offset(driver d, race r) = car_effect(team(d), r)
                              + driver_skill(d, year(r))
                              + ε
```

The key identification lever is **teammate comparison** (same machinery cancels
the car). Methods: Bayesian rank-ordered logit, state-space latent pace, or
teammate-adjusted Elo. Output includes honest **credible intervals** — rank
claims among the elite overlap heavily.

> **Explainer:** *Most of a result comes from the car, not the driver — but we can
> tease them apart. By comparing teammates who share the same car and pooling many
> races in a Bayesian model, we estimate each driver's hidden skill and each car's
> performance separately, with honest uncertainty bands.*

Sources: [arXiv 2203.08489](https://arxiv.org/pdf/2203.08489),
[Adjusting Elo (SIAM)](https://www.siam.org/media/ze4lf1m2/s152289rrr.pdf).

---

## 6. Validation — are our probabilities honest?

The goal is **calibrated probabilities**, not just picking the winner. We score
with proper scoring rules and calibration plots, backtesting on **held-out races
via forward chaining** (train on past, predict future — never random K-fold across
time).

```
Brier   = mean( (p − o)^2 )                     # o ∈ {0,1}; lower better
LogLoss = −mean( o·ln p + (1−o)·ln(1−p) )
CRPS    = ∫ (F_pred(x) − 1{x ≥ obs})^2 dx       # ordinal finishing positions
```

Compare against naive baselines (grid position, market odds). Caveat: ~20–24
races/year ⇒ wide confidence intervals; backtest across multiple seasons.

> **Explainer:** *We don't just check if we picked the winner — we check whether
> our probabilities are honest. Using Brier score, log-loss, and calibration
> charts on past races we held out, we confirm that things we call "30% likely"
> actually happen about 30% of the time.*

Sources: [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html),
[State-Space paper (CRPS)](https://arxiv.org/html/2512.00640v1).
