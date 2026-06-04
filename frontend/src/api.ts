// Typed client for the F1Predict API. In dev, Vite proxies /api -> :8000.

export type Compound = "SOFT" | "MEDIUM" | "HARD" | "INTERMEDIATE" | "WET";

export interface Circuit {
  name: string;
  base_lap_ms: number;
  total_laps: number;
}

export interface CircuitInfo {
  name: string;
  base_lap_ms: number;
  total_laps: number;
  era: string;
  calibrated: boolean;
  compounds_calibrated: string[];
}

export interface NextRace {
  available: boolean;
  round?: number;
  event_name?: string;
  circuit?: string;
  race_utc?: string;
  quali_utc?: string;
  is_upcoming?: boolean;
  days_away?: number;
  calibrated?: boolean;
}

export interface ChampDriver {
  driver: string;
  team: string;
  title_pct: number;
  current_points: number;
  exp_points: number;
  p_top3: number;
  market_pct: number | null;
}

export interface ChampConstructor {
  team: string;
  title_pct: number;
  exp_points: number;
  market_pct: number | null;
}

export interface Championship {
  year: number;
  n_done: number;
  n_remaining: number;
  n_sims: number;
  market_available: boolean;
  drivers: ChampDriver[];
  constructors: ChampConstructor[];
}

export interface DriverOverride {
  pace_delta?: number;
  dnf_prob?: number | null;
  extra_dnfs?: number;
}

export interface ReplayModel {
  id: string;
  label: string;
  blurb: string;
}

export interface ReplayDriverPred {
  win: number;
  podium: number;
}

export interface ReplayDriver {
  driver: string;
  team: string;
  grid: number | null;
  finish: number;
  models: Record<string, ReplayDriverPred | null>;
}

export interface ReplayRace {
  year: number;
  circuit: string;
  seq: number;
  has_sim: boolean;
  drivers: ReplayDriver[];
}

export interface ModelReplay {
  models: ReplayModel[];
  n_races: number;
  races: ReplayRace[];
}

export interface CompanionOutcome {
  name: string;
  model_pct: number;
  market_pct: number | null;
  edge: number | null;
}

export interface CompanionProp {
  type: string;
  title: string;
  modelled: boolean;
  slug: string;
  outcomes: CompanionOutcome[];
}

export interface CompanionRace {
  circuit: string;
  event_name: string;
  round: number | null;
  race_utc: string | null;
  quali_utc: string | null;
  days_away: number | null;
  is_upcoming: boolean | null;
  modelled: boolean;
}

export interface Companion {
  available: boolean;
  race?: CompanionRace;
  n_props?: number;
  props?: CompanionProp[];
}

export interface StrategyResult {
  total_time_s: number;
  delta_to_best_s: number;
  avg_lap_s: number;
  pit_laps: number[];
  n_stops: number;
  valid: boolean;
  notes: string[];
  compounds: string[];
  stint_lengths: number[];
  lap_times_s?: number[];
}

export interface CoverExtendResult {
  recommendation: "COVER" | "EXTEND";
  cover_value_s: number;
  extend_value_s: number;
  rationale: string;
}

export interface UndercutResult {
  gap_s: number;
  pit_lap: number;
  projected_gap_after_s: number;
  undercut_works: boolean;
  fresh_tyre_gain_s: number;
  notes: string[];
}

export interface SafetyCarResult {
  recommendation: "PIT" | "STAY";
  pit_now_cost_s: number;
  stay_out_cost_s: number;
  delta_s: number;
  sc_pit_saving_s: number;
  stay_plan: string;
  rationale: string;
}

export interface StopForkOption {
  n_stops: number;
  compounds: string[];
  stint_lengths: number[];
  pit_laps: number[];
  avg_lap_s: number;
  total_time_s: number;
}

export interface StopForkResult {
  winner: "1-STOP" | "2-STOP";
  delta_s: number;
  one_stop: StopForkOption;
  two_stop: StopForkOption;
  rationale: string;
}

export interface RainCrossoverResult {
  recommendation: "SLICKS" | "INTERS";
  wetness: number;
  crossover_wetness: number;
  slick_penalty_s: number;
  inter_penalty_s: number;
  per_lap_delta_s: number;
  swing_over_remaining_s: number;
  rationale: string;
}

