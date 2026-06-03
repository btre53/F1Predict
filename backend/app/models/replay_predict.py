"""Model Replay precompute — forward-chained predictions for the methodology sandbox.

For every recent race, run each model variant using ONLY strictly-prior races (leak-free, exactly
as the validators do) and store its predicted win/podium per driver alongside the actual finishing
position. The sandbox (Methodology tab) then lets a user pick a past race + a model and SEE what it
would have predicted vs what happened — making the forward-chaining methodology interactive.

Models shown (the arc): a grid+quali baseline, the production Kalman rank model, the position-
resolution sim, and the position sim + the held-up asymmetry (brief 30). Writes data/model_replay.json.
Rebuilt offline:  uv run python -m app.models.replay_predict
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from app.engine import calibration_store as store
from app.engine.montecarlo import GridEntry
from app.engine.position_sim import run_position_simulation
from app.engine.strategy import optimize_strategy

from . import hazard
from .baseline import GridQualiBaseline
from .features import build_feature_table
from .kalman import KalmanModel
from .probability import strengths_to_probs

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
REPLAY_JSON = DATA_DIR / "model_replay.json"

MODELS = [
    {"id": "baseline", "label": "Baseline (grid + quali)",
     "blurb": "10 lines: z-score the grid and qualifying gap. The bar every fancy model must beat."},
    {"id": "kalman", "label": "Kalman (production)",
     "blurb": "Car + driver pace filter, forward-chained; fuses this race's quali. Ships the app's probabilities."},
    {"id": "position", "label": "Position-resolution sim",
     "blurb": "Track position is a state — you only pass if you're enough faster. Our best ordering engine."},
    {"id": "position_heldup", "label": "Position sim + held-up asymmetry",
     "blurb": "As above, but backmarkers yield to much-faster cars (brief 30) — better win/recovery."},
]


def _probs_from_strengths(drivers, strengths, *, temperature=0.5, dnf=None, n_sims=4000):
    sv = np.array([strengths[d] for d in drivers])
    p = strengths_to_probs(drivers, sv, temperature=temperature,
                           dnf_prob=dnf, n_sims=n_sims, seed=0)
    return {d: {"win": round(p[d]["win"], 4), "podium": round(p[d]["podium"], 4)} for d in drivers}


def build(*, n_recent: int = 40, min_history: int = 30, n_sims: int = 4000,
          sim_sims: int = 3000) -> dict:
    table = build_feature_table()
    seqs = sorted(table["seq"].unique().to_list())
    target = set(seqs[-n_recent:])
    clf, prior = hazard._cached_model()
    kal = KalmanModel(net_dnf=True); kal.reset()
    base = GridQualiBaseline()
    races: list[dict] = []
    seen = 0

    for s in seqs:
        race = table.filter(pl.col("seq") == s)
        if seen >= min_history and s in target and race.height >= 6:
            rows = race.to_dicts()
            kstr = kal.predict(race)
            drivers = [r["driver"] for r in rows if r["driver"] in kstr]
            if len(drivers) >= 6:
                rmap = {r["driver"]: r for r in rows}
                year, circuit = int(rows[0]["year"]), rows[0]["circuit"]
                try:
                    cp = store.circuit_params_for(circuit)
                    ov = store.tyre_overrides_for(circuit)
                except Exception:
                    cp = None
                bstr = base.predict(race)
                # DNF per driver (hazard) keyed by grid for the PL models.
                grid_rank = {d: i + 1 for i, d in enumerate(sorted(drivers, key=lambda x: -kstr[x]))}
                dnf = np.array([hazard.race_dnf_prob(clf, prior, grid=grid_rank[d],
                                team=rmap[d].get("team") or "", year=year, total_laps=57)
                                for d in drivers])
                preds = {
                    "baseline": _probs_from_strengths(drivers, {d: bstr.get(d, 0.0) for d in drivers}, n_sims=n_sims),
                    "kalman": _probs_from_strengths(drivers, kstr, dnf=dnf, n_sims=n_sims),
                }
                if cp is not None:
                    strat = optimize_strategy(cp, max_stops=2, tyre_overrides=ov, top_k=1)[0].strategy
                    with_grid = [d for d in drivers if rmap[d].get("grid") is not None]
                    grid_order = (sorted(with_grid, key=lambda d: rmap[d]["grid"])
                                  if len(with_grid) >= len(drivers) - 2
                                  else sorted(drivers, key=lambda d: -kstr[d]))
                    for d in drivers:
                        if d not in grid_order:
                            grid_order.append(d)
                    gpos = {d: i + 1 for i, d in enumerate(grid_order)}
                    smean = float(np.mean([kstr[d] for d in drivers]))
                    grid = [GridEntry(driver=d, strategy=strat, grid_pos=gpos[d],
                                      pace_offset_s=-(kstr[d] - smean) * 0.9,
                                      dnf_prob=float(dnf[i])) for i, d in enumerate(drivers)]
                    for mid, asym in (("position", False), ("position_heldup", True)):
                        res = run_position_simulation(cp, grid, n_sims=sim_sims, tyre_overrides=ov,
                                                      held_up_asymmetry=asym, seed=11)
                        preds[mid] = {o.driver: {"win": round(o.win_pct, 4),
                                                 "podium": round(o.podium_pct, 4)} for o in res.outcomes}
                drv_rows = []
                for d in sorted(drivers, key=lambda x: rmap[x]["finish_pos"]):
                    drv_rows.append({
                        "driver": d, "team": rmap[d].get("team") or "",
                        "grid": int(rmap[d]["grid"]) if rmap[d].get("grid") is not None else None,
                        "finish": int(rmap[d]["finish_pos"]),
                        "models": {m: preds.get(m, {}).get(d) for m in
                                   ("baseline", "kalman", "position", "position_heldup")},
                    })
                races.append({"year": year, "circuit": circuit, "seq": int(s),
                              "has_sim": cp is not None, "drivers": drv_rows})
        kal.update(race); base.update(race)
        seen += 1

    out = {"models": MODELS, "n_races": len(races), "races": races}
    REPLAY_JSON.write_text(json.dumps(out))
    return out


def load_replay() -> dict | None:
    if REPLAY_JSON.exists():
        return json.loads(REPLAY_JSON.read_text())
    return None


if __name__ == "__main__":
    r = build()
    print(f"Model replay: {r['n_races']} races x {len(r['models'])} models -> {REPLAY_JSON}")
    if r["races"]:
        ex = r["races"][-1]
        print(f"  e.g. {ex['year']} {ex['circuit']}: winner {ex['drivers'][0]['driver']}")
        for m in r["models"]:
            wp = ex["drivers"][0]["models"].get(m["id"])
            print(f"    {m['label']:34s} winner win% = {wp['win'] if wp else '—'}")
