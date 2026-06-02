"""Predictor engine: time-local Kalman car+driver pace -> finishing-position probs.

Replaces the old mechanistic-sim path (which used `drivers.json`, a flat all-time
pooled average — the wrong way: it had Perez at Red Bull and Verstappen winning Monaco).
This:
  1. forward-chains the Kalman pace-filter (app/models/kalman.py) over ALL races so the
     car+driver beliefs are time-local and current (between-race + season-boundary
     variance inflation already handles upgrades / season changes);
  2. takes the roster from the LATEST season in the data, so it's the real current grid
     and a moved driver inherits the new car (strength = car_team.mu + driver.mu);
  3. samples finishing orders (Plackett-Luce / Gumbel-max) with per-driver DNF from the
     survival/hazard model, yielding the full finishing-position distribution.

The car/driver split is the whole point: HAM in a 2026 Ferrari gets Ferrari's current car
pace + Hamilton's driver skill — not his Mercedes-era pooled average.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import polars as pl

from app.engine import calibration_store as store
from app.engine.montecarlo import DriverOutcome, RaceSimResult
from app.engine.predict import TEAM_COLOURS

from . import hazard
from .features import LAPS_PARQUET, build_feature_table
from .kalman import KalmanModel

# PL temperature = the forward-chained calibrated value (best win log-loss in the bake-off
# harness). Pre-qualifying this yields an honestly-tight field (no single ~90% favourite);
# it sharpens automatically once a real quali grid is fused (model.predict with quali_gap).
DEFAULT_TEMPERATURE = 0.5


@lru_cache(maxsize=1)
def _fitted():
    """Forward-chain the Kalman over all races; return (model, roster, latest_year).

    roster: one row per current-grid driver -> {driver, team, number} from the latest
    season (most-frequent team handles mid-season swaps; top-20 by laps drops reserves).
    """
    table = build_feature_table()
    model = KalmanModel()
    model.reset()
    for s in sorted(table["seq"].unique().to_list()):
        model.update(table.filter(pl.col("seq") == s))

    latest = int(table["year"].max())
    laps = pl.read_parquet(
        LAPS_PARQUET, columns=["year", "session_name", "driver", "driver_number", "team"]
    ).filter((pl.col("year") == latest) & (pl.col("session_name") == "R"))
    roster = (
        laps.group_by("driver").agg(
            pl.col("team").mode().first().alias("team"),
            pl.col("driver_number").mode().first().alias("number"),
            pl.len().alias("laps"),
        )
        .sort("laps", descending=True)
        .head(20)  # regulars only — drop one-off reserves
    )
    return model, roster, latest


def predict_race_kalman(
    circuit_name: str,
    *,
    n_sims: int = 10_000,
    grid_order: list[str] | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int = 12345,
) -> RaceSimResult:
    model, roster, latest = _fitted()
    cp = store.circuit_params_for(circuit_name)
    n_laps = cp.total_laps

    drivers = roster["driver"].to_list()
    team_of = {r["driver"]: r["team"] for r in roster.to_dicts()}
    num_of = {r["driver"]: r["number"] for r in roster.to_dicts()}

    # Kalman strength per driver for THIS car+driver pairing (pre-quali: no quali/grid obs).
    race = pl.DataFrame({
        "driver": drivers,
        "team": [team_of[d] for d in drivers],
        "quali_gap_pct": [None] * len(drivers),
        "grid": [None] * len(drivers),
    })
    strengths = model.predict(race)

    # Grid = predicted pace order pre-quali (or the supplied quali order).
    order = grid_order or sorted(drivers, key=lambda d: -strengths[d])
    grid_pos = {d: i + 1 for i, d in enumerate([d for d in order if d in strengths])}
    for d in drivers:
        grid_pos.setdefault(d, len(grid_pos) + 1)

    # Per-driver DNF from the survival/hazard model (time-local attrition by grid/era).
    clf, prior = hazard._cached_model()
    dnf = np.array([
        hazard.race_dnf_prob(clf, prior, grid=grid_pos[d], team=team_of[d],
                             year=latest, total_laps=n_laps)
        for d in drivers
    ])

    # Plackett-Luce Monte Carlo with DNF censoring -> full finishing distribution.
    n = len(drivers)
    sv = np.array([strengths[d] for d in drivers]) / max(temperature, 1e-6)
    rng = np.random.default_rng(seed)
    pos_counts = np.zeros((n, n))  # [driver, finish_pos-1]
    dnf_counts = np.zeros(n)
    for _ in range(n_sims):
        g = rng.gumbel(0.0, 1.0, n)
        retired = rng.random(n) < dnf
        score = np.where(retired, -1e9, sv + g)
        order_idx = np.argsort(-score)
        for finish, di in enumerate(order_idx):
            pos_counts[di, finish] += 1
        dnf_counts[retired] += 1

    outcomes: list[DriverOutcome] = []
    positions = np.arange(1, n + 1)
    for i, d in enumerate(drivers):
        dist = pos_counts[i] / n_sims
        cdf_win = dist[0]
        podium = dist[:3].sum()
        points = dist[:10].sum()
        mean_fin = float((positions * dist).sum())
        cum = np.cumsum(dist)
        p10 = int(np.searchsorted(cum, 0.10) + 1)
        p50 = int(np.searchsorted(cum, 0.50) + 1)
        p90 = int(np.searchsorted(cum, 0.90) + 1)
        outcomes.append(DriverOutcome(
            driver=d, number=int(num_of[d]) if num_of[d] is not None else None,
            team=team_of[d], colour=TEAM_COLOURS.get(team_of[d], "888888"),
            grid_pos=grid_pos[d],
            win_pct=float(cdf_win), podium_pct=float(podium), points_pct=float(points),
            mean_finish=mean_fin, p50_finish=p50, p10_finish=p10, p90_finish=p90,
            dnf_pct=float(dnf_counts[i] / n_sims),
            finish_distribution=[float(x) for x in dist],
        ))
    outcomes.sort(key=lambda o: o.win_pct, reverse=True)
    return RaceSimResult(
        circuit=cp.name, total_laps=n_laps, n_sims=n_sims, outcomes=outcomes,
        sc_probability=0.0,  # SC not modeled in the Kalman path (see Predictor notes)
    )


if __name__ == "__main__":
    res = predict_race_kalman("Monaco", n_sims=8000)
    print(f"Kalman Predictor — {res.circuit} ({res.total_laps} laps)")
    print("  drv  team                 grid  win%   pod%   dnf%")
    for o in res.outcomes[:12]:
        print(f"  {o.driver:4s} {o.team:20s} P{o.grid_pos:<2d}  {o.win_pct*100:5.1f}  "
              f"{o.podium_pct*100:5.1f}  {o.dnf_pct*100:4.1f}")
