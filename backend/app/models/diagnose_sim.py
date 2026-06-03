"""Diagnostic: WHY is the structural sim so wrong? Decompose per-race vs the anchor + reality.

Prints, for a handful of recent races (leak-free, same machinery as validate_structural_sim):
  actual winner | anchor fav + win% | sim fav + win% | do they agree? | sim fav's grid
plus field-level summaries: does the sim pick the same favourite as the anchor (pace order)?
is it over/under-confident? how concentrated is its win distribution?
"""

from __future__ import annotations

import numpy as np
import polars as pl

from app.engine import calibration_store as store

from . import hazard
from .features import build_feature_table
from .kalman import KalmanModel
from .structural_sim import dist_to_markets, simulate_field
from .validate_structural_sim import _rank_model_dist, DEFAULT_TEMPERATURE


def run(n_recent: int = 20, n_sims: int = 4000, min_history: int = 30, seed: int = 7):
    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    target = set(seqs[-n_recent:])
    clf, prior = hazard._cached_model()
    model = KalmanModel(); model.reset()

    agree = 0; n = 0
    sim_fav_winp = []; anc_fav_winp = []
    sim_fav_is_polepace = 0
    rows_out = []
    seen = 0
    for s in seqs:
        race = table.filter(pl.col("seq") == s)
        if seen >= min_history and s in target and race.height >= 6:
            rows = race.to_dicts()
            strengths = model.predict(race)
            drivers = [r["driver"] for r in rows if r["driver"] in strengths]
            if len(drivers) >= 6:
                rmap = {r["driver"]: r for r in rows}
                year = int(rows[0]["year"]); circuit = rows[0]["circuit"]
                cp = store.circuit_params_for(circuit)
                with_grid = [d for d in drivers if rmap[d].get("grid") is not None]
                grid_order = (sorted(with_grid, key=lambda d: rmap[d]["grid"])
                              if len(with_grid) >= len(drivers) - 2
                              else sorted(drivers, key=lambda d: -strengths[d]))
                for d in drivers:
                    if d not in grid_order:
                        grid_order.append(d)
                grid_pos = {d: i + 1 for i, d in enumerate(grid_order)}
                team_of = {d: rmap[d].get("team") or "" for d in drivers}
                dnf_of = {d: hazard.race_dnf_prob(clf, prior, grid=grid_pos[d], team=team_of[d],
                                                  year=year, total_laps=cp.total_laps) for d in drivers}
                anchor = _rank_model_dist(drivers, strengths, [dnf_of[d] for d in drivers],
                                          temperature=DEFAULT_TEMPERATURE, n_sims=n_sims, seed=seed)
                sim = simulate_field(circuit, strengths, grid_order=grid_order, team_of=team_of,
                                     dnf_of=dnf_of, cp=cp, n_sims=n_sims, seed=seed)
                amk = dist_to_markets(anchor); smk = dist_to_markets(sim)
                winner = min(drivers, key=lambda d: rmap[d]["finish_pos"])
                pace_fav = max(drivers, key=lambda d: strengths[d])     # highest Kalman strength
                anc_fav = max(drivers, key=lambda d: amk[d]["win"])
                sim_fav = max(drivers, key=lambda d: smk[d]["win"])
                n += 1
                agree += int(sim_fav == anc_fav)
                sim_fav_winp.append(smk[sim_fav]["win"]); anc_fav_winp.append(amk[anc_fav]["win"])
                sim_fav_is_polepace += int(sim_fav == pace_fav)
                rows_out.append(
                    f"  {circuit[:13]:13s} {year}  won {winner:3s} | "
                    f"anchor {anc_fav:3s} {amk[anc_fav]['win']*100:4.0f}% | "
                    f"sim {sim_fav:3s} {smk[sim_fav]['win']*100:4.0f}% (gridP{grid_pos[sim_fav]:<2d}) | "
                    f"pace_fav {pace_fav:3s} | {'agree' if sim_fav==anc_fav else 'DIFFER'}")
        model.update(race)
        seen += 1

    print(f"Sim diagnosis — {n} recent races (n_sims={n_sims})\n")
    print("\n".join(rows_out))
    print(f"\n  sim_fav == anchor_fav:        {agree}/{n} ({agree/n*100:.0f}%)")
    print(f"  sim_fav == highest-pace car:  {sim_fav_is_polepace}/{n} ({sim_fav_is_polepace/n*100:.0f}%)")
    print(f"  mean sim favourite win%:      {np.mean(sim_fav_winp)*100:.0f}%  (over-confident if >> reality)")
    print(f"  mean anchor favourite win%:   {np.mean(anc_fav_winp)*100:.0f}%")


if __name__ == "__main__":
    run()
