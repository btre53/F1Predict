"""Tests for the historical replay engine (guarded on ingested data)."""

from app.engine import track_geometry, track_positions
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
    # Real sector keys are always emitted (values may be null for in/out laps).
    for s in first["order"]:
        assert {"sector1_s", "sector2_s", "sector3_s"} <= set(s)


def test_track_outline_cache_shape_when_present():
    o = track_geometry.outline_for("Bahrain", 2024)
    if o is None:
        return  # cache not built in this environment
    assert isinstance(o["path"], str) and o["path"].startswith("M")
    assert o["path"].rstrip().endswith("Z")


def test_track_positions_cache_shape_when_present():
    p = track_positions.positions_for("Bahrain", 2024)
    if p is None:
        return  # cache not built in this environment
    assert p["view"] == [360, 180]
    assert p["n_frames"] > 0
    assert p["cars"]
    for pts in p["cars"].values():
        assert len(pts) == p["n_frames"]
        # Every non-null point sits inside the viewBox.
        for pt in pts:
            if pt is not None:
                assert 0 <= pt[0] <= 360 and 0 <= pt[1] <= 180
        break
