# 20 — Deterministic lap-time & tyre-degradation physics from telemetry (research + plan)

A deep, fact-checked survey (103 sub-agents, 21 sources fetched, 25 claims adversarially
verified — 23 confirmed, 2 killed) of **physics-based, deterministic** F1 lap-time and
tyre-degradation modeling, and exactly which pieces are buildable on our **free FastF1**
data. This is the **physics-engine lane** — distinct from the betting-edge lane (briefs
07–19), which is settled-null. Telemetry's genuine home is a better deterministic engine
(Strategy Lab, Predictor pace, Explainer), not a market edge.

> Source-quality note: the lap-time and QSS findings rest on peer-reviewed papers **plus the
> authors' own open-source repos**, unanimously verified (3-0). The wear-physics tier is
> medium-confidence: the laws are well-sourced but need data we lack. Two claims were
> **refuted 0-3** and are flagged below so we don't repeat them.

---

## The three tiers (two are implementable on free FastF1)

| Tier | What | FastF1? | Verdict |
|---|---|---|---|
| **1. Lap-wise additive sim** (Heilmeier 2020 / TUMFTM) | lap time = pace + fuel + per-compound tyre-age degradation + car + driver | **Yes** — fit from lap/sector timing alone | **Adopt + re-fit** (we already have a variant) |
| **2. QSS velocity profile on a racing line** (OpenLAP, TUMFTM, Brayshaw-Harrison; Perantoni-Limebeer is the OC gold-standard) | forward-backward velocity profile over a GGV envelope; min-curvature line ≈ min-time | **Partly** — curvature/speed are telemetry INPUTS we have; the GGV envelope must be estimated | **Add a first-cut** (corner/braking terms) |
| **3. Physics wear/grip** (Pacejka MF, MF-evo, Reye energy law) | tie slip/load/temperature to grip loss | **No** — needs tyre temp, normal load, slip velocity we DON'T have | **Proxy only** (coarse energy feature), don't calibrate |

---

## Tier 1 — Lap-wise additive decomposition (the implementable core)

**Governing form** (Heilmeier et al. 2020, *Applied Sciences* 10(12):4229; TUMFTM
`race-simulation`):

```
t_lap(driver, compound, age, lap) = t_q                      # qualifying base pace
                                   + t_gap_racepace           # race-vs-quali pace gap
                                   + Δt_tyre(compound, age)   # per-compound degradation
                                   + m_fuel(lap) · t_lap_sens_mass   # fuel-mass loss
                                   + t_car + t_driver         # constructor / driver offsets
```

**Per-compound tyre degradation** — four closed forms (`calc_tire_degradation.py`), fit per
compound; Heilmeier found the **logarithmic** best on 2014–2019:
- linear:    `Δt = k0 + k1·age`
- quadratic: `Δt = k0 + k1·age + k2·age²`
- cubic:     `Δt = k0 + k1·age + k2·age² + k3·age³`
- log:       `Δt = k0 + k1·log(k2·age + 1)`

**Fuel:** `Δt_fuel = m_fuel · t_lap_sens_mass`, fuel mass falling ~linearly with lap
(matches our existing `WEAR_FUEL_SENSITIVITY` idea). All coefficients fit from **lap/sector
timing only — no tyre temp/slip/load** → fully re-fittable on free FastF1. TUMFTM shipped
121-race parameter files (2014–2019); **we must re-fit for the 2022+ ground-effect era**
(same data type, so mechanical).

**Where we stand:** our `engine/tyres.py` already does a per-circuit *3-phase* degradation fit
from stint residuals. The upgrade is to **add the Heilmeier per-compound closed forms**,
fit on our stint residuals, and **test which form wins in 2022+** (open question: is log
still best?). See the plan below.

---

## Tier 2 — QSS velocity profile on a min-curvature line (corner/braking terms)

**Method** (OpenLAP + OpenTRACK; TUMFTM `laptime-simulation` & `global_racetrajectory_optimization`;
Brayshaw-Harrison 2005 *Proc. IMechE* 7-DOF GG speed diagram):
1. **Track model**: discretize the lap into segments with curvature κ(s) (from distance +
   speed + lateral acceleration, or X/Y position — **all FastF1 channels**).
2. **GGV envelope**: max lateral accel from a friction ellipse; max longitudinal accel
   `ax_max = F_x_drivetrain / m_veh` (power/traction limited) and braking limit; aero is
   quadratic in speed: downforce `F_az = ½·C_l·ρ·A·u²`, drag `F_ax = −½·C_d·ρ·A·u²`
   (nominal generic-F1 `C_l≈3.0, C_d≈0.9, A≈1.5, ρ≈1.2`).
