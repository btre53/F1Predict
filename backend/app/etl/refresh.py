"""Idempotent post-race refresh: pull newly-completed races, recalibrate, bust caches.

This is the job a weekly cron (or the in-app scheduler in app.main) calls. It only
ingests races that have already happened and aren't in the archive yet, appends them,
re-runs calibration, and clears the in-process caches so a running API serves the new
data without a restart. Safe to run any time — it no-ops when nothing is new.

    uv run python -m app.etl.refresh
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from app.etl.calibrate import run as calibrate_run
from app.etl.fastf1_client import _ensure_cache
from app.etl.ingest import LAPS_PARQUET, PRACTICE_PARQUET, ingest_events


def _existing(parquet) -> set[tuple[int, str]]:
    if not parquet.exists():
        return set()
    df = pl.read_parquet(parquet, columns=["year", "circuit"]).unique()
    return {(int(r["year"]), r["circuit"]) for r in df.to_dicts()}


def _completed_races(years: list[int] | None = None) -> list[tuple[int, str]]:
    """All race events whose date is in the past, for the given (or recent) years."""
    _ensure_cache()
    import fastf1
    import pandas as pd

    now = pd.Timestamp(dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))
    if years is None:
        y = now.year
        years = [y - 1, y]
    out: list[tuple[int, str]] = []
    for year in years:
        try:
            sched = fastf1.get_event_schedule(year, include_testing=False)
        except Exception:
            continue
        for _, row in sched.iterrows():
            if int(row["RoundNumber"]) == 0:
                continue
            evd = row.get("EventDate")
            if evd is None or pd.isna(evd) or pd.Timestamp(evd) > now:
                continue  # future / undated event
            out.append((year, str(row["EventName"])))
    return out


def _append(parquet, new: pl.DataFrame) -> int:
    if new.height == 0:
        return 0
    if parquet.exists():
        old = pl.read_parquet(parquet)
        combined = pl.concat([old, new], how="vertical_relaxed")
    else:
        combined = new
    combined = combined.unique(
        subset=["year", "circuit", "session_name", "driver", "lap_number"],
        keep="first",
    )
    combined.write_parquet(parquet)
    return combined.height


def _bust_caches() -> None:
    """Clear lru_caches so a running API serves fresh calibration/replay data."""
    from app.engine import calibration_store as store
    from app.engine import replay
    from app.models import features as feat

    for fn in (
        store._load_raw,
        store.load_drivers,
        store.load_team_tyres,
        replay._laps,
        feat._race_seq,
        feat._practice,
    ):
        try:
            fn.cache_clear()
        except Exception:
            pass


def refresh(years: list[int] | None = None) -> dict:
    have = _existing(LAPS_PARQUET)
    todo = [
        (y, gp)
        for (y, gp) in _completed_races(years)
        if (y, str(gp).replace(" Grand Prix", "").strip()) not in have
    ]
    if not todo:
        return {"new_races": 0, "ingested": [], "recalibrated": False}

    laps = ingest_events(todo, sessions=("Q", "R"))
    fp = ingest_events(todo, sessions=("FP1", "FP2"))
    ingested = []
    if laps.height:
        _append(LAPS_PARQUET, laps)
        ingested = sorted(
            {(int(r["year"]), r["circuit"]) for r in laps.select(["year", "circuit"]).unique().to_dicts()}
        )
    if fp.height:
        _append(PRACTICE_PARQUET, fp)

    recalibrated = False
    if laps.height:
        calibrate_run()
        _bust_caches()
        recalibrated = True
    return {"new_races": len(ingested), "ingested": ingested, "recalibrated": recalibrated}


if __name__ == "__main__":
    summary = refresh()
    print(f"refresh: {summary['new_races']} new races ingested {summary['ingested']}")
    print(f"  recalibrated: {summary['recalibrated']}")
