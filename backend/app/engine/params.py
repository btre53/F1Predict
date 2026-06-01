"""Calibrated physical parameters seeded from research.

Every value here is sourced in ``docs/science/`` (and cross-checked against the
original spec in ``docs/science/04-spec-validation.md``). These are *defaults* /
seeds; circuit- and era-specific values override them once the ETL + calibration
jobs run on real data.

Primary source for the numeric seeds: the TUM Heilmeier race simulator
(github.com/TUMFTM/race-simulation) and the state-space tyre-degradation paper
(arXiv 2512.00640).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RegulationEra(str, Enum):
    """Regulatory eras. 2026 parameters are projections, flagged low-confidence."""

    GROUND_EFFECT_DRS = "GE_DRS_2022_2025"
    ACTIVE_AERO_2026 = "ACTIVE_AERO_2026"


class Compound(str, Enum):
    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"


class TrackStatus(str, Enum):
    GREEN = "GREEN"
    VSC = "VSC"
    SAFETY_CAR = "SAFETY_CAR"
    RED = "RED"


# A heavier (full-fuel) car stresses the tyres more, so degradation runs faster
# early in the race. This dimensionless sensitivity scales the degradation penalty
# by up to this fraction at full fuel vs. empty -> "hards early, softs late".
WEAR_FUEL_SENSITIVITY: float = 0.30


# --------------------------------------------------------------------------- #
# Fuel model  (docs/science/01-lap-time-model.md  section 2)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FuelModel:
    # Lap-time sensitivity to fuel mass, seconds per kg. Rule of thumb 0.3 s/10 kg.
    k_fuel_s_per_kg: float = 0.030
    # Burn per lap, kg. Circuit-specific in production (Spa/Silverstone higher).
    burn_kg_per_lap: float = 1.6
    # Starting fuel load, kg. 2026 drops the max toward ~70 kg.
    start_fuel_kg: float = 105.0


FUEL_BY_ERA: dict[RegulationEra, FuelModel] = {
    # Lighter 2026 chassis -> lower fuel sensitivity and smaller fuel load.
    RegulationEra.GROUND_EFFECT_DRS: FuelModel(0.030, 1.6, 105.0),
    RegulationEra.ACTIVE_AERO_2026: FuelModel(0.026, 1.35, 70.0),
}


# --------------------------------------------------------------------------- #
# Tyre degradation  (docs/science/01  section 3)
#   t_deg(age) = t1*exp(-t2*age) + t3*age + t4/(1+exp(-t5*(age-t6)))
#   Phase 1 warm-up   Phase 2 linear      Phase 3 logistic cliff
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TyreParams:
    theta1: float  # thermal warm-up magnitude (s)
    theta2: float  # warm-up decay rate
    theta3: float  # linear wear rate (s/lap)
    theta4: float  # cliff magnitude (s)
    theta5: float  # cliff steepness
    theta6: float  # cliff inflection lap
    pace_offset_s: float  # compound pace delta vs the reference (HARD), seconds


# Seed degradation curves (dry, generic circuit). Replaced by per-circuit Bayesian
# fits from FP long runs. Linear rates ~0.05 s/lap for hard/medium per FIA targets.
TYRE_SEED: dict[Compound, TyreParams] = {
    Compound.SOFT: TyreParams(0.8, 0.55, 0.11, 3.5, 0.6, 18.0, -0.9),
    Compound.MEDIUM: TyreParams(0.7, 0.50, 0.060, 3.0, 0.5, 28.0, -0.4),
    Compound.HARD: TyreParams(0.6, 0.45, 0.050, 2.5, 0.45, 38.0, 0.0),
    # Wet compounds: dominated by water clearance, not thermal deg (placeholder).
    Compound.INTERMEDIATE: TyreParams(0.5, 0.4, 0.04, 2.0, 0.4, 30.0, 4.0),
    Compound.WET: TyreParams(0.5, 0.4, 0.03, 1.5, 0.4, 30.0, 7.0),
}

# Bounds for the bounded SLSQP / Bayesian fit (physical realism; prevents the
# weakly-identified cliff params from running away on sparse data).
TYRE_FIT_BOUNDS: tuple[tuple[float, float], ...] = (
    (0.0, 3.0),    # theta1
    (0.05, 2.0),   # theta2
    (0.0, 0.4),    # theta3
    (0.0, 8.0),    # theta4
    (0.05, 2.0),   # theta5
    (5.0, 60.0),   # theta6
)
TYRE_FIT_INITIAL = (0.8, 0.5, 0.05, 3.0, 0.5, 25.0)


# --------------------------------------------------------------------------- #
# Driver execution noise  (docs/science/01  section 4)
#   Positively-skewed t  ->  drivers lose more time than they gain.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NoiseParams:
    sigma_s: float = 0.28      # clean-lap scale, seconds (0.20-0.35 driver-specific)
    skew: float = 4.0          # skew-normal alpha; positive = long slow tail
    df: float = 4.0            # t degrees of freedom (heavy tails for blips)
    traffic_inflation: float = 1.6   # multiply sigma when in dirty air
    wet_inflation: float = 2.2       # multiply sigma in wet conditions


# --------------------------------------------------------------------------- #
# Pit loss  (docs/science/02  sections 1 & 6) -- decomposed, status-scaled.
#   Only the DRIVE portion scales with track status; the standstill does not.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PitLossModel:
    standstill_s: float = 2.4        # tyre change (team-dependent); does NOT scale
    drive_inlap_s: float = 3.04      # TUM Catalunya 2019
    drive_outlap_s: float = 16.0
    # Drive-portion multipliers by track status.
    sc_drive_mult: float = 0.45
    vsc_drive_mult: float = 0.62

    def total_loss(self, status: TrackStatus = TrackStatus.GREEN) -> float:
        drive = self.drive_inlap_s + self.drive_outlap_s
        if status == TrackStatus.SAFETY_CAR:
            drive *= self.sc_drive_mult
        elif status == TrackStatus.VSC:
            drive *= self.vsc_drive_mult
        return self.standstill_s + drive


# --------------------------------------------------------------------------- #
# Safety car  (docs/science/02  section 5)  -- three-part model, NOT flat hazard.
#   TUM pars_mcs.ini, seasons 2014-2019.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SafetyCarModel:
    # P(number of SC phases in a race) for [0, 1, 2, 3].
    count_pmf: tuple[float, ...] = (0.455, 0.413, 0.099, 0.033)
    # P(SC starts in) [lap 1, then race-distance quintiles <20/<40/<60/<80/<100%].
    start_pmf: tuple[float, ...] = (0.364, 0.136, 0.136, 0.08, 0.193, 0.091)
    # P(SC duration in laps) for durations 1..10 (peaks at 2-4 laps).
    duration_pmf: tuple[float, ...] = (
        0.05, 0.20, 0.25, 0.20, 0.12, 0.08, 0.05, 0.03, 0.01, 0.01,
    )
    # Per-circuit base-rate multiplier on count_pmf (Singapore >> Paul Ricard).
    circuit_multiplier: float = 1.0
    # Lap-time multiplier and consumption/deg multipliers under SC.
    lap_time_mult_sc: float = 1.6
    consumption_mult_sc: float = 0.25
    tyre_deg_mult_sc: float = 0.25


# --------------------------------------------------------------------------- #
# Overtaking / dirty air  (docs/science/02  section 7)
#   pace_loss(gap) = L_max * exp(-gap / g0)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OvertakeModel:
    dirty_air_lmax_s: float = 0.6     # max following pace loss inside the wake
    dirty_air_g0_s: float = 1.0       # wake decay length (seconds of gap)
    overtake_threshold_s: float = 1.0  # pace advantage needed to pass (track-dep.)
    drs_benefit_s: float = 0.5        # GE_DRS era only
    min_following_gap_s: float = 0.5
    duel_cost_s: float = 0.3


@dataclass(frozen=True)
class CircuitParams:
    """Per-circuit constants. Seeded generic; overwritten by ETL calibration."""

    name: str = "generic"
    base_lap_ms: int = 85_000
    total_laps: int = 57
    era: RegulationEra = RegulationEra.GROUND_EFFECT_DRS
    fuel: FuelModel = field(default_factory=FuelModel)
    pit_loss: PitLossModel = field(default_factory=PitLossModel)
    safety_car: SafetyCarModel = field(default_factory=SafetyCarModel)
    overtake: OvertakeModel = field(default_factory=OvertakeModel)
    noise: NoiseParams = field(default_factory=NoiseParams)
