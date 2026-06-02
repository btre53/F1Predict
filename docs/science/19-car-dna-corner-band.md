# 19 — Car-DNA: Corner-Band Pace Decomposition (task #22): build + validation

Brief 16 §2, built — the owner's flagship anti-brand idea. Not "Ferrari is strong at
Monaco" but **"a car relatively fast in low-speed corners does well at low-speed-corner
circuits."** Decompose each car's qualifying telemetry into its relative speed in
physically-named speed bands; a circuit is a demand profile over those bands; suitability
= car band-factor · circuit demand. A brand-new team inherits its rating from its
*measured factors*, so it generalizes by construction.

Code: `backend/app/models/car_dna.py` (extract + decomposition + validation),
`data/car_dna.parquet` (cached telemetry sample), `GET /cars/dna` (Explainer artifact).

---

## How it's built (all from FastF1 telemetry, qualifying only)

- **Bands** by speed (km/h): low <130, med 130–210, high 210–290, straight >290. The
  ~130/210 corner split is an established telemetry heuristic.
- **Circuit demand** = lap-distance share in each band on the field-fastest lap
  (`get_circuit_info()` not even needed — the speed-vs-distance trace gives it directly).
- **Car band speeds** = mean speed in each band on each driver's own fastest qualifying lap.
- **Shape-normalization (the crux — two stages):** dividing by lap-mean speed is *not
  enough* (a faster, higher-downforce car carries proportionally more speed through every
  band). So: (1) `rel_b = spd_b / lap-mean`; (2) **cross-band demean per car-circuit** →
  a zero-sum profile, so a uniformly-fast car is flat (this is the "WHERE not HOW FAST"
  step); (3) field-net within circuit. The factor is then "where this car's profile
  differs from the field's."
- **Suitability** = leave-one-circuit-out (the car's *general* band DNA from its other
  circuits) · this circuit's demand.

Sample: 2024 qualifying, 12 circuits spanning the corner spectrum (Monaco/Hungary/
Singapore low-speed; Monza/Las Vegas/Baku straight; Silverstone/Spa/Suzuka high-speed),
238 car-circuits, cached (telemetry is ~10 s/session, network-bound).

### The decomposition is real and physically correct
Circuit demand profiles are textbook: **Monaco** 19 % low / 35 % med / 46 % high /
**0 % straight**; **Monza (Italian)** 55 % straight; **Las Vegas** 54 % straight;
**Spain** 52 % high-speed-corner. Per-car DNA (shape-normalized) is mechanistically
sensible: **McLaren (PIA/NOR) and VER relatively strong in low-speed corners, weak on
straights** (2024's high-downforce McLaren — correct); **Alpine/Sauber (OCO/GAS/BOT/ZHO)
the reverse** (low-downforce, straight-line). This is genuine, interpretable car
character extracted from telemetry.

---

## Validation — and the honest result

The gate (brief 16 §2): does the corner-band suitability predict a car's circuit-specific
qualifying deviation **incrementally over scalar pace**, and is it **distinct from the
rejected affinity**?

| check | value | meaning |
|---|---|---|
| `corr(suitability, scalar pace)` | **0.18** | shape-normalization worked (was **0.92** before the cross-band demean — i.e. naive normalization *is* scalar pace in five hats) |
| `corr(suitability, quali deviation)` | **−0.01** | **no incremental predictive signal** over scalar pace |

So once the decomposition is *honestly* purged of scalar pace, the corner-band fit carries
**essentially zero** predictive power for where a car over/under-performs in qualifying
(leave-one-circuit-out, 234 car-circuits). Because it predicts ~nothing, it trivially does
not collapse into the affinity either — it is simply not a predictive feature at this grain.

**Why it disappoints (as brief 16 §2 pre-registered):** (1) the 88/12 car/driver split plus
one season of clean telemetry is a thin, pace-converged sample; (2) qualifying deviation is
dominated by track evolution, tow, fuel/engine modes and sector-specific setup, not a
stable corner-band trait; (3) the very normalization that makes the factor *honest* (not
scalar pace) also strips most of the signal — what's left is small. The brief called this
"the most likely to disappoint," and it did.

---

## Verdict (reframed): KEEP as an Explainer feature — interpretable, not predictive

Per the owner's bar (don't bin mechanistic features): **kept as an Explainer artifact**,
not wired into the predictor. The per-car corner-band radar ("this car gains in slow
corners, loses on the straights here") and the circuit demand profiles are strong,
honest portfolio content — served at `GET /cars/dna`, labelled clearly as *interpretable
but not predictive over scalar pace*. We do **not** add it to the prediction path (no lift,
and it would only add parameters/overfit risk).

### v2 ideas
1. **Multi-season sample** (2022–2025) — more car-circuits, less pace-convergence; re-test
   the incremental claim with real statistical power.
2. **Traction + braking sub-factors** — Δspeed in the first ~100 m after slow-corner apexes
   (traction) and deceleration gradient into heavy braking (braking), per brief 16 §2 — the
   two named factors we have *not* yet measured; they may carry signal the speed bands miss.
3. **Validate on race pace, not just qualifying** — fuel-corrected long-run band speeds,
   where corner-band fit might matter more (tyre/aero interaction over a stint).
4. **Similarity-shrinkage backbone (brief 16 §5)** — shrink a car's thin-sample band factor
   toward structurally similar circuits, to de-noise the estimate.
5. **Tie telemetry to tyre-deg & lap-time physics** — a separate, more promising lane:
   braking/corner-speed/throttle traces → mechanistic lap-time and degradation terms (the
   deterministic-engine direction, not the edge direction). Worth a dedicated research pass.

---

## Sources
Internal: [16-novel-edge-features.md](16-novel-edge-features.md) §2 (the spec + the
"scalar-pace in five hats" and overfit warnings), [12-telemetry-racecraft-validation.md](12-telemetry-racecraft-validation.md)
(telemetry *style* doesn't separate racecraft — converges with this),
`backend/app/models/telemetry_signatures.py` (the telemetry-pull pattern reused),
`backend/app/models/kalman.py` (`KalmanTrackModel`, the affinity this must not become).
External (per brief 16): AWS Car Performance Scores (public mirror of a telemetry factor
decomposition); FastF1 `circuit_info` (corner geometry); corner-speed heuristics
(Radicalbit, motorsport.com fastest/slowest turns).
