// PIT WALL — Markets tab. Wired to api.backtest() + api.vsMarket().
import { useEffect, useState } from "react";
import { api, type Backtest, type VsMarket, type ScoreMetric, type LiveMarkets } from "../api";
import { Calibration, pct } from "./charts/Charts";

const f4 = (x: number | null) => (x == null ? "—" : x.toFixed(4));

// Liquidity badge: how the live price was derived (honest about thin books).
const SRC_LABEL: Record<string, { t: string; c: string }> = {
  book_mid: { t: "mid", c: "var(--green)" },
  last_trade: { t: "last", c: "var(--amber)" },
  gamma: { t: "est", c: "var(--ink-3)" },
};

export function Markets() {
  const [bt, setBt] = useState<Backtest | null>(null);
  const [vm, setVm] = useState<VsMarket | null>(null);
  const [live, setLive] = useState<LiveMarkets | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.backtest().then(setBt).catch((e) => setErr(String(e)));
    api.vsMarket().then(setVm).catch(() => {});
    const load = () => api.liveMarkets().then(setLive).catch(() => {});
    load();
    // Poll a few-second cadence — the F1 winner market moves in <8% of minutes, so this
    // is plenty fresh while staying well under any rate limit (the WS push is a follow-up).
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const tiles: { k: string; m: ScoreMetric; baseline?: number | null }[] = bt
    ? [
        { k: "Win", m: bt.metrics.win, baseline: bt.baseline_win.brier },
        { k: "Podium", m: bt.metrics.podium },
        { k: "Points", m: bt.metrics.points },
      ]
    : [];

  return (
    <div className="pw-stack">
      <div className="pw-intro" style={{ paddingTop: 6 }}>
        <h2>Model vs market</h2>
        <p>Backtested against every historical race, then put head-to-head with de-vigged Polymarket prices. Lower Brier wins.</p>
      </div>

      {err && <div className="pw-panel" style={{ borderColor: "var(--red)", color: "var(--red-bright)" }}>{err}</div>}

      {live && live.available && live.markets.length > 0 && (
        <div className="pw-grid2">
          {live.markets.map((mk) => (
            <div className="pw-panel" key={mk.slug}>
              <div className="pw-phead">
                <h2>{mk.question.replace("Grand Prix: Driver ", "· ")}</h2>
                <span className="label" style={{ color: live.source === "live" ? "var(--green)" : "var(--amber)" }}>
                  {live.source === "live" ? "● LIVE" : `snapshot ${(live.as_of || "").slice(0, 10)}`}
                  {" · "}{(mk.overround * 100).toFixed(0)}% vig
                </span>
              </div>
              <table className="pw-table">
                <thead><tr><th>Driver</th><th className="num">Implied</th><th className="num">Price</th><th className="num">Bid–Ask</th><th></th></tr></thead>
                <tbody>
                  {mk.outcomes.filter((o) => o.implied >= 0.01).map((o) => {
                    const s = SRC_LABEL[o.source ?? "gamma"];
                    return (
                      <tr key={o.name}>
                        <td>{o.name}</td>
                        <td className="num"><b>{pct(o.implied)}</b></td>
                        <td className="num">{o.price.toFixed(3)}</td>
                        <td className="num" style={{ color: "var(--ink-3)", fontSize: 11 }}>
                          {o.bid != null && o.ask != null ? `${o.bid.toFixed(2)}–${o.ask.toFixed(2)}` : "—"}
                        </td>
                        <td><span className="label" style={{ color: s.c, fontSize: 9 }}>{s.t}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="label" style={{ marginTop: 8, fontSize: 10, color: "var(--ink-3)" }}>
                Price = CLOB order-book midpoint (tight two-sided books) · last trade / est. on thin books · implied = de-vigged. Read-only.
              </div>
            </div>
          ))}
        </div>
      )}

      {bt && (
        <>
          <div className="pw-controls" style={{ borderBottom: "none", paddingBottom: 0 }}>
            <div className="pw-readouts" style={{ marginLeft: 0, gap: 34 }}>
              <div className="pw-readout" style={{ textAlign: "left" }}><div className="label">Races backtested</div><div className="v">{bt.n_races}</div></div>
              <div className="pw-readout" style={{ textAlign: "left" }}><div className="label">Sims / race</div><div className="v">{bt.n_sims.toLocaleString()}</div></div>
              <div className="pw-readout" style={{ textAlign: "left" }}><div className="label">Top-pick winner hit</div><div className="v" style={{ color: "var(--red)" }}>{pct(bt.top_pick_accuracy)}</div></div>
            </div>
          </div>

          <div className="pw-tiles">
            {tiles.map((t) => (
              <div className="pw-tile" key={t.k}>
                <div className="label" style={{ marginBottom: 8 }}>{t.k}<span style={{ float: "right" }}>N={t.m.n}</span></div>
                <div className="row"><span className="big">{f4(t.m.brier)}</span><span className="sm">Brier ↓</span></div>
                <div className="row" style={{ marginTop: 4 }}><span className="sm">{f4(t.m.logloss)}</span><span className="sm">log-loss ↓</span></div>
                {t.baseline != null && <div className="label" style={{ marginTop: 10 }}>baseline {f4(t.baseline)}</div>}
              </div>
            ))}
          </div>

          <div className="pw-grid2">
            <div className="pw-panel">
              <div className="pw-phead"><h2>Calibration — win probability</h2></div>
              <p className="desc" style={{ marginBottom: 8 }}>Points on the dashed line = perfectly calibrated.</p>
              <Calibration points={bt.calibration_win.map((c) => ({ predicted: c.predicted, observed: c.observed }))} />
            </div>
            {vm && (
              <div className="pw-panel">
                <div className="pw-phead"><h2>Model vs Polymarket</h2><span className="label">{vm.n_races} races · de-vigged</span></div>
                <div className="pw-grid2" style={{ gap: 12, marginBottom: 14 }}>
                  <div className="pw-tile"><div className="label">Win Brier ↓</div>
                    <div className="row" style={{ gap: 18 }}><span><span className="label">Model</span><div className="big">{f4(vm.model_win.brier)}</div></span>
                      <span><span className="label">Market</span><div className="big" style={{ color: "var(--green)" }}>{f4(vm.market_win.brier)}</div></span></div></div>
                  <div className="pw-tile"><div className="label">Top-pick acc.</div>
                    <div className="row" style={{ gap: 18 }}><span><span className="label">Model</span><div className="big">{pct(vm.model_top_pick_accuracy)}</div></span>
                      <span><span className="label">Market</span><div className="big" style={{ color: "var(--green)" }}>{pct(vm.market_top_pick_accuracy)}</div></span></div></div>
                </div>
              </div>
            )}
          </div>

          <div className="pw-panel flush">
            <div style={{ padding: "18px 20px 0" }}><div className="pw-phead"><h2>Per-race backtest</h2></div></div>
            <div style={{ overflowX: "auto" }}>
              <table className="pw-table">
                <thead><tr><th>Race</th><th>Actual winner</th><th>Model top pick</th><th className="num">P(win)</th><th className="num">Hit</th></tr></thead>
                <tbody>
                  {bt.per_race.map((r, i) => (
                    <tr key={i}>
                      <td>{r.year} {r.circuit}</td><td><b>{r.actual_winner}</b></td><td>{r.model_top_pick}</td>
                      <td className="num">{pct(r.model_win_pct)}</td>
                      <td className="num">{r.hit ? <span className="pw-hit">✓</span> : <span className="pw-miss">·</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
