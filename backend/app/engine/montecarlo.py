"""Vectorized Monte Carlo race simulation (docs/science/01 §4, docs/science/02 §5).

Runs N independent race simulations over all drivers and laps using contiguous
NumPy arrays, producing finishing-position distributions. Each lap, every driver's
time is the deterministic physics value plus positively-skewed execution noise;
safety cars (sampled per-sim from the 3-part TUM model) bunch the field and
discount pit stops; per-race retirements are sampled per driver.

Position resolution v1: drivers are ranked by cumulative race time per simulation.
This is the standard MVP simplification — it does not yet enforce track-position /
dirty-air overtaking constraints (the weakest-validated part of any sim; see
docs/science/02 §7). Documented as a known limitation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .params import CircuitParams, Compound, SafetyCarModel, TrackStatus, TyreParams, WEAR_FUEL_SENSITIVITY
from .physics import fuel_mass, fuel_penalty
from .strategy import Strategy, _tyre_params_for
from .tyres import degradation_penalty

# Whole-race pace uncertainty (s, 1-sigma) applied per driver per sim. Stands in
# for run-to-run form + the overtaking/track-position friction not yet modeled,
# so the fastest car doesn't win deterministically. Raised to ~0.12 s/lap-equivalent
# after the market backtest showed the model was grossly overconfident (predicting
# ~91% for its favourite vs the market's well-calibrated ~30-50%). See docs/science/02 §7.
FORM_SIGMA_S: float = 7.0


@dataclass
class GridEntry:
    driver: str           # 3-letter code
    strategy: Strategy
    pace_offset_s: float = 0.0   # +ve slower than the reference car
    grid_pos: int = 1
    number: int | None = None
    team: str = ""
    colour: str = "888888"
    dnf_prob: float = 0.08       # per-race retirement probability
    deg_multiplier: float = 1.0  # per-team tyre-management scaling on degradation


@dataclass
class DriverOutcome:
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
    p10_finish: int          # optimistic (better) finish
    p90_finish: int          # pessimistic
    dnf_pct: float
    finish_distribution: list[float]  # P(finish == k) for k = 1..n_drivers


@dataclass
class RaceSimResult:
    circuit: str
    total_laps: int
    n_sims: int
    outcomes: list[DriverOutcome]   # sorted by win_pct desc
    sc_probability: float           # P(>=1 safety car) across sims
    elapsed_ms: float = 0.0
    post_quali: bool = False        # True if a real qualifying grid was fused (sharper)
    rain_prob: float = 0.0          # race-window rain intensity 0 (dry) .. 1 (wet); realism number
    wet: bool = False               # True if rain widened the points market (see science/21)


def _per_lap_state(entry: GridEntry, n_laps: int, overrides) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-lap degradation, compound offset, and pit-flag arrays for one driver."""
    deg = np.zeros(n_laps, dtype=np.float64)
    off = np.zeros(n_laps, dtype=np.float64)
    pit = np.zeros(n_laps, dtype=bool)
    lap = 0
    for si, stint in enumerate(entry.strategy.stints):
        tp: TyreParams = _tyre_params_for(stint.compound, overrides)
        for k in range(stint.length):
            if lap >= n_laps:
                break
            age = stint.start_tyre_age + k
            deg[lap] = float(degradation_penalty(age, tp))
            off[lap] = tp.pace_offset_s
            lap += 1
        if si < len(entry.strategy.stints) - 1 and lap <= n_laps:
            pit[lap - 1] = True  # pit at the end of this stint's last lap
    return deg, off, pit


def _sample_safety_cars(
    n_laps: int, n_sims: int, sc: SafetyCarModel, rng: np.random.Generator
) -> np.ndarray:
    """Boolean (n_laps, n_sims) mask of safety-car laps from the 3-part model."""
    mask = np.zeros((n_laps, n_sims), dtype=bool)
    counts = rng.choice(len(sc.count_pmf), size=n_sims, p=_norm(sc.count_pmf))
    counts = np.minimum(counts, 3)
    # Quintile -> lap-range start; index 0 means "lap 1".
    start_choices = np.arange(len(sc.start_pmf))
    dur_choices = np.arange(1, len(sc.duration_pmf) + 1)
    max_count = int(counts.max()) if n_sims else 0
    for phase in range(max_count):
        active = counts > phase
        idx = np.where(active)[0]
        if idx.size == 0:
            continue
        starts = rng.choice(start_choices, size=idx.size, p=_norm(sc.start_pmf))
        durs = rng.choice(dur_choices, size=idx.size, p=_norm(sc.duration_pmf))
        for j, sim in enumerate(idx):
            if starts[j] == 0:
                s0 = 0
            else:
                frac_lo = (starts[j] - 1) / 5.0
                s0 = int(frac_lo * n_laps)
            s1 = min(n_laps, s0 + int(durs[j]))
            mask[s0:s1, sim] = True
    return mask


