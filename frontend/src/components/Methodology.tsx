// PIT WALL — Methodology & Findings (#15). The honest-research showcase: what the model is,
// every model we tested, the findings, and the live mechanistic indices (overtaking, safety
// car, tyre degradation, car-DNA) pulled from the API. Content mirrors docs/MODEL.md +
// docs/science/ briefs 16-20.
import { useEffect, useMemo, useState } from "react";
import {
  api, type OvertakingRow, type SafetyCarRow, type TyreDegradation, type CarDna,
  type WeatherRow,
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
  { tag: "NO EDGE", title: "Not even on pole — the most predictable session", body: "Qualifying is the most deterministic part of a weekend, so the pole market was the best remaining edge candidate. Tested over all 23 races Polymarket has priced pole on (2025 from Miami + 2026 to date — found by enumerating Polymarket's F1 tag, since pole markets use two different slug formats): the market is still better-calibrated (pole Brier 0.039 vs our 0.045) and out-top-picked us 30% to 26% in a wild 2025 (VER/PIA/NOR/RUS/LEC all took poles). Our pre-quali grid forecast and the market's are both built from the same public history — no edge. See brief 27." },
  { tag: "KILLED", title: "Telemetry style ≠ racecraft", body: "At the reliable grain, sub-lap driving style doesn’t separate racecraft from the car. A paid live-telemetry feed would mostly re-derive what we get free from lap timing." },
  { tag: "KILLED", title: "Team×circuit affinity overfits", body: "At ~5–8 visits/circuit a team-track residual is race-day variance, not stable suitability. The principled, brand-agnostic replacement is the overtaking-difficulty index → it tunes confidence, applied equally to every team." },
  { tag: "HONEST", title: "More physics ≠ better prediction", body: "The detailed mechanistic sim lost to the simple rank model for who-wins. The model’s value is calibration + transparent, interpretable tooling — the “anti-AWS” — not a betting edge." },
  { tag: "KEPT", title: "Rain is a points-market term", body: "Counter-intuitively, rain doesn’t raise retirements (modern reliability + safety-car running) and the wet favourite is already calibrated. What it does scramble is WHO SCORES in the midfield — so we widen only the points market in the wet. See brief 21." },
  { tag: "HONEST", title: "A sim that can’t lose to the rank model", body: "We re-built the field sim anchored to the Kalman and ensembled, so its blend weight can never make the rank model worse (proven forward-chained). The first-cut physics still adds no who-wins skill — its niche is lap-resolved props. See brief 22." },
  { tag: "HONEST", title: "Absolute tyre compound doesn’t help", body: "We sourced Pirelli’s real C1–C6 nominations for 94 races to make degradation comparable across weekends. It backfired: the softest compounds (C5/C6) show the LOWEST in-race wear — because they’re only nominated at low-deg tracks (Monaco, Imola) and run in short, managed stints. The plain relative compound (soft wears fastest) is the cleaner signal. Sourced, tested, and shelved. See brief 24." },
  { tag: "SIGNAL", title: "Why track position is gold: 1.3s a lap", body: "Measured from real gap-to-car-ahead data: a FAST car stuck in traffic loses ~1.3s/lap, vs ~0.5s for a slow car — because it’s being held up, not just aero. That single number explains why qualifying dominates the result and why the leader sprints into clean air. It also rejected a tempting model fix (“strong cars shrug off dirty air”) — the data points the other way. See brief 25." },
];

const BRIEFS = [
  "01 lap-time model", "07 Polymarket backtest (market efficient)",
  "12 telemetry→racecraft (amber)", "13 in-play WPA (null edge)",
  "15 hazard DNF (beats flat)", "16 mechanistic edge features (ranked)",
  "17 overtaking-difficulty index (kept)", "18 structural SC index (ordering)",
  "19 car-DNA corner-band (Explainer-only)", "20 lap-time/tyre physics (research)",
  "21 weather-as-variance (points-only)", "22 structural sim anchor+ensemble",
  "26 position-resolution sim", "27 pole-market backtest (no edge)",
  "28 straight-line defence + 2026 era gate",
];

const OPEN_QUESTIONS: { t: string; b: string }[] = [
  { t: "Props are the sim’s real niche", b: "Score the structural sim on lap-resolved markets the rank model can’t produce — pit-window timing, “podium without the favourite”, points-with-a-top-car-DNF — not on who-wins, where the rank model is already at the ceiling." },
  { t: "Per-car best-response strategy", b: "Lift the Strategy Lab single-car optimiser to a full field game (Stackelberg) so each car pits optimally against the others inside the sim, instead of sharing one strategy." },
  { t: "A real rain forecast", b: "Swap the leak-free ERA5 realized-precip stand-in for an ex-ante Open-Meteo forecast on upcoming races — the predictor already accepts a rain override for exactly this." },
  { t: "Qualifying-prediction model", b: "Predict the grid itself and condition the race on it, closing the pre-qualifying gap probabilistically instead of only fusing a grid once quali has run." },
  { t: "Energy-proxy tyre wear", b: "Does ∫|a|·v per lap from free telemetry improve degradation beyond the tyre-age polynomial? (brief 20). Linear/quadratic already beat the log form for the ground-effect era." },
  { t: "Market-anchored (Benter) blend", b: "Blend model and market log-probabilities (α=β=0.75) for market-level calibration — now surfaced as the Blend column in Markets. In-sample it beats both model and market; out-of-sample it beats our model but the market is still best. A calibration aid, not a free edge." },
];

