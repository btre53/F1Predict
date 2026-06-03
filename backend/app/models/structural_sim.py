"""Structural field sim, ANCHORED to the Kalman + ENSEMBLED (MODEL_ROADMAP flagship).

The honest history (docs/MODEL.md, MODEL_ROADMAP.md): a physically-detailed per-lap field
sim (engine/montecarlo.py) *underperformed* the simple Kalman rank model forward-chained
(~31.7% vs ~63% top-pick) -- it predicts a high-dimensional intermediate (every car, every
lap) and integrates, so small per-lap biases compound, and more physics != better-calibrated
probabilities for *who finishes where*.

The fix (the roadmap design) makes it complex AND provably-not-worse:

  1. ANCHOR the sim to the rank model. Seed each car's race pace from the **Kalman strength**
     (the rank model's calibrated belief), mapped to a per-lap pace offset. The sim inherits
     the anchor's calibration instead of re-deriving pace from scratch.
  2. Let the physics add what it's *good* at -- strategy, tyre deg, fuel, safety cars, weather
     variance -- as structured spread on top of that anchor.
  3. ENSEMBLE the sim's finishing distribution with the rank model's at a learned weight w
     (Benter-style). At w=0 it IS the rank model, so the blend can never score worse than the
     anchor: the physics only helps where it helps. Judge on PROP logloss (points / podium /
     who-scores), the markets where the extra physics actually pays, not just top-pick.

This module is the field-sim + ensemble primitives; `validate_structural_sim.py` is the
forward-chained proof that ensemble >= anchor.
"""

from __future__ import annotations

import numpy as np

from app.engine import calibration_store as store
from app.engine.montecarlo import GridEntry, run_race_simulation
from app.engine.params import CircuitParams
from app.engine.strategy import optimize_strategy

# Pace mapping: one Kalman strength std (z=1 across the field) -> this many s/lap of race
# pace. CALIBRATED forward-chained (brief 22): at ~0.15-0.20 the sim's favourite win% matches
# reality (~28%) and it beats the rank model on win/podium/points; the old 0.45 made the pace
# edge x ~57 laps far too decisive (favourite ~60%). NOTE this is a stopgap: shrinking the pace
# field is a fudge for the real fix -- anchoring on a *measured* clean-air race pace and adding
# tyre-deg / reliability / traffic from their own observables instead of the lumped strength.
PACE_S_PER_Z = 0.18


def strengths_to_pace_offsets(strengths: dict[str, float], *, scale: float = PACE_S_PER_Z) -> dict[str, float]:
    """Kalman strength (higher=faster, z-units) -> per-lap pace offset s (+ve = slower)."""
    drivers = list(strengths)
    s = np.array([strengths[d] for d in drivers], dtype=float)
    mu, sd = s.mean(), s.std()
    z = (s - mu) / sd if sd > 1e-9 else np.zeros_like(s)
    return {d: float(-z[i] * scale) for i, d in enumerate(drivers)}


