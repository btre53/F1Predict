// PIT WALL — Explainer tab. Static science + interactive sandboxes.
// TeamTyreOverlay is wired to api.teamTyres().
import { useEffect, useState } from "react";
import { api, type TeamTyres } from "../api";
import { EXPLAINER, SOURCES } from "./explainerContent";
import { TyreSandbox, TeamTyreOverlay } from "./charts/Sandboxes";

export function Explainer() {
  const [tyres, setTyres] = useState<TeamTyres | null>(null);
  useEffect(() => { api.teamTyres().then(setTyres).catch(() => {}); }, []);

  return (
    <div className="pw-stack">
      <div className="pw-intro">
        <div className="pw-chip">▮ HOW THE ENGINE THINKS</div>
        <h2>The model</h2>
        <p>Lap time = <b style={{ color: "var(--red)" }}>predictable physics</b> + a <b style={{ color: "#3b8dff" }}>learned residual</b> + <b style={{ color: "var(--amber)" }}>skewed randomness</b>. Everything downstream is bookkeeping.</p>
      </div>

      <div className="pw-grid2">
        {EXPLAINER.map((s) => (
          <div className="pw-sci" key={s.n}>
            <div className="n">{s.n}</div>
            <div>
              <div className="pw-chip">{s.tag}</div>
              <h3>{s.title}</h3>
              <div className="body">{s.body}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="pw-intro" style={{ paddingTop: 8 }}>
        <div className="pw-chip">▮ PLAY WITH THE MATHS</div>
        <h2 style={{ fontSize: 20 }}>Two live models you can poke at</h2>
      </div>

      <TyreSandbox />
      {tyres && <TeamTyreOverlay data={tyres} />}

      <div className="pw-panel">
        <div className="pw-phead"><h2>Sources</h2></div>
        <div className="pw-stack" style={{ gap: 8 }}>
          {SOURCES.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 12, fontSize: 13, color: "var(--ink-2)" }}>
              <span className="mono" style={{ color: "var(--ink-3)" }}>{String(i + 1).padStart(2, "0")}</span>{s}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
