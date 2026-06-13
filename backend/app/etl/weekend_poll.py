"""Race-weekend poller: ingest each session the moment OpenF1 shows it finished.

Replaces "wait until Monday" with "react to the data". Designed to run frequently across a
race weekend (see deploy/f1-weekend-poll.sh); every run is cheap and idempotent.

ROBUST TO DELAYS / RED FLAGS BY CONSTRUCTION. A session is treated as finished only when
OpenF1 has published its official classification (`session_result`) AND the lap feed has gone
quiet -- never when a scheduled clock time passes. So a delayed start, a long red-flag
stoppage, or an extended session can't trigger a premature ingest. For the race we additionally
require the lap feed to reach the winner's lap count, so a partial mid-race feed can never be
ingested (which matters: refresh() dedups keep-first and skips a circuit it already has, so a
half-ingested race would never self-heal -- the Monday backstop notwithstanding).

Two actions per weekend:
  - Quali settled -> fetch + cache the real grid (predict_kalman.fetch_quali_gaps, OpenF1-backed),
    so the live predictor/companion fuse the post-quali grid server-side, no residential box.
  - Race settled  -> run the full app.etl.refresh (laps + recalibration + overlays), the same job
    the Monday cron runs, just triggered Sunday evening instead.

    uv run python -m app.etl.weekend_poll
"""

from __future__ import annotations

import datetime as dt

from app.etl import openf1 as of1
from app.etl.openf1_ingest import _resolve_session_key

# How long the OpenF1 lap feed must be quiet (no newer lap end) before we trust a session is
# over. Generous, because a late ingest is harmless (the Monday cron is the backstop) but an
# early/partial one is not.
QUIET_MINUTES = 20
# A finished F1 session classifies ~20 cars; require a near-full result so a half-populated
# (provisional, mid-session) classification can't be mistaken for the official one.
MIN_CLASSIFIED = 15
# Watch from this many days before lights-out (covers a Thu/Fri-start weekend) ...
WEEKEND_LEAD_DAYS = 4
# ... through this many hours after (so a delayed/red-flagged Sunday race is still caught).
WEEKEND_TRAIL_HOURS = 36


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _session_status(year: int, circuit: str, session_name: str) -> dict:
    """OpenF1-derived completion facts for one session (all best-effort, never raises).

    {exists, classified, winner_laps, feed_max_lap, last_activity} where last_activity is the
    UTC datetime of the latest lap's end (None if no laps yet)."""
    sk = _resolve_session_key(year, circuit, session_name)
    if sk is None:
        return {"exists": False}
    result = of1._get("session_result", session_key=sk) or []
    laps = of1._get("laps", session_key=sk) or []
    ends: list[float] = []
    max_lap = 0
    for lp in laps:
        ln = lp.get("lap_number")
        if isinstance(ln, int):
            max_lap = max(max_lap, ln)
        ds, dur = lp.get("date_start"), lp.get("lap_duration")
        if ds and isinstance(dur, (int, float)):
            ends.append(of1._ts(ds) + float(dur))
    winner_laps = max((int(r.get("number_of_laps") or 0) for r in result), default=0)
    last = (
        dt.datetime.fromtimestamp(max(ends), dt.timezone.utc) if ends else None
    )
    return {
        "exists": True,
        "classified": len(result),
        "winner_laps": winner_laps,
        "feed_max_lap": max_lap,
        "last_activity": last,
    }


def session_finished(
    year: int,
    circuit: str,
    session_name: str,
    *,
    now: dt.datetime | None = None,
    quiet_minutes: int = QUIET_MINUTES,
    require_full_laps: bool = False,
) -> bool:
    """True iff OpenF1 shows this session officially classified AND its lap feed has settled.

    require_full_laps (use for the race): also demand the lap feed reach the winner's lap count,
    so a still-streaming race is never ingested as if complete."""
    st = _session_status(year, circuit, session_name)
    if not st.get("exists") or st["classified"] < MIN_CLASSIFIED:
        return False
    last = st["last_activity"]
    if last is None:
        return False
    now = now or _now()
    if (now - last).total_seconds() < quiet_minutes * 60:
        return False
    if require_full_laps and st["winner_laps"] and st["feed_max_lap"] < st["winner_laps"]:
        return False
    return True


def active_weekend(now: dt.datetime | None = None) -> dict | None:
    """The race-weekend calendar entry currently in window, or None outside any weekend."""
    from app.etl.calendar import season_calendar

    now = now or _now()
    for year in {now.year, now.year - 1}:  # handle a Jan race / year boundary
        for ev in season_calendar(year):
            rutc = ev.get("race_utc")
            if not rutc:
                continue
            try:
                race_dt = dt.datetime.fromisoformat(rutc)
            except ValueError:
                continue
            if (
                race_dt - dt.timedelta(days=WEEKEND_LEAD_DAYS)
                <= now
                <= race_dt + dt.timedelta(hours=WEEKEND_TRAIL_HOURS)
            ):
                return ev
    return None


def _race_already_ingested(year: int, circuit: str) -> bool:
    from app.etl.ingest import LAPS_PARQUET
    from app.etl.refresh import _existing

    return (year, circuit) in _existing(LAPS_PARQUET)


def poll(now: dt.datetime | None = None, *, quiet_minutes: int = QUIET_MINUTES) -> dict:
    """One poll pass. No-ops cheaply outside a race weekend; idempotent within one."""
    now = now or _now()
    wk = active_weekend(now)
    if wk is None:
        return {"active_weekend": None, "actions": [], "now": now.isoformat()}

    year, circuit = int(wk["year"]), wk["circuit"]
    actions: list[dict] = []

    # --- Quali grid: cache the real post-quali grid for the live predictor/companion. ---
    try:
        from app.models.predict_kalman import _quali_cache, fetch_quali_gaps

        if f"{year}-{circuit}" not in _quali_cache() and session_finished(
            year, circuit, "Q", now=now, quiet_minutes=quiet_minutes
        ):
            gaps = fetch_quali_gaps(circuit, year)  # OpenF1-backed; writes data/quali_gaps.json
            if gaps:
                actions.append({"action": "quali_grid", "circuit": circuit, "drivers": len(gaps)})
    except Exception as e:  # noqa: BLE001 -- never let one action break the poll
        actions.append({"action": "quali_grid", "error": f"{type(e).__name__}: {e}"})

    # --- Race: full refresh (laps + recalibration + overlays), gated on a COMPLETE race. ---
    try:
        if not _race_already_ingested(year, circuit) and session_finished(
            year, circuit, "R", now=now, quiet_minutes=quiet_minutes, require_full_laps=True
        ):
            from app.etl.refresh import refresh

            summary = refresh()
            actions.append({"action": "race_refresh", **summary})
    except Exception as e:  # noqa: BLE001
        actions.append({"action": "race_refresh", "error": f"{type(e).__name__}: {e}"})

    return {"active_weekend": f"{year} {circuit}", "actions": actions, "now": now.isoformat()}


if __name__ == "__main__":
    import sys

    summary = poll()
    wk = summary["active_weekend"]
    if wk is None:
        print("no active race weekend")
    else:
        print(f"weekend: {wk}")
        if not summary["actions"]:
            print("  nothing new to ingest")
        for a in summary["actions"]:
            print(f"  {a}")
    # Exit 10 when a race was actually ingested, so the cron knows to restart the api (quali-grid
    # caching needs no restart -- the predictor reads data/quali_gaps.json fresh on each request).
    race = next(
        (a for a in summary["actions"]
         if a.get("action") == "race_refresh" and not a.get("error") and a.get("new_races")),
        None,
    )
    sys.exit(10 if race else 0)
