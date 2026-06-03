"""Forward-chained proof: the anchored+ensembled structural sim is never worse than the
rank model, and measure where (if anywhere) the physics adds skill.

For each race in a recent sample (leak-free: Kalman chained on strictly-prior races; actual
grid is pre-race):
  * ANCHOR  = rank-model finishing distribution (Kalman strengths -> PL Monte Carlo + hazard DNF)
  * SIM     = structural field sim seeded by the SAME strengths (engine/montecarlo)
  * ENSEMBLE(w) = (1-w)*ANCHOR + w*SIM, per driver

We sweep w and score win/podium/points logloss + top-pick / best-of-rest. The headline:
the best w should give ensemble <= anchor on prop logloss (it can't be worse: w=0 IS the
anchor), and w=1 (pure sim) should be visibly worse -- reproducing the honest history while
proving the redesign's guarantee.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from app.engine import calibration_store as store

from . import hazard
from .features import build_feature_table
from .kalman import KalmanModel
from . import structural_sim
from .structural_sim import blend_distributions, dist_to_markets, simulate_field

_EPS = 1e-12
DEFAULT_TEMPERATURE = 0.5


def _rank_model_dist(drivers, strengths, dnf, *, temperature, n_sims, seed):
    """Rank-model (anchor) finishing distribution via PL/Gumbel MC + DNF censoring."""
    n = len(drivers)
    sv = np.array([strengths[d] for d in drivers]) / max(temperature, 1e-6)
    dnf = np.asarray(dnf)
    rng = np.random.default_rng(seed)
    pos = np.zeros((n, n))
    for _ in range(n_sims):
        g = rng.gumbel(0.0, 1.0, n)
        retired = rng.random(n) < dnf
        score = np.where(retired, -1e9, sv + g)
        order = np.argsort(-score)
        for finish, di in enumerate(order):
            pos[di, finish] += 1
    return {d: pos[i] / n_sims for i, d in enumerate(drivers)}


def _score(pairs):
    if not pairs:
        return None
    p = np.clip(np.array([x[0] for x in pairs]), _EPS, 1 - _EPS)
    o = np.array([x[1] for x in pairs], dtype=float)
    return round(float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p))), 4)


def evaluate(*, n_recent: int = 45, ws=(0.0, 0.15, 0.3, 0.5, 0.75, 1.0),
             n_sims: int = 4000, min_history: int = 30, seed: int = 7,
             pace_scale: float = structural_sim.PACE_S_PER_Z, team_deg: bool = False,
             dirty_air_s: float = 0.0, measured_dirty_air: bool = False) -> dict:
    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    target = set(seqs[-n_recent:])

    clf, prior = hazard._cached_model()
    model = KalmanModel()
    model.reset()

    # markets x w -> list[(p, outcome)]
    pairs = {m: {w: [] for w in ws} for m in ("win", "podium", "points")}
    top_hits = {w: 0 for w in ws}
    bor_hits = {w: 0 for w in ws}
    n_races = 0
    bor_races = 0
    seen = 0

    for s in seqs:
        race = table.filter(pl.col("seq") == s)
        if seen >= min_history and s in target and race.height >= 6:
            rows = race.to_dicts()
            strengths = model.predict(race)
            drivers = [r["driver"] for r in rows if r["driver"] in strengths]
            if len(drivers) >= 6:
                rmap = {r["driver"]: r for r in rows}
                year = int(rows[0]["year"])
                circuit = rows[0]["circuit"]
                cp = store.circuit_params_for(circuit)
                # Pre-race grid (leak-free): actual grid order, fallback to pace order.
                with_grid = [d for d in drivers if rmap[d].get("grid") is not None]
                grid_order = (sorted(with_grid, key=lambda d: rmap[d]["grid"])
                              if len(with_grid) >= len(drivers) - 2
                              else sorted(drivers, key=lambda d: -strengths[d]))
                for d in drivers:
                    if d not in grid_order:
                        grid_order.append(d)
                grid_pos = {d: i + 1 for i, d in enumerate(grid_order)}
                team_of = {d: rmap[d].get("team") or "" for d in drivers}
                dnf_of = {
                    d: hazard.race_dnf_prob(clf, prior, grid=grid_pos[d],
                                            team=team_of[d], year=year,
                                            total_laps=cp.total_laps)
                    for d in drivers
                }
                anchor = _rank_model_dist(drivers, strengths,
                                          [dnf_of[d] for d in drivers],
                                          temperature=DEFAULT_TEMPERATURE,
                                          n_sims=n_sims, seed=seed)
                sim = simulate_field(circuit, strengths, grid_order=grid_order,
                                     team_of=team_of, dnf_of=dnf_of, cp=cp,
                                     pace_scale=pace_scale, team_deg=team_deg,
                                     dirty_air_s=dirty_air_s, measured_dirty_air=measured_dirty_air,
                                     n_sims=n_sims, seed=seed)
                winner = min(drivers, key=lambda d: rmap[d]["finish_pos"])
                actual_bor = next((d for d in drivers if rmap[d]["finish_pos"] == 2), None)
                n_races += 1
                if actual_bor is not None:
                    bor_races += 1
                for w in ws:
                    blend = blend_distributions(anchor, sim, w)
                    mk = dist_to_markets(blend)
                    pick = max(drivers, key=lambda d: mk[d]["win"])
                    top_hits[w] += int(pick == winner)
                    if actual_bor is not None:
                        rest = [d for d in drivers if d != winner]
                        bor_pick = max(rest, key=lambda d: mk[d]["win"])
                        bor_hits[w] += int(bor_pick == actual_bor)
                    for d in drivers:
                        fin = rmap[d]["finish_pos"]
                        pairs["win"][w].append((mk[d]["win"], int(fin == 1)))
                        pairs["podium"][w].append((mk[d]["podium"], int(fin <= 3)))
                        pairs["points"][w].append((mk[d]["points"], int(fin <= 10)))
        model.update(race)
        seen += 1

    sweep = []
    for w in ws:
        sweep.append({
            "w": w,
            "win_ll": _score(pairs["win"][w]),
            "podium_ll": _score(pairs["podium"][w]),
            "points_ll": _score(pairs["points"][w]),
            "top_pick": round(top_hits[w] / n_races, 3) if n_races else None,
            "best_of_rest": round(bor_hits[w] / bor_races, 3) if bor_races else None,
        })
    return {"n_races": n_races, "n_sims": n_sims,
            "pace_s_per_z": structural_sim.PACE_S_PER_Z, "sweep": sweep}


if __name__ == "__main__":
    out = evaluate()
    print(f"Structural sim ensemble -- forward-chained over {out['n_races']} recent races "
          f"(n_sims={out['n_sims']}, pace_s/z={out['pace_s_per_z']})\n")
    print(f"  {'w':>5} {'win_ll':>8} {'pod_ll':>8} {'pts_ll':>8} {'top%':>6} {'bor%':>6}   note")
    base = out["sweep"][0]
    for r in out["sweep"]:
        note = "ANCHOR (rank model)" if r["w"] == 0.0 else ("pure SIM" if r["w"] == 1.0 else "")
        print(f"  {r['w']:>5} {r['win_ll']:>8} {r['podium_ll']:>8} {r['points_ll']:>8} "
              f"{r['top_pick']:>6} {r['best_of_rest']:>6}   {note}")
    # Best ensemble per market
    for m in ("win_ll", "podium_ll", "points_ll"):
        best = min(out["sweep"], key=lambda r: r[m])
        tag = "= anchor" if best["w"] == 0.0 else f"better at w={best['w']}"
        print(f"  best {m}: {best[m]} ({tag}; anchor {base[m]})")
