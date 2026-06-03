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

## v2 (the dedicated-session backlog)

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
