// PIT WALL — Predictor tab. Wired to api.circuits() + api.predict().
import { useEffect, useState } from "react";
import { api, type CircuitInfo, type NextRace, type RaceSim } from "../api";
import { ProbBar, Heatmap, pct } from "./charts/Charts";
import { TrackLoader } from "./charts/TrackLoader";

// First paint runs a fast, lower-fidelity pass so a visitor sees real standings in ~1-2s
// instead of an open-ended spinner; we then transparently upscale to the full-fidelity run.
const FAST_SIMS = 2000;     // backend floor is 1000 (ge=1000); 2000 is quick + already stable
const FULL_SIMS = 10000;
const FAST_TIMEOUT_MS = 9000; // hard ceiling so the loader can never hang forever

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
  const [loading, setLoading] = useState(false);   // true only until the FIRST result paints
  const [refining, setRefining] = useState(false);  // background upscale to full fidelity
  const [err, setErr] = useState<string | null>(null);

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
    }).catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (!circuit) return;
    let cancelled = false;
    setLoading(true); setRefining(false); setErr(null);

    // 1) Fast pass: real standings on screen ASAP. On timeout the loader clears with an error
    //    rather than hanging. 2) Then quietly re-run at full fidelity and swap the result in.
    withTimeout(api.predict(circuit, FAST_SIMS), FAST_TIMEOUT_MS)
      .then((fast) => {
        if (cancelled) return;
        setSim(fast);
        setLoading(false);
        setRefining(true);
        api.predict(circuit, FULL_SIMS)
          .then((full) => { if (!cancelled) setSim(full); })
          .catch(() => { /* keep the fast result if the full run fails */ })
          .finally(() => { if (!cancelled) setRefining(false); });
      })
      .catch((e) => {
        if (cancelled) return;
        setErr(String(e));
        setLoading(false);
      });

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
