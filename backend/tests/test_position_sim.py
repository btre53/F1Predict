"""Per-lap track-position-resolution sim (brief 26, task #24 step 2)."""

import numpy as np

from app.engine import calibration_store as store
from app.engine.montecarlo import GridEntry, run_race_simulation
from app.engine.position_sim import run_position_simulation
from app.engine.strategy import optimize_strategy


def _grid(cp, ov):
    strat = optimize_strategy(cp, max_stops=2, tyre_overrides=ov, top_k=1)[0].strategy
    pace = np.linspace(-0.4, 0.5, 10)   # D0 fastest, on pole
    return [GridEntry(driver=f"D{i}", strategy=strat, pace_offset_s=float(pace[i]),
                      grid_pos=i + 1, dnf_prob=0.05) for i in range(10)]


def test_runs_and_returns_valid_distribution():
    cp = store.circuit_params_for("Bahrain")
    ov = store.tyre_overrides_for("Bahrain")
    res = run_position_simulation(cp, _grid(cp, ov), n_sims=2000, tyre_overrides=ov, seed=1)
    assert len(res.outcomes) == 10
    for o in res.outcomes:
        assert abs(sum(o.finish_distribution) - 1.0) < 0.05
        assert 0.0 <= o.win_pct <= 1.0


def test_lock_strengthens_with_track_difficulty():
    """The core mechanism: a fast pole car is harder to pass at a hard-to-pass circuit, so its
    win prob rises with `overtaking`. (At low difficulty the field shuffles freely.)"""
    cp = store.circuit_params_for("Monaco")
    ov = store.tyre_overrides_for("Monaco")
    g = _grid(cp, ov)
    easy = run_position_simulation(cp, g, n_sims=3000, tyre_overrides=ov, overtaking=0.5, seed=1)
    hard = run_position_simulation(cp, g, n_sims=3000, tyre_overrides=ov, overtaking=3.0, seed=1)
    pole_easy = next(o.win_pct for o in easy.outcomes if o.driver == "D0")
    pole_hard = next(o.win_pct for o in hard.outcomes if o.driver == "D0")
    assert pole_hard > pole_easy   # harder to pass -> leader more locked in
