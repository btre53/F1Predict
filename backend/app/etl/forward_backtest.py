"""Strict forward-chaining backtest — the leak-free version.

For each race, the model is built ONLY from information available before lights-out:
  * driver pace      -> calibrated from races strictly BEFORE this one (chronological)
  * tyre degradation -> fit from THIS weekend's free-practice long runs (pre-race)
  * base lap time    -> fastest clean lap of THIS weekend's practice (pre-race)
  * starting grid    -> the actual lap-1 order (pre-race)

This removes the in-sample lookahead in the simpler `backtest.py` (which fit tyre
curves and pooled driver pace on the full dataset, including the race being scored).
Residual, documented leakage: per-team tyre multipliers and the safety-car model are
still global priors (stable properties, not per-race edges).

Writes data/forward_backtest.json. Network only to read the season schedule (cached).
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from app.engine import calibration_store as store
from app.engine.montecarlo import GridEntry, run_race_simulation
from app.engine.params import CircuitParams, Compound
from app.engine.predict import TEAM_COLOURS
from app.engine.strategy import optimize_strategy
from app.engine.tyres import fit_tyre_parameters, seed_for
from app.etl import backtest as bt
from app.etl.calibrate import calibrate_drivers

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
PRACTICE_PARQUET = DATA_DIR / "practice.parquet"
FORWARD_JSON = DATA_DIR / "forward_backtest.json"

DRY = ("SOFT", "MEDIUM", "HARD")
MIN_PRIOR_RACES = 5  # need enough history for a pace estimate


def load_forward_backtest() -> dict | None:
    if FORWARD_JSON.exists():
        return json.loads(FORWARD_JSON.read_text())
    return None


def _race_seq() -> dict[tuple[int, str], int]:
    """Chronological index per (year, circuit) from the FastF1 schedules."""
    from app.etl.fastf1_client import _ensure_cache

    _ensure_cache()
    import fastf1

    ordered: list[tuple[int, int, str]] = []
    for year in (2023, 2024):
        sched = fastf1.get_event_schedule(year, include_testing=False)
        for _, row in sched.iterrows():
            rnd = int(row["RoundNumber"])
            if rnd == 0:
                continue
            circuit = str(row["EventName"]).replace(" Grand Prix", "").strip()
            ordered.append((year, rnd, circuit))
    ordered.sort(key=lambda t: (t[0], t[1]))
    return {(y, c): i for i, (y, r, c) in enumerate(ordered)}


def _fp_clean(practice: pl.DataFrame, circuit: str, year: int) -> pl.DataFrame:
    return practice.filter(
        (pl.col("circuit") == circuit)
        & (pl.col("year") == year)
        & (pl.col("track_status") == "1")
        & pl.col("is_accurate")
        & ~pl.col("is_pit_out")
        & ~pl.col("is_pit_in")
        & pl.col("lap_time_s").is_not_null()
        & pl.col("compound").is_in(DRY)
    )


def tyre_params_from_practice(practice: pl.DataFrame, circuit: str, year: int) -> dict:
    """Fit the 3-phase curve per compound from this weekend's FP long runs.

    No fuel correction (FP fuel is unknown); we use stint-relative residuals
    (lap minus the stint's best lap vs tyre age), which captures the deg *shape*.
    """
    sub = _fp_clean(practice, circuit, year)
    if sub.height == 0:
        return {}
    stint_min = sub.group_by(["driver", "stint"]).agg(
        pl.col("lap_time_s").min().alias("base"), pl.len().alias("slen")
    )
    sub = sub.join(stint_min, on=["driver", "stint"]).filter(pl.col("slen") >= 6)
    sub = sub.with_columns(
        (pl.col("lap_time_s") - pl.col("base")).alias("resid")
    )
    out: dict[Compound, object] = {}
    for comp in DRY:
        c = sub.filter(pl.col("compound") == comp)
        if c.height < 25:
            continue
        ages = c["tyre_life"].to_numpy().astype(float)
        resid = c["resid"].to_numpy().astype(float)
        tp = fit_tyre_parameters(ages, resid, pace_offset_s=seed_for(Compound(comp)).pace_offset_s)
        out[Compound(comp)] = tp
    return out


def _fp_base_lap_ms(practice: pl.DataFrame, circuit: str, year: int) -> int | None:
    sub = _fp_clean(practice, circuit, year)
    if sub.height == 0:
        return None
    return int(float(sub["lap_time_s"].min()) * 1000)


def run_forward_backtest(n_sims: int = 4000) -> dict:
    full = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")
    practice = (
        pl.read_parquet(PRACTICE_PARQUET)
        if PRACTICE_PARQUET.exists()
        else pl.DataFrame()
    )
    seq = _race_seq()

    # Attach chronological index to each lap's race.
    keys = full.select(["circuit", "year"]).unique().to_dicts()
    pairs = {"win": [], "podium": [], "points": []}
    per_race: list[dict] = []
    strat_cache: dict = {}
    skipped = 0

    race_keys = sorted(
        keys, key=lambda k: seq.get((k["year"], k["circuit"]), 1_000)
    )
    for rk in race_keys:
        circuit, year = rk["circuit"], rk["year"]
        s = seq.get((year, circuit))
        if s is None:
            continue
        race = full.filter(
            (pl.col("circuit") == circuit) & (pl.col("year") == year)
        )
        actual = bt._actual_finish(race)
        if not actual:
            continue

        # Prior races only (chronologically before this one).
        prior_pairs = [k for k in keys if seq.get((k["year"], k["circuit"]), 1_000) < s]
        if len(prior_pairs) < MIN_PRIOR_RACES:
            skipped += 1
            continue
        prior_keys = {(k["year"], k["circuit"]) for k in prior_pairs}
        prior = full.filter(
            pl.struct(["year", "circuit"]).map_elements(
                lambda r: (r["year"], r["circuit"]) in prior_keys,
                return_dtype=pl.Boolean,
            )
        )
        offsets = {d["driver"]: d for d in calibrate_drivers(prior)}

        # Pre-race tyre + base lap from this weekend's FP (fall back to seeds).
        overrides = tyre_params_from_practice(practice, circuit, year) if practice.height else {}
        base_ms = _fp_base_lap_ms(practice, circuit, year) if practice.height else None
        total_laps = int(race["lap_number"].max())
        cp = CircuitParams(
            name=circuit,
            base_lap_ms=base_ms or store.circuit_params_for(circuit).base_lap_ms,
            total_laps=total_laps,
        )

        grid = bt._grid_order(race)
        if not grid:
            continue
        ck = (circuit, year)
        if ck not in strat_cache:
            opt = optimize_strategy(cp, max_stops=2, tyre_overrides=overrides, top_k=1)
            strat_cache[ck] = opt[0].strategy if opt else None
        strategy = strat_cache[ck]
        if strategy is None:
            continue

        entries = []
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
                    # deg_multiplier 1.0 — per-team tyre form is display-only.
                )
            )
        res = run_race_simulation(cp, entries, n_sims=n_sims, tyre_overrides=overrides)
        probs = {o.driver: o for o in res.outcomes}

        winner = min(actual, key=actual.get)
        model_winner = max(probs, key=lambda d: probs[d].win_pct)
        for drv, fin in actual.items():
            o = probs.get(drv)
            if o is None:
                continue
            pairs["win"].append((o.win_pct, int(fin == 1)))
            pairs["podium"].append((o.podium_pct, int(fin <= 3)))
            pairs["points"].append((o.points_pct, int(fin <= 10)))
        per_race.append(
            {
                "circuit": circuit,
                "year": year,
                "n_prior_races": len(prior_pairs),
                "fp_calibrated": bool(overrides),
                "actual_winner": winner,
                "model_top_pick": model_winner,
                "model_win_pct": round(probs[model_winner].win_pct, 3),
                "hit": winner == model_winner,
            }
        )

    out = {
        "n_races": len(per_race),
        "n_skipped_insufficient_history": skipped,
        "n_sims": n_sims,
        "metrics": {k: bt._score(v) for k, v in pairs.items()},
        "calibration_win": bt._calibration(pairs["win"]),
        "top_pick_accuracy": round(
            sum(p["hit"] for p in per_race) / len(per_race), 3
        )
        if per_race
        else 0.0,
        "per_race": per_race,
    }
    FORWARD_JSON.write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    r = run_forward_backtest()
    print(
        f"Forward-chained backtest: {r['n_races']} races "
        f"(skipped {r['n_skipped_insufficient_history']} for thin history)"
    )
    print(f"  top-pick winner accuracy: {r['top_pick_accuracy']:.1%}")
    for k in ("win", "podium", "points"):
        s = r["metrics"][k]
        print(f"  {k:7s} Brier={s['brier']} logloss={s['logloss']} (n={s['n']})")
    print(f"  -> wrote {FORWARD_JSON}")
