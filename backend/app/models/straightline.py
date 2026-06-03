"""Measured per-car straight-line speed — the "Abu Dhabi straight-line defence" (task #24 cont).

The position-resolution sim (`engine/position_sim`) uses one global pass threshold scaled by the
per-circuit overtaking index. But two cars with the same race pace do NOT pass each other equally:
a car with a straight-line speed advantage clears traffic more easily (and defends better) — the
"Abu Dhabi straight" effect. This module measures that, traceably, from the speed trap.

Decoupling (the project's spine): the index ties ONLY to observed data — each car's median
speed-trap reading (`speed_st`), z-scored WITHIN each race (absolute top speed is circuit-dependent
— Monza fast, Monaco slow — so only the within-race ranking is a car trait). It is NOT a brand
label and NOT folded into pace; it adjusts only HOW a pass resolves given pace.

VALIDATED (brief 28): straight-line z is a stable per-team trait (2024->2025 team corr 0.82) and it
predicts clearing traffic even after controlling for pace strength — in 3,480 resolved
stuck-behind episodes a logistic `pass ~ sl_z + strength` gives sl_z coef +0.094 (se 0.039,
z=2.4): a fast-straight car passes ~5pp more often than a slow-straight one at equal pace.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import polars as pl

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"


@lru_cache(maxsize=1)
def straightline_table() -> pl.DataFrame:
    """Per (year, circuit, driver): sl_z = within-race z-score of the car's median speed-trap."""
    laps = pl.read_parquet(
        LAPS_PARQUET, columns=["year", "circuit", "driver", "session_name", "speed_st"]
    ).filter((pl.col("session_name") == "R") & pl.col("speed_st").is_not_null())
    car = laps.group_by(["year", "circuit", "driver"]).agg(pl.col("speed_st").median().alias("top"))
    return car.with_columns(
        ((pl.col("top") - pl.col("top").mean().over(["year", "circuit"]))
         / (pl.col("top").std().over(["year", "circuit"]) + 1e-9)).alias("sl_z")
    ).select(["year", "circuit", "driver", "sl_z"])


@lru_cache(maxsize=1)
def driver_straightline() -> dict[str, float]:
    """Each current driver's straight-line tendency = mean of their within-race sl_z over their
    most recent season of data. A stable per-car trait (corr 0.82 year-on-year), used to seed the
    sim when a specific race's reading isn't supplied. Falls back to 0 (neutral)."""
    t = straightline_table()
    if t.is_empty():
        return {}
    latest = t["year"].max()
    recent = t.filter(pl.col("year") >= latest - 0)  # current season; widen if sparse
    if recent.height < 20:
        recent = t.filter(pl.col("year") >= latest - 1)
    agg = recent.group_by("driver").agg(pl.col("sl_z").mean().alias("sl"))
    return {r["driver"]: float(r["sl"]) for r in agg.to_dicts()}


if __name__ == "__main__":
    d = driver_straightline()
    print("Driver straight-line speed tendency (within-race speed-trap z, current season):")
    for drv, sl in sorted(d.items(), key=lambda x: -x[1])[:24]:
        print(f"  {drv:4s} {sl:+.2f}")
