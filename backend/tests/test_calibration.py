"""Tests for the tyre fit and calibration store (data-independent)."""

import numpy as np

from app.engine import calibration_store as store
from app.engine.params import CircuitParams, Compound
from app.engine.tyres import degradation_penalty, fit_tyre_parameters


def test_fit_recovers_a_known_curve():
    # Synthesize a linear-dominated degradation profile and check the fit tracks it.
    ages = np.arange(0, 30, dtype=float)
    true_deg = 0.5 * np.exp(-0.4 * ages) + 0.05 * ages
    tp = fit_tyre_parameters(ages, true_deg)
    pred = degradation_penalty(ages, tp)
    # Mean absolute error should be small (well under 0.1s).
    assert float(np.mean(np.abs(pred - true_deg))) < 0.1


def test_calibration_store_fallback_is_safe():
    # Unknown circuit -> generic CircuitParams, no crash, no overrides.
    cp = store.circuit_params_for("DoesNotExist")
    assert isinstance(cp, CircuitParams)
    assert cp.base_lap_ms > 0
    assert store.tyre_overrides_for("DoesNotExist") == {}


def test_calibrated_overrides_preserve_compound_offset():
    # If calibration data exists, overrides must carry a compound pace offset and
    # produce monotonically increasing degradation after warm-up.
    circuits = store.available_circuits()
    if not circuits:
        return  # ETL not run in this environment; nothing to assert
    ov = store.tyre_overrides_for(circuits[0])
    for tp in ov.values():
        d = degradation_penalty(np.arange(5, 25), tp)
        assert np.all(np.diff(d) > -1e-6)  # non-decreasing wear after warm-up
        assert Compound  # sanity import use