def _norm(p) -> np.ndarray:
    a = np.asarray(p, dtype=np.float64)
    return a / a.sum()


def _apply_dirty_air(
    cum: np.ndarray, sc_row: np.ndarray, loss_s: float, gap_s: float, rng: np.random.Generator
) -> None:
    """Add a per-lap dirty-air / track-position time loss to cars stuck in traffic (in place).

    Within each sim, a car running within `gap_s` of the car directly ahead (by cumulative
    time) loses a stochastic chunk of time (~U(0,loss_s)) -- the cost of dirty air + defending +
    not being able to pass. The leader (no car ahead) and any car with clear air ahead lose
    nothing, so a dominant car romps while a tight pack shuffles. Skipped under safety car (the
    field is bunched but not racing). `loss_s` already folds in the circuit's overtaking
    difficulty, so the effect is larger at hard-to-pass tracks (Monaco) than open ones (Monza).
    """
    order = np.argsort(cum, axis=0)                      # (d, sims): row r -> driver in P(r+1)
    sorted_cum = np.take_along_axis(cum, order, axis=0)
    gap_ahead = np.empty_like(sorted_cum)
    gap_ahead[0, :] = np.inf                             # leader: clear air
    gap_ahead[1:, :] = sorted_cum[1:, :] - sorted_cum[:-1, :]
    loss = (gap_ahead < gap_s) * loss_s * rng.random(sorted_cum.shape)
    loss *= ~sc_row[None, :]                             # no battling under the safety car
    penalty = np.empty_like(cum)
    np.put_along_axis(penalty, order, loss, axis=0)
    cum += penalty