export interface DriverOutcome {
  driver: string;
  number: number | null;
  team: string;
  colour: string;
  grid_pos: number;
  win_pct: number;
  podium_pct: number;
  points_pct: number;
  mean_finish: number;
  p50_finish: number;
  p10_finish: number;
  p90_finish: number;
  dnf_pct: number;
  finish_distribution: number[];
}

export interface RaceSim {
  circuit: string;
  total_laps: number;
  n_sims: number;
  sc_probability: number;
  post_quali: boolean; // true if a real qualifying grid was fused (sharper than pre-quali)
  outcomes: DriverOutcome[];
}

export interface RaceRef {
  circuit: string;
  year: number;
  total_laps: number;
  n_drivers: number;
}

export interface ReplayDriver {
  driver: string;
  number: number | null;
  team: string;
  colour: string;
}

export interface ReplaySlot {
  driver: string;
  position: number;
  compound: string;
  tyre_life: number;
  pitting: boolean;
  gap_s: number;
  // Optional real sector times (present once backend_patch/real_sectors.md is applied;
  // until then charts/deriveSectors.ts reconstructs them from gap_s). Older parquet rows
  // that predate sector capture stay valid as null.
  sector1_s?: number | null;
  sector2_s?: number | null;
  sector3_s?: number | null;
}

export interface ReplayLap {
  lap: number;
  track_status: string;
  order: ReplaySlot[];
}

export interface Replay {
  circuit: string;
  year: number;
  total_laps: number;
  drivers: ReplayDriver[];
  laps: ReplayLap[];
}

export interface TrackOutline {
  path: string;
}

// Per-lap model vs de-vigged Polymarket win-prob overlay for the replay leaderboard (#23).
// `laps` is keyed by lap number (string) -> driver code -> {model, market}. Calibrated but
// does NOT lead the market (brief 13) -- a transparency companion, not a trading signal.
export interface InplayProb {
  model: number;
  market: number | null;
}
export interface InplayOverlay {
  winner: string | null;
  n_laps: number;
  delayed: boolean;
  laps: Record<string, Record<string, InplayProb>>;
}

export interface ReplayPositions {
  view: [number, number];
  frame_s: number;
  n_frames: number;
  // Per-driver code -> per-frame [x, y] (null when the car is off-track that frame).
  cars: Record<string, ([number, number] | null)[]>;
}

export interface ScoreMetric {
  brier: number | null;
  logloss: number | null;
  n: number;
  base_rate: number | null;
}

export interface CalibrationBin {
  bin: string;
  predicted: number;
  observed: number;
  n: number;
}

export interface PerRace {
  circuit: string;
  year: number;
  actual_winner: string;
  model_top_pick: string;
  model_win_pct: number;
  hit: boolean;
}

export interface Backtest {
  n_races: number;
  n_sims: number;
  metrics: { win: ScoreMetric; podium: ScoreMetric; points: ScoreMetric };
  baseline_win: ScoreMetric;
  calibration_win: CalibrationBin[];
  top_pick_accuracy: number;
  per_race: PerRace[];
}

export interface MarketOutcome {
  name: string;
  price: number;
  implied: number;
  // Live order-book detail (present on /markets/live; null on the older snapshot shape).
  // `source` = how `price` was derived: book_mid (tight two-sided book), last_trade
  // (one-sided/wide book), or gamma (no book) — surfaced so thin liquidity is visible.
  bid?: number | null;
  ask?: number | null;
  spread?: number | null;
  source?: "book_mid" | "last_trade" | "gamma";
}

export interface LiveMarket {
  question: string;
  slug: string;
  overround: number;
  outcomes: MarketOutcome[];
}

export interface LiveMarkets {
  available: boolean;
  source?: "ws" | "live" | "snapshot" | "none";
  as_of?: string | null;
  markets: LiveMarket[];
}

export interface ForwardBacktest {
  n_races: number;
  n_skipped_insufficient_history: number;
  n_sims: number;
  metrics: { win: ScoreMetric; podium: ScoreMetric; points: ScoreMetric };
  calibration_win: CalibrationBin[];
  top_pick_accuracy: number;
}

