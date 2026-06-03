"""Lo-Bacon-Shone lambda sweep (brief 30): does discounting strong cars in the LOWER placings
improve podium/points calibration over plain Harville/Plackett-Luce?

Harville (=PL, what we use) is known to over-state strong competitors in 2nd/3rd. Lo & Bacon-Shone
fix it cheaply by raising the strengths to a power lambda<=1 for every placing below the win
(lam=1 is exact PL). We forward-chain the production Kalman (leak-free), sweep lambda, and score
win/podium/points log-loss against the real finishing positions. Win is unchanged by lambda (the
winner is the lam=1 choice); the test is whether podium/points improve. Network-free.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from . import hazard
from .features import build_feature_table
from .kalman import KalmanModel
from .probability import strengths_to_probs_lbs

_EPS = 1e-12
DEFAULT_TEMPERATURE = 0.5


def _score(pairs):
    if not pairs:
        return None
    p = np.clip(np.array([x[0] for x in pairs]), _EPS, 1 - _EPS)
    o = np.array([x[1] for x in pairs], dtype=float)
    return round(float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p))), 4)


def evaluate(*, lambdas=(1.0, 0.9, 0.8, 0.7, 0.6, 0.5), n_recent: int = 60,
             n_sims: int = 8000, min_history: int = 30, seed: int = 0) -> dict:
    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    target = set(seqs[-n_recent:])
    clf, prior = hazard._cached_model()
    model = KalmanModel(net_dnf=True)
    model.reset()

    pairs = {lam: {m: [] for m in ("win", "podium", "points")} for lam in lambdas}
    seen = 0
    for s in seqs:
        race = table.filter(pl.col("seq") == s)
        if seen >= min_history and s in target and race.height >= 6:
            rows = race.to_dicts()
            strengths = model.predict(race)
            drivers = [r["driver"] for r in rows if r["driver"] in strengths]
            if len(drivers) >= 6:
                rmap = {r["driver"]: r for r in rows}
                year, circuit = int(rows[0]["year"]), rows[0]["circuit"]
                total_laps = 57
                grid_rank = {d: i + 1 for i, d in enumerate(sorted(drivers, key=lambda x: -strengths[x]))}
                sv = np.array([strengths[d] for d in drivers])
                dnf = np.array([hazard.race_dnf_prob(clf, prior, grid=grid_rank[d],
                                                     team=rmap[d].get("team") or "", year=year,
                                                     total_laps=total_laps) for d in drivers])
                for lam in lambdas:
                    probs = strengths_to_probs_lbs(drivers, sv, temperature=DEFAULT_TEMPERATURE,
                                                   lam=lam, dnf_prob=dnf, n_sims=n_sims, seed=seed)
                    for d in drivers:
                        fin = rmap[d]["finish_pos"]
                        pairs[lam]["win"].append((probs[d]["win"], int(fin == 1)))
                        pairs[lam]["podium"].append((probs[d]["podium"], int(fin <= 3)))
                        pairs[lam]["points"].append((probs[d]["points"], int(fin <= 10)))
        model.update(race)
        seen += 1

    sweep = [{"lam": lam, "win_ll": _score(pairs[lam]["win"]),
              "podium_ll": _score(pairs[lam]["podium"]), "points_ll": _score(pairs[lam]["points"])}
             for lam in lambdas]
    best_pod = min(sweep, key=lambda x: x["podium_ll"])
    best_pts = min(sweep, key=lambda x: x["points_ll"])
    return {"n_races": sum(1 for _ in target), "sweep": sweep,
            "best_podium_lam": best_pod["lam"], "best_points_lam": best_pts["lam"]}


if __name__ == "__main__":
    r = evaluate()
    print("Lo-Bacon-Shone lambda sweep — forward-chained (lam=1 is plain Plackett-Luce)\n")
    print(f"  {'lambda':>7} {'win_ll':>8} {'podium_ll':>10} {'points_ll':>10}")
    for x in r["sweep"]:
        tag = "  <- PL baseline" if x["lam"] == 1.0 else ""
        print(f"  {x['lam']:>7} {x['win_ll']:>8} {x['podium_ll']:>10} {x['points_ll']:>10}{tag}")
    print(f"\n  best podium lambda {r['best_podium_lam']} · best points lambda {r['best_points_lam']}")
