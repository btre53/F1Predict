"""Three-phase tyre degradation model and calibration.

See docs/science/01-lap-time-model.md section 3.

    t_deg(age) = t1*exp(-t2*age) + t3*age + t4/(1+exp(-t5*(age-t6)))
                 \\__ warm-up __/  \\linear/  \\______ cliff ______/
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from .params import TYRE_FIT_BOUNDS, TYRE_FIT_INITIAL, Compound, TyreParams


def degradation_penalty(age: np.ndarray | float, p: TyreParams) -> np.ndarray | float:
    """Lap-time penalty (s) from tyre age, relative to a fresh in-window tyre.

    Vectorized over ``age`` (works on scalars or NumPy arrays).
    """
    age = np.asarray(age, dtype=np.float64)
    warmup = p.theta1 * np.exp(-p.theta2 * age)
    linear = p.theta3 * age
    cliff = p.theta4 / (1.0 + np.exp(-p.theta5 * (age - p.theta6)))
    return warmup + linear + cliff


def compound_lap_penalty(age: np.ndarray | float, p: TyreParams) -> np.ndarray | float:
    """Total tyre contribution to lap time: degradation + compound pace offset."""
    return degradation_penalty(age, p) + p.pace_offset_s


def fit_tyre_parameters(
    ages: np.ndarray,
    residuals: np.ndarray,
    *,
    pace_offset_s: float = 0.0,
) -> TyreParams:
    """Bounded least-squares fit of the three-phase curve to fuel-corrected data.

    ``residuals`` are fuel-corrected lap-time deltas (s) vs. the fresh-tyre
    baseline. We use bounded SLSQP (not a free fit) because the cliff parameters
    are weakly identified on sparse long-run data — see docs/science/04 (C2).
    """
    ages = np.asarray(ages, dtype=np.float64)
    residuals = np.asarray(residuals, dtype=np.float64)

    def loss(x: np.ndarray) -> float:
        t1, t2, t3, t4, t5, t6 = x
        pred = (
            t1 * np.exp(-t2 * ages)
            + t3 * ages
            + t4 / (1.0 + np.exp(-t5 * (ages - t6)))
        )
        return float(np.sum((residuals - pred) ** 2))

    result = minimize(
        loss,
        x0=np.array(TYRE_FIT_INITIAL),
        method="SLSQP",
        bounds=TYRE_FIT_BOUNDS,
    )
    t1, t2, t3, t4, t5, t6 = result.x
    return TyreParams(t1, t2, t3, t4, t5, t6, pace_offset_s)


def cliff_lap(p: TyreParams) -> float:
    """The estimated 'cliff' lap (logistic inflection point)."""
    return p.theta6


def estimate_optimal_stint(p: TyreParams, max_laps: int = 40) -> int:
    """Cheap heuristic: the lap by which cumulative deg crosses a pit-worthy cost.

    Used as a sensible default stint length before the full optimizer runs.
    """
    ages = np.arange(1, max_laps + 1)
    marginal = np.diff(degradation_penalty(np.arange(0, max_laps + 1), p))
    # Pit when marginal deg per lap exceeds ~0.15 s (tyres falling off a cliff).
    over = np.where(marginal > 0.15)[0]
    return int(over[0]) if len(over) else max_laps


# Convenience: seed lookup that always returns a usable curve.
def seed_for(compound: Compound) -> TyreParams:
    from .params import TYRE_SEED

    return TYRE_SEED[compound]
