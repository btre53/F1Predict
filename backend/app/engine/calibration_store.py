"""Load calibrated per-circuit parameters (from the ETL) into engine objects.

Falls back to generic seeds when no calibration exists, so the engine always runs
even before the ETL has been executed.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .params import (
    CircuitParams,
    Compound,
    FUEL_BY_ERA,
    RegulationEra,
    TyreParams,
)
from .tyres import seed_for

_DATA = Path(__file__).resolve().parents[2] / "data"
CALIBRATION_JSON = _DATA / "calibration.json"
DRIVERS_JSON = _DATA / "drivers.json"
TEAM_TYRES_JSON = _DATA / "team_tyres.json"


@lru_cache
def _load_raw() -> dict:
    if CALIBRATION_JSON.exists():
        return json.loads(CALIBRATION_JSON.read_text())
    return {}


@lru_cache
def load_drivers() -> list[dict]:
    """Calibrated driver pace order (fastest first); empty if ETL not run."""
    if DRIVERS_JSON.exists():
        return json.loads(DRIVERS_JSON.read_text())
    return []


@lru_cache
def load_team_tyres() -> dict:
    """Per-team tyre-management multipliers; {} if not calibrated."""
    if TEAM_TYRES_JSON.exists():
        return json.loads(TEAM_TYRES_JSON.read_text())
    return {}


def team_deg_multiplier(team: str) -> float:
    """Degradation scaling for a team (1.0 if unknown)."""
    teams = load_team_tyres().get("teams", {})
    entry = teams.get(team)
    return float(entry["deg_multiplier"]) if entry else 1.0


def available_circuits() -> list[str]:
    return sorted(_load_raw().keys())


def _tyre_params_from(d: dict, compound: Compound) -> TyreParams:
    # Preserve the seed compound pace-offset (degradation fit is offset-free).
    offset = seed_for(compound).pace_offset_s
    return TyreParams(
        d["theta1"], d["theta2"], d["theta3"],
        d["theta4"], d["theta5"], d["theta6"],
        pace_offset_s=offset,
    )


def tyre_overrides_for(circuit: str) -> dict[Compound, TyreParams]:
    """Calibrated tyre curves for a circuit (empty dict if none)."""
    cal = _load_raw().get(circuit)
    if not cal:
        return {}
    out: dict[Compound, TyreParams] = {}
    for comp_name, d in cal.get("tyres", {}).items():
        try:
            out[Compound(comp_name)] = _tyre_params_from(d, Compound(comp_name))
        except (KeyError, ValueError):
            continue
    return out


def circuit_params_for(circuit: str) -> CircuitParams:
    """Build CircuitParams from calibration, falling back to generic seeds."""
    cal = _load_raw().get(circuit)
    if not cal or not cal.get("base_lap_ms"):
        return CircuitParams(name=circuit)
    era = RegulationEra(cal.get("era", RegulationEra.GROUND_EFFECT_DRS.value))
    return CircuitParams(
        name=circuit,
        base_lap_ms=int(cal["base_lap_ms"]),
        total_laps=int(cal["total_laps"]),
        era=era,
        fuel=FUEL_BY_ERA[era],
    )
