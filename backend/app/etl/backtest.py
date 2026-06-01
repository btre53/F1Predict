"""Backtest the model's probabilities against real race outcomes.

For every historical race in the archive we:
  1. recompute driver pace offsets **excluding that race** (leave-one-race-out, to
     avoid the most direct lookahead bias),
  2. predict the race with the Monte Carlo engine using the *actual* starting grid,
  3. score the model's win / podium / points probabilities against what happened.

Outputs proper scoring rules (Brier, log-loss), a calibration curve, and a
comparison vs a naive grid-favourite baseline. Writes data/backtest.json.

Honesty notes (surfaced in the UI):
  * Circuit base-lap / tyre curves are still fit in-sample (a circuit property, not
    a per-race prediction edge); only driver pace is left-one-out.
  * Sample size is small — this is a calibration check, not a p-value.
  * No real market prices are used here; model-vs-market (Polymarket de-vig) is a
    separate, live capability — see app/etl/polymarket.py.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from app.engine import calibration_store as store
from app.engine.montecarlo import GridEntry, run_race_simulation
from app.engine.predict import TEAM_COLOURS
from app.engine.strategy import optimize_strategy
from app.etl.calibrate import calibrate_drivers

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
BACKTEST_JSON = DATA_DIR / "backtest.json"

_EPS = 1e-6


def load_backtest() -> dict | None:
    """Read the precomputed backtest results (None if not run yet)."""
    if BACKTEST_JSON.exists():
        return json.loads(BACKTEST_JSON.read_text())
    return None


def _actual_finish(race: pl.DataFrame) -> dict[str, int]:
    """Finishing position per driver: rank by (laps completed desc, last pos asc)."""
    last = (
        race.with_columns(pl.col("lap_number").max().over("driver").alias("mx"))
        .filter(pl.col("lap_number") == pl.col("mx"))
        .unique(subset=["driver"], keep="first")
        .select(["driver", "lap_number", "position"])
        .with_columns(pl.col("position").fill_null(99))
        .sort(["lap_number", "position"], descending=[True, False])
    )
    return {r["driver"]: i + 1 for i, r in enumerate(last.to_dicts())}


def _grid_order(race: pl.DataFrame) -> list[str]:
    """Actual starting grid = lap-1 positions (pre-race info, no lookahead)."""
    g1 = (
        race.filter(pl.col("lap_number") == 1)
        .filter(pl.col("position").is_not_null())
        .sort("position")
    )
    return [r["driver"] for r in g1.to_dicts()]


def _predict_race(
    circuit: str,
    year: int,
    full: pl.DataFrame,
    race: pl.DataFrame,
    *,
    n_sims: int,
    strat_cache: dict,
) -> dict[str, dict] | None:
    cp = store.circuit_params_for(circuit)
    overrides = store.tyre_overrides_for(circuit)

    # Leave-one-race-out driver pace offsets.
    excl = full.filter(~((pl.col("circuit") == circuit) & (pl.col("year") == year)))
    offsets = {d["driver"]: d for d in calibrate_drivers(excl)}

    grid = _grid_order(race)
    if not grid:
        return None

    key = circuit
    if key not in strat_cache:
        opt = optimize_strategy(cp, max_stops=2, tyre_overrides=overrides, top_k=1)
        strat_cache[key] = opt[0].strategy if opt else None
    strategy = strat_cache[key]
    if strategy is None:
        return None

    entries: list[GridEntry] = []
    for i, drv in enumerate(grid):
        o = offsets.get(drv)
        team = o["team"] if o else ""
        entries.append(
            GridEntry(
                driver=drv,
                strategy=strategy,
                pace_offset_s=float(o["pace_offset_s"]) if o else 0.0,
                grid_pos=i + 1,
                team=team,
                colour=TEAM_COLOURS.get(team, "888888"),
                # deg_multiplier left at 1.0 — per-team tyre form is display-only
                # (pooled-season team form degrades per-race predictions).
            )
        )
    res = run_race_simulation(cp, entries, n_sims=n_sims, tyre_overrides=overrides)
    return {o.driver: o for o in res.outcomes}


def _baseline_win(grid: list[str], tau: float = 3.0) -> dict[str, float]:
    """Naive grid-favourite win probabilities: w_g = exp(-(g-1)/tau), normalized."""
    w = {d: math.exp(-i / tau) for i, d in enumerate(grid)}
    z = sum(w.values()) or 1.0
    return {d: v / z for d, v in w.items()}


def run_backtest(n_sims: int = 4000) -> dict:
    if not LAPS_PARQUET.exists():
        raise FileNotFoundError("Run the ingest + calibrate first")
    full = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")

    race_keys = (
        full.select(["circuit", "year"]).unique().sort(["year", "circuit"]).to_dicts()
    )
    calibrated = set(store.available_circuits())

    # Collected (probability, outcome) pairs for each metric.
    pairs = {"win": [], "podium": [], "points": []}
    base_win_pairs: list[tuple[float, int]] = []
    per_race: list[dict] = []
    strat_cache: dict = {}

    for rk in race_keys:
        circuit, year = rk["circuit"], rk["year"]
        if circuit not in calibrated:
            continue
        race = full.filter(
            (pl.col("circuit") == circuit) & (pl.col("year") == year)
        )
        actual = _actual_finish(race)
        if not actual:
            continue
        probs = _predict_race(
            circuit, year, full, race, n_sims=n_sims, strat_cache=strat_cache
        )
        if not probs:
            continue
        grid = _grid_order(race)
        base = _baseline_win(grid)

        winner = min(actual, key=actual.get)
        model_winner = max(probs, key=lambda d: probs[d].win_pct)
        for drv, fin in actual.items():
            o = probs.get(drv)
            if o is None:
                continue
            pairs["win"].append((o.win_pct, int(fin == 1)))
            pairs["podium"].append((o.podium_pct, int(fin <= 3)))
            pairs["points"].append((o.points_pct, int(fin <= 10)))
            base_win_pairs.append((base.get(drv, 0.0), int(fin == 1)))

        per_race.append(
            {
                "circuit": circuit,
                "year": year,
                "actual_winner": winner,
                "model_top_pick": model_winner,
                "model_win_pct": round(probs[model_winner].win_pct, 3),
                "hit": winner == model_winner,
            }
        )

    out = {
        "n_races": len(per_race),
        "n_sims": n_sims,
        "metrics": {k: _score(v) for k, v in pairs.items()},
        "baseline_win": _score(base_win_pairs),
        "calibration_win": _calibration(pairs["win"]),
        "top_pick_accuracy": round(
            np.mean([p["hit"] for p in per_race]) if per_race else 0.0, 3
        ),
        "per_race": per_race,
    }
    BACKTEST_JSON.write_text(json.dumps(out, indent=2))
    return out


def _score(pairs: list[tuple[float, int]]) -> dict:
    if not pairs:
        return {"brier": None, "logloss": None, "n": 0, "base_rate": None}
    p = np.clip(np.array([x[0] for x in pairs]), _EPS, 1 - _EPS)
    o = np.array([x[1] for x in pairs], dtype=float)
    brier = float(np.mean((p - o) ** 2))
    logloss = float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p)))
    return {
        "brier": round(brier, 4),
        "logloss": round(logloss, 4),
        "n": len(pairs),
        "base_rate": round(float(o.mean()), 4),
    }


def _calibration(pairs: list[tuple[float, int]], n_bins: int = 5) -> list[dict]:
    """Reliability curve: predicted vs observed frequency per probability bin."""
    if not pairs:
        return []
    p = np.array([x[0] for x in pairs])
    o = np.array([x[1] for x in pairs], dtype=float)
    bins = np.linspace(0, 1, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (p >= lo) & (p < hi if i < n_bins - 1 else p <= hi)
        if mask.sum() == 0:
            continue
        out.append(
            {
                "bin": f"{int(lo*100)}-{int(hi*100)}%",
                "predicted": round(float(p[mask].mean()), 3),
                "observed": round(float(o[mask].mean()), 3),
                "n": int(mask.sum()),
            }
        )
    return out


if __name__ == "__main__":
    r = run_backtest()
    m = r["metrics"]
    print(f"Backtested {r['n_races']} races ({r['n_sims']} sims each)")
    print(f"  top-pick winner accuracy: {r['top_pick_accuracy']:.1%}")
    for k in ("win", "podium", "points"):
        s = m[k]
        print(f"  {k:7s} Brier={s['brier']} logloss={s['logloss']} (n={s['n']}, base={s['base_rate']})")
    print(f"  baseline win Brier={r['baseline_win']['brier']} (grid-favourite)")
    print(f"  -> wrote {BACKTEST_JSON}")
