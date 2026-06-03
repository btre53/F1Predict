"""Per-car straight-line term + 2026 era-gate in the position sim (brief 28)."""

import numpy as np

from app.engine import calibration_store as store
from app.engine.montecarlo import GridEntry
from app.engine.position_sim import run_position_simulation
from app.engine.strategy import optimize_strategy
from app.models.straightline import driver_straightline, straightline_table


def _grid(cp, ov):
    strat = optimize_strategy(cp, max_stops=2, tyre_overrides=ov, top_k=1)[0].strategy
    pace = np.linspace(-0.4, 0.5, 10)
    return [GridEntry(driver=f"D{i}", strategy=strat, pace_offset_s=float(pace[i]),
                      grid_pos=i + 1, dnf_prob=0.05) for i in range(10)]


def test_straightline_index_is_a_real_trait():
    t = straightline_table()
    assert t.height > 0 and {"sl_z"} <= set(t.columns)
    d = driver_straightline()
    assert d and all(abs(v) < 6 for v in d.values())   # z-scores, bounded


def test_era_gate_eases_passing_in_2026():
    """Active aero (2026) lowers the global threshold -> easier passing -> a fast car starting at
    the BACK carves forward more than in the DRS era (clearest where it has to overtake)."""
    cp = store.circuit_params_for("Bahrain")
    ov = store.tyre_overrides_for("Bahrain")
    strat = optimize_strategy(cp, max_stops=2, tyre_overrides=ov, top_k=1)[0].strategy
    # Small, threshold-gated pace gaps: a modestly-faster car (D0) starts mid-pack behind slower
    # cars. Its pace surplus (~0.3-0.5s) sits below the threshold, so passing is contested -> the
    # era's threshold actually matters (unlike a runaway car that clears the field regardless).
    pace = np.linspace(0.0, 0.9, 10)            # D0 fastest by a small margin
    grid_pos = [6, 1, 2, 3, 4, 5, 7, 8, 9, 10]  # D0 lines up 6th, behind 5 slower cars
    g = [GridEntry(driver=f"D{i}", strategy=strat, pace_offset_s=float(pace[i]),
                   grid_pos=grid_pos[i], dnf_prob=0.02) for i in range(10)]
    drs = run_position_simulation(cp, g, n_sims=8000, tyre_overrides=ov, era="drs", seed=1)
    y26 = run_position_simulation(cp, g, n_sims=8000, tyre_overrides=ov, era="2026", seed=1)
    mean_drs = next(o.mean_finish for o in drs.outcomes if o.driver == "D0")
    mean_26 = next(o.mean_finish for o in y26.outcomes if o.driver == "D0")
    assert mean_26 < mean_drs   # easier to pass -> the fast car carves forward more


def test_straightline_term_helps_a_fast_straightline_car():
    """A car with a straight-line advantage should gain finishing share when the term is on."""
    cp = store.circuit_params_for("Bahrain")
    ov = store.tyre_overrides_for("Bahrain")
    g = _grid(cp, ov)
    sl = np.zeros(10)
    sl[5] = 2.0   # a mid-grid car with a big straight-line advantage
    off = run_position_simulation(cp, g, n_sims=6000, tyre_overrides=ov,
                                  straightline=sl, straightline_s_per_z=0.0, seed=3)
    on = run_position_simulation(cp, g, n_sims=6000, tyre_overrides=ov,
                                 straightline=sl, straightline_s_per_z=0.3, seed=3)
    mean_off = next(o.mean_finish for o in off.outcomes if o.driver == "D5")
    mean_on = next(o.mean_finish for o in on.outcomes if o.driver == "D5")
    assert mean_on < mean_off   # the fast-straightline car finishes better (lower mean position)


def test_held_up_asymmetry_helps_a_fast_car_recover(cp_ov=None):
    """The owner's unwritten rule (brief 30): a much-faster car trapped behind a backmarker loses
    less (the slow car yields), so a fast car starting low recovers BETTER with the asymmetry on."""
    cp = store.circuit_params_for("Bahrain")
    ov = store.tyre_overrides_for("Bahrain")
    strat = optimize_strategy(cp, max_stops=2, tyre_overrides=ov, top_k=1)[0].strategy
    # D0 is clearly the fastest car but starts P10, behind 9 slower cars.
    pace = np.array([-0.9, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    grid_pos = [10, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    g = [GridEntry(driver=f"D{i}", strategy=strat, pace_offset_s=float(pace[i]),
                   grid_pos=grid_pos[i], dnf_prob=0.02) for i in range(10)]
    off = run_position_simulation(cp, g, n_sims=8000, tyre_overrides=ov,
                                  held_up_asymmetry=False, seed=5)
    on = run_position_simulation(cp, g, n_sims=8000, tyre_overrides=ov,
                                 held_up_asymmetry=True, seed=5)
    mean_off = next(o.mean_finish for o in off.outcomes if o.driver == "D0")
    mean_on = next(o.mean_finish for o in on.outcomes if o.driver == "D0")
    assert mean_on < mean_off   # yields -> the fast back-marker carves through faster
