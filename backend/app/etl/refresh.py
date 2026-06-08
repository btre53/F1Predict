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
from app.etl.ingest import LAPS_PARQUET, PRACTICE_PARQUET
from app.etl.openf1_ingest import ingest_events_openf1


def _existing(parquet) -> set[tuple[int, str]]:
    if not parquet.exists():
        return set()
    df = pl.read_parquet(parquet, columns=["year", "circuit"]).unique()
    return {(int(r["year"]), r["circuit"]) for r in df.to_dicts()}


def _completed_races(years: list[int] | None = None) -> list[tuple[int, str]]:
    """All race events whose lights-out is in the past, for the given (or recent) years.

    Sourced from the Jolpica calendar (datacenter-friendly), so this runs on the VPS where
    FastF1's schedule endpoint is blocked. See the f1-datacenter-ip-block finding."""
    from app.etl.calendar import season_calendar

    now = dt.datetime.now(dt.timezone.utc)
    if years is None:
        y = now.year
        years = [y - 1, y]
    out: list[tuple[int, str]] = []
    for year in years:
        for ev in season_calendar(year):
            rutc = ev.get("race_utc")
            if not rutc:
                continue
            try:
                race_dt = dt.datetime.fromisoformat(rutc)
            except ValueError:
                continue
            if race_dt <= now:
                out.append((year, ev["event_name"]))
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
    from app.models import hazard
    from app.models import overtaking
    from app.models import predict_kalman
    from app.models import sc_index
    from app.etl import weather

    for fn in (
        weather.weather_map,       # rebuilt below; clear the stale lookup
        weather._race_datetimes,
        store._load_raw,
        store.load_drivers,
        store.load_team_tyres,
        replay._laps,
        feat._race_seq,
        feat._practice,
        hazard._cached_model,  # refit the DNF hazard on the new race next time it's used
        overtaking._proxy_table,  # rebuilt below; clear the stale cache
        sc_index._fitted,  # refit the structural SC model on the new race
        predict_kalman._ot_index,  # holds an index over the old proxy table
        predict_kalman._fitted,  # re-forward-chain the Kalman over the new race
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

    laps = ingest_events_openf1(todo, sessions=("Q", "R"))
    fp = ingest_events_openf1(todo, sessions=("FP1", "FP2"))
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
        # Authoritative per-car classification (DNF flag + cause) for the new race(s). Feeds the
        # hazard DNF model AND the championship standings (season_sim reads results.parquet), so it
        # MUST stay current — without this, both lag a race behind. Offline (FastF1 cache).
        try:
            from app.etl.results import build_results

            build_results()
        except Exception:
            pass
        _bust_caches()
        # Rebuild the overtaking-difficulty proxies on the new race (forward-chained
        # index stays current). Best-effort: never fail the refresh on it.
        try:
            from app.models.overtaking import build_running_proxies, PROXIES_PARQUET

            build_running_proxies().write_parquet(PROXIES_PARQUET)
        except Exception:
            pass
        # Re-fit per-compound tyre degradation on the new stint data (offline, cheap).
        try:
            from app.etl.tyre_degradation import run as refit_degradation

            refit_degradation()
        except Exception:
            pass
        # Rebuild the race-window weather table for the new race(s) (Open-Meteo, cached;
        # best-effort -- never fail the refresh on a network blip). See docs/science/21.
        try:
            from app.etl.weather import build_weather_table

            build_weather_table(force=True)
        except Exception:
            pass
        # Incrementally fetch OpenF1 clean-air gaps for just the new 2023+ races (avoids the
        # full ~6-min rebuild). Best-effort; rate-limited. See docs/science/24.
        try:
            from app.etl.openf1 import update_openf1_clean_laps

            update_openf1_clean_laps(ingested)
            # clean-air pace depends on the gaps -> rebuild + bust its lookup cache
            from app.models.clean_air_pace import build_clean_air_pace, clean_air_map

            build_clean_air_pace(force=True)
            clean_air_map.cache_clear()
        except Exception:
            pass
        # Per-car tyre deg from stints + the measured dirty-air curve (offline; cheap). See #11/#20.
        try:
            from app.models.tyre_deg_car import build_car_deg

            build_car_deg(force=True)
        except Exception:
            pass
        try:
            from app.models.dirty_air import build_dirty_air

            build_dirty_air(force=True)
        except Exception:
            pass
        # Official starting grid (Jolpica) — feeds the feature table's grid (vs lap-1). See #19.
        try:
            from app.etl.jolpica import build_grids, official_grid_map

            build_grids(force=True)
            official_grid_map.cache_clear()
        except Exception:
            pass
        # Backfill the in-play Polymarket winner-price curve for the new race(s) and rebuild
        # the model-vs-market overlay, so the Explorer/companion shows it. The live-capture
        # Action records the curve live too; this is the guaranteed post-race pull (network,
        # best-effort). LOCKBOX: 2026 is OOS -- this is display-only overlay data, not training.
        try:
            from app.engine import replay as _replay
            from app.etl.inplay_backtest import build_overlay
            from app.etl.inplay_probe import fetch_year

            by_year: dict[int, set[str]] = {}
            for (yy, circ) in ingested:
                by_year.setdefault(int(yy), set()).add(circ)
            for yy, circs in by_year.items():
                fetch_year(yy, only=circs)
            build_overlay()
            _replay._inplay_overlay_all.cache_clear()
        except Exception:
            pass
        # Auto-build the GPS track map (outline + per-frame positions) for the new race(s)
        # from OpenF1 location, so the map feature stays current for every race (network,
        # best-effort). The api restart after refresh picks up the new outline/positions.
        try:
            from app.etl.build_map_openf1 import build_map

            for (yy, circ) in ingested:
                build_map(yy, circ)
        except Exception:
            pass
        recalibrated = True

    # Refresh the Polymarket fallback snapshot too (best-effort; never fails the refresh).
    snapshot_updated = False
    try:
        from app.etl.polymarket import refresh_markets_snapshot

        snap = refresh_markets_snapshot()
        snapshot_updated = bool(snap.get("markets"))
    except Exception:
        pass

    return {
        "new_races": len(ingested),
        "ingested": ingested,
        "recalibrated": recalibrated,
        "snapshot_updated": snapshot_updated,
    }


if __name__ == "__main__":
    summary = refresh()
    print(f"refresh: {summary['new_races']} new races ingested {summary['ingested']}")
    print(f"  recalibrated: {summary['recalibrated']}")
