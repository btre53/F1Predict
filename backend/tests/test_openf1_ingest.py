"""Unit tests for the FastF1-free OpenF1 lap ingest (pure logic; no network)."""

from app.etl.calendar import _combine_utc
from app.etl.openf1_ingest import _track_status_by_lap


def test_combine_utc():
    assert _combine_utc("2026-06-07", "13:00:00Z") == "2026-06-07T13:00:00+00:00"
    assert _combine_utc("2026-06-07", None) == "2026-06-07T00:00:00+00:00"
    assert _combine_utc(None, "13:00:00Z") is None


def test_track_status_safety_car_window():
    rc = [
        {"date": "2026-01-01T13:00:00+00:00", "lap_number": 5,
         "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
        {"date": "2026-01-01T13:10:00+00:00", "lap_number": 8,
         "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"},
    ]
    st = _track_status_by_lap(rc)
    assert st.get(5) == "4" and st.get(6) == "4" and st.get(8) == "4"
    assert 9 not in st  # window closed


def test_track_status_vsc_and_red():
    rc = [
        {"date": "2026-01-01T13:00:00+00:00", "lap_number": 3,
         "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR DEPLOYED"},
        {"date": "2026-01-01T13:02:00+00:00", "lap_number": 4,
         "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR ENDING"},
        {"date": "2026-01-01T13:30:00+00:00", "lap_number": 10,
         "category": "Flag", "flag": "RED"},
        {"date": "2026-01-01T14:00:00+00:00", "lap_number": 12,
         "category": "Flag", "flag": "GREEN"},
    ]
    st = _track_status_by_lap(rc)
    assert st.get(3) == "6" and st.get(4) == "6"  # VSC
    assert st.get(10) == "5" and st.get(11) == "5"  # red window


def test_track_status_empty():
    assert _track_status_by_lap([]) == {}
