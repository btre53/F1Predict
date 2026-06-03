// PIT WALL — CHAMPIONSHIP (task #25). Monte-Carlo the rest of the season into title odds for
// every driver and constructor, with a model-vs-Polymarket-outright column (honest framing: the
// title market is efficient, so we expect no edge — the column just shows where we agree/diverge)
// and an interactive sandbox: nudge a driver's pace / give them extra DNFs and watch the title
// race re-shake. Wired to GET /championship + POST /championship/simulate.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Championship as Champ, type DriverOverride } from "../api";
import { pct } from "./charts/Charts";

// Team colours for the 2026 grid (the /championship payload carries no colour).
const TEAM_COLORS: Record<string, string> = {
  "Red Bull Racing": "#3671C6", Ferrari: "#E8002D", Mercedes: "#27F4D2", McLaren: "#FF8000",
  "Aston Martin": "#229971", Alpine: "#0093CC", Williams: "#64C4FF", "Racing Bulls": "#6692FF",
  "Haas F1 Team": "#B6BABD", Audi: "#52E252", Cadillac: "#CFB991",
};
const colorOf = (team: string) => TEAM_COLORS[team] ?? "#9aa0ab";

// Signed model−market delta, rendered as a coloured pp figure (green = model higher).
function Delta({ model, market }: { model: number; market: number | null }) {
  if (market == null) return <span className="label" style={{ color: "var(--ink-3)" }}>—</span>;
  const d = Math.round((model - market) * 100);
  const c = d > 4 ? "var(--green)" : d < -4 ? "var(--red)" : "var(--ink-3)";
  return <span className="tnum" style={{ color: c }}>{d > 0 ? "+" : ""}{d}pp</span>;
}

function OddsBar({ value, market, color }: { value: number; market: number | null; color: string }) {
  return (
    <div className="pw-track" style={{ position: "relative" }} title={`model ${pct(value)}${market != null ? ` · market ${pct(market)}` : ""}`}>
      <div className="pw-fill" style={{ width: `${Math.max(1.5, value * 100)}%`, background: color }} />
      {market != null && (
        <span style={{
          position: "absolute", top: -2, bottom: -2, left: `${Math.min(99, market * 100)}%`,
          width: 2, background: "var(--ink-1)", opacity: 0.85,
        }} title={`market ${pct(market)}`} />
      )}
    </div>
  );
}

