"""Reliability double-count test (brief 22, task #10).

The Kalman strength is fit on finishing position, which a DNF depresses — so a car's
unreliability is baked into its *pace* strength. The sim/predictor then ALSO censors with the
hazard DNF model → reliability counted twice. The fix: `net_dnf` skips the finish observation
for races a car retired from, so the strength is pace-when-running and the hazard model is the
single home of reliability.

This compares, forward-chained WITH hazard DNF censoring (the realistic config), the standard
Kalman vs the net_dnf Kalman on win/podium/points/best-of-rest. If netting is >= standard, the
decoupling is clean (reliability lives only in the hazard model).
"""

from __future__ import annotations

import numpy as np
import polars as pl

from app.engine import calibration_store as store

from . import hazard
from .features import build_feature_table
from .kalman import KalmanModel
from .validate_structural_sim import _rank_model_dist, _score, DEFAULT_TEMPERATURE


def evaluate(*, min_history: int = 20, n_sims: int = 6000, seed: int = 7) -> dict:
    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    clf, prior = hazard._cached_model()

    std = KalmanModel(); std.reset()
    net = KalmanModel(net_dnf=True); net.reset()

    res = {tag: {m: [] for m in ("win", "podium", "points")} for tag in ("standard", "net_dnf")}
    top = {"standard": 0, "net_dnf": 0}
    bor = {"standard": 0, "net_dnf": 0}
    n_races = bor_races = seen = 0

    for s in seqs:
        race = table.filter(pl.col("seq") == s)
        std_str = std.predict(race)
        net_str = net.predict(race)
        if seen >= min_history and race.height >= 6:
            rows = race.to_dicts()
            drivers = [r["driver"] for r in rows if r["driver"] in std_str]
            if len(drivers) >= 6:
                rmap = {r["driver"]: r for r in rows}
                year = int(rows[0]["year"]); circuit = rows[0]["circuit"]
                cp = store.circuit_params_for(circuit)
                with_grid = [d for d in drivers if rmap[d].get("grid") is not None]
                grid_order = (sorted(with_grid, key=lambda d: rmap[d]["grid"])
                              if len(with_grid) >= len(drivers) - 2
                              else sorted(drivers, key=lambda d: -std_str[d]))
                for d in drivers:
                    if d not in grid_order:
                        grid_order.append(d)
                gp = {d: i + 1 for i, d in enumerate(grid_order)}
                team = {d: rmap[d].get("team") or "" for d in drivers}
                dnf = [hazard.race_dnf_prob(clf, prior, grid=gp[d], team=team[d],
                                            year=year, total_laps=cp.total_laps) for d in drivers]
                winner = min(drivers, key=lambda d: rmap[d]["finish_pos"])
                actual_bor = next((d for d in drivers if rmap[d]["finish_pos"] == 2), None)
                n_races += 1
                if actual_bor is not None:
                    bor_races += 1
                for tag, strn in (("standard", std_str), ("net_dnf", net_str)):
                    dist = _rank_model_dist(drivers, strn, dnf, temperature=DEFAULT_TEMPERATURE,
                                            n_sims=n_sims, seed=seed)
                    mk = {d: {"win": float(v[0]), "podium": float(v[:3].sum()),
                              "points": float(v[:10].sum())} for d, v in dist.items()}
                    pick = max(drivers, key=lambda d: mk[d]["win"])
                    top[tag] += int(pick == winner)
                    if actual_bor is not None:
                        rest = [d for d in drivers if d != winner]
                        bor[tag] += int(max(rest, key=lambda d: mk[d]["win"]) == actual_bor)
                    for d in drivers:
                        f = rmap[d]["finish_pos"]
                        res[tag]["win"].append((mk[d]["win"], int(f == 1)))
                        res[tag]["podium"].append((mk[d]["podium"], int(f <= 3)))
                        res[tag]["points"].append((mk[d]["points"], int(f <= 10)))
        std.update(race); net.update(race); seen += 1

    out = {
        tag: {
            "win_ll": _score(res[tag]["win"]), "podium_ll": _score(res[tag]["podium"]),
            "points_ll": _score(res[tag]["points"]),
            "top_pick": round(top[tag] / n_races, 3) if n_races else None,
            "best_of_rest": round(bor[tag] / bor_races, 3) if bor_races else None,
        } for tag in ("standard", "net_dnf")
    }
    out["n_races"] = n_races
    return out


if __name__ == "__main__":
    r = evaluate()
    print(f"Reliability double-count test — forward-chained + hazard DNF, {r['n_races']} races\n")
    print(f"  {'config':9s} | win    podium points | top%   bor%")
    for tag in ("standard", "net_dnf"):
        s = r[tag]
        print(f"  {tag:9s} | {s['win_ll']:.4f} {s['podium_ll']:.4f} {s['points_ll']:.4f} | "
              f"{s['top_pick']:.3f} {s['best_of_rest']:.3f}")
    print("\n  net_dnf removes the reliability double-count (reliability -> hazard model only).")
