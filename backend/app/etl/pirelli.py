"""Pirelli compound nominations: map a weekend's relative SOFT/MEDIUM/HARD to the ABSOLUTE
C-compound (C0..C6) — so tyre deg is comparable across races (brief 24, task #18).

FastF1 only gives the *relative* compound (the softest of the three nominated = SOFT, etc.),
so the same physical compound can be "SOFT" at one race and "MEDIUM" at another. Pirelli's
per-race C-number nomination (no API; sourced from press releases + season tables) pins the
absolute compound, which is what actually drives degradation.

Data: data/pirelli_compounds.json — {year: {circuit: {"hard":"C1","medium":"C2","soft":"C3"}}}.
Sourced, never fabricated: races without a confirmed nomination are simply absent (-> None).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PIRELLI_JSON = DATA_DIR / "pirelli_compounds.json"

_REL = {"SOFT": "soft", "MEDIUM": "medium", "HARD": "hard"}


@lru_cache(maxsize=1)
def _raw() -> dict:
    if PIRELLI_JSON.exists():
        try:
            return json.loads(PIRELLI_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


@lru_cache(maxsize=1)
def compound_map() -> dict[tuple[int, str], dict[str, str]]:
    """(year, circuit) -> {"SOFT": "C3", "MEDIUM": "C2", "HARD": "C1"} (uppercase relative keys)."""
    out: dict[tuple[int, str], dict[str, str]] = {}
    for year, races in _raw().items():
        for circuit, comps in races.items():
            m = {rel: comps.get(low) for rel, low in _REL.items() if comps.get(low)}
            if m:
                out[(int(year), circuit)] = m
    return out


def absolute_compound(year: int, circuit: str, relative: str) -> str | None:
    """Absolute C-compound (e.g. 'C3') for a relative SOFT/MEDIUM/HARD at a race, or None."""
    return compound_map().get((int(year), circuit), {}).get(str(relative).upper())


def validate_absolute_deg() -> dict:
    """Does the absolute C-compound track degradation (softer C -> faster deg)?

    For covered races, fit each stint's fuel-corrected deg slope and group by absolute C-number.
    If mean deg rises monotonically with the C-number, the table is a valid, value-adding deg
    descriptor that FastF1's relative SOFT/MEDIUM/HARD can't give. Returns mean slope per C.
    """
    import numpy as np
    import polars as pl

    from app.engine import calibration_store as store
    from app.engine.physics import fuel_penalty

    cm = compound_map()
    if not cm:
        return {"covered_races": 0}
    laps = pl.read_parquet(DATA_DIR / "laps.parquet").filter(
        (pl.col("session_name") == "R") & (pl.col("track_status").cast(pl.Utf8) == "1")
        & pl.col("is_accurate") & ~pl.col("is_pit_in") & ~pl.col("is_pit_out")
        & pl.col("lap_time_s").is_not_null() & pl.col("compound").is_in(["SOFT", "MEDIUM", "HARD"])
        & pl.col("tyre_life").is_not_null()
    )
    by_c: dict[str, list[float]] = {}
    by_rel: dict[str, list[float]] = {}
    for key, race in laps.group_by(["year", "circuit"]):
        year, circuit = int(key[0]), str(key[1])
        if (year, circuit) not in cm:
            continue
        cp = store.circuit_params_for(circuit)
        for (_d, _s, comp), st in race.group_by(["driver", "stint", "compound"]):
            st = st.filter(pl.col("tyre_life") >= 2)
            if st.height < 8:
                continue
            ages = st["tyre_life"].to_numpy().astype(float)
            if len(np.unique(ages)) < 5:
                continue
            lapn = st["lap_number"].to_numpy().astype(float)
            corr = st["lap_time_s"].to_numpy().astype(float) - np.asarray(fuel_penalty(lapn, cp.fuel), float)
            if not np.all(np.isfinite(corr)):
                continue
            slope = float(np.polyfit(ages, corr, 1)[0])
            if abs(slope) > 0.6:
                continue
            c = absolute_compound(year, circuit, str(comp))
            if c:
                by_c.setdefault(c, []).append(slope)
            by_rel.setdefault(str(comp), []).append(slope)

    import numpy as np
    def summ(d):
        return {k: {"mean_deg_s_per_lap2": round(float(np.mean(v)), 4), "n": len(v)}
                for k, v in sorted(d.items())}
    return {"covered_races": len(cm), "by_absolute_C": summ(by_c), "by_relative": summ(by_rel)}


def coverage() -> dict:
    cm = compound_map()
    years: dict[int, int] = {}
    for (y, _c) in cm:
        years[y] = years.get(y, 0) + 1
    return {"races": len(cm), "by_year": dict(sorted(years.items()))}


if __name__ == "__main__":
    c = coverage()
    print(f"Pirelli compound table: {c['races']} races covered")
    print("  by year:", c["by_year"])
