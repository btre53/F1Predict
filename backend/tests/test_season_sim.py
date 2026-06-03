"""Season championship simulator (task #25)."""

from app.models.season_sim import simulate_season


def test_title_probabilities_are_valid():
    r = simulate_season(n_sims=4000)
    assert r["n_remaining"] >= 0 and r["drivers"] and r["constructors"]
    dt = sum(x["title_pct"] for x in r["drivers"])
    ct = sum(x["title_pct"] for x in r["constructors"])
    assert 0.98 <= dt <= 1.02 and 0.98 <= ct <= 1.02   # probabilities sum to ~1
    assert all(0.0 <= x["title_pct"] <= 1.0 for x in r["drivers"])


def test_overrides_shift_the_title_race():
    """The interactive lever: giving the favourite extra DNFs must lower its title odds."""
    base = simulate_season(n_sims=6000, seed=3)
    fav = base["drivers"][0]["driver"]
    nerfed = simulate_season(n_sims=6000, seed=3, overrides={fav: {"extra_dnfs": 6}})
    base_p = next(x["title_pct"] for x in base["drivers"] if x["driver"] == fav)
    new_p = next(x["title_pct"] for x in nerfed["drivers"] if x["driver"] == fav)
    assert new_p < base_p
