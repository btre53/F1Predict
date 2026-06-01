"""Tests for the historical replay engine (guarded on ingested data)."""

from app.engine.replay import available_races, load_replay


def test_replay_races_listed_when_data_present():
    races = available_races()
    if not races:
        return  # ETL not run in this environment
    r = races[0]
    assert {"circuit", "year", "total_laps", "n_drivers"} <= set(r)
    assert r["total_laps"] > 0


def test_load_replay_shapes_are_consistent():
    races = available_races()
    if not races:
        return
    r = races[0]
    data = load_replay(r["circuit"], r["year"])
    assert data.total_laps == r["total_laps"]
    assert len(data.laps) >= 1
    # Each lap is an ordered grid; positions sorted, gaps non-negative with a
    # zero-gap time-leader (the position-1 car need not be the elapsed-time leader
    # on lap 1, since position is track order and gap is cumulative time).
    first = data.laps[0]
    positions = [s["position"] for s in first["order"]]
    assert positions == sorted(positions)
    gaps = [s["gap_s"] for s in first["order"]]
    assert min(gaps) == 0.0 and all(g >= 0 for g in gaps)
    assert first["track_status"] in {"GREEN", "YELLOW", "SC", "VSC", "RED"}
