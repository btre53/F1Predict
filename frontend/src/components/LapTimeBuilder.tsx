import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { tyreDeg } from "./TyreSandbox";

// "Build a lap time" — illustrative layers over laps 1..40:
//   base   : constant pace
//   fuel   : +k·fuel_mass, drifts down as fuel burns off
//   tyre   : the three-phase deg curve over a single stint
//   noise  : small positive-ish jitter (precomputed, deterministic LCG)

const LAPS = 40;
const BASE = 90; // s
const K_FUEL = 0.03; // s per kg
const FUEL_START = 100; // kg
const BURN = 1.8; // kg/lap

// Deterministic pseudo-noise so the chart never flickers across re-renders.
function lcgNoise(n: number): number[] {
  let seed = 1337;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    const u = seed / 0x7fffffff; // [0,1)
    // Slight positive skew: square pushes mass toward 0, scale to ~±0.4s with bias up.
    out.push((u * u) * 0.5 - 0.1);
  }
  return out;
}

type Layers = { base: boolean; fuel: boolean; tyre: boolean; noise: boolean };

const LAYER_META: { key: keyof Layers; label: string; color: string }[] = [
  { key: "base", label: "Base pace", color: "#a1a1aa" },
  { key: "fuel", label: "Fuel mass", color: "#64C4FF" },
  { key: "tyre", label: "Tyre deg", color: "#FF8000" },
  { key: "noise", label: "Driver noise", color: "#52E252" },
];

export function LapTimeBuilder() {
  const [layers, setLayers] = useState<Layers>({
    base: true,
    fuel: true,
    tyre: true,
    noise: true,
  });

  const noise = useMemo(() => lcgNoise(LAPS), []);

  const data = useMemo(() => {
    const rows: { lap: number; time: number }[] = [];
    for (let lap = 1; lap <= LAPS; lap++) {
      let t = 0;
      if (layers.base) t += BASE;
      if (layers.fuel) {
        const fuelMass = Math.max(0, FUEL_START - BURN * lap);
        t += K_FUEL * fuelMass;
      }
      if (layers.tyre) {
        // Single stint: tyre age == lap index.
        t += tyreDeg(lap, 0.7, 0.5, 0.05, 3.0, 0.5, 28);
      }
      if (layers.noise) t += noise[lap - 1];
      rows.push({ lap, time: t });
    }
    return rows;
  }, [layers, noise]);

  const anyOn = layers.base || layers.fuel || layers.tyre || layers.noise;

  function toggle(key: keyof Layers) {
    setLayers((l) => ({ ...l, [key]: !l[key] }));
  }

  return (
    <div className="rounded-xl border border-edge bg-graphite p-5">
      <div className="mb-1 flex items-baseline gap-3">
        <span className="font-mono text-xs font-bold tabular text-f1-red">01·a</span>
        <h3 className="text-base font-semibold text-zinc-100">Build a lap time</h3>
      </div>
      <div className="mb-4 text-[10px] uppercase tracking-wider text-zinc-500">
        toggle the layers · see how a lap is composed
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {LAYER_META.map((m) => {
          const on = layers[m.key];
          return (
            <button
              key={m.key}
              onClick={() => toggle(m.key)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-wider transition ${
                on
                  ? "border-edge bg-slate-panel text-zinc-200"
                  : "border-transparent bg-carbon text-zinc-600 hover:text-zinc-400"
              }`}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: m.color, opacity: on ? 1 : 0.3 }}
              />
              {m.label}
            </button>
          );
        })}
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="#2a2a35" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="lap"
            tick={{ fill: "#71717a", fontSize: 10 }}
            stroke="#2a2a35"
            interval="preserveStartEnd"
            minTickGap={24}
            label={{
              value: "lap",
              position: "insideBottom",
              offset: -2,
              fill: "#52525b",
              fontSize: 10,
            }}
          />
          <YAxis
            domain={anyOn ? ["dataMin - 0.5", "dataMax + 0.5"] : [0, 1]}
            tick={{ fill: "#71717a", fontSize: 10 }}
            stroke="#2a2a35"
            width={54}
            tickFormatter={(v) => (v as number).toFixed(1)}
          />
          <Tooltip
            contentStyle={{
              background: "#1c1c24",
              border: "1px solid #2a2a35",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#a1a1aa" }}
            itemStyle={{ color: "#ff1e1e" }}
            formatter={(v) => [`${(v as number).toFixed(2)}s`, "Lap time"]}
            labelFormatter={(l) => `Lap ${l as number}`}
          />
          <Line
            type="monotone"
            dataKey="time"
            stroke="#e10600"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>

      <p className="mt-3 text-[11px] leading-relaxed text-zinc-600">
        Base {BASE}s + fuel ({K_FUEL} s/kg over {FUEL_START}kg burning {BURN} kg/lap) + a single-stint
        tyre curve + deterministic positively-skewed noise. The downward drift is fuel burn-off;
        the upward sweep at the end is the tyre cliff.
      </p>
    </div>
  );
}
