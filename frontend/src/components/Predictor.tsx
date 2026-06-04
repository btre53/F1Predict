// PIT WALL — Predictor tab. Wired to api.circuits() + api.predict().
import { useEffect, useState } from "react";
import { api, type CircuitInfo, type NextRace, type RaceSim } from "../api";
import { ProbBar, Heatmap, pct } from "./charts/Charts";
import { TrackLoader } from "./charts/TrackLoader";

// First paint reads a committed, pre-computed default forecast from disk (api.predictDefault)
// so a visitor sees REAL standings in well under a second instead of an open-ended spinner —
// the full 10k-sim run can be a multi-second cold start. Once a circuit is chosen we run the
// live sim for it in the background and transparently swap the sharper result in.
const FULL_SIMS = 10000;
const PREDICT_TIMEOUT_MS = 15000; // hard ceiling so a stalled request can never hang the loader

// Reject a fetch if it outruns the timeout, so a slow/stalled request surfaces as an error
// (and the loader clears) rather than spinning indefinitely.
function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("request timed out — the engine is busy, retry")), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

export function Predictor() {
  const [circuits, setCircuits] = useState<CircuitInfo[]>([]);
  const [circuit, setCircuit] = useState("");
  const [next, setNext] = useState<NextRace | null>(null);
  const [sim, setSim] = useState<RaceSim | null>(null);
  const [loading, setLoading] = useState(true);    // true only until the FIRST result paints
  const [refining, setRefining] = useState(false);  // background live re-run for the chosen circuit
  const [err, setErr] = useState<string | null>(null);

  // INSTANT first paint: read the committed default-forecast snapshot from disk (no sim, no
  // cold start) so the dashboard shows a REAL result immediately rather than a spinner. The
  // circuit effect below then swaps in the live forecast for whatever circuit we land on.
  useEffect(() => {
    let cancelled = false;
    api.predictDefault()
      .then((snap) => { if (!cancelled) { setSim(snap); setLoading(false); } })
      .catch(() => { /* loader stays until the live sim below resolves */ });
    return () => { cancelled = true; };
  }, []);

  // Default to the upcoming race (from the FastF1 calendar) when we have data for it,
  // so the app opens on "the next race" instead of a stale dropdown default.
  useEffect(() => {
    api.circuits().then((list) => {
      setCircuits(list);
      api.nextRace()
        .then((nr) => {
          setNext(nr);
          const useNext = nr.available && nr.calibrated && list.some((c) => c.name === nr.circuit);
          setCircuit(useNext ? nr.circuit! : list[0]?.name ?? "");
        })
        .catch(() => { if (list.length) setCircuit(list[0].name); });
    }).catch((e) => { if (!sim) setErr(String(e)); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!circuit) return;
    let cancelled = false;
    // Don't gate the page behind this: if the instant snapshot already painted we keep it on
    // screen and refine in the background; the full-screen loader only shows if nothing exists.
    setRefining(true); setErr(null);

    // Run the live full-fidelity forecast for the chosen circuit. On timeout we clear the
    // loader with an error rather than hanging; any already-painted result stays put.
    withTimeout(api.predict(circuit, FULL_SIMS), PREDICT_TIMEOUT_MS)
      .then((full) => {
        if (cancelled) return;
        setSim(full);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        // Keep whatever's already on screen (e.g. the default snapshot); only surface an
        // error if the user is still staring at an empty loader.
        setSim((cur) => { if (!cur) setErr(String(e)); return cur; });
        setLoading(false);
      })
      .finally(() => { if (!cancelled) setRefining(false); });

    return () => { cancelled = true; };
  }, [circuit]);

  const top = sim?.outcomes.slice(0, 12) ?? [];

  return (
    <div className="pw-stack">
      <div className="pw-controls">
        <div className="pw-field">
          <span className="label">Circuit</span>
          <select className="pw-select" value={circuit} onChange={(e) => setCircuit(e.target.value)}>
            {circuits.map((c) => <option key={c.name} value={c.name}>{c.name} GP</option>)}
          </select>
          {next?.available && next.is_upcoming && (
            <button
              className="pw-badge"
              style={{ marginTop: 8, cursor: next.calibrated ? "pointer" : "default" }}
              disabled={!next.calibrated}
              onClick={() => next.circuit && setCircuit(next.circuit)}
              title={next.calibrated ? "Jump to the next race" : "Next race not calibrated yet"}
            >
              <span className="live" style={{ background: "var(--red)", boxShadow: "0 0 8px var(--red)" }} />
              NEXT: {next.circuit} GP{typeof next.days_away === "number" ? ` · ${next.days_away}d` : ""}
              {circuit === next.circuit && " ✓"}
            </button>
          )}
        </div>
        {sim && (
          <div className="pw-readouts">
            <div className="pw-readout"><div className="label">Grid</div>
              <div className="v" style={{ color: sim.post_quali ? "var(--green)" : "var(--amber)" }}>
                {sim.post_quali ? "POST-QUALI" : "PRE-QUALI"}
              </div></div>
            <div className="pw-readout"><div className="label">Simulations</div>
              <div className="v">{sim.n_sims.toLocaleString()}{refining && <span className="label" style={{ marginLeft: 6, color: "var(--amber)" }}>refining…</span>}</div></div>
            <div className="pw-readout"><div className="label">Safety car</div><div className="v">{pct(sim.sc_probability)}</div></div>
            <div className="pw-readout"><div className="label">Race laps</div><div className="v">{sim.total_laps}</div></div>
          </div>
        )}
      </div>

      {err && <div className="pw-panel" style={{ borderColor: "var(--red)", color: "var(--red-bright)" }}>{err}</div>}
      {loading && !sim && <TrackLoader label="Running the race simulation…" />}

      {sim && (
        <div className="pw-predictor-grid">
          <div className="pw-panel">
            <div className="pw-phead"><h2>Win · Podium · Points probability</h2><span className="label">N = {sim.n_sims.toLocaleString()} sims</span></div>
            {top.map((o, i) => {
              const tc = `#${o.colour}`;
              return (
                <div className="pw-driver" key={o.driver}>
                  <span className="pw-pos tnum">{o.grid_pos || i + 1}</span>
                  <span className="pw-spine" style={{ background: tc }} />
                  <div className="pw-dinfo">
                    <div className="pw-dtop">
                      <span className="pw-code">{o.driver}</span>
                      <span className="pw-team">{o.team}</span>
                      {o.number != null && <span className="pw-num">#{o.number}</span>}
                    </div>
                    <div className="pw-bars">
                      <ProbBar k="WIN" value={o.win_pct} color={tc} />
                      <ProbBar k="PODIUM" value={o.podium_pct} color={`color-mix(in srgb, ${tc} 65%, var(--track))`} />
                      <ProbBar k="POINTS" value={o.points_pct} color={`color-mix(in srgb, ${tc} 38%, var(--track))`} />
                    </div>
                  </div>
                  <span className="pw-winpct" style={{ color: tc }}>{pct(o.win_pct)}</span>
                </div>
              );
            })}
          </div>

          <div className="pw-panel">
            <div className="pw-phead"><h2>Finishing-position distribution</h2>
              <span className="desc">Rows = drivers by win probability · columns = finishing position · brighter = more likely.</span></div>
            <Heatmap rows={sim.outcomes.map((o) => ({ driver: o.driver, colour: o.colour, dist: o.finish_distribution }))} />
          </div>
        </div>
      )}
    </div>
  );
}
