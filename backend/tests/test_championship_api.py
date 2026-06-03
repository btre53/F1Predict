"""Championship endpoints (task #25): GET /championship + the POST sandbox.

Network-free: the Polymarket title column is fetched with with_market=False so these stay
offline + deterministic (the market join itself degrades gracefully and is covered by hand).
"""

from fastapi.testclient import TestClient

from app.main import app
from app.models.season_sim import _current_standings

client = TestClient(app)


def test_current_standings_present_for_latest_season():
    """Regression: results.parquet must carry the latest season so standings aren't all-zero."""
    from app.models.predict_kalman import _fitted

    _, _, latest = _fitted()
    pts, done = _current_standings(latest, None)
    assert done, f"no classified results for {latest} -> standings would read 0-done"
    assert any(v > 0 for v in pts.values())


def test_championship_endpoint_shape():
    r = client.get("/api/championship", params={"n_sims": 3000, "with_market": False})
    assert r.status_code == 200
    j = r.json()
    assert j["drivers"] and j["constructors"]
    assert j["n_remaining"] >= 0 and j["n_done"] >= 0
    assert j["market_available"] is False
    top = j["drivers"][0]
    assert set(top) >= {"driver", "team", "title_pct", "current_points", "exp_points",
                        "p_top3", "market_pct"}
    assert sum(d["title_pct"] for d in j["drivers"]) == \
        __import__("pytest").approx(1.0, abs=0.02)


def test_sandbox_overrides_reshape_the_title():
    """The interactive lever through the API: extra DNFs for the leader cut its odds."""
    base = client.get("/api/championship",
                      params={"n_sims": 5000, "with_market": False}).json()
    fav = base["drivers"][0]["driver"]
    base_p = base["drivers"][0]["title_pct"]
    r = client.post("/api/championship/simulate",
                    json={"n_sims": 5000, "overrides": {fav: {"extra_dnfs": 8}}})
    assert r.status_code == 200
    new_p = next(d["title_pct"] for d in r.json()["drivers"] if d["driver"] == fav)
    assert new_p < base_p


def test_sandbox_rejects_out_of_range_override():
    r = client.post("/api/championship/simulate",
                    json={"overrides": {"VER": {"dnf_prob": 1.5}}})
    assert r.status_code == 422  # pydantic bound on dnf_prob in [0,1]
