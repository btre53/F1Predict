"""Decide whether/what the live-capture Action should record this firing.

Reads the trigger context from env (set by .github/workflows/live_capture.yml) and emits
GitHub Actions `key=value` output lines on stdout (the workflow redirects to $GITHUB_OUTPUT):

    proceed   true | false   -- false no-ops the capture jobs (e.g. a non-race weekend)
    gp        comma-separated GP name aliases for the Polymarket slug (e.g. barcelona,spanish)
    date      race date YYYY-MM-DD
    label     quali | race | manual   -- used in the artifact name
    minutes   Polymarket capture duration

On a manual dispatch we trust the inputs. On a scheduled run we resolve the upcoming race
from the FastF1 schedule and only proceed if its race is within ~30h (so the Sat quali-day
and Sun race-day crons fire on a race weekend, but every other weekend is a cheap no-op).
"""

from __future__ import annotations

import datetime as dt
import os

# Polymarket slugs the F1-official GP name, which doesn't always match our circuit key.
# Try the listed aliases (whichever event exists is the one captured); default = the
# circuit name slugified.
ALIASES: dict[str, list[str]] = {
    "barcelona": ["barcelona", "spanish"],
    "spanish": ["spanish", "barcelona"],
    "são paulo": ["sao-paulo", "brazil"],
    "sao paulo": ["sao-paulo", "brazil"],
    "mexico city": ["mexico-city", "mexico"],
    "abu dhabi": ["abu-dhabi"],
    "las vegas": ["las-vegas"],
}

# How far ahead of the race a scheduled firing is still allowed to capture.
GUARD_HOURS = 30


def _aliases(circuit: str) -> str:
    key = circuit.strip().lower()
    if key in ALIASES:
        return ",".join(ALIASES[key])
    return key.replace(" ", "-")


def _emit(**kv) -> None:
    for k, v in kv.items():
        print(f"{k}={v}")


def main() -> None:
    event = os.environ.get("EVENT_NAME", "")

    if event == "workflow_dispatch":
        _emit(
            proceed="true",
            gp=os.environ.get("IN_GP", "barcelona,spanish"),
            date=os.environ.get("IN_DATE", ""),
            label="manual",
            minutes=os.environ.get("IN_MINUTES") or "60",
        )
        return

    schedule = os.environ.get("SCHEDULE", "")
    dow = schedule.split()[-1] if schedule else ""
    label = "quali" if dow == "6" else "race"
    # Race day captures a longer window (pre-race drift + the ~2h race + resolution).
    minutes = "300" if schedule == "0 11 * * 0" else "240"

    try:
        from app.etl.calendar import next_race

        r = next_race()
    except Exception:
        r = None

    if not r or not r.get("is_upcoming") or not r.get("race_utc"):
        _emit(proceed="false", gp="", date="", label=label, minutes=minutes)
        return

    race_dt = dt.datetime.fromisoformat(r["race_utc"])
    if race_dt.tzinfo is None:
        race_dt = race_dt.replace(tzinfo=dt.timezone.utc)
    hours_away = (race_dt - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600.0
    proceed = "true" if 0 <= hours_away <= GUARD_HOURS else "false"

    _emit(
        proceed=proceed,
        gp=_aliases(r["circuit"]),
        date=race_dt.date().isoformat(),
        label=label,
        minutes=minutes,
    )


if __name__ == "__main__":
    main()
