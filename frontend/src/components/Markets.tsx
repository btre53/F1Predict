import { useEffect, useState } from "react";
import {
  CartesianGrid,
  ReferenceLine,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import {
  api,
  type Backtest,
  type ForwardBacktest,
  type LiveMarkets,
  type ScoreMetric,
  type VsMarket,
} from "../api";

export function Markets() {
  const [bt, setBt] = useState<Backtest | null>(null);
  const [fwd, setFwd] = useState<ForwardBacktest | null>(null);
  const [vs, setVs] = useState<VsMarket | null>(null);
  const [live, setLive] = useState<LiveMarkets | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.backtest().then(setBt).catch((e) => setErr(String(e)));
    api.forwardBacktest().then(setFwd).catch(() => setFwd(null));
    api.vsMarket().then(setVs).catch(() => setVs(null));
    api.liveMarkets().then(setLive).catch(() => setLive({ available: false, markets: [] }));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Model vs Market</h2>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-zinc-500">
          Before risking a cent, we ask a free question: are our probabilities
          honest, and do they beat a naive baseline? We backtest every historical
          race — scoring the model's win/podium/points probabilities against what
          actually happened — then show the live market de-vig pipeline that would
          gate any real trading.
        </p>
      </div>

      {err && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-400">
          {err}. Run <code className="text-amber-300">app.etl.backtest</code> to
          compute it (free, offline).
        </div>
      )}

      {bt && <BacktestView bt={bt} />}
      {bt && fwd && <LeakFreeBanner bt={bt} fwd={fwd} />}
      {vs && <VsMarketView vs={vs} />}
      {live && <LiveView live={live} />}
    </div>
  );
}

