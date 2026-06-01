"""FastF1 ingest: load a session and normalize laps to a Polars frame.

FastF1 returns pandas with Timedelta columns; we convert at this boundary so the
rest of the pipeline is pure Polars (per project conventions).
"""

from __future__ import annotations

import logging
import warnings

import polars as pl

from app.config import get_settings
from app.engine.params import RegulationEra

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)

_CACHE_READY = False


def _ensure_cache() -> None:
    global _CACHE_READY
    if not _CACHE_READY:
        import os

        import fastf1

        cache = get_settings().fastf1_cache_dir
        os.makedirs(cache, exist_ok=True)
        fastf1.Cache.enable_cache(cache)
        _CACHE_READY = True


def era_for_year(year: int) -> RegulationEra:
    """2022-2025 is the ground-effect/DRS era; 2026+ is active aero."""
    return (
        RegulationEra.ACTIVE_AERO_2026
        if year >= 2026
        else RegulationEra.GROUND_EFFECT_DRS
    )


def _td_seconds(series) -> pl.Series:
    """Convert a pandas Timedelta column to float seconds (NaT -> null)."""
    return pl.from_pandas(series.dt.total_seconds())


# Normalized lap columns we keep across the pipeline.
LAP_COLUMNS = [
    "year",
    "circuit",
    "session_name",
    "regulation_era",
    "driver",
    "driver_number",
    "team",
    "lap_number",
    "stint",
    "compound",
    "tyre_life",
    "fresh_tyre",
    "lap_time_s",
    "sector1_s",
    "sector2_s",
    "sector3_s",
    "speed_st",
    "track_status",
    "position",
    "is_pit_out",
    "is_pit_in",
    "is_accurate",
]


def load_session_laps(year: int, gp: str | int, session: str) -> pl.DataFrame:
    """Load one session's laps as a normalized Polars DataFrame.

    ``session`` is one of FP1/FP2/FP3/Q/SQ/Sprint/R. Telemetry is not loaded
    (not needed for fuel/tyre calibration), keeping this fast.
    """
    _ensure_cache()
    import fastf1

    s = fastf1.get_session(year, gp, session)
    s.load(laps=True, telemetry=False, weather=False, messages=False)
    laps = s.laps
    if laps is None or len(laps) == 0:
        return pl.DataFrame(schema={c: pl.Utf8 for c in LAP_COLUMNS})

    circuit = str(s.event["EventName"]).replace(" Grand Prix", "").strip()

    df = pl.DataFrame(
        {
            "driver": pl.from_pandas(laps["Driver"]),
            "driver_number": pl.from_pandas(laps["DriverNumber"]).cast(
                pl.Int32, strict=False
            ),
            "team": pl.from_pandas(laps["Team"]),
            "lap_number": pl.from_pandas(laps["LapNumber"]).cast(pl.Int32, strict=False),
            "stint": pl.from_pandas(laps["Stint"]).cast(pl.Int32, strict=False),
            "compound": pl.from_pandas(laps["Compound"]),
            "tyre_life": pl.from_pandas(laps["TyreLife"]).cast(pl.Int32, strict=False),
            "fresh_tyre": pl.from_pandas(laps["FreshTyre"]).cast(pl.Boolean, strict=False),
            "lap_time_s": _td_seconds(laps["LapTime"]),
            "sector1_s": _td_seconds(laps["Sector1Time"]),
            "sector2_s": _td_seconds(laps["Sector2Time"]),
            "sector3_s": _td_seconds(laps["Sector3Time"]),
            "speed_st": pl.from_pandas(laps["SpeedST"]).cast(pl.Float64, strict=False),
            "track_status": pl.from_pandas(laps["TrackStatus"]).cast(pl.Utf8),
            "position": pl.from_pandas(laps["Position"]).cast(pl.Int32, strict=False),
            "pit_in_s": _td_seconds(laps["PitInTime"]),
            "pit_out_s": _td_seconds(laps["PitOutTime"]),
            "is_accurate": pl.from_pandas(laps["IsAccurate"]).cast(pl.Boolean, strict=False),
        }
    )

    df = df.with_columns(
        pl.lit(year).alias("year"),
        pl.lit(circuit).alias("circuit"),
        pl.lit(session).alias("session_name"),
        pl.lit(era_for_year(year).value).alias("regulation_era"),
        pl.col("pit_in_s").is_not_null().alias("is_pit_in"),
        pl.col("pit_out_s").is_not_null().alias("is_pit_out"),
    )
    return df.select(LAP_COLUMNS)