// --- Brief 22: the forward-chained ensemble sweep (research artifact, 45 recent races) ---
const ENS_W = [0, 0.15, 0.3, 0.5, 0.75, 1.0];
const ENS = {
  win: [0.131, 0.135, 0.141, 0.152, 0.175, 0.51],
  podium: [0.244, 0.247, 0.254, 0.272, 0.316, 0.82],
  points: [0.464, 0.466, 0.476, 0.506, 0.584, 1.713],
};

function interp(arr: number[], w: number): number {
  if (w <= ENS_W[0]) return arr[0];
  if (w >= ENS_W[ENS_W.length - 1]) return arr[arr.length - 1];
  let i = 0;
  while (w > ENS_W[i + 1]) i++;
  const t = (w - ENS_W[i]) / (ENS_W[i + 1] - ENS_W[i]);
  return arr[i] + t * (arr[i + 1] - arr[i]);
}

// Drag the ensemble weight w from anchor (rank model) -> pure sim and watch the leak-free
// logloss explode. Bars show "how much worse than the anchor" per market: 0 at w=0 (the
// floor — the blend can never be worse), full at w=1 (pure sim, catastrophic). Brief 22.
function EnsembleBlock() {
  const [w, setW] = useState(0);
  const markets = ["win", "podium", "points"] as const;
  const cur = useMemo(() => ({
    win: interp(ENS.win, w), podium: interp(ENS.podium, w), points: interp(ENS.points, w),
  }), [w]);
  // bar fraction = (ll - anchor) / (pure_sim - anchor)
  const frac = (m: typeof markets[number]) =>
    (cur[m] - ENS[m][0]) / (ENS[m][ENS[m].length - 1] - ENS[m][0]);
  const col = w < 0.05 ? "var(--green)" : w > 0.8 ? "var(--red)" : "var(--amber)";
  const verdict =
    w < 0.05 ? "This IS the rank model — the floor. The ensemble can never score worse."
    : w <= 0.3 ? "The physics is only adding noise; the learned weight wants almost none of it."
    : w < 0.85 ? "Calibration degrading fast as the sim takes over."
    : "Pure physical sim — catastrophic. This is the model that historically lost badly.";

  return (
    <div className="pw-panel pw-toolpanel">
      <div className="pw-phead">
        <h2>The ensemble guarantee — drag it yourself</h2>
        <span className="pw-interactive"><span className="pulse" /> interactive</span>
      </div>
      <div className="pw-slider" style={{ marginBottom: 4 }}>
        <div className="top">
          <span className="label">ensemble weight on the sim &nbsp;<b style={{ color: col }}>w = {w.toFixed(2)}</b></span>
          <span className="v" style={{ color: col }}>{w < 0.05 ? "ANCHOR" : w > 0.95 ? "PURE SIM" : "BLEND"}</span>
        </div>
        <input className="pw-range" type="range" min={0} max={1} step={0.01}
          value={w} onChange={(e) => setW(parseFloat(e.target.value))} />
        <div className="pw-wmarks"><span>0 · rank model</span><span>0.5</span><span>1 · pure sim</span></div>
      </div>
      <div style={{ marginTop: 14 }}>
        {markets.map((m) => (
          <div className="pw-ens" key={m}>
            <span className="k">{m} logloss</span>
            <div className="bar"><span style={{ width: `${Math.max(1, frac(m) * 100)}%`, background: col }} /></div>
            <span className="v" style={{ color: col }}>{cur[m].toFixed(3)}</span>
          </div>
        ))}
      </div>
      <div className="label" style={{ marginTop: 12, color: col, minHeight: 18 }}>{verdict}</div>
      <div className="label" style={{ marginTop: 6 }}>
        Forward-chained over 45 recent races. Best weight is w=0 on every market — so the
        sim, ensembled, is provably never worse than the rank model. Detail in brief 22.
      </div>
    </div>
  );
}