3. **Forward-backward integration**: apex speeds `v=√(a_lat,max/κ)` at curvature peaks, then
   integrate forward (accel-limited) and backward (brake-limited) and take the min → a
   deterministic velocity profile → lap time by `∫ ds/v`.
4. **Racing line**: the **minimum-curvature line ≈ minimum-time** in corners (QP-solvable;
   the min-time line is only ~0.42–0.92 s/lap faster) — so min-curvature is a cheap, robust
   proxy for the optimal line.

**Perantoni-Limebeer 2014** (*Vehicle System Dynamics* 52(5)) is the OC gold standard
(direct transcription → NLP via IPOPT, minimize `∫ Sf⁻¹`; long/lat/yaw DOF, load transfer,
four-wheel braking, LSD, Pacejka tyre) — too heavyweight to run, but it **defines the term
structure** the QSS approximates.

**FastF1 feasibility:** curvature, speed, lateral accel, X/Y, distance are all present at
~10 Hz. The **GGV envelope must be estimated** (we don't have mass/grip/aero directly) — but
it can be *fit from observed telemetry* (the empirical g-g envelope a car actually uses per
circuit). This yields **corner-by-corner time decomposition** (apex-speed deficit, braking
zones, traction zones) — exactly the "driving inputs → time" decomposition, and great
Explainer content.

---

## Tier 3 — Physics wear/grip (NOT calibratable on free data)

- **Pacejka Magic Formula** (original): temperature- and wear-naive.
- **MF-evo** (Farroni/Sakhnevych 2022, *Simul. Model. Pract. Theory*): ties MF friction &
  stiffness to **layered tyre thermal state + wear** — significant, but needs tyre temps.
- **Radrizzani** (PMC12915245): couples a wear index `Im = m/m0` to MF coefficients
  (μ_λ, μ_α, C_λ, C_α).
- **Reye energy-dissipation law** (verified 2-1, idealized): `dV = k_Reye · ∫ μ·p·v_slip dt`
  — wear ∝ frictional energy. Physically sound but needs **slip velocity and normal
  pressure**, neither in FastF1.

**Hard boundary:** every wear/grip-physics model needs **tyre temperature, normal load, and
slip velocity** — none in free FastF1. So these can only be **coarsely proxied**, never
calibrated. The honest proxy is a per-lap **energy feature** `∫|a_lat|·v ds` or
`∫|a_long|·v ds` (from Speed + X/Y accelerations) as an *optional* covariate on the tyre-age
polynomial — to be tested, not assumed (open question #1).

### Refuted (do NOT repeat) — verified 0-3
- A frictional-power **power-law** wear form `ṁ = k1·ẇ^k2` (Braghin/Radrizzani) with exponent
  k2≈1–3 as a fit-from-lap-deltas law — **refuted**; not a free-data-fittable law.
- That TUMFTM `laptime-simulation` is the *exact* implementation of Heilmeier 2019 EVER —
  **refuted**; treat the repo as adoptable prior art on its README terms, not a paper mirror.

---

## Open questions the research leaves us (these become our validation gates)
1. Does a FastF1 **energy-proxy** (`∫|a_lat|·v`, `∫|a_long|·v` per lap) correlate with observed
   per-stint degradation slope **beyond** the tyre-age polynomial?
2. How accurately can **curvature + racing line** be reconstructed from ~10 Hz X/Y + speed,
   and does a QSS velocity profile add predictive skill over the lap-wise model?
3. Realistic **per-compound (k0,k1,k2)** ranges on 2022+ FastF1 stints — is **log** still the
   best-fitting form (Heilmeier's 2014–2019 finding)?
4. Can a **temperature proxy** from single-station air/track temp + driving-intensity recover
   any MF-evo thermal sensitivity, or is single-station too coarse (brief 11 says coarse)?

---

## Concrete plan for F1Predict (what we build, in order)

**A. Re-fit per-compound tyre degradation on stint residuals** *(implemented — `app/etl/tyre_degradation.py`)*.
Extract green, accurate, dry stint laps; fuel-correct; per compound fit the four Heilmeier
closed forms to age→lap-time-loss; select by AIC/RMSE; report coefficients + which form wins
in the 2022+ era (answers open Q3). Keep it a documented artifact (`data/tyre_degradation.json`)
feeding the Explainer + a candidate to sharpen the sim's tyre model.

**B. QSS corner/braking terms on a min-curvature line** *(first cut — `app/engine/qss.py`)*.
Reconstruct curvature κ(s) from a fastest lap's X/Y + speed; fit the car's empirical g-g
envelope; forward-backward integrate a velocity profile; decompose the lap into corner/
braking/traction time. Validate the reconstruction against the actual telemetry speed trace
(answers open Q2). Explainer-first; predictive use only if it beats the lap-wise model.

**C. Energy-proxy wear feature** *(optional, gated)*. Add `∫|a_lat|·v` per lap as a covariate;
keep only if it beats the tyre-age polynomial forward-chained (open Q1). Do **not** attempt
MF-evo/Reye calibration — we lack the inputs.

---

## Results — what we built and measured (this session)

**A. Per-compound degradation re-fit on 2022+ stint residuals** (`app/etl/tyre_degradation.py`,
`data/tyre_degradation.json`). Pooled green/accurate/dry stint laps, fuel-corrected,
stint-relative; **age-binned medians** (per-lap residuals are swamped by ~±2.9 s traffic
noise — binning + median is essential) fit to all four closed forms, AIC-selected.
**Headline finding (answers open Q3): the logarithmic form is NOT best for the
ground-effect era.** SOFT and MEDIUM are best-fit **linear**, HARD **quadratic** — Heilmeier's
2014–2019 "log is best" does **not** carry to 2022+. Observed in-race degradation vs a fresh
tyre is gentle (SOFT ~0.012, MEDIUM ~0.017 s/lap; HARD accelerating to ~0.9 s by age 30) —
this is *managed, in-traffic* degradation, not theoretical max. Caveat: pooled across
circuits, and soft high-age data is partly censored (softs run short), so treat the absolute
magnitudes as era-typical, not circuit-exact. A documented artifact + Explainer content;
**not yet wired into the sim's per-circuit 3-phase model** (it's a cross-check / candidate).

**B. QSS velocity profile on the driven line** (`app/engine/qss.py`, `data/qss_profiles.json`).
Curvature κ(s) from the fastest lap's X/Y; empirical g-g envelope fit from the car's own
telemetry (98th-pctl lateral/forward/brake accel); forward-backward velocity profile.
**Validation (answers open Q2): the reconstructed profile tracks the real speed trace's SHAPE
(corr 0.80–0.92) but systematically overestimates pace** — QSS lap times come out ~20–30 %
fast (e.g. Monaco 49.6 s vs 70.1 s actual). Root cause: curvature from ~10 Hz X/Y
under-resolves tight corners, so apex speeds are too high; a limit-based profile also assumes
the car is at the grip limit in every corner. **Verdict: a useful corner/straight *decomposition*
and shape tool (Explainer), NOT a lap-time predictor on free data** — accurate lap time needs
the true racing-line geometry / finer position data we don't have. Not wired into the predictor.

**Net:** Tier 1 (per-compound degradation) is the genuinely usable free-data win and produced a
real era finding; Tier 2 (QSS) is honest-but-limited on free data — kept as an Explainer
decomposition; Tier 3 (physics wear) remains un-calibratable (no slip/load/temp). Both new
artifacts are served for the Methodology page (`GET /tyres/degradation`, `GET /circuits/qss`).

## Sources (verified)
Primary: Heilmeier et al. 2020 [Applied Sciences 10(12):4229](https://www.mdpi.com/2076-3417/10/12/4229)
+ [TUMFTM/race-simulation](https://github.com/TUMFTM/race-simulation);
Perantoni & Limebeer 2014 [VSD 52(5)](https://www.tandfonline.com/doi/abs/10.1080/00423114.2014.889315);
Brayshaw & Harrison 2005 [Proc. IMechE](https://journals.sagepub.com/doi/10.1243/095440705X11211);
[OpenLAP](https://github.com/mc12027/OpenLAP-Lap-Time-Simulator);
[TUMFTM/global_racetrajectory_optimization](https://github.com/TUMFTM/global_racetrajectory_optimization),
[TUMFTM/laptime-simulation](https://github.com/TUMFTM/laptime-simulation);
friction-ellipse/racing-line [arXiv 2504.10225](https://arxiv.org/pdf/2504.10225);
MF-evo [Farroni/Sakhnevych, SIMPAT](https://www.sciencedirect.com/science/article/abs/pii/S1569190X22000247),
[Springer thermal layers](https://link.springer.com/chapter/10.1007/978-3-030-41057-5_88),
Radrizzani/Reye [PMC12915245](https://pmc.ncbi.nlm.nih.gov/articles/PMC12915245/).
Practitioner: [driver61 racing line](https://driver61.com/uni/racing-line/),
[drracing lap-time sim](https://drracing.wordpress.com/2019/10/18/lap-time-simulation-the-matlab-awakens/),
[FastF1 telemetry discussion](https://github.com/theOehrly/Fast-F1/discussions/613).
Internal: brief 01 (lap-time model), brief 11 (single-station weather), `app/engine/tyres.py`,
`app/etl/calibrate.py`.
