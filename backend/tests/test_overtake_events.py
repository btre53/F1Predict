"""Overtake-event probe (task #24): do strong cars clear traffic more reliably?"""

from app.models.overtake_events import analyse


def test_strong_cars_pass_more_reliably_but_not_faster():
    r = analyse()
    assert r["n_episodes"] > 500
    b = r["buckets"]
    strong, slow = b["strong"], b["slow"]
    assert strong and slow
    # the finding: strong cars CLEAR traffic more often (higher pass rate)...
    assert strong["pass_rate"] > slow["pass_rate"]
    # ...but NOT in fewer laps (laps-stuck is ~flat) -> the lever is pass-probability, not time
    assert abs(strong["median_laps_stuck"] - slow["median_laps_stuck"]) <= 2
