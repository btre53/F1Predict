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
}

export interface LiveMarket {
  question: string;
  slug: string;
  overround: number;
  outcomes: MarketOutcome[];
}

export interface LiveMarkets {
  available: boolean;
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

  predict: (circuitName: string, nSims = 10000) =>
    post<RaceSim>("/predict/race", {
      circuit_name: circuitName,
      n_sims: nSims,
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
};

export const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#ff3b3b",
  MEDIUM: "#ffd23b",
  HARD: "#e8e8ee",
  INTERMEDIATE: "#3bd07a",
  WET: "#3b8dff",
};
