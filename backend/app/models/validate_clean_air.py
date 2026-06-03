"""Is prior-race CLEAN-AIR PACE a predictive, non-redundant anchor? (brief 22 decoupling)

Clean-air pace is measured FROM a race, so it can only predict FUTURE races: we carry a
forward-chained, EWMA belief of each car's clean-air gap from strictly-prior races and ask:
  1. does that prior clean-air-pace belief predict this race's finishing order?
  2. does it add signal beyond this race's qualifying gap (the other clean observable)?
If yes, swapping the lumped "finishing position" Kalman observation for clean-air pace is a
real decoupling, not a loss of signal.

Per-team EWMA (clean-air gap is a car property; a driver inherits the team's pace on a move).
"""

from __future__ import annotations

import numpy as np
import polars as pl
from scipy.stats import spearmanr

from .clean_air_pace import build_clean_air_pace
from .features import build_feature_table

EWMA_ALPHA = 0.45     # weight on the most recent race's clean-air gap
SEASON_REVERT = 0.5   # pull the belief toward the field on a new season (upgrades/regs)


def evaluate(min_history_races: int = 30) -> dict:
    feat = build_feature_table()
    ca = build_clean_air_pace()
    ca_map = {(int(r["year"]), r["circuit"], r["driver"]): r["clean_air_gap_pct"]
              for r in ca.to_dicts()}

    seqs = sorted(feat["seq"].unique().to_list())
    team_belief: dict[str, float] = {}     # team -> EWMA clean-air gap (lower = faster)
    last_year: int | None = None

    pairs = []  # (prior_clean_air, quali_gap, finish_pos)
    for s in seqs:
        race = feat.filter(pl.col("seq") == s).sort("finish_pos")
        rows = race.to_dicts()
        year = int(rows[0]["year"]); circuit = rows[0]["circuit"]
        if last_year is not None and year != last_year:
            for t in team_belief:
                team_belief[t] *= SEASON_REVERT   # revert toward 0 (field) across the winter
        last_year = year

        # Predict (use only beliefs from prior races).
        if s >= seqs[min_history_races]:
            for r in rows:
                t = r["team"]; q = r.get("quali_gap_pct")
                if t in team_belief and q is not None:
                    pairs.append((team_belief[t], float(q), int(r["finish_pos"])))

        # Update beliefs with THIS race's measured clean-air gap (for future races).
        for r in rows:
            g = ca_map.get((year, circuit, r["driver"]))
            if g is None:
                continue
            t = r["team"]
            team_belief[t] = (g if t not in team_belief
                              else EWMA_ALPHA * g + (1 - EWMA_ALPHA) * team_belief[t])

    ca_arr = np.array([p[0] for p in pairs])
    q_arr = np.array([p[1] for p in pairs])
    fin = np.array([p[2] for p in pairs])

    def z(a):
        return (a - a.mean()) / (a.std() + 1e-9)

    rho_ca = spearmanr(ca_arr, fin).correlation
    rho_q = spearmanr(q_arr, fin).correlation
    rho_combined = spearmanr(z(ca_arr) + z(q_arr), fin).correlation
    rho_ca_q = spearmanr(ca_arr, q_arr).correlation  # redundancy between the two signals
    return {
        "n_pairs": len(pairs),
        "spearman_finish": {
            "prior_clean_air": round(float(rho_ca), 3),
            "quali_gap": round(float(rho_q), 3),
            "combined_equal": round(float(rho_combined), 3),
        },
        "clean_air_vs_quali_corr": round(float(rho_ca_q), 3),
    }


