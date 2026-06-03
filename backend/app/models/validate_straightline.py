"""Forward-chained test of the per-car straight-line threshold term in the position sim (brief 28).

The probe (brief 28 / overtake_events) showed straight-line speed predicts CLEARING traffic. Here we
ask the product question: does feeding it into the position-resolution sim improve ORDER accuracy
(top-pick / best-of-rest) without wrecking calibration?

Leak-free: the Kalman is chained on strictly-prior races; the grid is the real pre-race grid; and —
critically — each car's straight-line tendency is its mean within-race speed-trap z over its races
BEFORE this one (a stable trait, corr 0.82 y/y), never this race's reading. For each target race we
run the position sim with the term OFF (s_per_z=0) and ON, and score against the real result.
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
from .straightline import straightline_table

_EPS = 1e-12


def _seq_sl_map(table: pl.DataFrame) -> dict[int, dict[str, float]]:
    """{seq: {driver: within-race straight-line z}} by joining the speed-trap table to seq."""
    key = table.select(["seq", "year", "circuit", "driver"]).unique()
    j = key.join(straightline_table(), on=["year", "circuit", "driver"], how="inner")
    out: dict[int, dict[str, float]] = {}
    for r in j.to_dicts():
        out.setdefault(int(r["seq"]), {})[r["driver"]] = float(r["sl_z"])
    return out


def _score(pairs):
    if not pairs:
        return None
    p = np.clip(np.array([x[0] for x in pairs]), _EPS, 1 - _EPS)
    o = np.array([x[1] for x in pairs], dtype=float)
    return round(float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p))), 4)


def evaluate(*, n_recent: int = 45, n_sims: int = 4000, min_history: int = 30,
             s_per_z: float = 0.15, seed: int = 7) -> dict:
    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    target = set(seqs[-n_recent:])
    sl_map = _seq_sl_map(table)

    clf, prior = hazard._cached_model()
    model = KalmanModel(net_dnf=True)
    model.reset()

    sl_hist: dict[str, list[float]] = {}          # per-driver PRIOR straight-line readings
    variants = {"off": 0.0, "on": s_per_z}
    pairs = {v: {m: [] for m in ("win", "podium", "points")} for v in variants}
    top_hits = {v: 0 for v in variants}
    bor_hits = {v: 0 for v in variants}
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
                team_of = {d: rmap[d].get("team") or "" for d in drivers}
                # mean clean-pace anchor: use Kalman strength as the pace offset (z -> ~s via a scale)
                smean = np.mean([strengths[d] for d in drivers])
                grid = []
                sl_vec = []
                for d in drivers:
                    grid.append(GridEntry(
                        driver=d, strategy=strat, grid_pos=gpos[d],
                        pace_offset_s=-(strengths[d] - smean) * 0.9,  # faster car -> lower lap time
                        dnf_prob=hazard.race_dnf_prob(clf, prior, grid=gpos[d], team=team_of[d],
                                                      year=year, total_laps=cp.total_laps)))
                    sl_vec.append(float(np.mean(sl_hist[d])) if sl_hist.get(d) else 0.0)
                sl_arr = np.array(sl_vec)
                winner = min(drivers, key=lambda d: rmap[d]["finish_pos"])
                actual_bor = next((d for d in drivers if rmap[d]["finish_pos"] == 2), None)
                n_races += 1
                bor_races += int(actual_bor is not None)
                for v, coef in variants.items():
                    res = run_position_simulation(
                        cp, grid, n_sims=n_sims, tyre_overrides=ov,
                        straightline=sl_arr, straightline_s_per_z=coef, seed=seed)
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
        # update the per-driver straight-line history AFTER predicting (leak-free)
        for d, z in sl_map.get(int(s), {}).items():
            sl_hist.setdefault(d, []).append(z)
        model.update(race)
        seen += 1

    res = {"n_races": n_races, "s_per_z": s_per_z, "variants": {}}
    for v in variants:
        res["variants"][v] = {
            "win_ll": _score(pairs[v]["win"]), "podium_ll": _score(pairs[v]["podium"]),
            "points_ll": _score(pairs[v]["points"]),
            "top_pick": round(top_hits[v] / n_races, 3) if n_races else None,
            "best_of_rest": round(bor_hits[v] / bor_races, 3) if bor_races else None,
        }
    return res


if __name__ == "__main__":
    r = evaluate()
    print(f"Straight-line threshold term — forward-chained over {r['n_races']} races "
          f"(s_per_z={r['s_per_z']})\n")
    print(f"  {'variant':>8} {'win_ll':>8} {'pod_ll':>8} {'pts_ll':>8} {'top%':>6} {'bor%':>6}")
    for v in ("off", "on"):
        x = r["variants"][v]
        print(f"  {v:>8} {x['win_ll']:>8} {x['podium_ll']:>8} {x['points_ll']:>8} "
              f"{x['top_pick']:>6} {x['best_of_rest']:>6}")