def simulate_field(
    circuit_name: str,
    strengths: dict[str, float],
    *,
    grid_order: list[str],
    team_of: dict[str, str],
    dnf_of: dict[str, float] | None = None,
    num_of: dict[str, int | None] | None = None,
    cp: CircuitParams | None = None,
    team_deg: bool = False,
    pace_scale: float = PACE_S_PER_Z,
    dirty_air_s: float = 0.0,
    overtaking: float = 1.0,
    measured_dirty_air: bool = False,
    start_sigma_s: float = 0.0,
    return_result: bool = False,
    n_sims: int = 6000,
    seed: int = 12345,
):
    """Run the physical field MC seeded by Kalman pace; return {driver: finish_distribution}.

    The sim's job is to add strategy/tyre/fuel/SC structure *around* the anchored pace order.
    Returns a per-driver P(finish==k) vector (length = #drivers), the unit the ensemble blends.

    team_deg=False (default) is the BUG FIX from brief 22's diagnosis: the per-team tyre
    `deg_multiplier` must NOT be re-applied here, because the Kalman pace anchor already encodes
    each car's race pace *including* how it manages tyres (finishing positions reflect deg). With
    all cars on one shared strategy the multiplier was the only thing breaking the pace tie -- and
    it's a large, clamped value (0.6..1.6), so it overrode the pace order and crowned gentle-tyre
    teams (Ferrari/Aston) regardless of speed. Differential tyre effects belong to STRATEGY
    DIVERGENCE (per-car pit timing/compound), not a flat per-team pace bonus -- that's v2.
    """
    cp = cp or store.circuit_params_for(circuit_name)
    overrides = store.tyre_overrides_for(circuit_name)
    pace = strengths_to_pace_offsets(strengths, scale=pace_scale)
    dnf_of = dnf_of or {}
    num_of = num_of or {}

    # One optimal strategy for the circuit (per-car best-response strategy is v2 -- the
    # Stackelberg field). Per-car variance still comes from pace + form + execution noise.
    opt = optimize_strategy(cp, max_stops=2, tyre_overrides=overrides, top_k=1)
    if not opt:
        # Degenerate fallback: a flat 1-stop so the sim still runs.
        from app.engine.params import Compound
        from app.engine.strategy import Stint, Strategy

        half = cp.total_laps // 2
        strategy = Strategy([Stint(Compound.MEDIUM, half),
                             Stint(Compound.HARD, cp.total_laps - half)])
    else:
        strategy = opt[0].strategy

    grid_pos = {d: i + 1 for i, d in enumerate(grid_order)}
    entries: list[GridEntry] = []
    for d in grid_order:
        team = team_of.get(d, "")
        entries.append(GridEntry(
            driver=d,
            strategy=strategy,
            pace_offset_s=pace.get(d, 0.0),
            grid_pos=grid_pos[d],
            number=num_of.get(d),
            team=team,
            colour="888888",
            dnf_prob=float(dnf_of.get(d, 0.08)),
            deg_multiplier=store.team_deg_multiplier(team) if team_deg else 1.0,
        ))
    curve = None
    if measured_dirty_air:
        from .dirty_air import penalty_curve
        mids, pen = penalty_curve(circuit_name)
        curve = (mids, pen) if len(mids) else None
    res = run_race_simulation(cp, entries, n_sims=n_sims, tyre_overrides=overrides,
                              dirty_air_s=dirty_air_s, overtaking=overtaking,
                              dirty_air_curve=curve, start_sigma_s=start_sigma_s,
                              return_ranks=return_result, seed=seed)
    if return_result:
        return res   # carries .ranks (d, sims) + .rank_drivers for joint/prop scoring
    return {o.driver: np.asarray(o.finish_distribution, dtype=float) for o in res.outcomes}


def blend_distributions(
    dist_a: dict[str, np.ndarray],
    dist_b: dict[str, np.ndarray],
    w: float,
) -> dict[str, np.ndarray]:
    """Convex blend of two finishing distributions: (1-w)*A + w*B, per driver, renormalized.

    A is the ANCHOR (rank model), B is the SIM. w=0 -> pure anchor (the can't-be-worse floor);
    w=1 -> pure sim. Drivers missing from one side fall back to the other.
    """
    out: dict[str, np.ndarray] = {}
    for d in set(dist_a) | set(dist_b):
        a = dist_a.get(d)
        b = dist_b.get(d)
        if a is None:
            out[d] = b
        elif b is None:
            out[d] = a
        else:
            n = min(len(a), len(b))
            v = (1.0 - w) * a[:n] + w * b[:n]
            tot = v.sum()
            out[d] = v / tot if tot > 0 else v
    return out


def dist_to_markets(dist: dict[str, np.ndarray]) -> dict[str, dict[str, float]]:
    """Finishing distribution -> {driver: {win, podium, points}} (cumulative slices)."""
    return {
        d: {
            "win": float(v[0]) if len(v) else 0.0,
            "podium": float(v[:3].sum()),
            "points": float(v[:10].sum()),
        }
        for d, v in dist.items()
    }