// Animated rain panel: the honest weather verdicts + the live wettest-races feed. Brief 21.
function WeatherBlock({ rows }: { rows: WeatherRow[] }) {
  const wettest = useMemo(
    () => [...rows].filter((r) => r.wet).sort((a, b) => b.precip_mm_window - a.precip_mm_window).slice(0, 6),
    [rows],
  );
  const maxMM = Math.max(...wettest.map((r) => r.precip_mm_window), 1);
  // points logloss: dry (calibrated) vs wet-before vs wet-after the widening (brief 21)
  const spread = [
    { lab: "Dry races (already calibrated)", v: 0.530, c: "var(--ink-3)" },
    { lab: "Wet — model before", v: 0.558, c: "var(--red)" },
    { lab: "Wet — after points widening", v: 0.517, c: "var(--green)" },
  ];
  const maxLL = 0.62;

  return (
    <div className="pw-grid2">
      <div className="pw-panel pw-wx">
        <div className="pw-rain" />
        <div className="pw-phead"><h2>Weather as variance</h2><span className="label">free · leak-free · ERA5</span></div>
        <div className="pw-bignum">
          <span className="from">0.558</span>
          <span className="arr">→</span>
          <span className="to">0.517</span>
          <span className="cap">wet-race <b style={{ color: "var(--ink)" }}>points</b> logloss, once we stop being over-confident in the rain</span>
        </div>
        <div className="pw-pills">
          <div className="pw-pill"><span className="mk no">✕</span><div><b>DNF multiplier — dead.</b> Wet 9.2% vs dry 9.3%. Rain doesn’t retire more cars.</div></div>
          <div className="pw-pill"><span className="mk no">✕</span><div><b>Win / podium spread — rejected.</b> The wet favourite is already well-calibrated.</div></div>
          <div className="pw-pill"><span className="mk yes">✓</span><div><b>Points spread — kept.</b> Rain scrambles who scores in the midfield, so we widen <i>only</i> the points market in the wet.</div></div>
        </div>
        <div style={{ marginTop: 16 }}>
          {spread.map((s) => (
            <div className="pw-spreadrow" key={s.lab}>
              <div className="lab"><span>{s.lab}</span><span style={{ color: s.c }}>{s.v.toFixed(3)}</span></div>
              <div className="pw-spreadbar"><span style={{ width: `${(s.v / maxLL) * 100}%`, background: s.c }} /></div>
            </div>
          ))}
        </div>
      </div>

      <div className="pw-panel">
        <div className="pw-phead"><h2>Wettest races in our data</h2><span className="label">race-window rain · live</span></div>
        {wettest.length === 0 ? (
          <div className="label">weather artifact not built yet (run app.etl.weather)</div>
        ) : (
          <div className="pw-wxlist">
            {wettest.map((r) => (
              <div className="row" key={`${r.year}-${r.circuit}`}>
                <span className="nm">{r.circuit}<span className="yr">{r.year}</span></span>
                <div className="bar"><span style={{ width: `${(r.precip_mm_window / maxMM) * 100}%` }} /></div>
                <span className="mm">{r.precip_mm_window.toFixed(1)} mm</span>
              </div>
            ))}
          </div>
        )}
        <div className="label" style={{ marginTop: 12 }}>
          Cross-checked 13/14 against FastF1’s trackside rain sensor. The same ERA5 column
          swaps for a live forecast on an upcoming race.
        </div>
      </div>
    </div>
  );
}

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
  const [wx, setWx] = useState<WeatherRow[]>([]);
  useEffect(() => {
    api.overtakingIndex().then(setOt).catch(() => {});
    api.safetyCarPrior().then(setSc).catch(() => {});
    api.tyreDegradation().then(setDeg).catch(() => {});
    api.carDna().then(setDna).catch(() => {});
    api.circuitWeather().then(setWx).catch(() => {});
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

      {/* Shipped this season — weather + the structural sim */}
      <div className="pw-intro" style={{ paddingTop: 8 }}>
        <div className="pw-chip">▮ SHIPPED THIS SEASON</div>
        <h2 style={{ fontSize: 20 }}>Weather-as-variance, and a sim that can’t lose to the rank model</h2>
        <p>Two roadmap ideas, validated forward-chained — and both gave a more interesting
          answer than the obvious one. Drag the slider; watch the rain.</p>
      </div>
      <WeatherBlock rows={wx} />
      <EnsembleBlock />

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

      {/* Open questions */}
      <div className="pw-panel">
        <div className="pw-phead"><h2>Open questions &amp; what’s next</h2><span className="label">the honest backlog</span></div>
        <div className="pw-grid2" style={{ gap: 12 }}>
          {OPEN_QUESTIONS.map((q) => (
            <div className="pw-pill" key={q.t}>
              <span className="mk" style={{ color: "var(--amber)" }}>?</span>
              <div><b>{q.t}.</b> {q.b}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Briefs */}
      <div className="pw-panel">
        <div className="pw-phead"><h2>Research briefs</h2><span className="label">docs/science · 22 briefs</span></div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {BRIEFS.map((b) => (
            <span key={b} className="pw-badge" style={{ fontSize: 11 }}>{b}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
