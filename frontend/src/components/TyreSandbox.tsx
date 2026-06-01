import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Three-phase tyre-degradation penalty (seconds) as a function of tyre age (laps):
//   t_deg(age) = θ1·exp(−θ2·age)              warm-up (decays away)
//              + θ3·age                        linear wear
//              + θ4 / (1 + exp(−θ5·(age−θ6)))  logistic cliff
export function tyreDeg(
  age: number,
  t1: number,
  t2: number,
  t3: number,
  t4: number,
  t5: number,
  t6: number,
): number {
  const warmup = t1 * Math.exp(-t2 * age);
  const wear = t3 * age;
  const cliff = t4 / (1 + Math.exp(-t5 * (age - t6)));
  return warmup + wear + cliff;
}

// Fixed (non-exposed) shape parameters.
const T2 = 0.5; // warm-up decay rate
const T5 = 0.5; // cliff steepness

const MAX_AGE = 45;
const MARGINAL_THRESHOLD = 0.15; // s/lap

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="mb-1 flex items-baseline justify-between text-xs text-zinc-400">
        <span>{label}</span>
        <span className="font-mono tabular text-zinc-200">{value.toFixed(step < 1 ? 2 : 0)}</span>
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-f1-red"
      />
    </div>
  );
}

export function TyreSandbox() {
  // Defaults: a MEDIUM tyre.
  const [t1, setT1] = useState(0.7); // warm-up magnitude
  const [t3, setT3] = useState(0.05); // linear wear rate
  const [t4, setT4] = useState(3.0); // cliff magnitude
  const [t6, setT6] = useState(28); // cliff lap

  const data = useMemo(() => {
    const rows: { age: number; deg: number }[] = [];
    for (let age = 0; age <= MAX_AGE; age++) {
      rows.push({ age, deg: tyreDeg(age, t1, T2, t3, t4, T5, t6) });
    }
    return rows;
  }, [t1, t3, t4, t6]);

  // "Optimal-ish" stint length: first age where the marginal deg per lap
  // exceeds the threshold (the tyres are giving up time faster than worth it).
  const optimalStint = useMemo(() => {
    for (let i = 1; i < data.length; i++) {
      if (data[i].deg - data[i - 1].deg > MARGINAL_THRESHOLD) return i;
    }
    return null;
  }, [data]);

  return (
    <div className="rounded-xl border border-edge bg-graphite p-5">
      <div className="mb-1 flex items-baseline gap-3">
        <span className="font-mono text-xs font-bold tabular text-f1-red">03·a</span>
        <h3 className="text-base font-semibold text-zinc-100">Tyre-degradation sandbox</h3>
      </div>
      <div className="mb-4 text-[10px] uppercase tracking-wider text-zinc-500">
        drag the curve coefficients · find the cliff
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_240px]">
        <div className="min-w-0">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
              <CartesianGrid stroke="#2a2a35" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="age"
                tick={{ fill: "#71717a", fontSize: 10 }}
                stroke="#2a2a35"
                interval="preserveStartEnd"
                minTickGap={24}
                label={{
                  value: "tyre age (laps)",
                  position: "insideBottom",
                  offset: -2,
                  fill: "#52525b",
                  fontSize: 10,
                }}
              />
              <YAxis
                domain={[0, "dataMax + 0.5"]}
                tick={{ fill: "#71717a", fontSize: 10 }}
                stroke="#2a2a35"
                width={42}
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
                formatter={(v) => [`+${(v as number).toFixed(2)}s`, "Penalty"]}
                labelFormatter={(l) => `Age ${l as number} laps`}
              />
              <ReferenceLine
                x={t6}
                stroke="#ff1e1e"
                strokeDasharray="4 4"
                label={{ value: "cliff", fill: "#ff1e1e", fontSize: 10, position: "top" }}
              />
              {optimalStint != null && (
                <ReferenceLine
                  x={optimalStint}
                  stroke="#52E252"
                  strokeDasharray="2 4"
                  label={{ value: "stint", fill: "#52E252", fontSize: 10, position: "insideTopRight" }}
                />
              )}
              <Line
                type="monotone"
                dataKey="deg"
                stroke="#e10600"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="space-y-4">
          <Slider label="θ1 warm-up" value={t1} min={0} max={2} step={0.05} onChange={setT1} />
          <Slider label="θ3 wear rate (s/lap)" value={t3} min={0} max={0.2} step={0.005} onChange={setT3} />
          <Slider label="θ4 cliff magnitude (s)" value={t4} min={0} max={8} step={0.1} onChange={setT4} />
          <Slider label="θ6 cliff lap" value={t6} min={10} max={45} step={1} onChange={setT6} />

          <div className="space-y-2 border-t border-edge pt-3 text-xs">
            <div className="flex items-baseline justify-between">
              <span className="text-zinc-500">Penalty at cliff lap</span>
              <span className="font-mono tabular text-zinc-200">
                +{tyreDeg(t6, t1, T2, t3, t4, T5, t6).toFixed(2)}s
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-zinc-500">Optimal-ish stint</span>
              <span className="font-mono tabular text-emerald-400">
                {optimalStint != null ? `~${optimalStint} laps` : "> 45 laps"}
              </span>
            </div>
            <p className="pt-1 text-[11px] leading-relaxed text-zinc-600">
              Stint flag = first lap where marginal deg exceeds {MARGINAL_THRESHOLD.toFixed(2)} s/lap.
              θ2, θ5 held fixed at {T2}.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
