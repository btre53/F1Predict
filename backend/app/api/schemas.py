"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.engine.params import Compound


class StintIn(BaseModel):
    compound: Compound
    length: int = Field(gt=0, le=100)
    start_tyre_age: int = Field(default=0, ge=0)


class StrategyIn(BaseModel):
    stints: list[StintIn] = Field(min_length=1)


class CircuitIn(BaseModel):
    """Minimal circuit override; falls back to generic seeds."""

    name: str = "generic"
    base_lap_ms: int = Field(default=85_000, gt=10_000)
    total_laps: int = Field(default=57, gt=1, le=100)


class EvaluateRequest(BaseModel):
    strategy: StrategyIn
    circuit: CircuitIn = CircuitIn()
    circuit_name: str | None = None  # if set, use calibrated params + tyre curves
    pace_offset_s: float = 0.0
    sc_laps: list[int] = []


class StrategyResultOut(BaseModel):
    total_time_s: float
    delta_to_best_s: float
    avg_lap_s: float
    pit_laps: list[int]
    n_stops: int
    valid: bool
    notes: list[str]
    compounds: list[str]
    stint_lengths: list[int]
    lap_times_s: list[float] = []


class OptimizeRequest(BaseModel):
    circuit: CircuitIn = CircuitIn()
    circuit_name: str | None = None  # if set, use calibrated params + tyre curves
    compounds: list[Compound] | None = None
    max_stops: int = Field(default=2, ge=1, le=3)
    pace_offset_s: float = 0.0
    top_k: int = Field(default=5, ge=1, le=20)


class CircuitInfo(BaseModel):
    name: str
    base_lap_ms: int
    total_laps: int
    era: str
    calibrated: bool
    compounds_calibrated: list[str]


class UndercutRequest(BaseModel):
    gap_s: float = Field(ge=0)
    attacker_compound: Compound
    attacker_tyre_age: int = Field(default=0, ge=0)
    defender_compound: Compound
    defender_tyre_age: int = Field(ge=0)
    pit_lap: int = Field(gt=0)
    circuit: CircuitIn = CircuitIn()
    window_laps: int = Field(default=3, ge=1, le=10)


class UndercutResultOut(BaseModel):
    gap_s: float
    pit_lap: int
    projected_gap_after_s: float
    undercut_works: bool
    fresh_tyre_gain_s: float
    notes: list[str]


class CoverExtendRequest(BaseModel):
    circuit_name: str
    gap_to_follower_s: float = Field(ge=0)
    laps_remaining: int = Field(gt=0, le=100)
    leader_tyre_age: int = Field(ge=0)
    leader_compound: Compound


class CoverExtendResultOut(BaseModel):
    recommendation: str
    cover_value_s: float
    extend_value_s: float
    rationale: str


class SafetyCarRequest(BaseModel):
    circuit_name: str
    current_lap: int = Field(gt=0, le=100)
    current_compound: Compound
    current_tyre_age: int = Field(ge=0, le=80)
    fresh_compound: Compound = Compound.HARD


class SafetyCarResultOut(BaseModel):
    recommendation: str
    pit_now_cost_s: float
    stay_out_cost_s: float
    delta_s: float
    sc_pit_saving_s: float
    stay_plan: str
    rationale: str


class PredictRequest(BaseModel):
    circuit_name: str
    n_sims: int = Field(default=10_000, ge=1000, le=50_000)
    grid_order: list[str] | None = None  # driver codes, pole first (optional)


class DriverOutcomeOut(BaseModel):
    driver: str
    number: int | None
    team: str
    colour: str
    grid_pos: int
    win_pct: float
    podium_pct: float
    points_pct: float
    mean_finish: float
    p50_finish: int
    p10_finish: int
    p90_finish: int
    dnf_pct: float
    finish_distribution: list[float]


class RaceSimOut(BaseModel):
    circuit: str
    total_laps: int
    n_sims: int
    sc_probability: float
    outcomes: list[DriverOutcomeOut]
