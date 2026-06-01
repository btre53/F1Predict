import { useEffect, useState } from "react";
import { api, type CircuitInfo, type RaceSim } from "../api";

function pct(x: number): string {
  if (x >= 0.995) return "100%";
  if (x < 0.005) return "<1%";
  return `${Math.round(x * 100)}%`;
}

// Heat colour for a probability cell (carbon -> F1 red).
function heat(p: number): string {
  if (p <= 0) return "transparent";
  const a = Math.min(1, 0.12 + p * 1.6);
  return `rgba(225, 6, 0, ${a})`;
}

export function Predictor() {
  const [circuits, setCircuits] = useState<CircuitInfo[]>([]);
  const [circuit, setCircuit] = useState<string>("");
  const [sim, setSim] = useState<RaceSim | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .circuits()
      .then((list) => {
        setCircuits(list);
        if (list.length) setCircuit(list[0].name);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (!circuit) return;
    setLoading(true);
    setErr(null);
    api
      .predict(circuit, 10000)
      .then(setSim)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [circuit]);

  const topN = sim?.outcomes.slice(0, 12) ?? [];
  const positions = sim ? sim.outcomes.length : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="mb-1 block text-xs uppercase tracking-wider text-zinc-500">
            Circuit
          </label>
          <select
            value={circuit}
            onChange={(e) => setCircuit(e.target.value)}
            className="rounded-md border border-edge bg-slate-panel px-3 py-2 text-sm outline-none focus:border-f1-red"
          >
            {circuits.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} GP
              </option>
            ))}
          </select>
        </div>
        {sim && (
          <div className="ml-auto flex items-center gap-5 text-right">
            <Stat label="Simulations" value={sim.n_sims.toLocaleString()} />
            <Stat label="Safety car" value={pct(sim.sc_probability)} />
            <Stat label="Race laps" value={String(sim.total_laps)} />
          </div>
        )}
      </div>

      {err && (
        <div className="rounded-md border border-f1-red/40 bg-f1-red/10 px-4 py-3 text-sm text-f1-redbright">
          {err}
        </div>
      )}
      {loading && (
        <div className="animate-pulse text-sm text-zinc-500">
          Running 10,000 race simulations…
        </div>
      )}

      {sim && !loading && (
        <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
          {/* Win / podium / points probabilities */}
          <div className="space-y-2">
            <h3 className="text-xs uppercase tracking-wider text-zinc-500">
              Win · Podium · Points probability
            </h3>
            {topN.map((o, i) => (
              <div
                key={o.driver}
                className="rounded-lg border border-edge bg-graphite p-3"
              >
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs tabular text-zinc-600">{i + 1}</span>
                    <span
                      className="h-3 w-1 rounded-full"
                      style={{ background: `#${o.colour}` }}
                    />
                    <span className="text-sm font-semibold">{o.driver}</span>
                    <span className="text-[11px] text-zinc-500">{o.team}</span>
                  </div>
                  <span className="font-mono text-sm font-bold tabular text-f1-redbright">
                    {pct(o.win_pct)}
                  </span>
                </div>
                <div className="space-y-1">
                  <Bar label="Win" value={o.win_pct} colour="#e10600" />
                  <Bar label="Podium" value={o.podium_pct} colour="#c0a000" />
                  <Bar label="Points" value={o.points_pct} colour="#3b8d5a" />
                </div>
              </div>
            ))}
          </div>

          {/* Finishing-position heatmap */}
          <div>
            <h3 className="mb-2 text-xs uppercase tracking-wider text-zinc-500">
              Finishing-position distribution
            </h3>
            <div className="overflow-x-auto rounded-lg border border-edge bg-graphite p-3">
              <div
                className="grid gap-px"
                style={{
                  gridTemplateColumns: `48px repeat(${positions}, minmax(20px, 1fr))`,
                }}
              >
                <div />
                {Array.from({ length: positions }, (_, k) => (
                  <div
                    key={k}
                    className="pb-1 text-center text-[9px] tabular text-zinc-600"
                  >
                    {k + 1}
                  </div>
                ))}
                {sim.outcomes.map((o) => (
                  <Row key={o.driver} driver={o.driver} dist={o.finish_distribution} />
                ))}
              </div>
              <p className="mt-2 text-[10px] text-zinc-600">
                Rows = drivers (by win probability), columns = finishing position.
                Brighter = more likely. Hover a cell for the probability.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ driver, dist }: { driver: string; dist: number[] }) {
  return (
    <>
      <div className="flex items-center pr-2 text-right text-[10px] font-medium text-zinc-400">
        {driver}
      </div>
      {dist.map((p, k) => (
        <div
          key={k}
          title={`P${k + 1}: ${(p * 100).toFixed(1)}%`}
          className="aspect-square rounded-[2px]"
          style={{ background: heat(p) }}
        />
      ))}
    </>
  );
}

function Bar({
  label,
  value,
  colour,
}: {
  label: string;
  value: number;
  colour: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 text-[10px] uppercase text-zinc-600">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-carbon">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.max(1, value * 100)}%`, background: colour }}
        />
      </div>
      <span className="w-9 text-right text-[10px] tabular text-zinc-400">
        {pct(value)}
      </span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-zinc-600">
        {label}
      </div>
      <div className="font-mono text-sm font-semibold tabular">{value}</div>
    </div>
  );
}