function BacktestView({ bt }: { bt: Backtest }) {
  const calib = bt.calibration_win.map((b) => ({
    predicted: b.predicted,
    observed: b.observed,
    n: b.n,
  }));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-5">
        <Stat label="Races backtested" value={String(bt.n_races)} />
        <Stat label="Sims / race" value={bt.n_sims.toLocaleString()} />
        <Stat
          label="Top-pick winner hit"
          value={`${Math.round(bt.top_pick_accuracy * 100)}%`}
          accent
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <ScoreCard
          title="Win"
          m={bt.metrics.win}
          baseline={bt.baseline_win}
        />
        <ScoreCard title="Podium" m={bt.metrics.podium} />
        <ScoreCard title="Points" m={bt.metrics.points} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[420px_1fr]">
        {/* Calibration plot */}
        <div className="rounded-xl border border-edge bg-graphite p-4">
          <h3 className="mb-1 text-xs uppercase tracking-wider text-zinc-500">
            Calibration — win probability
          </h3>
          <p className="mb-2 text-[11px] text-zinc-600">
            Points on the dashed line = perfectly calibrated (e.g. "30% likely"
            things happen 30% of the time).
          </p>
          <ScatterChart
            width={380}
            height={260}
            margin={{ top: 8, right: 12, bottom: 20, left: 0 }}
          >
            <CartesianGrid stroke="#2a2a35" />
            <XAxis
              type="number"
              dataKey="predicted"
              domain={[0, 1]}
              name="Predicted"
              tick={{ fill: "#71717a", fontSize: 10 }}
              stroke="#2a2a35"
              label={{ value: "predicted", position: "bottom", fill: "#52525b", fontSize: 10 }}
            />
            <YAxis
              type="number"
              dataKey="observed"
              domain={[0, 1]}
              name="Observed"
              tick={{ fill: "#71717a", fontSize: 10 }}
              stroke="#2a2a35"
            />
            <ZAxis type="number" dataKey="n" range={[40, 400]} name="samples" />
            <ReferenceLine
              segment={[
                { x: 0, y: 0 },
                { x: 1, y: 1 },
              ]}
              stroke="#52525b"
              strokeDasharray="4 4"
            />
            <Tooltip
              cursor={{ stroke: "#2a2a35" }}
              contentStyle={{
                background: "#1c1c24",
                border: "1px solid #2a2a35",
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Scatter data={calib} fill="#ff1e1e" />
          </ScatterChart>
        </div>

        {/* Per-race table */}
        <div className="overflow-hidden rounded-xl border border-edge bg-graphite">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge text-[10px] uppercase tracking-wider text-zinc-600">
                <th className="px-3 py-2 text-left font-medium">Race</th>
                <th className="px-3 py-2 text-left font-medium">Actual winner</th>
                <th className="px-3 py-2 text-left font-medium">Model top pick</th>
                <th className="px-3 py-2 text-right font-medium">P(win)</th>
                <th className="px-3 py-2 text-center font-medium">Hit</th>
              </tr>
            </thead>
            <tbody>
              {bt.per_race.map((r, i) => (
                <tr
                  key={i}
                  className="border-b border-edge/50 last:border-0 hover:bg-slate-panel/40"
                >
                  <td className="px-3 py-1.5 text-zinc-400">
                    {r.year} {r.circuit}
                  </td>
                  <td className="px-3 py-1.5 font-medium">{r.actual_winner}</td>
                  <td className="px-3 py-1.5 text-zinc-300">{r.model_top_pick}</td>
                  <td className="px-3 py-1.5 text-right tabular text-zinc-400">
                    {Math.round(r.model_win_pct * 100)}%
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <span className={r.hit ? "text-emerald-400" : "text-zinc-600"}>
                      {r.hit ? "✓" : "·"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-zinc-600">
        <span className="text-zinc-500">Honesty notes:</span> driver pace is
        leave-one-race-out (the race being predicted is excluded), but circuit
        base-lap/tyre curves are still in-sample (a circuit property, not a per-race
        edge). The sample is small — this is a calibration check, not a p-value. No
        real market prices are used in the backtest; the de-vig pipeline below is the
        separate live capability.
      </p>
    </div>
  );
}

function LeakFreeBanner({
  bt,
  fwd,
}: {
  bt: Backtest;
  fwd: ForwardBacktest;
}) {
  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
      <h3 className="text-xs uppercase tracking-wider text-amber-400">
        Leak-free check (forward-chaining)
      </h3>
      <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-zinc-500">
        The calibration above is partly <span className="text-zinc-400">in-sample</span>{" "}
        (tyre curves saw the race being scored). The strict{" "}
        <span className="text-zinc-300">forward-chained</span> version trains only on
        data <em>before</em> each race — driver pace from prior races, tyre deg from
        that weekend's free practice. It lands almost identically, so our lookahead is
        mild and the numbers above are roughly trustworthy:
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-8">
        <Compare
          label="Top-pick winner"
          inSample={`${Math.round(bt.top_pick_accuracy * 100)}%`}
          honest={`${Math.round(fwd.top_pick_accuracy * 100)}%`}
        />
        <Compare
          label="Win Brier (lower=better)"
          inSample={(bt.metrics.win.brier ?? 0).toFixed(3)}
          honest={(fwd.metrics.win.brier ?? 0).toFixed(3)}
          lowerBetter
        />
        <div className="text-[11px] text-zinc-600">
          {fwd.n_races} races · {fwd.n_skipped_insufficient_history} skipped (thin
          early-season history)
        </div>
      </div>
    </div>
  );
}

function Compare({
  label,
  inSample,
  honest,
}: {
  label: string;
  inSample: string;
  honest: string;
  lowerBetter?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-zinc-600">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-2 font-mono tabular">
        <span className="text-zinc-400">{inSample}</span>
        <span className="text-[10px] text-zinc-600">in-sample</span>
        <span className="text-zinc-600">→</span>
        <span className="text-lg font-bold text-amber-400">{honest}</span>
        <span className="text-[10px] text-zinc-600">leak-free</span>
      </div>
    </div>
  );
}

function VsMarketView({ vs }: { vs: VsMarket }) {
  const modelBrier = vs.model_win.brier ?? 1;
  const marketBrier = vs.market_win.brier ?? 1;
  const marketWins = marketBrier < modelBrier;
  return (
    <div className="space-y-4 rounded-xl border border-f1-red/30 bg-gradient-to-br from-slate-panel to-graphite p-5">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-f1-redbright">
          vs the real Polymarket market
        </h3>
        <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">
          The honest test: our pre-race win probabilities against the actual de-vigged
          Polymarket odds (snapshotted before lights-out via Jolpica race times), over
          the {vs.n_races} 2024 races Polymarket covered. The market is a strong,
          well-calibrated opponent.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-edge bg-graphite p-4">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-zinc-600">
            Win Brier (lower = better)
          </div>
          <div className="flex items-end gap-6">
            <Versus label="Our model" value={modelBrier.toFixed(3)} win={!marketWins} />
            <Versus label="Market" value={marketBrier.toFixed(3)} win={marketWins} />
          </div>
        </div>
        <div className="rounded-lg border border-edge bg-graphite p-4">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-zinc-600">
            Top-pick winner accuracy
          </div>
          <div className="flex items-end gap-6">
            <Versus
              label="Our model"
              value={`${Math.round(vs.model_top_pick_accuracy * 100)}%`}
              win={vs.model_top_pick_accuracy >= vs.market_top_pick_accuracy}
            />
            <Versus
              label="Market"
              value={`${Math.round(vs.market_top_pick_accuracy * 100)}%`}
              win={vs.market_top_pick_accuracy > vs.model_top_pick_accuracy}
            />
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-edge bg-graphite">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-edge text-[10px] uppercase tracking-wider text-zinc-600">
              <th className="px-3 py-2 text-left font-medium">Race</th>
              <th className="px-3 py-2 text-left font-medium">Won</th>
              <th className="px-3 py-2 text-left font-medium">Market favourite</th>
              <th className="px-3 py-2 text-left font-medium">Model favourite</th>
            </tr>
          </thead>
          <tbody>
            {vs.per_race.map((r, i) => (
              <tr key={i} className="border-b border-edge/50 last:border-0">
                <td className="px-3 py-1.5 text-zinc-400">{r.circuit}</td>
                <td className="px-3 py-1.5 font-semibold">{r.winner}</td>
                <td className="px-3 py-1.5">
                  <span className={r.market_hit ? "text-emerald-400" : "text-zinc-300"}>
                    {r.market_fav} {Math.round(r.market_fav_p * 100)}%
                  </span>
                </td>
                <td className="px-3 py-1.5">
                  <span className={r.model_hit ? "text-emerald-400" : "text-zinc-300"}>
                    {r.model_fav} {Math.round((r.model_fav_p ?? 0) * 100)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] leading-relaxed text-zinc-500">
        <span className="text-zinc-400">Verdict:</span>{" "}
        {marketWins ? (
          <>
            the market beats us — no demonstrated edge, so there's no case to pay for
            live data. The model is over-reliant on season-average pace (it tends to
            favour the same driver each race) and lacks an overtaking model, so the
            actual qualifying grid doesn't move it enough. That's the honest gate
            result.
          </>
        ) : (
          <>our model is competitive with the market on this sample.</>
        )}
      </p>
    </div>
  );
}

function Versus({
  label,
  value,
  win,
}: {
  label: string;
  value: string;
  win: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-zinc-600">{label}</div>
      <div
        className={`font-mono text-2xl font-bold tabular ${
          win ? "text-emerald-400" : "text-zinc-400"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function LiveView({ live }: { live: LiveMarkets }) {
  return (
    <div className="rounded-xl border border-edge bg-graphite p-4">
      <h3 className="text-xs uppercase tracking-wider text-zinc-500">
        Live market de-vig (read-only · paper)
      </h3>
      {live.available ? (
        <div className="mt-3 space-y-4">
          {live.markets.map((m, i) => (
            <div key={i} className="rounded-lg border border-edge bg-slate-panel/40 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium">{m.question}</span>
                <span className="text-[11px] tabular text-amber-400">
                  vig {Math.round(m.overround * 1000) / 10}%
                </span>
              </div>
              <div className="space-y-1">
                {m.outcomes.slice(0, 6).map((o, j) => (
                  <div key={j} className="flex items-center gap-3 text-xs">
                    <span className="w-28 truncate text-zinc-300">{o.name}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-carbon">
                      <div
                        className="h-full rounded-full bg-f1-red"
                        style={{ width: `${o.implied * 100}%` }}
                      />
                    </div>
                    <span className="w-12 text-right tabular text-zinc-400">
                      {Math.round(o.implied * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-edge bg-slate-panel/40 p-4 text-sm leading-relaxed text-zinc-500">
          No live Polymarket F1 markets right now. When a race market is open, this
          panel reads the public mid-prices, removes the bookmaker's vig
          (normalising so outcomes sum to 100%), and would compare the clean
          probabilities to our model — surfacing any edge with fractional-Kelly
          sizing. It is strictly read-only / paper; no orders are placed. Whether
          that edge is ever real (and worth paying for live data) is exactly what the
          backtest above is built to decide.
        </div>
      )}
    </div>
  );
}

function ScoreCard({
  title,
  m,
  baseline,
}: {
  title: string;
  m: ScoreMetric;
  baseline?: ScoreMetric;
}) {
  const beatsBaseline =
    baseline?.brier != null && m.brier != null && m.brier < baseline.brier;
  return (
    <div className="rounded-xl border border-edge bg-graphite p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold">{title}</span>
        <span className="text-[10px] uppercase tracking-wider text-zinc-600">
          n={m.n}
        </span>
      </div>
      <div className="flex items-baseline gap-4">
        <div>
          <div className="font-mono text-xl font-bold tabular">
            {m.brier ?? "—"}
          </div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600">
            Brier ↓
          </div>
        </div>
        <div>
          <div className="font-mono text-sm tabular text-zinc-400">
            {m.logloss ?? "—"}
          </div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-600">
            log-loss ↓
          </div>
        </div>
      </div>
      {baseline?.brier != null && (
        <div className="mt-2 text-[11px] tabular text-zinc-500">
          grid baseline {baseline.brier} ·{" "}
          <span className={beatsBaseline ? "text-emerald-400" : "text-amber-400"}>
            {beatsBaseline ? "model wins" : "baseline wins"}
          </span>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-zinc-600">
        {label}
      </div>
      <div
        className={`font-mono text-lg font-semibold tabular ${
          accent ? "text-f1-redbright" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}
