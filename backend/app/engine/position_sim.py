"""Per-lap track-position-resolution Monte Carlo (brief 26, task #24 step 2).

The standard sim (`montecarlo.run_race_simulation`) ranks cars by total cumulative time, so a
faster car passes for FREE — the clean-air leader gets shuffled back by noise and the front
over-disperses (why the sim trails the rank model on win/podium).

This model makes TRACK POSITION a state that only changes when a pass succeeds. Each lap, in
track order, a following car passes the car ahead with probability

    p_pass = sigmoid(k · (pace_surplus − threshold))          (Michelin overtaking curve)

where pace_surplus is how much faster its clean lap is than the car ahead's, and `threshold` is
the pace delta needed to pass (higher at hard-to-pass circuits via the overtaking index). If it
can't pass, it's HELD UP — it runs at the car-ahead's pace plus a dirty-air penalty (brief 24/25:
being stuck costs a fast car ~1 s/lap). So a clean-air leader with a pace surplus over the field is
near-unpassable, and the front tightens toward reality.

Seed pace from the CLEAN-AIR anchor (`clean_anchor.py`) so pace_surplus is pure pace (no
double-count). Vectorised over sims via odd-even transposition with stochastic pass gates.
"""

from __future__ import annotations

import numpy as np

from .montecarlo import (
    DriverOutcome,
    GridEntry,
    RaceSimResult,
    _per_lap_state,
    _sample_safety_cars,
    _skewed_noise,
    FORM_SIGMA_S,
)
from .params import CircuitParams, Compound, TrackStatus, TyreParams
from .physics import fuel_mass, fuel_penalty
from .params import WEAR_FUEL_SENSITIVITY

# Overtaking-curve defaults, anchored to the Michelin model + the brief-26 probe (~10%/lap pass
# for a typical stuck car). threshold = pace delta (s/lap) for a 50% per-lap pass on an open track.
PASS_THRESHOLD_S = 0.8
PASS_K = 1.5
HELD_UP_S = 0.5           # per-lap time a stuck car loses behind the car it can't pass (dirty air)


def run_position_simulation(
    circuit: CircuitParams,
    grid: list[GridEntry],
    *,
    n_sims: int = 6000,
    tyre_overrides: dict[Compound, TyreParams] | None = None,
    overtaking: float = 1.0,
    pass_threshold_s: float = PASS_THRESHOLD_S,
    pass_k: float = PASS_K,
    held_up_s: float = HELD_UP_S,
    seed: int = 12345,
) -> RaceSimResult:
    rng = np.random.default_rng(seed)
    n = circuit.total_laps
    d = len(grid)
    base_s = circuit.base_lap_ms / 1000.0
    laps = np.arange(1, n + 1, dtype=np.float64)
    base_fuel = base_s + np.asarray(fuel_penalty(laps, circuit.fuel))
    fuel_frac = np.asarray(fuel_mass(laps, circuit.fuel)) / max(1e-6, circuit.fuel.start_fuel_kg)
    fuel_mult = 1.0 + WEAR_FUEL_SENSITIVITY * fuel_frac

    det = np.zeros((d, n))
    for di, e in enumerate(grid):
        deg, off, _pit = _per_lap_state(e, n, tyre_overrides)
        det[di] = base_fuel + deg * fuel_mult * e.deg_multiplier + off + e.pace_offset_s

    # Whole-race form variance (per driver per sim), as in the base sim.
    form = rng.normal(0.0, FORM_SIGMA_S / max(1, n), size=(d, n_sims))  # spread across laps
    noise = _skewed_noise((n, d, n_sims), circuit.noise.sigma_s, circuit.noise.skew, rng)

    sc_mask = _sample_safety_cars(n, n_sims, circuit.safety_car, rng)
    sc_lap_time = base_s * circuit.safety_car.lap_time_mult_sc

    # Initial track order = grid order (leader first). order[r, sim] = driver index at position r.
    grid_pos = np.array([e.grid_pos for e in grid])
    init_order = np.argsort(grid_pos)
    order = np.tile(init_order[:, None], (1, n_sims))

    cum = np.zeros((d, n_sims))                       # per-driver race time
    thr = pass_threshold_s * max(0.3, overtaking)     # harder to pass at high-overtaking circuits
    even = np.arange(0, d - 1, 2)
    odd = np.arange(1, d - 1, 2)

    for li in range(n):
        sc_row = sc_mask[li]                                          # (sims,)
        clean = det[:, li][:, None] + noise[li] + form               # (d, sims) per-driver pace
        clean = np.maximum(clean, base_s * 0.5)                      # guard
        # Pass resolution (skip under SC — field is bunched, no racing).
        pace_pos = np.take_along_axis(clean, order, axis=0)          # pace at each track position
        for pair in (even, odd):
            ahead, behind = pace_pos[pair], pace_pos[pair + 1]
            surplus = ahead - behind                                 # +ve = car behind is faster
            p = 1.0 / (1.0 + np.exp(-pass_k * (surplus - thr)))
            do = (surplus > 0) & (rng.random(ahead.shape) < p) & (~sc_row[None, :])
            # swap track positions where a pass happens
            oa, ob = order[pair].copy(), order[pair + 1].copy()
            order[pair] = np.where(do, ob, oa)
            order[pair + 1] = np.where(do, oa, ob)
            pa, pb = pace_pos[pair].copy(), pace_pos[pair + 1].copy()
            pace_pos[pair] = np.where(do, pb, pa)
            pace_pos[pair + 1] = np.where(do, pa, pb)
        # Held-up: a car can't be faster than the car ahead it failed to pass (+dirty air).
        realized = pace_pos.copy()
        for r in range(1, d):
            realized[r] = np.maximum(realized[r], realized[r - 1] + held_up_s)
        # Under SC, everyone runs the neutralized lap (bunched), no held-up stacking.
        realized = np.where(sc_row[None, :], sc_lap_time, realized)
        # Scatter realized (position space) back to driver space and accumulate.
        lap_driver = np.empty_like(cum)
        np.put_along_axis(lap_driver, order, realized, axis=0)
        cum += lap_driver

    # Retirements (whole-race, classified at the back).
    dnf_counts = np.zeros(d)
    for di, e in enumerate(grid):
        ret = rng.random(n_sims) < e.dnf_prob
        cum[di, ret] = np.inf
        dnf_counts[di] = ret.sum()

    ranks = cum.argsort(axis=0).argsort(axis=0) + 1
    outcomes: list[DriverOutcome] = []
    for di, e in enumerate(grid):
        r = ranks[di]
        dist = (np.bincount(r, minlength=d + 1)[1 : d + 1] / n_sims).tolist()
        outcomes.append(DriverOutcome(
            driver=e.driver, number=e.number, team=e.team, colour=e.colour, grid_pos=e.grid_pos,
            win_pct=float(np.mean(r == 1)), podium_pct=float(np.mean(r <= 3)),
            points_pct=float(np.mean(r <= 10)), mean_finish=float(np.mean(r)),
            p50_finish=int(np.median(r)), p10_finish=int(np.percentile(r, 10)),
            p90_finish=int(np.percentile(r, 90)), dnf_pct=float(dnf_counts[di] / n_sims),
            finish_distribution=dist,
        ))
    outcomes.sort(key=lambda o: o.win_pct, reverse=True)
    return RaceSimResult(
        circuit=circuit.name, total_laps=n, n_sims=n_sims, outcomes=outcomes,
        sc_probability=float(np.mean(sc_mask.any(axis=0))),
    )
