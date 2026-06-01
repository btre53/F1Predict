import { useEffect, useState } from "react";
import {
  api,
  type Circuit,
  type CircuitInfo,
  type Compound,
  type SafetyCarResult,
  type UndercutResult,
} from "../api";
import { CoverExtendPanel } from "./CoverExtendPanel";

// The Scenario Runner: pick a live race situation + a triggering event, and the
// calibrated engine gives the strategic call (the "anti-AWS" — transparent, not a
// black-box probability). Each scenario composes the Strategy Lab primitives.
const SCENARIOS = [
  { id: "sc", label: "Safety car" },
  { id: "undercut", label: "Undercut" },
  { id: "cover", label: "Cover vs extend" },
] as const;

const DRY: Compound[] = ["SOFT", "MEDIUM", "HARD"];

export function ScenarioRunner() {
  const [circuits, setCircuits] = useState<CircuitInfo[]>([]);
  const [circuit, setCircuit] = useState<CircuitInfo | null>(null);
  const [scenario, setScenario] = useState<(typeof SCENARIOS)[number]["id"]>("sc");

  useEffect(() => {
    api.circuits().then((cs) => {
      setCircuits(cs);
      setCircuit(cs[0] ?? null);
    });
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Scenario Runner</h2>
          <p className="mt-1 max-w-xl text-sm leading-relaxed text-zinc-500">
            Put the car in a live situation and let the calibrated strategy engine make the
            call — the reasoning a race engineer would, shown in the open.
          </p>
        </div>
        {circuit && (
          <label className="text-xs text-zinc-400">
            Circuit
            <select
              value={circuit.name}
              onChange={(e) =>
                setCircuit(circuits.find((c) => c.name === e.target.value) ?? circuit)
              }
              className="ml-2 rounded-md border border-edge bg-graphite px-2 py-1 text-sm text-zinc-200"
            >
              {circuits.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.total_laps} laps)
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="flex gap-2">
        {SCENARIOS.map((s) => (
          <button
            key={s.id}
            onClick={() => setScenario(s.id)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition ${
              scenario === s.id
                ? "bg-f1-red text-white"
                : "border border-edge bg-graphite text-zinc-400 hover:text-white"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {!circuit ? (
        <p className="text-sm text-zinc-500">Loading calibrated circuits…</p>
      ) : (
        <div className="max-w-2xl">
          {scenario === "sc" && <SafetyCarScenario circuit={circuit} />}
          {scenario === "undercut" && <UndercutScenario circuit={circuit} />}
          {scenario === "cover" && <CoverExtendPanel circuit={circuit} />}
        </div>
      )}
    </div>
  );
}

// ---- Safety car: pit now (cheap stop) vs stay out -------------------------- //
function SafetyCarScenario({ circuit }: { circuit: CircuitInfo }) {
  const [lap, setLap] = useState(Math.round(circuit.total_laps * 0.45));
  const [compound, setCompound] = useState<Compound>("MEDIUM");
  const [age, setAge] = useState(20);
  const [fresh, setFresh] = useState<Compound>("HARD");
  const [res, setRes] = useState<SafetyCarResult | null>(null);

  useEffect(() => setLap(Math.round(circuit.total_laps * 0.45)), [circuit]);

  useEffect(() => {
    let cancelled = false;
    const id = setTimeout(() => {
      api
        .safetyCar({
          circuit_name: circuit.name,
          current_lap: lap,
          current_compound: compound,
          current_tyre_age: age,
          fresh_compound: fresh,
        })
        .then((r) => !cancelled && setRes(r))
        .catch(() => {});
    }, 90);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [lap, compound, age, fresh, circuit]);

  const pit = res?.recommendation === "PIT";

  return (
    <section className="space-y-5 rounded-xl border border-edge bg-graphite p-6">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
          Safety car is out — box, or stay out?
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-zinc-500">
          A safety car bunches the field, so a pit stop costs far less time than usual. The
          call: take the cheap stop for fresh tyres, or hold track position?
        </p>
      </div>

      <Slider
        label={`Current lap: ${lap} of ${circuit.total_laps} (${circuit.total_laps - lap} to go)`}
        min={1}
        max={circuit.total_laps - 1}
        value={lap}
        onChange={setLap}
      />
      <Segmented label="Tyre on the car now" value={compound} onChange={setCompound} />
      <Slider
        label={`Tyre age: ${age} laps`}
        min={0}
        max={40}
        value={age}
        onChange={setAge}
      />
      <Segmented label="Fresh set you'd fit" value={fresh} onChange={setFresh} />

      {res && (
        <div
          className={`rounded-lg border p-5 ${
            pit ? "border-f1-red/40 bg-f1-red/10" : "border-sky-500/40 bg-sky-500/10"
          }`}
        >
          <div className="flex items-baseline justify-between">
            <div
              className={`text-2xl font-extrabold tracking-tight ${
                pit ? "text-f1-redbright" : "text-sky-400"
              }`}
            >
              {pit ? "BOX NOW" : "STAY OUT"}
            </div>
            <div className="text-xs text-zinc-400">
              {pit ? "+" : ""}
              {Math.abs(res.delta_s).toFixed(1)}s {pit ? "faster" : "better staying"}
            </div>
          </div>

          <div className="mt-4 space-y-1.5 text-xs">
            <CostBar label="Pit now" value={res.pit_now_cost_s} best={pit} />
            <CostBar label="Stay out" value={res.stay_out_cost_s} best={!pit} />
          </div>

          <div className="mt-3 flex justify-between border-t border-white/10 pt-3 text-xs text-zinc-400">
            <span>SC stop discount vs green</span>
            <span className="tabular text-zinc-200">−{res.sc_pit_saving_s.toFixed(1)}s</span>
          </div>
          <p className="mt-3 text-[11px] italic leading-snug text-zinc-400">{res.rationale}</p>
        </div>
      )}
    </section>
  );
}

function CostBar({ label, value, best }: { label: string; value: number; best: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className={best ? "font-semibold text-zinc-100" : "text-zinc-500"}>
        {label}
        {best && <span className="ml-1.5 text-[10px] text-emerald-400">◀ pick</span>}
      </span>
      <span className={`tabular ${best ? "text-zinc-100" : "text-zinc-500"}`}>
        {value.toFixed(1)}s
      </span>
    </div>
  );
}

// ---- Undercut: does pitting now clear the car ahead? ----------------------- //
function UndercutScenario({ circuit }: { circuit: CircuitInfo }) {
  const [gap, setGap] = useState(1.5);
  const [atkCompound, setAtkCompound] = useState<Compound>("SOFT");
  const [defCompound, setDefCompound] = useState<Compound>("MEDIUM");
  const [defAge, setDefAge] = useState(18);
  const [res, setRes] = useState<UndercutResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    const c: Circuit = {
      name: circuit.name,
      base_lap_ms: circuit.base_lap_ms,
      total_laps: circuit.total_laps,
    };
    const id = setTimeout(() => {
      api
        .undercut({
          gap_s: gap,
          attacker_compound: atkCompound,
          attacker_tyre_age: 0,
          defender_compound: defCompound,
          defender_tyre_age: defAge,
          pit_lap: Math.round(circuit.total_laps * 0.4),
          circuit: c,
        })
        .then((r) => !cancelled && setRes(r))
        .catch(() => {});
    }, 90);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [gap, atkCompound, defCompound, defAge, circuit]);

  const works = res?.undercut_works;

  return (
    <section className="space-y-5 rounded-xl border border-edge bg-graphite p-6">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
          Undercut — pit now to jump the car ahead?
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-zinc-500">
          You pit for fresh tyres while the car ahead stays out on worn rubber. Does the
          fresh-tyre pace make up the gap before they react?
        </p>
      </div>

      <Slider
        label={`Gap to car ahead: ${gap.toFixed(1)}s`}
        min={0}
        max={4}
        step={0.1}
        value={gap}
        onChange={setGap}
      />
      <Segmented label="Your fresh tyre" value={atkCompound} onChange={setAtkCompound} />
      <Segmented label="Their tyre" value={defCompound} onChange={setDefCompound} />
      <Slider
        label={`Their tyre age: ${defAge} laps`}
        min={0}
        max={40}
        value={defAge}
        onChange={setDefAge}
      />

      {res && (
        <div
          className={`rounded-lg border p-5 ${
            works
              ? "border-emerald-500/40 bg-emerald-500/10"
              : "border-zinc-600/40 bg-zinc-600/10"
          }`}
        >
          <div
            className={`text-2xl font-extrabold tracking-tight ${
              works ? "text-emerald-400" : "text-zinc-300"
            }`}
          >
            {works ? "UNDERCUT WORKS" : "GAP TOO BIG"}
          </div>
          <div className="mt-3 space-y-1 text-xs text-zinc-400">
            <div className="flex justify-between tabular">
              <span>Fresh-tyre gain over the window</span>
              <span className="text-zinc-200">+{res.fresh_tyre_gain_s.toFixed(2)}s</span>
            </div>
            <div className="flex justify-between tabular">
              <span>Projected gap after the cycle</span>
              <span className={works ? "text-emerald-400" : "text-zinc-300"}>
                {res.projected_gap_after_s > 0 ? "+" : ""}
                {res.projected_gap_after_s.toFixed(2)}s
              </span>
            </div>
          </div>
          {res.notes.map((n, i) => (
            <p key={i} className="mt-2 text-[11px] italic leading-snug text-zinc-500">
              {n}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}

// ---- shared controls ------------------------------------------------------- //
function Slider({
  label,
  min,
  max,
  step = 1,
  value,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step?: number;
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

function Segmented({
  label,
  value,
  onChange,
}: {
  label: string;
  value: Compound;
  onChange: (c: Compound) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-zinc-400">{label}</label>
      <div className="flex gap-1.5">
        {DRY.map((c) => (
          <button
            key={c}
            onClick={() => onChange(c)}
            className={`flex-1 rounded-md border px-2 py-1.5 text-xs font-medium transition ${
              value === c
                ? "border-f1-red bg-f1-red/15 text-white"
                : "border-edge bg-carbon text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {c}
          </button>
        ))}
      </div>
    </div>
  );
}
