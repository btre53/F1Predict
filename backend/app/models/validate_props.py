"""Score the sim on PROP markets where the JOINT structure matters (task #14).

The rank model and the sim both give marginal win/podium/points. The sim's distinctive value is
its *dependence* structure — physical correlations (pace proximity, safety-car bunching, dirty-air,
per-car deg) vs the rank model's parametric Plackett-Luce joint. So we score JOINT props:
  * head-to-head: P(driver i finishes ahead of driver j) over ALL pairs — the matchup market;
  * podium-without-the-favourite: P(the pre-race favourite finishes off the podium).
Both are computed from each model's per-sim finishing orders (Brier, lower=better), forward-chained.
If the sim beats the rank model here, its physics earns its keep on the markets it's actually for.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from app.engine import calibration_store as store

from . import hazard
from .features import build_feature_table
from .kalman import KalmanModel
from .structural_sim import simulate_field
from .validate_structural_sim import DEFAULT_TEMPERATURE


def _rank_model_ranks(drivers, strengths, dnf, *, temperature, n_sims, seed):
    """Rank-model (anchor) per-sim finishing positions: (n_drivers, n_sims)."""
    n = len(drivers)
    sv = np.array([strengths[d] for d in drivers]) / max(temperature, 1e-6)
    dnf = np.asarray(dnf)
    rng = np.random.default_rng(seed)
    ranks = np.empty((n, n_sims), dtype=np.int32)
    for s in range(n_sims):
        score = np.where(rng.random(n) < dnf, -1e9, sv + rng.gumbel(0.0, 1.0, n))
        order = np.argsort(-score)
        pos = np.empty(n, dtype=np.int32)
        pos[order] = np.arange(1, n + 1)
        ranks[:, s] = pos
    return ranks, drivers


def _props(ranks, drivers, actual: dict, fav: str):
    """(pairwise (p,o) list, (podium_without_fav p, o))."""
    idx = {d: i for i, d in enumerate(drivers)}
    ds = [d for d in drivers if d in actual and d in idx]
    pairs = []
    for a in range(len(ds)):
        ra = ranks[idx[ds[a]]]
        for b in range(a + 1, len(ds)):
            p = float((ra < ranks[idx[ds[b]]]).mean())
            pairs.append((p, int(actual[ds[a]] < actual[ds[b]])))
    pwf = None
    if fav in idx and fav in actual:
        pwf = (float((ranks[idx[fav]] >= 4).mean()), int(actual[fav] >= 4))
    return pairs, pwf


def _brier(pairs):
    if not pairs:
        return None
    p = np.array([x[0] for x in pairs]); o = np.array([x[1] for x in pairs], dtype=float)
    return round(float(np.mean((p - o) ** 2)), 4)


def evaluate(*, n_recent: int = 45, n_sims: int = 4000, min_history: int = 30, seed: int = 7) -> dict:
    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    target = set(seqs[-n_recent:])
    clf, prior = hazard._cached_model()
    model = KalmanModel(net_dnf=True); model.reset()

    res = {tag: {"pair": [], "pwf": []} for tag in ("sim", "anchor")}
    seen = 0
    for s in seqs:
        race = table.filter(pl.col("seq") == s)
        if seen >= min_history and s in target and race.height >= 6:
            rows = race.to_dicts()
            strn = model.predict(race)
            drivers = [r["driver"] for r in rows if r["driver"] in strn]
            if len(drivers) >= 6:
                rmap = {r["driver"]: r for r in rows}
                year = int(rows[0]["year"]); circuit = rows[0]["circuit"]
                cp = store.circuit_params_for(circuit)
                actual = {d: rmap[d]["finish_pos"] for d in drivers}
                fav = max(drivers, key=lambda d: strn[d])
                wg = [d for d in drivers if rmap[d].get("grid") is not None]
                go = (sorted(wg, key=lambda d: rmap[d]["grid"]) if len(wg) >= len(drivers) - 2
                      else sorted(drivers, key=lambda d: -strn[d]))
                for d in drivers:
                    if d not in go:
                        go.append(d)
                gp = {d: i + 1 for i, d in enumerate(go)}
                team = {d: rmap[d].get("team") or "" for d in drivers}
                dnf = {d: hazard.race_dnf_prob(clf, prior, grid=gp[d], team=team[d],
                                               year=year, total_laps=cp.total_laps) for d in drivers}
                # sim ranks (measured dirty-air, calibrated pace)
                sim_res = simulate_field(circuit, strn, grid_order=go, team_of=team, dnf_of=dnf,
                                         cp=cp, measured_dirty_air=True, return_result=True,
                                         n_sims=n_sims, seed=seed)
                sp, spwf = _props(sim_res.ranks, sim_res.rank_drivers, actual, fav)
                # anchor ranks
                ar, ad = _rank_model_ranks(drivers, strn, [dnf[d] for d in drivers],
                                           temperature=DEFAULT_TEMPERATURE, n_sims=n_sims, seed=seed)
                ap, apwf = _props(ar, ad, actual, fav)
                res["sim"]["pair"] += sp; res["anchor"]["pair"] += ap
                if spwf: res["sim"]["pwf"].append(spwf)
                if apwf: res["anchor"]["pwf"].append(apwf)
        model.update(race); seen += 1

    return {tag: {"head_to_head_brier": _brier(res[tag]["pair"]),
                  "podium_without_fav_brier": _brier(res[tag]["pwf"]),
                  "n_pairs": len(res[tag]["pair"])} for tag in ("sim", "anchor")}


if __name__ == "__main__":
    r = evaluate()
    print("Prop-market scoring — sim (measured physics) vs rank model (Brier, lower=better)\n")
    print(f"  {'model':7s} | head-to-head | podium-without-fav")
    for tag in ("anchor", "sim"):
        s = r[tag]
        print(f"  {tag:7s} | {s['head_to_head_brier']:>11} | {s['podium_without_fav_brier']:>11}")
    print(f"\n  (head-to-head over {r['sim']['n_pairs']} driver pairs)")