export interface VsMarketRace {
  circuit: string;
  winner: string;
  market_fav: string;
  market_fav_p: number;
  market_p_winner: number;
  model_fav: string | null;
  model_fav_p: number | null;
  model_p_winner: number;
  market_hit: boolean;
  model_hit: boolean;
}

export interface VsMarket {
  n_races: number;
  n_sims: number;
  model_win: ScoreMetric;
  market_win: ScoreMetric;
  blend_win?: ScoreMetric;
  blend_alpha?: number;
  blend_beta?: number;
  model_top_pick_accuracy: number;
  market_top_pick_accuracy: number;
  per_race: VsMarketRace[];
}

export interface TeamTyre {
  deg_multiplier: number;
  wear_rate_s_per_lap: number;
  n_laps: number;
}

export interface TeamTyres {
  field_wear_rate_s_per_lap: number;
  teams: Record<string, TeamTyre>;
}

// --- Mechanistic-index endpoints (Methodology page) ---
export interface OvertakingRow { circuit: string; index: number; spread_temperature: number; }
export interface SafetyCarRow { circuit: string; sc_prior: number; }
export interface TyreForm { coefs: number[]; rmse: number; aic: number; }
export interface TyreCompound {
  n_laps: number; best_form: string; max_age_fitted: number;
  loss_at_age_s: Record<string, number>; forms: Record<string, TyreForm>;
}
export interface TyreDegradation { era: string; compounds: Record<string, TyreCompound>; }
export interface CarDnaBand { driver?: string; circuit?: string; team?: string; n?: number;
  low: number; med: number; high: number; straight: number; }
export interface CarDna {
  bands: string[]; year: number; note: string;
  circuit_demand: CarDnaBand[]; car_dna: CarDnaBand[];
}
export interface WeatherRow {
  year: number; circuit: string; wet: boolean;
  precip_mm_window: number; precip_mm_max: number; temp_c: number | null;
}

