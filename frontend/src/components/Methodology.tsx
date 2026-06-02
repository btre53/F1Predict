// PIT WALL — Methodology & Findings (#15). The honest-research showcase: what the model is,
// every model we tested, the findings, and the live mechanistic indices (overtaking, safety
// car, tyre degradation, car-DNA) pulled from the API. Content mirrors docs/MODEL.md +
// docs/science/ briefs 16-20.
import { useEffect, useState } from "react";
import {
  api, type OvertakingRow, type SafetyCarRow, type TyreDegradation, type CarDna,
} from "../api";

const BAKEOFF: { model: string; what: string; verdict: string; kept: boolean }[] = [
  { model: "Baseline", what: "grid + quali, 10 lines", verdict: "the bar to beat", kept: true },
  { model: "PL-Glicko rating", what: "sequential rating, grid-aware", verdict: "≈ baseline", kept: false },
  { model: "Kalman pace filter", what: "car + driver Gaussian filter", verdict: "SHIPPED — best calibration", kept: true },
  { model: "LightGBM ranker", what: "gradient-boosted features", verdict: "≈ baseline, less interpretable", kept: false },
  { model: "Mechanistic Monte Carlo", what: "per-lap pace + tyre + pit sim", verdict: "superseded (~32% top-pick)", kept: false },
  { model: "Kalman + track affinity", what: "“does this car suit this track”", verdict: "REJECTED — overfit", kept: false },
];

const FINDINGS: { tag: string; title: string; body: string }[] = [
  { tag: "SIGNAL", title: "Grid / qualifying dominates", body: "Fancy models barely beat a 10-line grid+quali baseline. The winner is near-trivial (pole); the real variance is the rest-of-field, so we score on best-of-rest / podium, not win." },
  { tag: "NO EDGE", title: "The pre-race market is efficient", body: "Our forward-chained Kalman is competitive with Polymarket (win Brier ~0.054 vs ~0.049 over 23 races) but does not beat it. No outright edge." },
  { tag: "NO EDGE", title: "No in-play edge either", body: "Our live win-prob is well-calibrated (Brier ~0.048) but does NOT lead the market — the detrended increment cross-correlation is flat at every lag. A lap-completion engine structurally lags ~90s." },
  { tag: "KILLED", title: "Telemetry style ≠ racecraft", body: "At the reliable grain, sub-lap driving style doesn’t separate racecraft from the car. A paid live-telemetry feed would mostly re-derive what we get free from lap timing." },
  { tag: "KILLED", title: "Team×circuit affinity overfits", body: "At ~5–8 visits/circuit a team-track residual is race-day variance, not stable suitability. The principled, brand-agnostic replacement is the overtaking-difficulty index → it tunes confidence, applied equally to every team." },
  { tag: "HONEST", title: "More physics ≠ better prediction", body: "The detailed mechanistic sim lost to the simple rank model for who-wins. The model’s value is calibration + transparent, interpretable tooling — the “anti-AWS” — not a betting edge." },
];

const BRIEFS = [
  "01 lap-time model", "07 Polymarket backtest (market efficient)",
  "12 telemetry→racecraft (amber)", "13 in-play WPA (null edge)",
  "15 hazard DNF (beats flat)", "16 mechanistic edge features (ranked)",
  "17 overtaking-difficulty index (kept)", "18 structural SC index (ordering)",
  "19 car-DNA corner-band (Explainer-only)", "20 lap-time/tyre physics (research)",
];

