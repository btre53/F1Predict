"""Forward-chained, calibration-first evaluation harness for the model bake-off.

A model implements ``predict(history, race) -> {driver: strength}`` where ``history``
is every race strictly before the current one (so everything is leak-free by
construction). The harness converts strengths to probabilities, scores them against
the realized result (Brier / log-loss / reliability / top-pick), and sweeps a single
global temperature to report the best-calibrated version (calibration is the primary
target). Market (CLV) comparison plugs in later via the Polymarket/Betfair join.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import polars as pl

from .features import build_feature_table
from .probability import softmax, strengths_to_probs

_EPS = 1e-12


class Model(Protocol):
    """Stateful, incrementally-retrainable model.

    The harness drives a forward-chained loop: for each race it calls predict()
    (using only state from prior races), scores it, then calls update() with the
    realized result. update() is exactly what a post-race cronjob calls to keep the
    model current on new data — no full retrain needed for the online models.
    """

    name: str

    def reset(self) -> None:
        """Clear all learned state."""
        ...

    def predict(self, race: pl.DataFrame) -> dict[str, float]:
        """Per-driver strength (higher = faster) from current state + pre-race info."""
        ...

    def update(self, race: pl.DataFrame) -> None:
        """Fold this race's realized result into the state (incremental retrain)."""
        ...


def _brier_logloss(pairs: list[tuple[float, int]]) -> tuple[float, float]:
    p = np.clip(np.array([x[0] for x in pairs]), _EPS, 1 - _EPS)
    o = np.array([x[1] for x in pairs], dtype=float)
    brier = float(np.mean((p - o) ** 2))
    logloss = float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p)))
    return brier, logloss


def run_model(model: Model, *, table: pl.DataFrame | None = None, temperature: float = 1.0,
              min_history: int = 5, n_sims: int = 4000) -> dict:
    """Forward-chain a model over the feature table; score win/podium/points."""
    t = table if table is not None else build_feature_table()
    seqs = sorted(t["seq"].unique().to_list())

    win_pairs: list[tuple[float, int]] = []
    pod_pairs: list[tuple[float, int]] = []
    pts_pairs: list[tuple[float, int]] = []
    top_hits = 0
    bor_hits = 0  # best-of-the-rest: predict P2 with the actual winner removed
    bor_races = 0
    n_races = 0
    seen = 0

    model.reset()
    for s in seqs:
        race = t.filter(pl.col("seq") == s)
        if seen >= min_history and race.height >= 4:
            strengths = model.predict(race)
            drivers = [d for d in race["driver"].to_list() if d in strengths]
            if len(drivers) >= 4:
                sv = np.array([strengths[d] for d in drivers])
                probs = strengths_to_probs(
                    drivers, sv, temperature=temperature, n_sims=n_sims
                )
                rmap = {r["driver"]: r for r in race.to_dicts()}
                winner = min(rmap, key=lambda d: rmap[d]["finish_pos"])
                model_pick = max(drivers, key=lambda d: probs[d]["win"])
                top_hits += int(model_pick == winner)
                n_races += 1
                # Best-of-the-rest: the harder, higher-variance signal — strip the
                # actual winner, does the model's next pick match the real P2?
                actual_bor = next((d for d in drivers if rmap[d]["finish_pos"] == 2), None)
                rest = [d for d in drivers if d != winner]
                if actual_bor is not None and rest:
                    model_bor = max(rest, key=lambda d: strengths[d])
                    bor_hits += int(model_bor == actual_bor)
                    bor_races += 1
                for d in drivers:
                    fin = rmap[d]["finish_pos"]
                    win_pairs.append((probs[d]["win"], int(fin == 1)))
                    pod_pairs.append((probs[d]["podium"], int(fin <= 3)))
                    pts_pairs.append((probs[d]["points"], int(fin <= 10)))
        model.update(race)
        seen += 1

    wb, wl = _brier_logloss(win_pairs)
    pb, pl_ = _brier_logloss(pod_pairs)
    sb, sl = _brier_logloss(pts_pairs)
    return {
        "model": getattr(model, "name", "model"),
        "temperature": temperature,
        "n_races": n_races,
        "top_pick_accuracy": round(top_hits / n_races, 3) if n_races else 0.0,
        "best_of_rest_accuracy": round(bor_hits / bor_races, 3) if bor_races else 0.0,
        "win": {"brier": round(wb, 4), "logloss": round(wl, 4)},
        "podium": {"brier": round(pb, 4), "logloss": round(pl_, 4)},
        "points": {"brier": round(sb, 4), "logloss": round(sl, 4)},
    }


def tune_temperature(model: Model, *, grid=(0.5, 0.75, 1.0, 1.5, 2.0, 3.0),
                     table: pl.DataFrame | None = None) -> dict:
    """Sweep global temperature; pick the one with the best win log-loss."""
    t = table if table is not None else build_feature_table()
    results = [run_model(model, table=t, temperature=T) for T in grid]
    best = min(results, key=lambda r: r["win"]["logloss"])
    return {"best": best, "sweep": results}
