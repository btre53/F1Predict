"""Batch ingest: load many sessions -> a single normalized Parquet archive.

Usage:
    uv run python -m app.etl.ingest                 # default backfill set
    uv run python -m app.etl.ingest 2023 Bahrain    # one (year, gp): all sessions
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import polars as pl

from app.etl.fastf1_client import load_session_laps

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
PRACTICE_PARQUET = DATA_DIR / "practice.parquet"

# Sessions used for calibration: race (clean long stints, known fuel) + practice
# (extra long runs). Expand this list to scale the backfill.
SESSIONS = ("FP2", "FP3", "R")

# A representative multi-circuit, multi-year set. Grow as needed; cached after first.
DEFAULT_BACKFILL: list[tuple[int, str]] = [
    (2023, "Bahrain"),
    (2023, "Spain"),
    (2023, "Great Britain"),
    (2023, "Italy"),
    (2023, "Singapore"),
    (2024, "Bahrain"),
    (2024, "Spain"),
    (2024, "Italy"),
]


def season_events(year: int) -> list[tuple[int, str]]:
    """Enumerate all race events in a season via the FastF1 schedule."""
    from app.etl.fastf1_client import _ensure_cache

    _ensure_cache()
    import fastf1

    sched = fastf1.get_event_schedule(year, include_testing=False)
    out: list[tuple[int, str]] = []
    for _, row in sched.iterrows():
        if int(row["RoundNumber"]) == 0:
            continue
        out.append((year, str(row["EventName"])))
    return out


def ingest_events(
    events: list[tuple[int, str]], sessions: tuple[str, ...] = SESSIONS
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for year, gp in events:
        for sess in sessions:
            t0 = time.time()
            try:
                df = load_session_laps(year, gp, sess)
                if df.height:
                    frames.append(df)
                print(
                    f"  [{year} {gp} {sess}] {df.height} laps "
                    f"({time.time() - t0:.1f}s)",
                    flush=True,
                )
            except Exception as e:  # noqa: BLE001 — keep going on a bad session
                print(f"  [{year} {gp} {sess}] SKIP: {type(e).__name__}: {e}", flush=True)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="vertical_relaxed")


def run(
    events: list[tuple[int, str]] | None = None,
    sessions: tuple[str, ...] = SESSIONS,
    out_path: Path = LAPS_PARQUET,
) -> Path:
    events = events or DEFAULT_BACKFILL
    DATA_DIR.mkdir(exist_ok=True)
    print(f"Ingesting {len(events)} events x {len(sessions)} sessions -> {out_path.name}")
    df = ingest_events(events, sessions=sessions)
    if df.height == 0:
        print("No data ingested.")
        return out_path
    df.write_parquet(out_path)
    print(
        f"Wrote {df.height} laps for "
        f"{df['circuit'].n_unique()} circuits -> {out_path}"
    )
    return out_path


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in ("--seasons", "--practice"):
        years = [int(y) for y in sys.argv[2:]]
        events: list[tuple[int, str]] = []
        for y in years:
            events.extend(season_events(y))
        if sys.argv[1] == "--practice":
            # FP long runs -> separate file (pre-race signal, leakage-free).
            run(events, sessions=("FP1", "FP2"), out_path=PRACTICE_PARQUET)
        else:
            # Qualifying (grid + one-lap pace) + Race -> laps.parquet.
            run(events, sessions=("Q", "R"))
    elif len(sys.argv) >= 3:
        run([(int(sys.argv[1]), sys.argv[2])])
    else:
        run()
