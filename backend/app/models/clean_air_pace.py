"""Clean-air race pace per car per race — a MEASURED pace observable (brief 22 decoupling).

The Kalman strength is a LUMP (fit on quali gap + finishing position), so it conflates pace
with tyre deg, reliability, traffic and strategy — which the structural sim then double-counts.
This module measures the one component the sim should actually anchor on: each car's **race
pace in clean air**, stripped of the things modelled separately, traceable to specific laps:

  corrected_lap = lap_time
                  - fuel_penalty(lap)        # remove the fuel-burn trend (engine model)
                  - degradation_penalty(age) # remove tyre-age deg (the same per-compound curve
                                             #   the sim uses) -> pace at fresh-tyre equivalent

Clean-air filter (v1): a car's *fastest* laps are its unimpeded ones (traffic/defending only
make laps slower), so after correction we take the fast quantile of a car's green laps as its
clean-air pace. This is a robust proxy for "gap-ahead > 1.5 s" without brittle cross-car race-
trace reconstruction (that's the v2 refinement). Everything ties to observed laps — no team
labels, no "good on tyres" assumptions.

Output (data/clean_air_pace.parquet), one row per (year, circuit, driver):
  clean_air_pace_s   median corrected pace over the car's fast clean laps
  clean_air_gap_pct  % gap to the race's fastest clean-air pace (drop-in like quali_gap_pct)
  n_clean_laps       sample size (traceability)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import polars as pl

from app.engine import calibration_store as store
from app.engine.params import Compound
from app.engine.physics import fuel_penalty
from app.engine.tyres import degradation_penalty, seed_for

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
CLEAN_AIR_PARQUET = DATA_DIR / "clean_air_pace.parquet"

DRY = ("SOFT", "MEDIUM", "HARD")
FAST_QUANTILE = 0.40   # fastest 40% of a car's corrected green laps ≈ its clean-air pace
MIN_CLEAN_LAPS = 6     # need a real sample to trust the median


def _tp(circuit: str, comp: Compound):
    return store.tyre_overrides_for(circuit).get(comp) or seed_for(comp)


def build_clean_air_pace(*, force: bool = False) -> pl.DataFrame:
    if CLEAN_AIR_PARQUET.exists() and not force:
        return pl.read_parquet(CLEAN_AIR_PARQUET)

    from app.etl import openf1

    from .features import _race_seq

    laps = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")
    seq = _race_seq()

    rows: list[dict] = []
    for key, race in laps.group_by(["year", "circuit"], maintain_order=True):
        year, circuit = int(key[0]), str(key[1])
        cp = store.circuit_params_for(circuit)
        sub = race.filter(
            (pl.col("track_status").cast(pl.Utf8) == "1")
            & pl.col("is_accurate")
            & ~pl.col("is_pit_out")
            & ~pl.col("is_pit_in")
            & pl.col("lap_time_s").is_not_null()
            & pl.col("compound").is_in(DRY)
        )
        if sub.height == 0:
            continue

        # Fuel + tyre-age correction, per compound (vectorized engine functions).
        parts: list[pl.DataFrame] = []
        for comp in DRY:
            c = sub.filter(pl.col("compound") == comp)
            if c.height == 0:
                continue
            tp = _tp(circuit, comp)
            ages = c["tyre_life"].to_numpy().astype(float)
            lapn = c["lap_number"].to_numpy().astype(float)
            deg = np.asarray(degradation_penalty(ages, tp), dtype=float)
            fuel = np.asarray(fuel_penalty(lapn, cp.fuel), dtype=float)
            corrected = c["lap_time_s"].to_numpy().astype(float) - deg - fuel
            parts.append(c.select(["driver", "lap_number"]).with_columns(pl.Series("corrected", corrected)))
        if not parts:
            continue
        cor = pl.concat(parts).filter(pl.col("corrected").is_finite())  # null tyre_life -> NaN
        if cor.height == 0:
            continue

        # MEASURED clean air where OpenF1 covers the race (gap-to-car-ahead > 1.5s); else the
        # fast-quantile proxy. Same downstream median, but the source is recorded for honesty.
        covered = (year, circuit) in openf1.covered_races()
        clean_set = openf1.clean_lap_set() if covered else set()

        race_rows: list[dict] = []
        for (driver,), dl in cor.group_by(["driver"]):
            if covered:
                mask = [(year, circuit, driver, int(l)) in clean_set
                        for l in dl["lap_number"].to_list()]
                clean = dl.filter(pl.Series(mask))["corrected"].to_numpy()
                source = "openf1"
            else:
                corr = dl["corrected"].to_numpy()
                if len(corr) < MIN_CLEAN_LAPS:
                    continue
                thresh = float(np.quantile(corr, FAST_QUANTILE))
                clean = corr[corr <= thresh]
                source = "proxy"
            clean = clean[np.isfinite(clean)]   # drop laps with a null tyre_life/time -> NaN
            if len(clean) < 3:
                continue
            race_rows.append({
                "year": year, "circuit": circuit, "driver": driver,
                "clean_air_pace_s": round(float(np.median(clean)), 4),
                "n_clean_laps": int(len(clean)), "source": source,
            })
        if not race_rows:
            continue
        fastest = min(r["clean_air_pace_s"] for r in race_rows)
        for r in race_rows:
            r["clean_air_gap_pct"] = round(r["clean_air_pace_s"] / fastest - 1.0, 5)
            r["seq"] = seq.get((year, circuit), 9999)
            rows.append(r)

    out = pl.DataFrame(rows).sort(["seq", "clean_air_gap_pct"])
    out.write_parquet(CLEAN_AIR_PARQUET)
    return out


@lru_cache(maxsize=1)
def clean_air_map() -> dict[tuple[int, str, str], dict]:
    """(year, circuit, driver) -> clean-air pace row, for the model/sim to look up."""
    if not CLEAN_AIR_PARQUET.exists():
        return {}
    return {(int(r["year"]), r["circuit"], r["driver"]): r
            for r in pl.read_parquet(CLEAN_AIR_PARQUET).to_dicts()}


if __name__ == "__main__":
    import sys
    t = build_clean_air_pace(force=True)
    print(f"clean-air pace: {t.height} car-races, {t['seq'].n_unique()} races")
    # Face-validity spot check: a recent race — fastest clean-air cars should be the class field.
    yr = int(t["year"].max())
    last = t.filter(pl.col("year") == yr)
    circ = last.sort("seq")["circuit"][-1]
    show = t.filter((pl.col("year") == yr) & (pl.col("circuit") == circ)).sort("clean_air_gap_pct")
    print(f"\n{circ} {yr} — clean-air pace order:")
    for r in show.head(10).to_dicts():
        print(f"  {r['driver']:4s} gap {r['clean_air_gap_pct']*100:+5.2f}%  ({r['n_clean_laps']} laps)")
