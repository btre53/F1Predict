"""Tie the calibrated data + strategy optimizer + Monte Carlo into a race forecast.

Builds a default grid from calibrated driver pace, assigns the optimal strategy,
and runs the vectorized simulation to produce finishing-position distributions.
"""

from __future__ import annotations

from . import calibration_store as store
from .montecarlo import GridEntry, RaceSimResult, run_race_simulation
from .params import CircuitParams
from .strategy import optimize_strategy

# Era year for the hazard DNF model on a forward-looking forecast (latest full season).
HAZARD_ERA_YEAR = 2025

# Team colours (hex, no #) for the UI. Falls back to grey.
TEAM_COLOURS: dict[str, str] = {
    "Red Bull Racing": "3671C6",
    "Ferrari": "E8002D",
    "Mercedes": "27F4D2",
    "McLaren": "FF8000",
    "Aston Martin": "229971",
    "Alpine": "0093CC",
    "Williams": "64C4FF",
    "RB": "6692FF",
    "AlphaTauri": "5E8FAA",
    "Kick Sauber": "52E252",
    "Alfa Romeo": "C92D4B",
    "Haas F1 Team": "B6BABD",
}

# A few well-known fallback offsets so the grid is populated even before the ETL
# runs. Pace offset in seconds vs a mid-field reference (negative = faster).
_FALLBACK_DRIVERS = [
    {"driver": "VER", "team": "Red Bull Racing", "pace_offset_s": -0.9, "driver_number": 1},
    {"driver": "NOR", "team": "McLaren", "pace_offset_s": -0.7, "driver_number": 4},
    {"driver": "LEC", "team": "Ferrari", "pace_offset_s": -0.6, "driver_number": 16},
    {"driver": "HAM", "team": "Mercedes", "pace_offset_s": -0.5, "driver_number": 44},
]


def build_default_grid(
    circuit: CircuitParams, tyre_overrides, max_drivers: int = 20
) -> list[GridEntry]:
    drivers = store.load_drivers() or _FALLBACK_DRIVERS
    drivers = drivers[:max_drivers]

    # Optimal strategy for this circuit, assigned to every car as the baseline.
    opt = optimize_strategy(
        circuit, max_stops=2, tyre_overrides=tyre_overrides, top_k=1
    )
    strategy = opt[0].strategy if opt else None

    grid: list[GridEntry] = []
    for i, d in enumerate(drivers):
        if strategy is None:
            continue
        team = d.get("team", "")
        grid.append(
            GridEntry(
                driver=d["driver"],
                strategy=strategy,
                pace_offset_s=float(d.get("pace_offset_s", 0.0)),
                grid_pos=i + 1,  # default grid = pace order; override per request
                number=d.get("driver_number"),
                team=team,
                colour=TEAM_COLOURS.get(team, "888888"),
                # Per-team tyre multiplier is display-only (Explainer): applied
                # globally it injects pooled-season team form into every race and
                # degrades predictions. deg_multiplier left at 1.0 here.
            )
        )
    return grid


def predict_race(
    circuit_name: str,
    *,
    n_sims: int = 10_000,
    grid_order: list[str] | None = None,
) -> RaceSimResult:
    """Forecast a race at ``circuit_name`` using calibrated data.

    ``grid_order`` optionally overrides the starting grid (list of driver codes,
    pole first); unspecified drivers keep pace order.
    """
    circuit = store.circuit_params_for(circuit_name)
    tyre_overrides = store.tyre_overrides_for(circuit_name)
    grid = build_default_grid(circuit, tyre_overrides)

    if grid_order:
        rank = {code: i for i, code in enumerate(grid_order)}
        grid.sort(key=lambda e: rank.get(e.driver, len(grid_order) + e.grid_pos))
        for i, e in enumerate(grid):
            e.grid_pos = i + 1

    # Per-driver DNF risk from the survival/hazard model (docs/science/15), replacing the
    # flat 0.08. Lazy import breaks the engine->models->etl->engine cycle; fails safe to
    # the flat default if the model/data is unavailable. HAZARD_ERA_YEAR sets the era term
    # (latest full season) for a modern-car forecast.
    try:
        from app.models import hazard

        hazard.apply_to_grid(grid, year=HAZARD_ERA_YEAR, total_laps=circuit.total_laps)
    except Exception:
        pass

    return run_race_simulation(
        circuit, grid, n_sims=n_sims, tyre_overrides=tyre_overrides
    )
