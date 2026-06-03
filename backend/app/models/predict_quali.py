"""Qualifying prediction: predict the starting GRID from one-lap pace (the last modelling gap).

We already FUSE the real grid once qualifying has happened (post-quali sharpening); this PREDICTS
it beforehand. The pre-quali Kalman strength (car μ + driver μ, with no this-weekend quali fused)
is each car+driver's pace belief; we Plackett-Luce / Gumbel sample the grid order from it at a
qualifying-specific temperature (qualifying is lower-variance than the race — the pole sitter is
more predictable than the winner — so a tighter temperature). Returns a per-driver grid-position
distribution + pole probability.

The season simulator uses `sample_grid` per rollout for future (pre-quali) races, then runs the
race conditioned on that grid — propagating qualifying uncertainty into the result.
"""

from __future__ import annotations

import numpy as np
import polars as pl

QUALI_TEMPERATURE = 0.35   # tuned (validate_quali): tighter than the race's 0.5


def _pre_quali_strength(model, drivers: list[str], team_of: dict[str, str]) -> dict[str, float]:
    """Car μ + driver μ with NO this-weekend quali fused (the pre-quali pace belief)."""
    out = {}
    for d in drivers:
        t = team_of.get(d, "")
        model._seed(d, t)
        out[d] = model.car[t][0] + model.drv[d][0]
    return out


def grid_distribution(drivers, strengths, *, temperature=QUALI_TEMPERATURE, n_sims=8000, seed=0):
    """Plackett-Luce grid sampling -> ({driver: P(grid==k) vector}, {driver: pole_prob})."""
    n = len(drivers)
    sv = np.array([strengths[d] for d in drivers]) / max(temperature, 1e-6)
    rng = np.random.default_rng(seed)
    pos = np.zeros((n, n))
    for _ in range(n_sims):
        order = np.argsort(-(sv + rng.gumbel(0.0, 1.0, n)))   # faster -> further forward
        for gpos, di in enumerate(order):
            pos[di, gpos] += 1
    pos /= n_sims
    dist = {d: pos[i] for i, d in enumerate(drivers)}
    pole = {d: float(pos[i, 0]) for i, d in enumerate(drivers)}
    return dist, pole


def sample_grid(drivers, strengths, *, temperature=QUALI_TEMPERATURE, rng=None) -> list[str]:
    """One sampled grid order (fastest first) — for season-sim rollouts."""
    rng = rng or np.random.default_rng()
    sv = np.array([strengths[d] for d in drivers]) / max(temperature, 1e-6)
    order = np.argsort(-(sv + rng.gumbel(0.0, 1.0, len(drivers))))
    return [drivers[i] for i in order]


def predict_grid(circuit_name: str, *, n_sims: int = 8000, temperature: float = QUALI_TEMPERATURE) -> dict:
    """Pre-quali grid prediction for the upcoming race (uses the fitted forward-chained Kalman)."""
    from .predict_kalman import _fitted

    model, roster, _latest = _fitted()
    drivers = roster["driver"].to_list()
    team_of = {r["driver"]: r["team"] for r in roster.to_dicts()}
    strengths = _pre_quali_strength(model, drivers, team_of)
    dist, pole = grid_distribution(drivers, strengths, temperature=temperature, n_sims=n_sims)
    order = sorted(drivers, key=lambda d: -strengths[d])
    return {
        "circuit": circuit_name,
        "predicted_pole": order[0],
        "grid": [{"driver": d, "pole_pct": round(pole[d], 3),
                  "exp_grid": round(float((np.arange(1, len(drivers) + 1) * dist[d]).sum()), 1)}
                 for d in order],
    }


def validate(grid_temps=(0.25, 0.35, 0.5, 0.75), min_history: int = 20) -> dict:
    """Forward-chained: predict the grid from the PRE-quali strength, score vs the official grid."""
    from scipy.stats import spearmanr

    from .features import build_feature_table
    from .kalman import KalmanModel

    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    _EPS = 1e-12

    best = None
    for T in grid_temps:
        model = KalmanModel(net_dnf=True); model.reset()
        pole_hits = 0; n = 0; rhos = []; pole_pairs = []
        seen = 0
        for s in seqs:
            race = table.filter(pl.col("seq") == s)
            rows = race.to_dicts()
            drivers = [r["driver"] for r in rows if r.get("grid") is not None]
            if seen >= min_history and len(drivers) >= 6:
                team_of = {r["driver"]: (r["team"] or "") for r in rows}
                strn = _pre_quali_strength(model, drivers, team_of)
                _dist, pole = grid_distribution(drivers, strn, temperature=T, n_sims=3000, seed=1)
                rmap = {r["driver"]: r for r in rows}
                actual_pole = min(drivers, key=lambda d: rmap[d]["grid"])
                pred_pole = max(drivers, key=lambda d: pole[d])
                pole_hits += int(pred_pole == actual_pole); n += 1
                pred_rank = [strn[d] for d in drivers]
                act_grid = [rmap[d]["grid"] for d in drivers]
                rho = spearmanr([-x for x in pred_rank], act_grid).correlation
                if rho == rho:
                    rhos.append(rho)
                for d in drivers:
                    pole_pairs.append((pole[d], int(rmap[d]["grid"] == 1)))
            model.update(race); seen += 1
        p = np.clip(np.array([x[0] for x in pole_pairs]), _EPS, 1 - _EPS)
        o = np.array([x[1] for x in pole_pairs], dtype=float)
        ll = float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p)))
        res = {"temperature": T, "pole_accuracy": round(pole_hits / n, 3),
               "grid_spearman": round(float(np.mean(rhos)), 3), "pole_logloss": round(ll, 4), "n": n}
        if best is None or ll < best["pole_logloss"]:
            best = res
        print(f"  T={T}: pole_acc {res['pole_accuracy']}  grid_rho {res['grid_spearman']}  pole_ll {res['pole_logloss']}")
    return best


if __name__ == "__main__":
    print("Qualifying-prediction validation (forward-chained, pre-quali strength vs official grid):")
    b = validate()
    print(f"\n  best: T={b['temperature']}  pole-accuracy {b['pole_accuracy']:.0%}  "
          f"grid Spearman {b['grid_spearman']}  ({b['n']} races)")
