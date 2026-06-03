"""Polymarket F1 market discovery / classification — the companion-mode prop index foundation.

The classifier is pure (no network) so we can pin Polymarket's slug taxonomy precisely; the
enumeration itself is network-best-effort and not asserted here.
"""

from app.etl.polymarket import classify_f1_market


def test_classify_known_slugs():
    cases = {
        # both pole naming conventions -> the same canonical type
        "f1-canadian-grand-prix-driver-pole-position-2026-05-23": "driver_pole",
        "miami-grand-prix-pole-winner": "driver_pole",
        "f1-monaco-grand-prix-constructor-pole-position-2026-06-06": "constructor_pole",
        "f1-canadian-grand-prix-sprint-qualifying-pole-winner-2026-05-22": "sprint_pole",
        "china-grand-prix-sprint-winner": "sprint_winner",
        "f1-miami-grand-prix-safety-car-2026-05-03": "safety_car",
        "f1-brazilian-grand-prix-red-flag-2025-11-08": "red_flag",
        "f1-monaco-grand-prix-driver-podium-2026-06-07": "driver_podium",
        "f1-bahrain-grand-prix-driver-fastest-lap-2026-04-12": "driver_fastest_lap",
        "f1-australian-grand-prix-practice-1-fastest-lap-2026-03-06": "practice_fastest_lap",
        "2026-f1-drivers-champion": "championship",
        "f1-constructors-champion": "championship",
        "british-grand-prix-winner": "race_winner",
        "f1-canadian-grand-prix-winner-2026-05-24": "race_winner",
    }
    for slug, want in cases.items():
        assert classify_f1_market(slug) == want, f"{slug} -> {classify_f1_market(slug)} (want {want})"


def test_sprint_pole_not_misread_as_driver_pole():
    # The sprint shootout pole is a DIFFERENT target than the main-quali pole — must not collide.
    assert classify_f1_market("f1-qatar-grand-prix-sprint-qualifying-pole-winner-2025-11-28") == "sprint_pole"
    assert classify_f1_market("f1-qatar-grand-prix-driver-pole-position-2025-11-29") == "driver_pole"