def sim_anchor_test(n_recent: int = 45, n_sims: int = 3000, min_history_races: int = 30,
                    w_quali: float = 0.7, w_ca: float = 0.3, pace_scale: float = 0.30,
                    dirty_air_s: float = 0.3, seed: int = 7) -> dict:
    """Anchor the sim on MEASURED (quali + prior clean-air pace) instead of the lumped Kalman,
    at a realistic pace scale, and score win/podium/points vs the rank-model anchor."""
    from app.engine import calibration_store as store
    from . import hazard
    from .structural_sim import simulate_field, dist_to_markets
    from .validate_structural_sim import _rank_model_dist, _score, DEFAULT_TEMPERATURE
    from .kalman import KalmanModel

    feat = build_feature_table()
    ca = build_clean_air_pace()
    ca_map = {(int(r["year"]), r["circuit"], r["driver"]): r["clean_air_gap_pct"] for r in ca.to_dicts()}
    seqs = sorted(feat["seq"].unique().to_list()); target = set(seqs[-n_recent:])
    clf, prior = hazard._cached_model()
    kal = KalmanModel(); kal.reset()
    team_belief: dict[str, float] = {}; last_year = None

    P = {a: {m: [] for m in ("win", "podium", "points")} for a in ("clean", "kalman")}
    for s in seqs:
        race = feat.filter(pl.col("seq") == s).sort("finish_pos"); rows = race.to_dicts()
        year = int(rows[0]["year"]); circuit = rows[0]["circuit"]
        if last_year is not None and year != last_year:
            for t in team_belief: team_belief[t] *= SEASON_REVERT
        last_year = year
        kstr = kal.predict(race)
        if s >= seqs[min_history_races] and s in target and race.height >= 6:
            drv = [r["driver"] for r in rows if r["driver"] in kstr]
            qg = {r["driver"]: r.get("quali_gap_pct") for r in rows}
            if len(drv) >= 6 and all(qg[d] is not None for d in drv):
                rmap = {r["driver"]: r for r in rows}
                cp = store.circuit_params_for(circuit)
                wg = [d for d in drv if rmap[d].get("grid") is not None]
                go = sorted(wg, key=lambda d: rmap[d]["grid"]) if len(wg) >= len(drv) - 2 else sorted(drv, key=lambda d: -kstr[d])
                for d in drv:
                    if d not in go: go.append(d)
                gp = {d: i + 1 for i, d in enumerate(go)}; team = {d: rmap[d].get("team") or "" for d in drv}
                dnf = {d: hazard.race_dnf_prob(clf, prior, grid=gp[d], team=team[d], year=year, total_laps=cp.total_laps) for d in drv}
                # MEASURED anchor: quali (this race) + prior clean-air belief (per team), z-scored.
                q = np.array([qg[d] for d in drv]); qz = -(q - q.mean()) / (q.std() + 1e-9)
                cb = np.array([team_belief.get(team[d], 0.0) for d in drv]); cz = -(cb - cb.mean()) / (cb.std() + 1e-9)
                clean_str = {d: float(w_quali * qz[i] + w_ca * cz[i]) for i, d in enumerate(drv)}
                for tag, st in (("clean", clean_str), ("kalman", kstr)):
                    sim = simulate_field(circuit, st, grid_order=go, team_of=team, dnf_of=dnf, cp=cp,
                                         pace_scale=pace_scale, dirty_air_s=dirty_air_s, n_sims=n_sims, seed=seed)
                    mk = dist_to_markets(sim)
                    for d in drv:
                        f = rmap[d]["finish_pos"]
                        P[tag]["win"].append((mk[d]["win"], int(f == 1)))
                        P[tag]["podium"].append((mk[d]["podium"], int(f <= 3)))
                        P[tag]["points"].append((mk[d]["points"], int(f <= 10)))
        # update beliefs with this race's measured clean-air gap; fold result into Kalman
        for r in rows:
            g = ca_map.get((year, circuit, r["driver"]))
            if g is not None:
                t = r["team"]
                team_belief[t] = g if t not in team_belief else EWMA_ALPHA * g + (1 - EWMA_ALPHA) * team_belief[t]
        kal.update(race)
    return {tag: {m: _score(P[tag][m]) for m in ("win", "podium", "points")} for tag in P}


if __name__ == "__main__":
    r = evaluate()
    s = r["spearman_finish"]
    print(f"Clean-air pace as a forward-chained anchor — {r['n_pairs']} driver-races\n")
    print("Spearman rank-corr with finishing position (higher |.| = more predictive):")
    print(f"  prior clean-air pace : {s['prior_clean_air']}")
    print(f"  this-race quali gap  : {s['quali_gap']}")
    print(f"  the two combined     : {s['combined_equal']}")
    print(f"\nredundancy (clean-air vs quali corr): {r['clean_air_vs_quali_corr']}  "
          f"(<1 ⇒ clean-air adds independent race-pace signal)")
