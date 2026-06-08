"""Authoritative per-car race classification (DNF flag + cause) from Jolpica results.

laps.parquet can't reliably tell a retirement from a lapped finisher. Jolpica (the Ergast
successor) gives `positionText` ('R'=retired, 'W'/'F'/'N'=DNS/unclassified, 'D'/'E'=DSQ,
numeric=classified) and a `status` string with the cause ('Accident', 'Engine', 'Gearbox'...).
We extract just what the hazard model + championship standings need and cache it to
data/results.parquet. Jolpica is datacenter-friendly, so this runs on the VPS where FastF1's
results endpoint is blocked (see the f1-datacenter-ip-block finding)."""

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
    from app.etl import jolpica as jol

    laps = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")
    have = {(int(r["year"]), r["circuit"])
            for r in laps.select(["year", "circuit"]).unique().to_dicts()}
    years = sorted({y for (y, _) in have})

    rows: list[dict] = []
    for year in years:
        offset = 0
        while True:
            j = jol._get(f"{year}/results.json", limit=100, offset=offset)
            if not j:
                break
            races = j["MRData"]["RaceTable"]["Races"]
            if not races:
                break
            for race in races:
                circuit = str(race["raceName"]).replace(" Grand Prix", "").strip()
                if (year, circuit) not in have:
                    continue
                for r in race.get("Results", []):
                    code = r.get("Driver", {}).get("code")
                    if not code:
                        continue
                    cls = str(r.get("positionText", ""))
                    status = str(r.get("status", ""))
                    dns = cls in ("W", "F", "N")  # withdrew / failed / not classified
                    dnf = cls == "R"               # retired during the race
                    rows.append({
                        "year": year, "circuit": circuit, "driver": code,
                        "classified_pos": cls, "status": status,
                        "dns": dns, "dnf": dnf,
                        "cause": _cause(status) if dnf else "finished",
                    })
            total = int(j["MRData"]["total"])
            offset += 100
            if offset >= total:
                break

    df = pl.DataFrame(rows)
    df.write_parquet(RESULTS_PARQUET)
    print(f"wrote {RESULTS_PARQUET} ({df.height} car-races, "
          f"{df.filter(pl.col('dnf')).height} DNFs)")
    return df


if __name__ == "__main__":
    build_results()