const BASE = "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${BASE}/health`).then((r) => r.json()),

  circuits: () =>
    fetch(`${BASE}/circuits`).then((r) => r.json() as Promise<CircuitInfo[]>),

  nextRace: () =>
    fetch(`${BASE}/calendar/next`).then((r) => r.json() as Promise<NextRace>),

  backtest: () =>
    fetch(`${BASE}/markets/backtest`).then((r) => {
      if (!r.ok) throw new Error(`backtest → ${r.status}`);
      return r.json() as Promise<Backtest>;
    }),

  forwardBacktest: () =>
    fetch(`${BASE}/markets/forward-backtest`).then((r) => {
      if (!r.ok) throw new Error(`forward → ${r.status}`);
      return r.json() as Promise<ForwardBacktest>;
    }),

  vsMarket: () =>
    fetch(`${BASE}/markets/vs-market`).then((r) => {
      if (!r.ok) throw new Error(`vs-market → ${r.status}`);
      return r.json() as Promise<VsMarket>;
    }),

  liveMarkets: () =>
    fetch(`${BASE}/markets/live`).then((r) => r.json() as Promise<LiveMarkets>),

  teamTyres: () =>
    fetch(`${BASE}/tyres/teams`).then((r) => {
      if (!r.ok) throw new Error(`tyres/teams → ${r.status}`);
      return r.json() as Promise<TeamTyres>;
    }),

  overtakingIndex: () =>
    fetch(`${BASE}/circuits/overtaking`).then((r) => r.json() as Promise<OvertakingRow[]>),
  safetyCarPrior: () =>
    fetch(`${BASE}/circuits/safety-car`).then((r) => r.json() as Promise<SafetyCarRow[]>),
  tyreDegradation: () =>
    fetch(`${BASE}/tyres/degradation`).then((r) => r.json() as Promise<TyreDegradation>),
  carDna: () => fetch(`${BASE}/cars/dna`).then((r) => r.json() as Promise<CarDna>),
  circuitWeather: () =>
    fetch(`${BASE}/circuits/weather`).then((r) => r.json() as Promise<WeatherRow[]>),

  evaluate: (
    stints: { compound: Compound; length: number }[],
    circuit: Circuit,
    circuitName?: string,
  ) =>
    post<StrategyResult>("/strategy/evaluate", {
      strategy: { stints },
      circuit,
      circuit_name: circuitName ?? null,
    }),

  // When circuitName is set, the backend uses calibrated params + tyre curves.
  optimize: (circuit: Circuit, maxStops = 2, topK = 6, circuitName?: string) =>
    post<StrategyResult[]>("/strategy/optimize", {
      circuit,
      circuit_name: circuitName ?? null,
      max_stops: maxStops,
      top_k: topK,
    }),

  replayRaces: () =>
    fetch(`${BASE}/replay/races`).then((r) => r.json() as Promise<RaceRef[]>),

  replayRace: (circuit: string, year: number) =>
    fetch(`${BASE}/replay/race?circuit=${encodeURIComponent(circuit)}&year=${year}`).then(
      (r) => r.json() as Promise<Replay>,
    ),

  trackOutline: (circuit: string, year: number) =>
    fetch(`${BASE}/replay/track?circuit=${encodeURIComponent(circuit)}&year=${year}`).then(
      (r) => (r.ok ? (r.json() as Promise<TrackOutline>) : null),
    ),

  replayPositions: (circuit: string, year: number) =>
    fetch(
      `${BASE}/replay/positions?circuit=${encodeURIComponent(circuit)}&year=${year}`,
    ).then((r) => (r.ok ? (r.json() as Promise<ReplayPositions>) : null)),

  replayInplay: (circuit: string, year: number) =>
    fetch(
      `${BASE}/replay/inplay?circuit=${encodeURIComponent(circuit)}&year=${year}`,
    ).then((r) => (r.ok ? (r.json() as Promise<InplayOverlay>) : null)),

  predict: (circuitName: string, nSims = 10000) =>
    post<RaceSim>("/predict/race", {
      circuit_name: circuitName,
      n_sims: nSims,
    }),

  // Committed, pre-computed default forecast served straight from disk (no sim, no cold
  // start) so the Predictor paints a real result instantly instead of a perpetual spinner.
  predictDefault: () =>
    fetch(`${BASE}/predict/default`).then((r) => {
      if (!r.ok) throw new Error(`predict/default → ${r.status}`);
      return r.json() as Promise<RaceSim>;
    }),

  championship: (withMarket = true, nSims = 20000) =>
    fetch(`${BASE}/championship?with_market=${withMarket}&n_sims=${nSims}`).then(
      (r) => {
        if (!r.ok) throw new Error(`championship → ${r.status}`);
        return r.json() as Promise<Championship>;
      },
    ),

  championshipSimulate: (
    overrides: Record<string, DriverOverride>,
    nSims = 12000,
  ) =>
    post<Championship>("/championship/simulate", { overrides, n_sims: nSims }),

  companion: () =>
    fetch(`${BASE}/companion/props`).then((r) => {
      if (!r.ok) throw new Error(`companion → ${r.status}`);
      return r.json() as Promise<Companion>;
    }),

  modelReplay: () =>
    fetch(`${BASE}/models/replay`).then((r) => {
      if (!r.ok) throw new Error(`models/replay → ${r.status}`);
      return r.json() as Promise<ModelReplay>;
    }),

  undercut: (body: {
    gap_s: number;
    attacker_compound: Compound;
    attacker_tyre_age: number;
    defender_compound: Compound;
    defender_tyre_age: number;
    pit_lap: number;
    circuit: Circuit;
  }) => post<UndercutResult>("/strategy/undercut", body),

  coverOrExtend: (body: {
    circuit_name: string;
    gap_to_follower_s: number;
    laps_remaining: number;
    leader_tyre_age: number;
    leader_compound: Compound;
  }) => post<CoverExtendResult>("/strategy/cover-or-extend", body),

  safetyCar: (body: {
    circuit_name: string;
    current_lap: number;
    current_compound: Compound;
    current_tyre_age: number;
    fresh_compound: Compound;
  }) => post<SafetyCarResult>("/scenario/safety-car", body),

  stopFork: (body: { circuit_name: string }) =>
    post<StopForkResult>("/scenario/stop-fork", body),

  rainCrossover: (body: { wetness: number; laps_remaining: number }) =>
    post<RainCrossoverResult>("/scenario/rain-crossover", body),
};

export const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#ff3b3b",
  MEDIUM: "#ffd23b",
  HARD: "#e8e8ee",
  INTERMEDIATE: "#3bd07a",
  WET: "#3b8dff",
};
