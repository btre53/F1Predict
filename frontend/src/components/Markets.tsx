// PIT WALL — Markets tab. Wired to api.backtest() + api.vsMarket().
import { useEffect, useState } from "react";
import { api, type Backtest, type VsMarket, type ScoreMetric } from "../api";
import { Calibration, pct } from "./charts/Charts";

const f4 = (x: number | null) => (x == null ? "—" : x.toFixed(4));

export function Markets() {
  const [bt, setBt] = useState<Backtest | null>(null);
  const [vm, setVm] = useState<VsMarket | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.backtest().then(setBt).catch((e) => setErr(String(e)));
    api.vsMarket().then(setVm).catch(() => {});
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
