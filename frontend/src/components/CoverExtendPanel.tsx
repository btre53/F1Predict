import { useEffect, useState } from "react";
import { api, type CircuitInfo, type CoverExtendResult } from "../api";

// Stackelberg leader decision: the leader has observed the follower's undercut
// threat and chooses to cover (pit now) or extend (build a tyre-age offset).
export function CoverExtendPanel({ circuit }: { circuit: CircuitInfo }) {
  const [gap, setGap] = useState(1.2);
  const [lapsRemaining, setLapsRemaining] = useState(
    Math.max(5, Math.round(circuit.total_laps * 0.4)),
  );
  const [tyreAge, setTyreAge] = useState(18);
  const [res, setRes] = useState<CoverExtendResult | null>(null);

  useEffect(() => {
    setLapsRemaining(Math.max(5, Math.round(circuit.total_laps * 0.4)));
  }, [circuit]);

  useEffect(() => {
    let cancelled = false;
    const id = setTimeout(() => {
      api
        .coverOrExtend({
          circuit_name: circuit.name,
          gap_to_follower_s: gap,
          laps_remaining: lapsRemaining,
          leader_tyre_age: tyreAge,
          leader_compound: "MEDIUM",
        })
        .then((r) => !cancelled && setRes(r))
        .catch(() => {});
    }, 90);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [gap, lapsRemaining, tyreAge, circuit]);

  const cover = res?.recommendation === "COVER";

  return (
    <aside className="h-fit space-y-4 rounded-xl border border-edge bg-graphite p-5">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
          Cover vs extend
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-zinc-500">
          Leader's Stackelberg call: react to the follower's undercut now, or extend
          to build a tyre-age offset for a fresher final stint.
        </p>
      </div>

      <Slider
        label={`Gap to follower: ${gap.toFixed(1)}s`}
        min={0}
        max={5}
        step={0.1}
        value={gap}
        onChange={setGap}
      />
      <Slider
        label={`Laps remaining: ${lapsRemaining}`}
        min={3}
        max={circuit.total_laps}
        step={1}
        value={lapsRemaining}
        onChange={setLapsRemaining}
      />
      <Slider
        label={`Leader tyre age: ${tyreAge} laps`}
        min={0}
        max={40}
        step={1}
        value={tyreAge}
        onChange={setTyreAge}
      />

      {res && (
        <div
          className={`rounded-lg border p-4 ${
            cover
              ? "border-f1-red/40 bg-f1-red/10"
              : "border-sky-500/40 bg-sky-500/10"
          }`}
        >
          <div
            className={`text-sm font-bold ${
              cover ? "text-f1-redbright" : "text-sky-400"
            }`}
          >
            {cover ? "COVER" : "EXTEND"}
          </div>
          <div className="mt-2 space-y-1 text-xs text-zinc-400">
            <div className="flex justify-between tabular">
              <span>Cover value</span>
              <span className={cover ? "text-zinc-100" : "text-zinc-300"}>
                {res.cover_value_s > 0 ? "+" : ""}
                {res.cover_value_s.toFixed(2)}s
              </span>
            </div>
            <div className="flex justify-between tabular">
              <span>Extend value</span>
              <span className={!cover ? "text-zinc-100" : "text-zinc-300"}>
                {res.extend_value_s > 0 ? "+" : ""}
                {res.extend_value_s.toFixed(2)}s
              </span>
            </div>
          </div>
          <p className="mt-2 text-[11px] italic leading-snug text-zinc-500">
            {res.rationale}
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
