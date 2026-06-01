import { useEffect, useState } from "react";
import {
  api,
  type CircuitInfo,
  type StrategyResult,
  type UndercutResult,
} from "../api";
import { CoverExtendPanel } from "./CoverExtendPanel";
import { StintBar } from "./StintBar";
import { StrategyBuilder } from "./StrategyBuilder";

// Fallback if the ETL hasn't been run yet (no calibrated circuits available).
const FALLBACK: CircuitInfo[] = [
  { name: "Spanish", base_lap_ms: 78000, total_laps: 66, era: "GE_DRS_2022_2025", calibrated: false, compounds_calibrated: [] },
];

// Lap time as M:SS.s (how F1 timing is actually read).
function lapfmt(s: number): string {
  const m = Math.floor(s / 60);
  const r = (s % 60).toFixed(1);
  return `${m}:${r.padStart(4, "0")}`;
}

export function StrategyLab() {
  const [circuits, setCircuits] = useState<CircuitInfo[]>(FALLBACK);
  const [circuit, setCircuit] = useState<CircuitInfo>(FALLBACK[0]);
  const [maxStops, setMaxStops] = useState(2);
  const [results, setResults] = useState<StrategyResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Load calibrated circuits from the API on mount.
  useEffect(() => {
    api
      .circuits()
      .then((list) => {
        if (list.length) {
          setCircuits(list);
          setCircuit(list[0]);
        }
      })
      .catch(() => {});
  }, []);

  async function run() {
    setLoading(true);
    setErr(null);
    try {
      const name = circuit.calibrated ? circuit.name : undefined;
      setResults(await api.optimize(circuit, maxStops, 6, name));
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [circuit, maxStops]);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wider text-zinc-500">
              Circuit
            </label>
            <select
              value={circuit.name}
              onChange={(e) =>
                setCircuit(circuits.find((c) => c.name === e.target.value)!)
              }
              className="rounded-md border border-edge bg-slate-panel px-3 py-2 text-sm outline-none focus:border-f1-red"
            >
              {circuits.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} GP
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wider text-zinc-500">
              Max stops
            </label>
            <div className="flex overflow-hidden rounded-md border border-edge">
              {[1, 2, 3].map((n) => (
                <button
                  key={n}
                  onClick={() => setMaxStops(n)}
                  className={`px-4 py-2 text-sm transition ${
                    maxStops === n
                      ? "bg-f1-red text-white"
                      : "bg-slate-panel text-zinc-400 hover:bg-edge"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="text-xs uppercase tracking-wider text-zinc-500">
              {circuit.total_laps} laps · base {lapfmt(circuit.base_lap_ms / 1000)}
            </div>
            {circuit.calibrated && (
              <div className="mt-1 inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                CALIBRATED FROM REAL DATA
              </div>
            )}
          </div>
        </div>

        {err && (
          <div className="rounded-md border border-f1-red/40 bg-f1-red/10 px-4 py-3 text-sm text-f1-redbright">
            {err} — is the API running on :8000?
          </div>
        )}

        <div className="space-y-3">
          {loading && (
            <div className="animate-pulse text-sm text-zinc-500">
              Optimizing strategies…
            </div>
          )}
          {results.map((r, i) => {
            const delta = r.delta_to_best_s;
            return (
              <div
                key={i}
                className={`rounded-xl border p-4 transition ${
                  i === 0
                    ? "border-f1-red/50 bg-gradient-to-br from-slate-panel to-graphite shadow-lg shadow-f1-red/5"
                    : "border-edge bg-graphite hover:border-zinc-600"
                }`}
              >
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span
                      className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                        i === 0 ? "bg-f1-red text-white" : "bg-edge text-zinc-300"
                      }`}
                    >
                      {i + 1}
                    </span>
                    <span className="text-sm font-medium text-zinc-300">
                      {r.n_stops}-stop
                    </span>
                    <span className="text-xs text-zinc-500">
                      pit {r.pit_laps.join(", ") || "—"}
                    </span>
                  </div>
                  <div className="text-right">
                    <div
                      className={`font-mono text-2xl font-bold tabular ${
                        i === 0 ? "text-f1-redbright" : "text-zinc-200"
                      }`}
                    >
                      {i === 0 ? "OPTIMAL" : `+${delta.toFixed(1)}s`}
                    </div>
                    <div className="text-xs tabular text-zinc-500">
                      avg {lapfmt(r.avg_lap_s)}/lap
                    </div>
                  </div>
                </div>
                <StintBar
                  compounds={r.compounds}
                  lengths={r.stint_lengths}
                  totalLaps={circuit.total_laps}
                />
              </div>
            );
          })}
        </div>

        <StrategyBuilder circuit={circuit} />
      </div>

      <div className="space-y-6">
        <UndercutCard circuit={circuit} />
        <CoverExtendPanel circuit={circuit} />
      </div>
    </div>
  );
}

function UndercutCard({ circuit }: { circuit: CircuitInfo }) {
  const [gap, setGap] = useState(1.5);
  const [defAge, setDefAge] = useState(22);
  const [res, setRes] = useState<UndercutResult | null>(null);

  // Debounce so dragging a slider doesn't fire a request on every tick.
  useEffect(() => {
    const id = setTimeout(() => {
      let cancelled = false;
      api
        .undercut({
          gap_s: gap,
          attacker_compound: "SOFT",
          attacker_tyre_age: 0,
          defender_compound: "HARD",
          defender_tyre_age: defAge,
          pit_lap: defAge,
          circuit,
        })
        .then((r) => !cancelled && setRes(r))
        .catch(() => {});
      return () => {
        cancelled = true;
      };
    }, 90);
    return () => clearTimeout(id);
  }, [gap, defAge, circuit]);

  return (
    <aside className="h-fit space-y-4 rounded-xl border border-edge bg-graphite p-5">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
          Undercut calculator
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-zinc-500">
          Attacker pits onto fresh softs; defender stays out on worn hards. Does the
          fresh-tyre advantage clear the gap?
        </p>
      </div>

      <Slider label={`Gap to rival: ${gap.toFixed(1)}s`} min={0} max={5} step={0.1} value={gap} onChange={setGap} />
      <Slider label={`Defender tyre age: ${defAge} laps`} min={5} max={40} step={1} value={defAge} onChange={setDefAge} />

      {res && (
        <div
          className={`rounded-lg border p-4 ${
            res.undercut_works
              ? "border-emerald-500/40 bg-emerald-500/10"
              : "border-amber-500/40 bg-amber-500/10"
          }`}
        >
          <div
            className={`text-sm font-bold ${
              res.undercut_works ? "text-emerald-400" : "text-amber-400"
            }`}
          >
            {res.undercut_works ? "UNDERCUT WORKS" : "GAP TOO LARGE"}
          </div>
          <div className="mt-2 space-y-1 text-xs text-zinc-400">
            <div className="flex justify-between tabular">
              <span>Fresh-tyre gain (3 laps)</span>
              <span className="text-zinc-200">{res.fresh_tyre_gain_s.toFixed(2)}s</span>
            </div>
            <div className="flex justify-between tabular">
              <span>Net after cycle</span>
              <span className="text-zinc-200">
                {res.projected_gap_after_s > 0 ? "+" : ""}
                {res.projected_gap_after_s.toFixed(2)}s
              </span>
            </div>
          </div>
          <p className="mt-2 text-[11px] italic leading-snug text-zinc-500">
            {res.notes[0]}
          </p>
        </div>
      )}
    </aside>
  );
}

function Slider({
  label,
  min,
  max,
  step,
  value,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-zinc-400">{label}</label>
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
