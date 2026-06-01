"""Authoritative per-car race classification (DNF flag + cause) from FastF1 results.

laps.parquet can't reliably tell a retirement from a lapped finisher. FastF1's
`session.results` gives `ClassifiedPosition` ('R'=retired, 'W'=DNS, 'D'=DSQ, numeric=
classified) and a `Status` string with the cause ('Accident', 'Power Unit', 'Gearbox'...),
both offline from the cache. We extract just what the hazard model needs and cache it to
data/results.parquet. (The Ergast/Jolpica read-timeout during load is non-fatal -- results
come from the F1 timing API.)
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import polars as pl

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
RESULTS_PARQUET = DATA_DIR / "results.parquet"

# Coarse cause classes from the FastF1 Status string.
_COLLISION = ("Accident", "Collision", "Spun", "Damage", "Debris", "Crash")
_MECHANICAL = ("Engine", "Power Unit", "Gearbox", "Hydraulics", "Transmission",
               "Electrical", "Brakes", "Suspension", "Cooling", "Oil", "Fuel",
               "Wheel", "Driveshaft", "Throttle", "Clutch", "Turbo", "Water",
               "Mechanical", "Battery", "ERS", "Exhaust", "Radiator", "Vibrations",
               "Overheating", "Tyre", "Puncture", "Retired", "Withdrew")


def _cause(status: str) -> str:
    s = status or ""
    if any(k in s for k in _COLLISION):
        return "collision"
    if any(k in s for k in _MECHANICAL):
        return "mechanical"
    return "other"


def build_results() -> pl.DataFrame:
    import fastf1

    from app.config import get_settings

    fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)

    laps = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")
    races = laps.select(["year", "circuit"]).unique().sort(["year", "circuit"]).to_dicts()

    rows: list[dict] = []
    for rk in races:
        year, circuit = rk["year"], rk["circuit"]
        try:
            s = fastf1.get_session(year, circuit, "R")
            s.load(laps=False, telemetry=False, weather=False, messages=False)
            res = s.results
        except Exception as e:  # noqa: BLE001
            print(f"  skip {year} {circuit}: {e}")
            continue
        if res is None or len(res) == 0:
            continue
        for _, r in res.iterrows():
            cls = str(r.get("ClassifiedPosition", ""))
            status = str(r.get("Status", ""))
            dns = cls in ("W", "F")  # withdrew / failed to qualify -> never at risk
            dnf = cls == "R"          # retired during the race
            rows.append({
                "year": year, "circuit": circuit,
                "driver": str(r.get("Abbreviation", "")),
                "classified_pos": cls,
                "status": status,
                "dns": dns,
                "dnf": dnf,
                "cause": _cause(status) if dnf else "finished",
            })
        print(f"  {year} {circuit}: {len(res)} cars")

    df = pl.DataFrame(rows)
    df.write_parquet(RESULTS_PARQUET)
    print(f"\nwrote {RESULTS_PARQUET} ({df.height} car-races, "
          f"{df.filter(pl.col('dnf')).height} DNFs)")
    return df


if __name__ == "__main__":
    build_results()