export function Championship() {
  const [base, setBase] = useState<Champ | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Sandbox state.
  const [driver, setDriver] = useState<string>("");
  const [pace, setPace] = useState(0);     // z, +ve = faster
  const [dnfs, setDnfs] = useState(0);     // extra DNFs over the rest of the season
  const [sandbox, setSandbox] = useState<Champ | null>(null);
  const [simming, setSimming] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    api.championship(true, 20000)
      .then((c) => { setBase(c); setDriver(c.drivers[0]?.driver ?? ""); })
      .catch((e) => setErr(String(e)));
  }, []);

  const active = !!(driver && (pace !== 0 || dnfs !== 0));

  // Debounced re-run of the sandbox whenever the knobs move.
  useEffect(() => {
    if (!active) { setSandbox(null); return; }
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const ov: Record<string, DriverOverride> = {
        [driver]: { pace_delta: pace, extra_dnfs: dnfs },
      };
      setSimming(true);
      api.championshipSimulate(ov, 12000)
        .then(setSandbox)
        .catch((e) => setErr(String(e)))
        .finally(() => setSimming(false));
    }, 260);
    return () => { if (timer.current) window.clearTimeout(timer.current); };
  }, [driver, pace, dnfs, active]);

  const shown = sandbox ?? base;
  const baseOddsOf = useMemo(() => {
    const m: Record<string, number> = {};
    base?.drivers.forEach((d) => (m[d.driver] = d.title_pct));
    return m;
  }, [base]);

  if (err) return <div className="pw-panel" style={{ borderColor: "var(--red)", color: "var(--red-bright)" }}>{err}</div>;
  if (!base || !shown) return <div className="label">Simulating the rest of the season…</div>;

  return (
    <div className="pw-stack">
      <div className="pw-controls">
        <div className="pw-readouts">
          <div className="pw-readout"><div className="label">Season</div><div className="v tnum">{shown.year}</div></div>
          <div className="pw-readout"><div className="label">Races run</div><div className="v tnum">{shown.n_done}</div></div>
          <div className="pw-readout"><div className="label">Remaining</div><div className="v tnum">{shown.n_remaining}</div></div>
          <div className="pw-readout"><div className="label">Simulations</div><div className="v tnum">{shown.n_sims.toLocaleString()}</div></div>
          <div className="pw-readout"><div className="label">Market</div>
            <div className="v" style={{ color: base.market_available ? "var(--green)" : "var(--amber)" }}>
              {base.market_available ? "Polymarket" : "n/a"}</div></div>
        </div>
      </div>

      {/* DRIVERS */}
      <div className="pw-panel">
        <div className="pw-phead">
          <h2>Drivers' championship — title odds</h2>
          <span className="label">{shown.n_remaining} races left · {shown.n_sims.toLocaleString()} season sims</span>
        </div>
        <table className="pw-table">
          <thead>
            <tr>
              <th></th><th>Driver</th><th className="num">Pts</th>
              <th>Title odds {base.market_available && <span className="label">(│ = market)</span>}</th>
              <th className="num">Model</th><th className="num">Market</th><th className="num">Δ</th>
              <th className="num">Exp pts</th><th className="num">Top-3</th>
            </tr>
          </thead>
          <tbody>
            {shown.drivers.filter((d) => d.title_pct > 0.001 || d.current_points > 0).slice(0, 12).map((d, i) => {
              const tc = colorOf(d.team);
              const moved = active && d.driver === driver;
              const baseP = baseOddsOf[d.driver] ?? d.title_pct;
              return (
                <tr key={d.driver} style={moved ? { boxShadow: "inset 3px 0 0 var(--amber)" } : undefined}>
                  <td className="tnum" style={{ color: "var(--ink-3)" }}>{i + 1}</td>
                  <td>
                    <span className="pw-spine" style={{ background: tc, display: "inline-block", width: 3, height: 13, marginRight: 7, verticalAlign: "middle" }} />
                    <span className="pw-code">{d.driver}</span>
                    <span className="pw-team" style={{ marginLeft: 6, color: "var(--ink-3)" }}>{d.team}</span>
                  </td>
                  <td className="num tnum">{d.current_points}</td>
                  <td style={{ minWidth: 180 }}><OddsBar value={d.title_pct} market={base.market_available ? d.market_pct : null} color={tc} /></td>
                  <td className="num tnum" style={{ color: tc, fontWeight: 600 }}>
                    {pct(d.title_pct)}
                    {active && d.driver === driver && (
                      <span className="label" style={{ marginLeft: 4, color: d.title_pct >= baseP ? "var(--green)" : "var(--red)" }}>
                        ({d.title_pct >= baseP ? "+" : ""}{Math.round((d.title_pct - baseP) * 100)})
                      </span>
                    )}
                  </td>
                  <td className="num tnum" style={{ color: "var(--ink-3)" }}>{d.market_pct != null ? pct(d.market_pct) : "—"}</td>
                  <td className="num"><Delta model={d.title_pct} market={active ? null : d.market_pct} /></td>
                  <td className="num tnum">{Math.round(d.exp_points)}</td>
                  <td className="num tnum" style={{ color: "var(--ink-3)" }}>{pct(d.p_top3)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* SANDBOX */}
      <div className="pw-panel">
        <div className="pw-phead">
          <h2>What-if sandbox {simming && <span className="label" style={{ color: "var(--amber)" }}>· re-running…</span>}</h2>
          <span className="label">Re-shake the title race</span>
        </div>
        <p className="desc" style={{ marginTop: 0 }}>
          Nudge a driver's pace or hand them bad luck and the whole championship re-simulates. The
          model only aggregates per-race predictions we already validate — so this is an honest
          counterfactual, not a tuned story.
        </p>
        <div className="pw-controls" style={{ alignItems: "flex-end", gap: 22 }}>
          <div className="pw-field">
            <span className="label">Driver</span>
            <select className="pw-select" value={driver} onChange={(e) => setDriver(e.target.value)}>
              {base.drivers.map((d) => <option key={d.driver} value={d.driver}>{d.driver} — {d.team}</option>)}
            </select>
          </div>
          <div style={{ minWidth: 200 }}>
            <div className="pw-slider">
              <div className="top"><span className="label">Pace shift</span><span className="v tnum">{pace > 0 ? "+" : ""}{pace.toFixed(2)}z</span></div>
              <input type="range" className="pw-range" min={-1} max={1} step={0.05} value={pace} onChange={(e) => setPace(+e.target.value)} />
            </div>
          </div>
          <div style={{ minWidth: 200 }}>
            <div className="pw-slider">
              <div className="top"><span className="label">Extra DNFs (rest of season)</span><span className="v tnum">{dnfs}</span></div>
              <input type="range" className="pw-range" min={0} max={10} step={1} value={dnfs} onChange={(e) => setDnfs(+e.target.value)} />
            </div>
          </div>
          <button className="pw-select" style={{ cursor: active ? "pointer" : "not-allowed", opacity: active ? 1 : 0.5 }}
            disabled={!active} onClick={() => { setPace(0); setDnfs(0); }}>Reset</button>
        </div>
        {active && sandbox && (() => {
          const d = sandbox.drivers.find((x) => x.driver === driver);
          const baseP = baseOddsOf[driver] ?? 0;
          if (!d) return null;
          const delta = Math.round((d.title_pct - baseP) * 100);
          return (
            <div className="label" style={{ marginTop: 12 }}>
              {driver}'s title odds {pace || dnfs ? "now" : ""} <b style={{ color: colorOf(d.team) }}>{pct(d.title_pct)}</b>{" "}
              <span style={{ color: delta >= 0 ? "var(--green)" : "var(--red)" }}>
                ({delta >= 0 ? "+" : ""}{delta}pp vs base {pct(baseP)})
              </span>
            </div>
          );
        })()}
      </div>

      {/* CONSTRUCTORS */}
      <div className="pw-panel">
        <div className="pw-phead"><h2>Constructors' championship</h2><span className="label">team points = both cars</span></div>
        <table className="pw-table">
          <thead><tr><th></th><th>Team</th><th>Title odds</th><th className="num">Model</th><th className="num">Market</th><th className="num">Δ</th><th className="num">Exp pts</th></tr></thead>
          <tbody>
            {shown.constructors.filter((c) => c.title_pct > 0.0005 || c.exp_points > 30).map((c, i) => {
              const tc = colorOf(c.team);
              return (
                <tr key={c.team}>
                  <td className="tnum" style={{ color: "var(--ink-3)" }}>{i + 1}</td>
                  <td><span className="pw-spine" style={{ background: tc, display: "inline-block", width: 3, height: 13, marginRight: 7, verticalAlign: "middle" }} /><span className="pw-code">{c.team}</span></td>
                  <td style={{ minWidth: 180 }}><OddsBar value={c.title_pct} market={base.market_available ? c.market_pct : null} color={tc} /></td>
                  <td className="num tnum" style={{ color: tc, fontWeight: 600 }}>{pct(c.title_pct)}</td>
                  <td className="num tnum" style={{ color: "var(--ink-3)" }}>{c.market_pct != null ? pct(c.market_pct) : "—"}</td>
                  <td className="num"><Delta model={c.title_pct} market={c.market_pct} /></td>
                  <td className="num tnum">{Math.round(c.exp_points)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* HONEST FRAMING */}
      <div className="pw-panel" style={{ borderColor: "var(--amber)" }}>
        <div className="pw-phead"><h2 style={{ color: "var(--amber)" }}>Reading the market column</h2></div>
        <p className="desc" style={{ marginTop: 0 }}>
          The │ tick and Market column are the de-vigged Polymarket title outright. This is honest
          framing, <b>not a betting signal</b> — the season-long title market is efficient and our
          season sim carries no edge over it. Where the two diverge it's usually the same story we
          see per race: the model leans harder on the <b>current standings leader</b> (it
          extrapolates measured pace), while the market prices in more of the long-season unknowns
          (form swings, upgrades, reliability). The value here is the transparent, re-runnable
          forecast — the "anti-AWS" — not alpha.
        </p>
      </div>
    </div>
  );
}
