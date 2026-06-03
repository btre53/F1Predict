"""Start performance = official grid − lap-1 position (task #22)."""

from app.models.start_perf import stability_gate, start_deltas


def test_start_deltas_shape():
    t = start_deltas()
    assert t.height > 1000
    for col in ("year", "circuit", "driver", "start_delta", "seq"):
        assert col in t.columns


def test_start_is_large_variance_weak_skill():
    """The honest finding: a big race-to-race shuffle, only weakly a persistent driver skill."""
    g = stability_gate()
    assert g["n"] > 100
    assert g["field_sd_places"] > 1.5          # the start is a real, large lap-1 shuffle
    assert g["spearman_prior_vs_next"] is not None
    assert 0.0 < g["spearman_prior_vs_next"] < 0.4   # weakly reproducible, mostly noise
