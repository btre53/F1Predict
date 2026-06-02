// PIT WALL — Strategy Lab tab.
// Wired to api.circuits(), api.optimize(), api.undercut(), api.coverOrExtend().
import { useEffect, useState } from "react";
import {
  api, type CircuitInfo, type Circuit, type StrategyResult,
  type UndercutResult, type CoverExtendResult, type Compound,
} from "../api";
import { StintBar, LineChart, Slider, DuelBar, Interactive } from "./charts/Charts";

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => { const id = setTimeout(() => setV(value), ms); return () => clearTimeout(id); }, [value, ms]);
  return v;
}

export function StrategyLab() {
  const [circuits, setCircuits] = useState<CircuitInfo[]>([]);
  const [ci, setCi] = useState<CircuitInfo | null>(null);
  const [stops, setStops] = useState(2);
  const [opts, setOpts] = useState<StrategyResult[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api.circuits().then((l) => { setCircuits(l); if (l.length) setCi(l[0]); }).catch((e) => setErr(String(e))); }, []);

  const circuit: Circuit | null = ci ? { name: ci.name, base_lap_ms: ci.base_lap_ms, total_laps: ci.total_laps } : null;

  useEffect(() => {
    if (!circuit || !ci) return;
    api.optimize(circuit, stops, 6, ci.name).then(setOpts).catch((e) => setErr(String(e)));
  }, [ci, stops]);

  // --- Undercut (debounced server call) ---
  const [gap, setGap] = useState(1.5);
  const [defAge, setDefAge] = useState(22);
  const dGap = useDebounced(gap), dDef = useDebounced(defAge);
  const [uc, setUc] = useState<UndercutResult | null>(null);
  useEffect(() => {
    if (!circuit) return;
    api.undercut({
      gap_s: dGap, attacker_compound: "SOFT" as Compound, attacker_tyre_age: 1,
      defender_compound: "HARD" as Compound, defender_tyre_age: dDef,
      pit_lap: Math.round((ci?.total_laps ?? 57) / 2), circuit,
    }).then(setUc).catch(() => {});
  }, [dGap, dDef, ci]);

  // --- Cover vs extend (debounced server call) ---
  const [cgap, setCgap] = useState(1.2);
  const [lapsRem, setLapsRem] = useState(23);
  const [leaderAge, setLeaderAge] = useState(18);
  const dC = useDebounced(cgap), dL = useDebounced(lapsRem), dA = useDebounced(leaderAge);
  const [ce, setCe] = useState<CoverExtendResult | null>(null);
  useEffect(() => {
    if (!ci) return;
    api.coverOrExtend({
      circuit_name: ci.name, gap_to_follower_s: dC, laps_remaining: dL,
      leader_tyre_age: dA, leader_compound: "MEDIUM" as Compound,
    }).then(setCe).catch(() => {});
  }, [dC, dL, dA, ci]);

  const best = opts[0];

  return (
    <div className="pw-stack">
      <div className="pw-controls">
        <div className="pw-field"><span className="label">Circuit</span>
          <select className="pw-select" value={ci?.name ?? ""} onChange={(e) => setCi(circuits.find((c) => c.name === e.target.value) ?? null)}>
            {circuits.map((c) => <option key={c.name} value={c.name}>{c.name} GP</option>)}
          </select></div>
        <div className="pw-field"><span className="label">Max stops</span>
          <div className="pw-seg">{[1, 2, 3].map((n) => <button key={n} className={stops === n ? "on" : ""} onClick={() => setStops(n)}>{n}</button>)}</div></div>
        {ci && <div className="pw-readouts" style={{ alignItems: "flex-end" }}>
          <div className="pw-readout"><div className="label">{ci.total_laps} laps</div>
            {ci.calibrated && <div className="pw-badge" style={{ marginTop: 6 }}><span className="live" />Calibrated from real data</div>}</div>
        </div>}
      </div>

      {err && <div className="pw-panel" style={{ borderColor: "var(--red)", color: "var(--red-bright)" }}>{err}</div>}

      <div className="pw-panel">
        <div className="pw-phead"><h2>Optimal strategies</h2><span className="label">Sorted by total race time</span></div>
        <div className="pw-stack">
          {opts.map((o, i) => (
            <div key={i} className={"pw-optrow" + (i === 0 ? " best" : "")}>
              <div className="pw-optnum">{i + 1}</div>
              <div>
                <div className="pw-optmeta">
                  <span><b className="mono">{o.n_stops}-stop</b> <span className="pw-team mono">pit {o.pit_laps.join(", ")}</span></span>
                  <span style={{ textAlign: "right" }}>
                    <span className={"delta" + (i === 0 ? " best" : "")}>{i === 0 ? "OPTIMAL" : `+${o.delta_to_best_s.toFixed(1)}s`}</span><br />
                    <span className="avg">avg {o.avg_lap_s.toFixed(1)}s/lap</span>
                  </span>
                </div>
                <StintBar compounds={o.compounds} lengths={o.stint_lengths} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {best?.lap_times_s && (
        <div className="pw-panel">
          <div className="pw-phead"><h2>Lap-time profile</h2><span className="desc">Drift down = fuel burn-off · saw-tooth = tyre deg · dashed = pit stops.</span></div>
          <LineChart data={best.lap_times_s} pits={best.pit_laps} />
        </div>
      )}

      <div className="pw-grid2">
        <div className="pw-panel pw-toolpanel">
          <div className="pw-phead"><h2>Undercut calculator</h2><Interactive /></div>
          <p className="desc" style={{ marginBottom: 18 }}>Attacker pits onto fresh softs; defender stays out on worn hards. Does the fresh-tyre advantage clear the gap?</p>
          <div className="pw-stack" style={{ gap: 22 }}>
            <Slider label="Gap to rival" value={gap} min={0} max={4} step={0.1} unit="s" onChange={setGap} />
            <Slider label="Defender tyre age" value={defAge} min={5} max={40} unit=" laps" onChange={setDefAge} />
            {uc && <DuelBar aLabel="Gap to clear" a={+gap.toFixed(1)} bLabel="Fresh-tyre gain" b={+uc.fresh_tyre_gain_s.toFixed(2)} />}
            {uc && (
              <div className="pw-verdict" style={{ borderColor: uc.undercut_works ? "var(--green)" : "var(--line)" }}>
                <h3 style={{ color: uc.undercut_works ? "var(--green)" : "var(--ink-2)" }}>{uc.undercut_works ? "UNDERCUT WORKS" : "STAY OUT"}</h3>
                <div className="pw-vrow"><span>Fresh-tyre gain</span><span className="v">{uc.fresh_tyre_gain_s.toFixed(2)}s</span></div>
                <div className="pw-vrow"><span>Projected gap after</span><span className="v">{uc.projected_gap_after_s.toFixed(2)}s</span></div>
                {uc.notes[0] && <div className="pw-vnote">{uc.notes[0]}</div>}
              </div>
            )}
          </div>
        </div>

        <div className="pw-panel pw-toolpanel">
          <div className="pw-phead"><h2>Cover vs extend</h2><Interactive /></div>
          <p className="desc" style={{ marginBottom: 18 }}>Leader's Stackelberg call: react to the follower's undercut now, or extend for a fresher final stint.</p>
          <div className="pw-stack" style={{ gap: 18 }}>
            <Slider label="Gap to follower" value={cgap} min={0} max={4} step={0.1} unit="s" onChange={setCgap} />
            <Slider label="Laps remaining" value={lapsRem} min={5} max={40} onChange={setLapsRem} />
            <Slider label="Leader tyre age" value={leaderAge} min={5} max={35} unit=" laps" onChange={setLeaderAge} />
            {ce && (
              <div className="pw-verdict" style={{ borderColor: ce.recommendation === "EXTEND" ? "#3b8dff" : "var(--amber)" }}>
                <h3 style={{ color: ce.recommendation === "EXTEND" ? "#3b8dff" : "var(--amber)" }}>{ce.recommendation}</h3>
                <div className="pw-vrow"><span>Cover value</span><span className="v">{ce.cover_value_s.toFixed(2)}s</span></div>
                <div className="pw-vrow"><span>Extend value</span><span className="v">{ce.extend_value_s.toFixed(2)}s</span></div>
                {ce.rationale && <div className="pw-vnote">{ce.rationale}</div>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
