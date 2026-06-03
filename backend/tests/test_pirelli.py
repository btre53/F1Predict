"""Pirelli C0-C6 compound table (task #18): sourced lookup; honest deg-comparability finding."""

from app.etl.pirelli import absolute_compound, compound_map, coverage


def test_table_loaded_and_covers_modern_era():
    c = coverage()
    assert c["races"] >= 80
    # ground-effect era is the deg model's target — must be well covered
    for yr in (2022, 2023, 2024, 2025):
        assert c["by_year"].get(yr, 0) >= 20


def test_known_nominations():
    # spot-checks against the sourced data
    assert absolute_compound(2024, "Bahrain", "SOFT") == "C3"
    assert absolute_compound(2024, "Bahrain", "HARD") == "C1"
    assert absolute_compound(2025, "Monaco", "SOFT") == "C6"   # the new C6, softest range
    assert absolute_compound(2019, "Bahrain", "SOFT") is None  # pre-2022 not sourced -> None


def test_relative_keys_uppercase():
    m = compound_map().get((2024, "Bahrain"))
    assert m and set(m) <= {"SOFT", "MEDIUM", "HARD"}
