"""Official F1 calendar from FastF1's schedule — for auto-selecting the next race.

No scraping: `fastf1.get_event_schedule(year)` is the published schedule (round, event
name, session times UTC), offline once cached. We use it to surface the upcoming race
so the UI can default to it instead of making the user pick from a dropdown.
"""

from __future__ import annotations

import datetime as dt
import logging
import warnings

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)


def _circuit_name(event_name: str) -> str:
    """Our normalized circuit key = EventName minus the 'Grand Prix' suffix."""
    return str(event_name).replace(" Grand Prix", "").strip()


def _iso(ts) -> str | None:
    import pandas as pd

    if ts is None or pd.isna(ts):
        return None
    return pd.Timestamp(ts).isoformat()


def season_calendar(year: int) -> list[dict]:
    """All race rounds in a season with session times (UTC)."""
    import fastf1

    from app.config import get_settings

    fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)
    sched = fastf1.get_event_schedule(year, include_testing=False)
    out: list[dict] = []
    for _, row in sched.iterrows():
        rnd = int(row["RoundNumber"])
        if rnd == 0:
            continue
        out.append({
            "year": year,
            "round": rnd,
            "event_name": str(row["EventName"]),
            "circuit": _circuit_name(row["EventName"]),
            "race_utc": _iso(row.get("Session5DateUtc")),
            "quali_utc": _iso(row.get("Session4DateUtc")),
        })
    return out


def next_race(now: dt.datetime | None = None) -> dict | None:
    """The next race whose lights-out is still ahead (this year, else next year).

    Falls back to the most recent past race if the season is over and next isn't loaded.
    Adds `is_upcoming` and `days_away`.
    """
    import pandas as pd

    now_ts = pd.Timestamp(now or dt.datetime.now(dt.timezone.utc)).tz_localize(None)
    seasons = sorted({now_ts.year, now_ts.year + 1})
    races: list[dict] = []
    for y in seasons:
        try:
            races.extend(season_calendar(y))
        except Exception:
            continue
    if not races:
        return None
    dated = [r for r in races if r["race_utc"]]
    upcoming = [r for r in dated if pd.Timestamp(r["race_utc"]).tz_localize(None) >= now_ts]
    if upcoming:
        r = min(upcoming, key=lambda x: pd.Timestamp(x["race_utc"]))
        r = {**r, "is_upcoming": True}
    else:  # season over / next not published — show the most recent past race
        r = max(dated, key=lambda x: pd.Timestamp(x["race_utc"]))
        r = {**r, "is_upcoming": False}
    days = (pd.Timestamp(r["race_utc"]).tz_localize(None) - now_ts).days
    return {**r, "days_away": days}
