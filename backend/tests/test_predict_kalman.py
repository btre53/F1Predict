"""Tests for the Kalman Predictor's pre-quali vs post-quali (grid-fusion) behaviour."""

import pytest

from app.models.predict_kalman import _fitted, predict_race_kalman


@pytest.fixture(scope="module")
def roster_drivers():
    try:
        _, roster, _ = _fitted()
    except Exception:
        pytest.skip("no ingested data in this environment")
    return roster["driver"].to_list()


def test_pre_quali_is_flagged_and_honestly_tight(roster_drivers):
    r = predict_race_kalman("Monaco", n_sims=2000)
    assert r.post_quali is False
    assert r.outcomes[0].win_pct < 0.5  # no single ~certain favourite before qualifying


def test_quali_fusion_sharpens_toward_the_pole_sitter(roster_drivers):
    # Put the strongest-prior driver (the pre-quali favourite) on a DECISIVE pole, so the
    # test doesn't depend on the prior-vs-quali fight or roster tie order.
    pre = predict_race_kalman("Monaco", n_sims=3000)
    assert pre.post_quali is False
    fav = pre.outcomes[0].driver
    qg = {d: (0.0 if d == fav else 0.02 + 0.002 * i) for i, d in enumerate(roster_drivers)}
    post = predict_race_kalman("Monaco", n_sims=3000, quali_gap=qg)
    assert post.post_quali is True
    assert post.outcomes[0].driver == fav                    # decisive pole-sitter is favourite
    assert post.outcomes[0].grid_pos == 1
    assert post.outcomes[0].win_pct > pre.outcomes[0].win_pct  # fusing the grid sharpens
