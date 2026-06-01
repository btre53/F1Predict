import { useEffect, useState } from "react";
import {
  api,
  COMPOUND_COLOR,
  type CircuitInfo,
  type Compound,
  type StrategyResult,
} from "../api";
import { LapTimeChart } from "./LapTimeChart";
import { StintBar } from "./StintBar";

const COMPOUNDS: Compound[] = ["SOFT", "MEDIUM", "HARD"];

interface BuilderStint {
  compound: Compound;
  length: number;
}

function lapfmt(s: number): string {
  const m = Math.floor(s / 60);
  const r = (s % 60).toFixed(1);
  return `${m}:${r.padStart(4, "0")}`;
}

// Compose a custom stint plan and test it against the optimizer. Each stint is a
// compound + lap count; the total should add up to the race distance.
export function StrategyBuilder({ circuit }: { circuit: CircuitInfo }) {
  const total = circuit.total_laps;
  const [stints, setStints] = useState<BuilderStint[]>([
    { compound: "MEDIUM", length: Math.round(total * 0.55) },
    { compound: "HARD", length: total - Math.round(total * 0.55) },
  ]);
  const [res, setRes] = useState<StrategyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Reset to a valid default split whenever the circuit (and its lap count)
  // changes — the builder mounts before calibrated circuits load, so the initial
  // state can otherwise be stale.
  useEffect(() => {
    const m = Math.round(total * 0.55);
    setStints([
      { compound: "MEDIUM", length: m },
      { compound: "HARD", length: total - m },
    ]);
    setRes(null);
  }, [circuit.name, total]);

  const planLaps = stints.reduce((a, s) => a + s.length, 0);

  function update(i: number, patch: Partial<BuilderStint>) {
    setStints((prev) => prev.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  }
  function addStint() {
    setStints((prev) => [...prev, { compound: "SOFT", length: 10 }]);
  }
  function removeStint(i: number) {
    setStints((prev) => (prev.length > 1 ? prev.filter((_, j) => j !== i) : prev));
  }

  async function evaluate() {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.evaluate(
        stints.map((s) => ({ compound: s.compound, length: s.length })),
        {
          name: circuit.name,
          base_lap_ms: circuit.base_lap_ms,
          total_laps: circuit.total_laps,
        },
        circuit.calibrated ? circuit.name : undefined,
      );
      setRes(r);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-edge bg-graphite p-5">
      <div className="mb-4 flex items-end justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
            Build your own strategy
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-zinc-500">
            Compose a stint plan and test it against the optimizer.
          </p>
        </div>
        <div className="text-right text-xs uppercase tracking-wider tabular text-zinc-500">
          <span className={planLaps === total ? "text-emerald-400" : "text-amber-400"}>
            {planLaps}
          </span>{" "}
          / {total} laps
        </div>
      </div>

      <div className="space-y-2">
        {stints.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="w-6 text-right text-xs tabular text-zinc-600">{i + 1}</span>
            <div className="flex overflow-hidden rounded-md border border-edge">
              {COMPOUNDS.map((c) => (
                <button
                  key={c}
                  onClick={() => update(i, { compound: c })}
                  className="px-3 py-1.5 text-xs font-semibold transition"
                  style={
                    s.compound === c
                      ? {
                          background: COMPOUND_COLOR[c],
                          color: c === "SOFT" ? "#fff" : "#0a0a0d",
                        }
                      : { background: "#1c1c24", color: "#71717a" }
                  }
                >
                  {c[0]}
                </button>
              ))}
            </div>
            <input
              type="number"
              min={1}
              max={100}
              value={s.length}
              onChange={(e) =>
                update(i, { length: Math.max(1, Number(e.target.value) || 1) })
              }
              className="w-16 rounded-md border border-edge bg-slate-panel px-2 py-1.5 text-sm tabular outline-none focus:border-f1-red"
            />
            <span className="text-xs text-zinc-600">laps</span>
            <button
              onClick={() => removeStint(i)}
              disabled={stints.length <= 1}
              className="ml-auto rounded-md border border-edge px-2 py-1 text-xs text-zinc-500 transition hover:border-f1-red/50 hover:text-f1-redbright disabled:opacity-30 disabled:hover:border-edge disabled:hover:text-zinc-500"
              aria-label="Remove stint"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={addStint}
          className="rounded-md border border-edge bg-slate-panel px-3 py-1.5 text-xs text-zinc-400 transition hover:bg-edge"
        >
          + Add stint
        </button>
        <button
          onClick={evaluate}
          disabled={loading}
          className="ml-auto rounded-md bg-f1-red px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-white transition hover:bg-f1-redbright disabled:opacity-50"
        >
          {loading ? "Evaluating…" : "Evaluate plan"}
        </button>
      </div>

      {err && (
        <div className="mt-3 rounded-md border border-f1-red/40 bg-f1-red/10 px-3 py-2 text-xs text-f1-redbright">
          {err}
        </div>
      )}

      {res && (
        <div className="mt-4 space-y-3 border-t border-edge pt-4">
          <div className="flex items-center justify-between">
            <div
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
                res.valid
                  ? "border border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                  : "border border-amber-500/40 bg-amber-500/10 text-amber-400"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  res.valid ? "bg-emerald-400" : "bg-amber-400"
                }`}
              />
              {res.valid ? "Valid plan" : "Invalid plan"}
            </div>
            <div className="text-right">
              <div className="font-mono text-xl font-bold tabular text-zinc-100">
                {lapfmt(res.total_time_s)}
              </div>
              <div className="text-xs tabular text-zinc-500">
                avg {lapfmt(res.avg_lap_s)}/lap
              </div>
            </div>
          </div>

          <StintBar
            compounds={res.compounds}
            lengths={res.stint_lengths}
            totalLaps={circuit.total_laps}
          />

          {res.notes.length > 0 && (
            <ul className="space-y-0.5 text-[11px] italic leading-snug text-zinc-500">
              {res.notes.map((n, i) => (
                <li key={i}>• {n}</li>
              ))}
            </ul>
          )}

          {res.lap_times_s && res.lap_times_s.length > 0 && (
            <div className="pt-2">
              <div className="mb-1 text-xs uppercase tracking-wider text-zinc-500">
                Lap-time profile
              </div>
              <LapTimeChart lapTimes={res.lap_times_s} pitLaps={res.pit_laps} />
              <p className="mt-1 text-[11px] italic leading-snug text-zinc-600">
                Drift down = fuel burn-off; saw-tooth = tyre deg; yellow spikes = pit
                stops.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
