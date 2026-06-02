"""Tests for the structural safety-car index (task #21)."""

from app.models.sc_index import build_sc_table, sc_probability


def test_sc_table_has_labels():
    t = build_sc_table()
    assert t.height > 100
    for col in ("any_sc", "n_periods", "pass_rate", "lap1_churn", "wet", "seq"):
        assert col in t.columns
    assert set(t["any_sc"].unique().to_list()) <= {0, 1}


def test_sc_prior_is_a_probability():
    for c in ("Monaco", "Azerbaijan", "Hungarian"):
        p = sc_probability(c)
        assert 0.0 < p < 1.0


def test_street_circuits_rank_above_open_ones():
    """Mechanistic ordering: walled/street circuits fire more cautions than open ones."""
    assert sc_probability("Azerbaijan") > sc_probability("Hungarian")


def test_wet_raises_the_prior():
    assert sc_probability("Monaco", wet=True) > sc_probability("Monaco", wet=False)
