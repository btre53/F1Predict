"""Unit tests for the race-weekend poller (pure logic; OpenF1 calls are monkeypatched).

The poller's whole value is its robustness rules -- it must NOT treat a session as finished
until it's officially classified and the lap feed has settled, and it must never ingest a
partial race. These tests pin exactly those rules without touching the network."""

import datetime as dt

import pytest

from app.etl import weekend_poll as wp


def _patch_status(monkeypatch, status: dict):
    monkeypatch.setattr(wp, "_session_status", lambda *a, **k: status)


NOW = dt.datetime(2026, 6, 13, 20, 0, tzinfo=dt.timezone.utc)
LONG_AGO = NOW - dt.timedelta(hours=4)
JUST_NOW = NOW - dt.timedelta(minutes=2)


def test_finished_when_classified_and_quiet(monkeypatch):
    _patch_status(monkeypatch, {
        "exists": True, "classified": 22, "winner_laps": 13,
        "feed_max_lap": 13, "last_activity": LONG_AGO,
    })
    assert wp.session_finished(2026, "Barcelona", "Q", now=NOW) is True


def test_not_finished_when_no_session(monkeypatch):
    _patch_status(monkeypatch, {"exists": False})
    assert wp.session_finished(2026, "Barcelona", "R", now=NOW) is False


def test_not_finished_when_unclassified(monkeypatch):
    # race session exists but hasn't run yet -> empty classification
    _patch_status(monkeypatch, {
        "exists": True, "classified": 0, "winner_laps": 0,
        "feed_max_lap": 0, "last_activity": None,
    })
    assert wp.session_finished(2026, "Barcelona", "R", now=NOW) is False


def test_not_finished_when_feed_still_live(monkeypatch):
    # classified rows exist (provisional) but the lap feed is still streaming -> hold off
    _patch_status(monkeypatch, {
        "exists": True, "classified": 20, "winner_laps": 66,
        "feed_max_lap": 40, "last_activity": JUST_NOW,
    })
    assert wp.session_finished(2026, "Barcelona", "R", now=NOW) is False


def test_race_blocked_until_full_distance(monkeypatch):
    # feed is quiet AND classified, but only 40 of 66 laps are in -> a partial race, never ingest
    _patch_status(monkeypatch, {
        "exists": True, "classified": 20, "winner_laps": 66,
        "feed_max_lap": 40, "last_activity": LONG_AGO,
    })
    assert wp.session_finished(2026, "Barcelona", "R", now=NOW, require_full_laps=True) is False
    # quali (no full-laps requirement) is fine on the same shape
    assert wp.session_finished(2026, "Barcelona", "Q", now=NOW) is True


def test_race_allowed_when_complete(monkeypatch):
    _patch_status(monkeypatch, {
        "exists": True, "classified": 20, "winner_laps": 66,
        "feed_max_lap": 66, "last_activity": LONG_AGO,
    })
    assert wp.session_finished(2026, "Barcelona", "R", now=NOW, require_full_laps=True) is True


@pytest.mark.parametrize("delta,expect", [
    (dt.timedelta(days=2), True),       # two days before lights-out -> in window
    (dt.timedelta(hours=12), True),     # day after -> still in window (delayed/red-flag tail)
    (dt.timedelta(days=10), False),     # well before -> out
    (-dt.timedelta(days=3), False),     # long after -> out
])
def test_active_weekend_window(monkeypatch, delta, expect):
    race = NOW + delta
    cal = [{"year": 2026, "round": 7, "event_name": "Barcelona Grand Prix",
            "circuit": "Barcelona", "race_utc": race.isoformat(), "quali_utc": None}]
    monkeypatch.setattr("app.etl.calendar.season_calendar", lambda y: cal if y == 2026 else [])
    wk = wp.active_weekend(now=NOW)
    assert (wk is not None) is expect


def test_poll_no_weekend(monkeypatch):
    monkeypatch.setattr(wp, "active_weekend", lambda now=None: None)
    out = wp.poll(now=NOW)
    assert out["active_weekend"] is None and out["actions"] == []
