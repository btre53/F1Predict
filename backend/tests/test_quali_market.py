"""Pole-market backtest (#28). Network-free: validates the committed artifact's shape + that the
exhaustive (tag-enumerated, two-slug-format) discovery actually grew the sample."""

from app.models.validate_quali_market import load_quali_market_backtest


def test_pole_backtest_artifact_shape():
    d = load_quali_market_backtest()
    assert d is not None, "data/quali_market_backtest.json missing — run validate_quali_market"
    # Discovery enumerates Polymarket's F1 tag (both 'pole-winner' + 'driver-pole-position'
    # formats), so the priced-race sample must be the full ~23, not the 9 the old slug-guess found.
    assert d["n_races"] >= 18, f"only {d['n_races']} races — discovery regressed to slug-guessing?"
    for k in ("model_pole", "market_pole"):
        assert "brier" in d[k]
    assert 0.0 <= d["model_top_pick_accuracy"] <= 1.0
    assert 0.0 <= d["market_top_pick_accuracy"] <= 1.0
    # The honest finding the artifact must encode: no pole edge (market at least as calibrated).
    assert d["market_pole"]["brier"] <= d["model_pole"]["brier"] + 1e-6
    for p in d["per_race"]:
        assert {"year", "circuit", "pole", "market_fav", "model_fav"} <= set(p)
