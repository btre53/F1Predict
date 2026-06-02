// PIT WALL — S1/S2/S3 sector splits for the Explorer timing tower.
//
// PREFERRED: if the backend patch (see README "real sector times") surfaces sector1_s/
// 2_s/3_s on each ReplaySlot — which FastF1 already ingests into laps.parquet — they are
// used verbatim. OTHERWISE we reconstruct splits from ReplaySlot.gap_s: the CHANGE in a
// car's gap to the leader between laps equals its lap time minus the leader's, so we anchor
// the leader's lap time with a light physics model (base lap + fuel burn-off + tyre-age
// degradation using the real compound/tyre_life), reconstruct every car's lap time, split
// into sectors, and colour against rolling session bests across the field. The reconstruction
// is a principled approximation; the real-sector path is ground truth.
import type { Replay } from "../../api";

// Optional real sector splits, IF the backend patch surfaces them on each ReplaySlot.
type MaybeRealSectors = { sector1_s?: number | null; sector2_s?: number | null; sector3_s?: number | null };
const realSectors = (slot: unknown): [number, number, number] | null => {
  const s = slot as MaybeRealSectors;
  if (s.sector1_s != null && s.sector2_s != null && s.sector3_s != null) {
    return [s.sector1_s, s.sector2_s, s.sector3_s];
  }
  return null;
};

export type SectorColor = "sbest" | "pbest" | "slower";
export interface SectorTableEntry {
  t: [number, number, number]; // sector times (s)
  colors: SectorColor[];
  last: number | null;         // previous lap total (s)
  best: number | null;         // best lap so far (s)
}

const SEC_FRAC: [number, number, number] = [0.305, 0.420, 0.275]; // characteristic split
const WEAR: Record<string, number> = { SOFT: 0.09, MEDIUM: 0.055, HARD: 0.035, INTERMEDIATE: 0.07, WET: 0.08 };

// Physics anchor for the leader's lap time (seconds).
function physLeaderLapS(baseLapS: number, lap: number, total: number, compound: string, tyreLife: number): number {
  const fuel = 1.8 * (total - lap) / Math.max(1, total);       // heavier early = slower
  const deg = (WEAR[compound] ?? 0.05) * tyreLife;             // linear wear
  const cliff = 1.0 / (1 + Math.exp(-(tyreLife - 30) * 0.5));  // late-stint cliff
  return baseLapS + fuel + deg + cliff;
}

// Deterministic, stable per-(lap,sector) jitter so sectors don't move in lockstep.
function jit(lap: number, s: number): number {
  const x = Math.sin(lap * 12.9898 + s * 78.233) * 43758.5453;
  return (x - Math.floor(x) - 0.5) * 0.012;
}

// Reconstruct absolute lap time (s) for every driver every lap from gap_s deltas.
export function reconstructLapTimes(replay: Replay, baseLapS: number): Record<string, number[]> {
  const total = replay.total_laps;
  const out: Record<string, number[]> = {};
  const prev: Record<string, number> = {};
  replay.drivers.forEach((d) => { out[d.driver] = []; });
  for (const lap of replay.laps) {
    const leader = lap.order.find((o) => o.position === 1) ?? lap.order[0];
    const base = physLeaderLapS(baseLapS, lap.lap, total, leader.compound, leader.tyre_life);
    for (const s of lap.order) {
      const pg = prev[s.driver];
      let d = pg == null ? 0 : s.gap_s - pg;
      d = Math.max(-3, Math.min(3, d)); // cap so pit cycling can't explode a lap
      (out[s.driver] ??= []).push(base + d);
      prev[s.driver] = s.gap_s;
    }
  }
  return out;
}

function splitLap(lapS: number, lapNo: number): [number, number, number] {
  const raw = SEC_FRAC.map((fr, s) => lapS * fr * (1 + jit(lapNo, s)));
  const k = lapS / (raw[0] + raw[1] + raw[2]);
  return raw.map((v) => +(v * k).toFixed(3)) as [number, number, number];
}

// Per-lap LEADER sector state, coloured against session bests across the whole field.
// baseLapS = circuit base_lap_ms / 1000 (from CircuitInfo); pass a sane default if unknown.
export function deriveSectorTable(replay: Replay, baseLapS: number): SectorTableEntry[] {
  const lapTimes = reconstructLapTimes(replay, baseLapS);
  const bestSec: [number, number, number] = [Infinity, Infinity, Infinity];
  let bestLap = Infinity;
  let prevTotal: number | null = null;
  const table: SectorTableEntry[] = [];

  replay.laps.forEach((lap, i) => {
    // fold every driver's sectors into the rolling session bests first
    for (const o of lap.order) {
      const ft = realSectors(o) ?? splitLap(lapTimes[o.driver]?.[i] ?? 0, lap.lap);
      ft.forEach((v, s) => { if (v && v < bestSec[s]) bestSec[s] = v; });
    }
    const leader = lap.order.find((o) => o.position === 1) ?? lap.order[0];
    const t = realSectors(leader) ?? splitLap(lapTimes[leader.driver]?.[i] ?? baseLapS, lap.lap);
    const colors: SectorColor[] = t.map((v, s) =>
      v <= bestSec[s] + 0.001 ? "sbest" : v <= bestSec[s] + 0.18 ? "pbest" : "slower");
    const lapTotal = +(t[0] + t[1] + t[2]).toFixed(3);
    if (lapTotal < bestLap) bestLap = lapTotal;
    table.push({ t, colors, last: prevTotal, best: bestLap });
    prevTotal = lapTotal;
  });
  return table;
}
