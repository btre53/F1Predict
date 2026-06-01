"""Deterministic physics layer: the baseline lap time before ML residual + noise.

See docs/science/01-lap-time-model.md sections 1-3.

    t_physics(lap) = base_lap
                   + k_fuel * fuel_mass(lap)        # fuel effect (linear)
                   + tyre_penalty(compound, age)    # three-phase degradation
                   + driver/car pace offset
"""

from __future__ import annotations

import numpy as np

from .params import CircuitParams, Compound, FuelModel
from .tyres import compound_lap_penalty, seed_for


def fuel_mass(lap: np.ndarray | float, fuel: FuelModel) -> np.ndarray | float:
    """Remaining fuel mass (kg) at the start of ``lap`` (1-indexed)."""
    lap = np.asarray(lap, dtype=np.float64)
    return np.clip(fuel.start_fuel_kg - fuel.burn_kg_per_lap * (lap - 1), 0.0, None)


def fuel_penalty(lap: np.ndarray | float, fuel: FuelModel) -> np.ndarray | float:
    """Lap-time penalty (s) from carrying fuel on ``lap``."""
    return fuel.k_fuel_s_per_kg * fuel_mass(lap, fuel)


def baseline_lap_time_s(
    lap: int,
    *,
    tyre_age: int,
    compound: Compound,
    circuit: CircuitParams,
    pace_offset_s: float = 0.0,
    tyre_params=None,
) -> float:
    """Deterministic physics lap time (seconds) for one driver on one lap."""
    base_s = circuit.base_lap_ms / 1000.0
    fuel_s = float(fuel_penalty(lap, circuit.fuel))
    tp = tyre_params if tyre_params is not None else seed_for(compound)
    tyre_s = float(compound_lap_penalty(tyre_age, tp))
    return base_s + fuel_s + tyre_s + pace_offset_s


def fuel_correct(
    observed_lap_time_s: float, lap: int, fuel: FuelModel
) -> float:
    """Convert an observed lap to zero-fuel-equivalent pace (for tyre fitting)."""
    return observed_lap_time_s - float(fuel_penalty(lap, fuel))
