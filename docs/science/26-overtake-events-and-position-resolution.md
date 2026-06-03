# 26 — Overtake events + the position-resolution design (the win/podium-gap fix)

_Task #24. Brief 25 rejected the per-lap strength-scaled wake. This brief (a) reports the
overtake-event probe that decides the right primitive, and (b) — backed by a research scan of what
F1 teams actually optimize — designs the position-resolution model that should close the win/podium
gap. Probe is built (`overtake_events.py`); the resolution model is designed, not yet built._

## The probe — do strong cars clear traffic faster? (`app/models/overtake_events.py`)

3,683 "stuck-behind" episodes (a car within 1.5 s of the car ahead for ≥2 consecutive green laps,
2023+ OpenF1), credited a PASS if the next lap its `position` improves AND its gap opens ≥1 s.
Bucketed by the following car's strength (clean-air pace-gap tercile):

| Following car | episodes | **pass rate** | laps-stuck (mean/med) | total time lost/episode |
|---|---|---|---|---|
| STRONG (<0.5%) | 463 | **51.8%** | 6.3 / 4 | 8.3 s |
| MID (0.5–1.5%) | 1069 | **49.2%** | 5.7 / 4 | 4.3 s |
| SLOW (>1.5%) | 2151 | **44.0%** | 5.8 / 4 | 2.7 s |

**Finding:** strong cars clear traffic **more reliably** (pass rate 52→49→44%, robustness-checked)
but **not faster** (laps-stuck is flat) — and they lose MORE total time while stuck (brief 25's
per-lap held-up cost dominates). So the right primitive is a per-lap **pass probability** that rises
with the follower's pace surplus — NOT a reduced time penalty for strong cars (rejected, brief 25).

## What F1 teams actually optimize (research scan — informs the target)

High-confidence, multi-source: the deterministic kernel minimizes **race time** (the only quantity
cleanly computable for a single car), but the **decision target is a probability distribution over
finishing position**, evaluated against named rivals and judged on expected position + robustness
(Heilmeier/TUMFTM run 10k Monte Carlo rollouts → position distribution). Race time is the *currency*;
**track position is the maximand**; the decision variable is "is the undercut in range" =
gap-to-rival vs (pit-loss − tyre-delta gain). Crucially: **rivals REACT** (cover undercuts) —
a reactive Stackelberg leader-first/follower-second cover is the validated formulation (Aguad &
Thraves 2024: ~2.3 s, ~17.8% less undercut risk); a sim with fixed rival strategies **overstates**
undercut payoffs. Teammate-cooperation is NOT a productized objective even for teams → we keep it a
documented, unmodeled effect (no overfitting on a rare, unobservable intent).

**Vindication:** our target — a **per-driver finishing-position distribution** — is exactly what
teams optimize; win/podium are its marginals. The gap is not the target, it's the **position-
resolution mechanism**.

## The design — per-lap position resolution with a pass-probability gate

Today the MC ranks cars by *total cumulative time*, so a faster car passes for free — no track-
position lock. Replace that with per-lap position resolution:

1. **Track order is a state.** Each lap, for adjacent pairs (follower f behind leader l), compute a
   **pass probability** `p_pass = σ(k · (pace_surplus_f − threshold(track, DRS, car_f)))`, where
   `pace_surplus_f` = f's clean-air pace advantage over l this lap, and `threshold` is the pace
   delta needed to pass — anchored on Michelin (~1.3 s/lap for ~20% pass chance, ~0.2 s with DRS),
   made **car/track-dependent** by measured top speed + DRS delta + circuit straight content + the
   overtaking-difficulty index (#20). Calibrate `k`/threshold so simulated per-lap pass rates match
   the probe (≈9–12%/lap; 44–52% over a ~6-lap episode).
2. **While stuck**, the follower pays the measured dirty-air penalty (brief 24 curve) — so being
   held up costs time *and* you can't cheaply teleport past (brief 25). A clean-air leader with a
   pace surplus over everyone → `p_pass`≈0 against it → **near-unpassable** → the over-dispersion
   at the front collapses toward reality.
3. **This is the “Abu Dhabi straight-line defence” mechanism, generalised + measurable:** the
   threshold is higher (harder to pass) for a car with high top speed / on a long-straight, DRS-poor
   track — a continuous physical property, not a per-race intent. Low overfit risk; forward-chained
   validation is the guard.
4. **Reactive rivals:** the simulated car ahead covers an undercut (use the existing
   `cover_or_extend`/`evaluate_undercut` primitives) so undercut payoffs aren't overstated.
5. **Free outputs:** once position is a per-lap state, the sim yields the lap-resolved PROP markets
   it's actually for (lead-at-lap-k, lead changes, pit-window outcomes) — the niche from brief 14.

**Validation plan:** forward-chained win/podium log-loss should tighten toward the rank model
(front over-dispersion fixed) while best-of-rest holds; per-lap simulated pass rate should match the
probe. Only meaningful on the **clean-air-anchored** sim (else the pace_surplus is contaminated).

## BUILT + validated (`app/engine/position_sim.py`, task #24)

Implemented the per-lap position-resolution MC: track order is a state, resolved by odd-even
transposition with a stochastic pass gate `p = σ(k·(pace_surplus − threshold·overtaking))`; a car
that can't pass is held at the car-ahead's pace + dirty air. Seeded by the **clean-air anchor**
(step 1) so pace_surplus is pure pace. Threshold raised at hard-to-pass circuits via the
overtaking index (#20); calibrated to the probe (~10%/lap pass for a typical stuck car).

Forward-chained (45 recent races, clean anchor), vs the rank-model bar:

| Model | win | podium | points | **top-pick** | **best-of-rest** |
|---|---|---|---|---|---|
| Rank model (anchor) | 0.125 | 0.245 | 0.458 | 0.47 | 0.31 |
| **Position sim** | 0.130 | 0.294 | 0.586 | **0.53** | **0.49** |

**Result:** the position sim is the **best ordering engine we've built** — it beats the rank model
on *both* accuracy metrics (top-pick 0.47→0.53, best-of-rest 0.31→0.49) and is competitive on win,
because the leader-lock fixes the front over-dispersion (a fast pole car at Monaco wins ~92% with a
tight threshold). But it's still behind the rank model on probability **calibration** (podium/points
log-loss). First cut over-locked (points ll 1.27 at threshold 1.6); loosening to 0.8 fixed most of
that (→0.586) at the cost of some lock. So the calibration-vs-accuracy split is now sharpest:
**rank model for probabilities, position sim for order + the lap-resolved props** (its real job).

Knobs left to tune (a continued calibration, not a redesign): `PASS_THRESHOLD_S` / `PASS_K` /
`HELD_UP_S`, and a per-car threshold from measured top-speed/DRS (the "Abu Dhabi" term). Teammate
orders: documented, not modelled.
