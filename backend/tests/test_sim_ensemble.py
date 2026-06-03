"""Sim ensemble wiring in the predictor (task #16): opt-in, default off, fail-safe."""

from app.models.predict_kalman import predict_race_kalman


def test_default_is_pure_rank_model():
    """No sim_weight (and no F1P_SIM_WEIGHT env) -> the calibrated rank model is unchanged."""
    a = predict_race_kalman("Monaco", n_sims=3000, sim_weight=0.0)
    b = predict_race_kalman("Monaco", n_sims=3000, sim_weight=None)  # env default (0 in tests)
    da = {o.driver: o.win_pct for o in a.outcomes}
    db = {o.driver: o.win_pct for o in b.outcomes}
    assert all(abs(da[d] - db[d]) < 1e-9 for d in da)


def test_ensemble_runs_and_stays_a_valid_distribution():
    res = predict_race_kalman("Monaco", n_sims=3000, sim_weight=0.5)
    for o in res.outcomes:
        s = sum(o.finish_distribution)
        assert abs(s - 1.0) < 0.02
        assert 0.0 <= o.win_pct <= 1.0 and 0.0 <= o.podium_pct <= 1.0