function Bars({ rows, label, hi, lo }: {
  rows: { name: string; v: number }[]; label: string; hi: string; lo: string;
}) {
  const max = Math.max(...rows.map((r) => Math.abs(r.v)), 0.01);
  return (
    <div className="pw-panel">
      <div className="pw-phead"><h2>{label}</h2><span className="label">{hi} ↑ · {lo} ↓</span></div>
      <div className="pw-stack" style={{ gap: 5 }}>
        {rows.map((r) => (
          <div key={r.name} style={{ display: "grid", gridTemplateColumns: "120px 1fr 46px", gap: 10, alignItems: "center" }}>
            <span className="pw-code" style={{ fontSize: 11 }}>{r.name}</span>
            <div className="pw-track"><div className="pw-fill" style={{ width: `${(Math.abs(r.v) / max) * 100}%`, background: r.v >= 0 ? "var(--red)" : "#3b8dff" }} /></div>
            <span className="mono" style={{ fontSize: 11, textAlign: "right", color: "var(--ink-2)" }}>{r.v.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Methodology() {
  const [ot, setOt] = useState<OvertakingRow[]>([]);
  const [sc, setSc] = useState<SafetyCarRow[]>([]);
  const [deg, setDeg] = useState<TyreDegradation | null>(null);
  const [dna, setDna] = useState<CarDna | null>(null);
  useEffect(() => {
    api.overtakingIndex().then(setOt).catch(() => {});
    api.safetyCarPrior().then(setSc).catch(() => {});
    api.tyreDegradation().then(setDeg).catch(() => {});
    api.carDna().then(setDna).catch(() => {});
  }, []);

  const top = (xs: { name: string; v: number }[]) =>
    [...xs].sort((a, b) => b.v - a.v).filter((_, i, a) => i < 6 || i >= a.length - 6);

  return (
    <div className="pw-stack">
      <div className="pw-intro">
        <div className="pw-chip">▮ HONEST RESEARCH</div>
        <h2>Methodology &amp; findings</h2>
        <p>Every model we tested, what we found, and the live mechanistic indices behind the
          predictor. The value here is <b style={{ color: "var(--red)" }}>calibration + transparency</b>,
          not a betting edge — and we kept the negatives.</p>
      </div>

      {/* The bake-off */}
      <div className="pw-panel flush">
        <div style={{ padding: "18px 20px 0" }}><div className="pw-phead"><h2>The bake-off — every model tested</h2><span className="label">forward-chained, leak-free</span></div></div>
        <div style={{ overflowX: "auto" }}>
          <table className="pw-table">
            <thead><tr><th>Model</th><th>What</th><th>Verdict</th></tr></thead>
            <tbody>
              {BAKEOFF.map((b) => (
                <tr key={b.model}>
                  <td><b style={{ color: b.kept ? "var(--green)" : "var(--ink-2)" }}>{b.model}</b></td>
                  <td style={{ color: "var(--ink-2)" }}>{b.what}</td>
                  <td>{b.verdict}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="label" style={{ padding: "0 20px 16px" }}>
          All cluster ~63% top-pick and barely beat the baseline — the signal is the grid. The
          Kalman ships: best-calibrated, fully online, interpretable. Detail in docs/MODEL.md.
        </div>
      </div>

      {/* Findings */}
      <div className="pw-grid2">
        {FINDINGS.map((f) => (
          <div className="pw-sci" key={f.title}>
            <div>
              <div className="pw-chip" style={{ color: f.tag === "SIGNAL" ? "var(--green)" : f.tag === "HONEST" ? "var(--amber)" : "var(--red)" }}>{f.tag}</div>
              <h3>{f.title}</h3>
              <div className="body">{f.body}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Live mechanistic indices */}
      <div className="pw-intro" style={{ paddingTop: 8 }}>
        <div className="pw-chip">▮ THE LIVE MECHANISTIC INDICES</div>
        <h2 style={{ fontSize: 20 }}>Brand-agnostic track physics, computed from our own data</h2>
      </div>

      <div className="pw-grid2">
        {ot.length > 0 && (
          <Bars label="Overtaking difficulty" hi="qualifying-locked (Monaco)" lo="pace overcomes grid (Spa)"
            rows={top(ot.map((r) => ({ name: r.circuit, v: r.index })))} />
        )}
        {sc.length > 0 && (
          <Bars label="Structural safety-car prior" hi="chaos-prone (street)" lo="clean (run-off)"
            rows={top(sc.map((r) => ({ name: r.circuit, v: r.sc_prior })))} />
        )}
      </div>

      <div className="pw-grid2">
        {deg && deg.compounds && (
          <div className="pw-panel">
            <div className="pw-phead"><h2>Tyre degradation (2022+ era)</h2><span className="label">loss vs fresh, s</span></div>
            <table className="pw-table">
              <thead><tr><th>Compound</th><th>Best fit</th><th className="num">@10</th><th className="num">@20</th><th className="num">@30</th></tr></thead>
              <tbody>
                {Object.entries(deg.compounds).map(([c, d]) => (
                  <tr key={c}>
                    <td><b>{c}</b></td><td style={{ color: "var(--ink-2)" }}>{d.best_form}</td>
                    <td className="num">{d.loss_at_age_s["10"] ?? "—"}</td>
                    <td className="num">{d.loss_at_age_s["20"] ?? "—"}</td>
                    <td className="num">{d.loss_at_age_s["30"] ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="label" style={{ marginTop: 8 }}>Finding: the log form (best 2014–19) is NOT best for ground-effect tyres — linear/quadratic win.</div>
          </div>
        )}
        {dna && dna.car_dna && dna.car_dna.length > 0 && (
          <div className="pw-panel">
            <div className="pw-phead"><h2>Car-DNA corner-band</h2><span className="label">where a car is relatively fast</span></div>
            <table className="pw-table">
              <thead><tr><th>Driver</th><th className="num">low</th><th className="num">med</th><th className="num">high</th><th className="num">str</th></tr></thead>
              <tbody>
                {dna.car_dna.slice(0, 8).map((r) => (
                  <tr key={r.driver}>
                    <td><b>{r.driver}</b></td>
                    {(["low", "med", "high", "straight"] as const).map((b) => (
                      <td key={b} className="num" style={{ color: (r[b] ?? 0) > 0 ? "var(--green)" : "var(--ink-3)" }}>
                        {r[b] == null || isNaN(r[b] as number) ? "—" : (r[b] as number).toFixed(3)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="label" style={{ marginTop: 8 }}>Interpretable but not predictive over scalar pace (Explainer-only). {dna.year} qualifying.</div>
          </div>
        )}
      </div>

      {/* Briefs */}
      <div className="pw-panel">
        <div className="pw-phead"><h2>Research briefs</h2><span className="label">docs/science · 20 briefs</span></div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {BRIEFS.map((b) => (
            <span key={b} className="pw-badge" style={{ fontSize: 11 }}>{b}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
