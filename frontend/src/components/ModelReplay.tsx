// PIT WALL — MODEL REPLAY sandbox. Pick a past race + a model and see what it would have predicted
// using ONLY strictly-prior races (leak-free, forward-chained — the methodology made interactive),
// next to what actually happened. Shows the arc: grid+quali baseline -> production Kalman ->
// position sim -> + held-up asymmetry. Wired to /models/replay (precomputed artifact).
import { useEffect, useMemo, useState } from "react";
import { api, type ModelReplay as MR } from "../api";
import { pct } from "./charts/Charts";
import { TrackLoader } from "./charts/TrackLoader";

function WinBar({ value, accent }: { value: number; accent: string }) {
  return (
    <div className="pw-track"><div className="pw-fill" style={{ width: `${Math.max(1.5, value * 100)}%`, background: accent }} /></div>
  );
}

export function ModelReplay() {
  const [data, setData] = useState<MR | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ri, setRi] = useState(0);
  const [modelId, setModelId] = useState("kalman");

  useEffect(() => {
    api.modelReplay()
      .then((d) => { setData(d); setRi(Math.max(0, d.races.length - 1)); })
      .catch((e) => setErr(String(e)));
  }, []);

  const race = data?.races[ri];
  const model = data?.models.find((m) => m.id === modelId);
  const simMissing = !!race && !race.has_sim && (modelId === "position" || modelId === "position_heldup");

  // The selected model's top pick + whether it actually won.
  const topPick = useMemo(() => {
    if (!race) return null;
    const withP = race.drivers.filter((d) => d.models[modelId]);
    if (!withP.length) return null;
    return withP.reduce((a, b) => ((b.models[modelId]!.win > a.models[modelId]!.win) ? b : a));
  }, [race, modelId]);
  const winner = race?.drivers.find((d) => d.finish === 1) ?? null;
  const hit = topPick && winner && topPick.driver === winner.driver;
  const accent = "var(--red)";

  if (err) return <div className="pw-panel" style={{ borderColor: "var(--red)", color: "var(--red-bright)" }}>Model replay unavailable ({err}). Run <code>app.models.replay_predict</code>.</div>;
  if (!data) return <TrackLoader label="Loading model replays…" />;
  if (!race) return <div className="label">No replay races available.</div>;

  return (
    <div className="pw-stack" style={{ gap: 14 }}>
      <div className="pw-panel">
        <div className="pw-phead">
          <h2>Model Replay — what would each model have predicted?</h2>
          <span className="label">{data.n_races} races · forward-chained · leak-free</span>
        </div>
        <p className="desc" style={{ marginTop: 0 }}>
          Pick a real past race and a model. Each prediction uses <b>only races before it</b> — the
          same forward-chained, no-peeking discipline every number in this project is scored under.
          See where each model nails the result and where it doesn't.
        </p>
        <div className="pw-controls" style={{ alignItems: "flex-end", gap: 18 }}>
          <div className="pw-field">
            <span className="label">Race</span>
            <select className="pw-select" value={ri} onChange={(e) => setRi(+e.target.value)}>
              {data.races.map((r, i) => (
                <option key={r.seq} value={i}>{r.year} · {r.circuit}</option>
              ))}
            </select>
          </div>
          <div className="pw-field" style={{ flex: 1, minWidth: 280 }}>
            <span className="label">Model</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {data.models.map((m) => {
                const on = modelId === m.id;
                return (
                  <button key={m.id} className="pw-select" onClick={() => setModelId(m.id)}
                    style={{ cursor: "pointer", padding: "7px 12px", fontSize: 12, width: "auto",
                             background: on ? "var(--red)" : "var(--panel-2)",
                             color: on ? "#fff" : "var(--ink)",
                             borderColor: on ? "var(--red)" : "var(--line)" }}>
                    {m.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        {model && <p className="label" style={{ marginTop: 10, color: "var(--ink-3)" }}>{model.blurb}</p>}
      </div>

      {/* Verdict banner */}
      {topPick && winner && !simMissing && (
        <div className="pw-panel" style={{ borderColor: hit ? "var(--green)" : "var(--amber)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
            <div>
              <span className="label">Model's pick to win</span>
              <div style={{ fontSize: 18 }}><b style={{ color: accent }}>{topPick.driver}</b> at {pct(topPick.models[modelId]!.win)}</div>
            </div>
            <div>
              <span className="label">Actually won</span>
              <div style={{ fontSize: 18 }}><b>{winner.driver}</b> · started P{winner.grid ?? "—"}</div>
            </div>
            <div>
              <span className="label">Model gave the winner</span>
              <div style={{ fontSize: 18 }} className="tnum">{winner.models[modelId] ? pct(winner.models[modelId]!.win) : "—"}</div>
            </div>
            <div className="pw-badge" style={{ borderColor: hit ? "var(--green)" : "var(--amber)", color: hit ? "var(--green)" : "var(--amber)" }}>
              {hit ? "✓ TOP PICK WON" : "✗ TOP PICK MISSED"}
            </div>
          </div>
        </div>
      )}

      {simMissing && (
        <div className="pw-panel"><p className="label" style={{ margin: 0 }}>
          The position sim needs calibrated circuit data, which we don't have for {race.circuit} —
          pick another model or race.</p></div>
      )}

      {/* Full field: actual finish vs the model's prediction */}
      {!simMissing && (
        <div className="pw-panel flush">
          <div style={{ padding: "16px 18px 0" }}>
            <div className="pw-phead"><h2>{race.year} {race.circuit}</h2>
              <span className="label">actual finish vs {model?.label}</span></div>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="pw-table">
              <thead><tr><th className="num">Fin</th><th>Driver</th><th className="num">Grid</th>
                <th>Win probability</th><th className="num">Win</th><th className="num">Podium</th></tr></thead>
              <tbody>
                {race.drivers.map((d) => {
                  const p = d.models[modelId];
                  const isWinner = d.finish === 1;
                  const isPick = topPick?.driver === d.driver;
                  return (
                    <tr key={d.driver} style={isWinner ? { boxShadow: "inset 3px 0 0 var(--green)" } : isPick ? { boxShadow: "inset 3px 0 0 var(--red)" } : undefined}>
                      <td className="num tnum" style={{ fontWeight: isWinner ? 700 : 400 }}>{d.finish}</td>
                      <td><span className="pw-code">{d.driver}</span> <span className="pw-team" style={{ color: "var(--ink-3)", marginLeft: 6 }}>{d.team}</span></td>
                      <td className="num tnum" style={{ color: "var(--ink-3)" }}>{d.grid ?? "—"}</td>
                      <td style={{ minWidth: 180 }}>{p ? <WinBar value={p.win} accent={accent} /> : <span className="label">—</span>}</td>
                      <td className="num tnum" style={{ color: accent, fontWeight: 600 }}>{p ? pct(p.win) : "—"}</td>
                      <td className="num tnum" style={{ color: "var(--ink-3)" }}>{p ? pct(p.podium) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* All-models comparison on the actual winner */}
      {winner && (
        <div className="pw-panel">
          <div className="pw-phead"><h2>Who believed in the winner?</h2>
            <span className="label">each model's win% for {winner.driver}</span></div>
          <table className="pw-table">
            <tbody>
              {data.models.map((m) => {
                const wp = winner.models[m.id];
                const sel = m.id === modelId;
                return (
                  <tr key={m.id} style={sel ? { boxShadow: "inset 3px 0 0 var(--red)" } : undefined}>
                    <td style={{ width: "40%" }}>{m.label}{sel && <span className="label" style={{ marginLeft: 6, color: "var(--red)" }}>selected</span>}</td>
                    <td style={{ minWidth: 180 }}>{wp ? <WinBar value={wp.win} accent={sel ? "var(--red)" : "var(--ink-3)"} /> : <span className="label">— (no sim for this circuit)</span>}</td>
                    <td className="num tnum" style={{ fontWeight: 600 }}>{wp ? pct(wp.win) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