def run_race_simulation(
    circuit: CircuitParams,
    grid: list[GridEntry],
    *,
    n_sims: int = 10_000,
    tyre_overrides: dict[Compound, TyreParams] | None = None,
    dirty_air_s: float = 0.0,
    dirty_air_gap_s: float = 1.0,
    overtaking: float = 1.0,
    seed: int = 12345,
) -> RaceSimResult:
    """Vectorized field MC. `dirty_air_s>0` enables the track-position/battling penalty
    (see `_apply_dirty_air`): each lap a car within `dirty_air_gap_s` of the car ahead loses
    a stochastic chunk of time scaled by `overtaking` (circuit difficulty); a clear leader
    loses nothing. This injects realistic, self-limiting finishing-order variance (brief 22)
    and is the physically-grounded reason fast cars don't win deterministically. Default 0
    keeps the Strategy Lab / legacy behaviour unchanged."""
    rng = np.random.default_rng(seed)
    n = circuit.total_laps
    d = len(grid)
    base_s = circuit.base_lap_ms / 1000.0

    laps = np.arange(1, n + 1, dtype=np.float64)
    base_fuel = base_s + np.asarray(fuel_penalty(laps, circuit.fuel))          # (n,)
    fuel_frac = np.asarray(fuel_mass(laps, circuit.fuel)) / max(1e-6, circuit.fuel.start_fuel_kg)
    fuel_mult = 1.0 + WEAR_FUEL_SENSITIVITY * fuel_frac                         # (n,)

    # Precompute deterministic per-driver, per-lap times: (d, n)
    det = np.zeros((d, n), dtype=np.float64)
    pit_flags = np.zeros((d, n), dtype=bool)
    for di, e in enumerate(grid):
        deg, off, pit = _per_lap_state(e, n, tyre_overrides)
        det[di] = base_fuel + deg * fuel_mult * e.deg_multiplier + off + e.pace_offset_s
        pit_flags[di] = pit

    # Safety car mask and neutralized lap time.
    sc_mask = _sample_safety_cars(n, n_sims, circuit.safety_car, rng)           # (n, sims)
    sc_lap_time = base_s * circuit.safety_car.lap_time_mult_sc

    pit_green = circuit.pit_loss.total_loss(TrackStatus.GREEN)
    pit_sc = circuit.pit_loss.total_loss(TrackStatus.SAFETY_CAR)

    cum = np.zeros((d, n_sims), dtype=np.float64)
    # Grid start penalty: ~0.25s per grid slot + small start randomness.
    grid_pos = np.array([e.grid_pos for e in grid], dtype=np.float64)[:, None]
    cum += 0.25 * (grid_pos - 1.0)
    cum += np.abs(rng.normal(0.0, 0.15, size=(d, n_sims)))
    # Race-form variance: a driver's true race pace is uncertain run-to-run
    # (setup, tyre prep, conditions). Applied once per sim as a whole-race offset.
    # Without this, deterministic pace gaps make the fastest car win too often;
    # it also stands in for the overtaking/track-position friction not yet modeled.
    cum += rng.normal(0.0, FORM_SIGMA_S, size=(d, n_sims))

    # Pre-generate skewed execution noise for all laps: (n, d, sims).
    noise = _skewed_noise((n, d, n_sims), circuit.noise.sigma_s, circuit.noise.skew, rng)

    for li in range(n):
        sc_row = sc_mask[li]                       # (sims,)
        det_l = det[:, li][:, None]                # (d, 1)
        lap_time = np.where(sc_row, sc_lap_time, det_l + noise[li])  # (d, sims)
        if pit_flags[:, li].any():
            add = np.where(sc_row, pit_sc, pit_green)               # (sims,)
            lap_time = lap_time + pit_flags[:, li][:, None] * add
        cum += lap_time
        if dirty_air_s > 0.0:
            _apply_dirty_air(cum, sc_row, dirty_air_s * overtaking, dirty_air_gap_s, rng)

    # Retirements: knock out some sims per driver (classified at the back).
    for di, e in enumerate(grid):
        dnf = rng.random(n_sims) < e.dnf_prob
        cum[di, dnf] = np.inf

    # Positions: rank by cumulative time per sim (1 = winner).
    ranks = cum.argsort(axis=0).argsort(axis=0) + 1                  # (d, sims)

    outcomes: list[DriverOutcome] = []
    for di, e in enumerate(grid):
        r = ranks[di]
        dnf_pct = float(np.mean(~np.isfinite(cum[di])))
        # Vectorized finishing-position histogram: P(finish == k) for k = 1..d.
        dist = (np.bincount(r, minlength=d + 1)[1 : d + 1] / n_sims).tolist()
        outcomes.append(
            DriverOutcome(
                driver=e.driver,
                number=e.number,
                team=e.team,
                colour=e.colour,
                grid_pos=e.grid_pos,
                win_pct=float(np.mean(r == 1)),
                podium_pct=float(np.mean(r <= 3)),
                points_pct=float(np.mean(r <= 10)),
                mean_finish=float(np.mean(r)),
                p50_finish=int(np.median(r)),
                p10_finish=int(np.percentile(r, 10)),
                p90_finish=int(np.percentile(r, 90)),
                dnf_pct=dnf_pct,
                finish_distribution=dist,
            )
        )

    outcomes.sort(key=lambda o: o.win_pct, reverse=True)
    sc_prob = float(np.mean(sc_mask.any(axis=0)))
    return RaceSimResult(
        circuit=circuit.name,
        total_laps=n,
        n_sims=n_sims,
        outcomes=outcomes,
        sc_probability=sc_prob,
    )


def _skewed_noise(
    shape: tuple[int, ...], sigma: float, skew: float, rng: np.random.Generator
) -> np.ndarray:
    """Positively-skewed, zero-median execution noise (seconds).

    Generates a skew-normal directly from two standard normals (Azzalini), which is
    ~30x faster than scipy.skewnorm.rvs on large arrays.
    """
    delta = skew / np.sqrt(1.0 + skew**2)
    u0 = rng.standard_normal(shape, dtype=np.float32)
    u1 = rng.standard_normal(shape, dtype=np.float32)
    x = delta * np.abs(u0) + np.sqrt(1.0 - delta**2) * u1   # skew-normal(skew)
    # Standardize to zero-mean unit-std, scale, then shift mode toward zero.
    sn_mean = delta * np.sqrt(2.0 / np.pi)
    sn_std = np.sqrt(1.0 - sn_mean**2)
    x = (x - sn_mean) / sn_std
    x *= np.float32(sigma)
    # Mode of a positively-skewed dist is below the mean; nudge so a clean lap is
    # the most likely outcome (small positive bias remains -> mostly time loss).
    x -= np.float32(sigma * 0.4)
    return x
