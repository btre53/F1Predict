"""Forward-chained test of the held-up ASYMMETRY in the position sim (brief 30, owner's idea).

Hypothesis: a backmarker yields to a much-faster car rather than wreck its tyres in a battle it
can't win, so the per-lap held-up penalty should shrink with the pace mismatch. If true, fast cars
that START LOW should RECOVER better — exactly the scenario where our model reads lower than the
market. We test both (a) overall order accuracy and (b) the targeted recovery metric.

Leak-free: Kalman on strictly-prior races, real pre-race grid, hazard DNF. For each target race we
run the position sim with the asymmetry OFF and ON and score against the real result.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from app.engine import calibration_store as store
from app.engine.montecarlo import GridEntry
from app.engine.position_sim import run_position_simulation
from app.engine.strategy import optimize_strategy

from . import hazard
from .features import build_feature_table
from .kalman import KalmanModel

_EPS = 1e-12


def _score(pairs):
    if not pairs:
        return None
    p = np.clip(np.array([x[0] for x in pairs]), _EPS, 1 - _EPS)
    o = np.array([x[1] for x in pairs], dtype=float)
    return round(float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p))), 4)


def evaluate(*, n_recent: int = 45, n_sims: int = 4000, min_history: int = 30, seed: int = 7) -> dict:
    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    target = set(seqs[-n_recent:])
    clf, prior = hazard._cached_model()
    model = KalmanModel(net_dnf=True)
    model.reset()

    variants = ("off", "on")
    pairs = {v: {m: [] for m in ("win", "podium", "points")} for v in variants}
    top_hits = {v: 0 for v in variants}
    bor_hits = {v: 0 for v in variants}
    # Targeted: cars that started P8+ but were top-6 on pace ("fast car from the back") — does
    # the model's predicted finishing share for them improve (move toward what actually happened)?
    recov_pairs = {v: [] for v in variants}
    n_races = bor_races = seen = 0

    for s in seqs:
        race = table.filter(pl.col("seq") == s)
        if seen >= min_history and s in target and race.height >= 6:
            rows = race.to_dicts()
            strengths = model.predict(race)
            drivers = [r["driver"] for r in rows if r["driver"] in strengths]
            if len(drivers) >= 6:
                rmap = {r["driver"]: r for r in rows}
                year, circuit = int(rows[0]["year"]), rows[0]["circuit"]
                cp = store.circuit_params_for(circuit)
                ov = store.tyre_overrides_for(circuit)
                strat = optimize_strategy(cp, max_stops=2, tyre_overrides=ov, top_k=1)[0].strategy
                with_grid = [d for d in drivers if rmap[d].get("grid") is not None]
                grid_order = (sorted(with_grid, key=lambda d: rmap[d]["grid"])
                              if len(with_grid) >= len(drivers) - 2
                              else sorted(drivers, key=lambda d: -strengths[d]))
                for d in drivers:
                    if d not in grid_order:
                        grid_order.append(d)
                gpos = {d: i + 1 for i, d in enumerate(grid_order)}
                pace_rank = {d: i + 1 for i, d in enumerate(sorted(drivers, key=lambda x: -strengths[x]))}
                team_of = {d: rmap[d].get("team") or "" for d in drivers}
                smean = np.mean([strengths[d] for d in drivers])
                grid = [GridEntry(
                    driver=d, strategy=strat, grid_pos=gpos[d],
                    pace_offset_s=-(strengths[d] - smean) * 0.9,
                    dnf_prob=hazard.race_dnf_prob(clf, prior, grid=gpos[d], team=team_of[d],
                                                  year=year, total_laps=cp.total_laps))
                    for d in drivers]
                winner = min(drivers, key=lambda d: rmap[d]["finish_pos"])
                actual_bor = next((d for d in drivers if rmap[d]["finish_pos"] == 2), None)
                # "fast car from the back": started P8+ but top-6 on pace.
                recoverers = [d for d in drivers if gpos[d] >= 8 and pace_rank[d] <= 6]
                n_races += 1
                bor_races += int(actual_bor is not None)
                for v in variants:
                    res = run_position_simulation(
                        cp, grid, n_sims=n_sims, tyre_overrides=ov,
                        held_up_asymmetry=(v == "on"), seed=seed)
                    mk = {o.driver: o for o in res.outcomes}
                    pick = max(drivers, key=lambda d: mk[d].win_pct)
                    top_hits[v] += int(pick == winner)
                    if actual_bor is not None:
                        rest = [d for d in drivers if d != winner]
                        bor_hits[v] += int(max(rest, key=lambda d: mk[d].win_pct) == actual_bor)
                    for d in drivers:
                        fin = rmap[d]["finish_pos"]
                        pairs[v]["win"].append((mk[d].win_pct, int(fin == 1)))
                        pairs[v]["podium"].append((mk[d].podium_pct, int(fin <= 3)))
                        pairs[v]["points"].append((mk[d].points_pct, int(fin <= 10)))
                    for d in recoverers:
                        recov_pairs[v].append((mk[d].podium_pct, int(rmap[d]["finish_pos"] <= 3)))
        model.update(race)
        seen += 1

    res = {"n_races": n_races, "variants": {}}
    for v in variants:
        res["variants"][v] = {
            "win_ll": _score(pairs[v]["win"]), "podium_ll": _score(pairs[v]["podium"]),
            "points_ll": _score(pairs[v]["points"]),
            "top_pick": round(top_hits[v] / n_races, 3) if n_races else None,
            "best_of_rest": round(bor_hits[v] / bor_races, 3) if bor_races else None,
            "recoverer_podium_ll": _score(recov_pairs[v]), "n_recoverers": len(recov_pairs[v]),
        }
    return res


if __name__ == "__main__":
    r = evaluate()
    print(f"Held-up asymmetry — forward-chained over {r['n_races']} races\n")
    print(f"  {'variant':>8} {'win_ll':>8} {'pod_ll':>8} {'pts_ll':>8} {'top%':>6} {'bor%':>6} "
          f"{'recov_pod_ll':>13}")
    for v in ("off", "on"):
        x = r["variants"][v]
        print(f"  {v:>8} {x['win_ll']:>8} {x['podium_ll']:>8} {x['points_ll']:>8} "
              f"{x['top_pick']:>6} {x['best_of_rest']:>6} {x['recoverer_podium_ll']:>13}")
    print(f"\n  ('fast car from the back' = started P8+ but top-6 on pace; "
          f"n={r['variants']['off']['n_recoverers']} car-races)")
