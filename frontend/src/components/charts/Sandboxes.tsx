// PIT WALL — interactive Explainer sandboxes.
// TyreSandbox: pure (drag coefficients, watch the wear curve).
// TeamTyreOverlay: wired to api.teamTyres() -> TeamTyres.
import { useMemo, useState } from "react";
import type { TeamTyres } from "../../api";
import { Interactive, Slider } from "./Charts";

// Team colours aren't in the /tyres/teams payload — map them from a predict() response
// (DriverOutcome.colour) or use this fallback. Keyed by the team strings the API returns.
const TEAM_COLORS: Record<string, string> = {
  "Red Bull Racing": "#3671C6", Ferrari: "#E8002D", Mercedes: "#27F4D2", McLaren: "#FF8000",
  "Aston Martin": "#229971", Alpine: "#0093CC", Williams: "#64C4FF", RB: "#6692FF",
  "Haas F1 Team": "#B6BABD", "Kick Sauber": "#52E252",
};
const colorOf = (team: string) => TEAM_COLORS[team] ?? "#9aa0ab";
// Recognisable F1 team codes (the 2-letter initials collide — Alpine/Audi/Aston all "A").
const TEAM_CODE: Record<string, string> = {
  "Red Bull Racing": "RBR", Ferrari: "FER", Mercedes: "MER", McLaren: "MCL",
  "Aston Martin": "AST", Alpine: "ALP", Williams: "WIL", "Racing Bulls": "RB", RB: "RB",
  "Haas F1 Team": "HAA", "Kick Sauber": "SAU", Audi: "AUD", Cadillac: "CAD",
};
const shortOf = (team: string) =>
  TEAM_CODE[team] ?? team.replace(/[^A-Za-z ]/g, "").split(" ")[0].slice(0, 3).toUpperCase();

export function TyreSandbox() {
  const [warm, setWarm] = useState(0.7);
  const [wear, setWear] = useState(0.05);
  const [cliffMag, setCliffMag] = useState(1.0);
  const [cliffLap, setCliffLap] = useState(28);
  const maxAge = 45;

  const data = useMemo(() => {
    const arr: number[] = [];
    for (let age = 0; age <= maxAge; age++) {
      const warmP = warm * Math.max(0, 1 - age / 4);
      const linear = wear * age;
      const cliff = cliffMag / (1 + Math.exp(-(age - cliffLap) * 0.7));
      arr.push(+(warmP + linear + cliff).toFixed(3));
    }
    return arr;
  }, [warm, wear, cliffMag, cliffLap]);

  const optimal = Math.max(6, Math.round(cliffLap - 2));
  const cliffPenalty = data[Math.min(maxAge, cliffLap + 4)];
  const w = 560, h = 240, pl = 36, pb = 24, pt = 14, pr = 8;
  const max = Math.max(...data, 1);
  const X = (i: number) => pl + (i / maxAge) * (w - pl - pr);
  const Y = (v: number) => pt + (1 - v / max) * (h - pt - pb);
  const path = data.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const area = `${path} L${X(maxAge)},${Y(0)} L${X(0)},${Y(0)} Z`;

  return (
    <div className="pw-panel pw-toolpanel">
      <div className="pw-phead"><h2>Tyre-degradation sandbox</h2><Interactive /></div>
      <p className="desc" style={{ marginBottom: 18 }}>Drag the coefficients and watch the wear curve — find the cliff, and the stint length that beats it.</p>
      <div className="pw-sandbox">
        <div className="ctrls">
          <Slider label="Warm-up penalty" value={warm} min={0} max={1.5} step={0.05} unit="s" onChange={setWarm} />
          <Slider label="Wear rate" value={wear} min={0.01} max={0.14} step={0.01} unit=" s/lap" onChange={setWear} />
          <Slider label="Cliff magnitude" value={cliffMag} min={0} max={3} step={0.1} unit="s" onChange={setCliffMag} />
          <Slider label="Cliff lap" value={cliffLap} min={10} max={40} step={1} onChange={setCliffLap} />
          <div className="pw-readout-lg">
            <div className="it"><div className="k">Penalty at cliff</div><div className="v" style={{ color: "var(--red)" }}>+{cliffPenalty.toFixed(2)}s</div></div>
            <div className="it"><div className="k">Optimal stint</div><div className="v">{optimal} laps</div></div>
          </div>
        </div>
        <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto" }}>
          <defs><linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--red)" stopOpacity="0.22" /><stop offset="100%" stopColor="var(--red)" stopOpacity="0" />
          </linearGradient></defs>
          {[0, 0.5, 1].map((g) => { const v = g * max; return (
            <g key={g}><line x1={pl} x2={w - pr} y1={Y(v)} y2={Y(v)} stroke="var(--line-soft)" />
              <text x={pl - 6} y={Y(v) + 3} textAnchor="end" fontSize="9" fill="var(--ink-3)" fontFamily="var(--font-mono)">+{v.toFixed(1)}</text></g>); })}
          {[0, 10, 20, 30, 40].map((l) => <text key={l} x={X(l)} y={h - 7} textAnchor="middle" fontSize="9" fill="var(--ink-3)" fontFamily="var(--font-mono)">{l}</text>)}
          <line x1={X(cliffLap)} x2={X(cliffLap)} y1={pt} y2={h - pb} stroke="var(--amber)" strokeDasharray="3 3" />
          <text x={X(cliffLap)} y={pt + 9} textAnchor="middle" fontSize="9" fill="var(--amber)" fontFamily="var(--font-mono)">CLIFF</text>
          <line x1={X(optimal)} x2={X(optimal)} y1={pt} y2={h - pb} stroke="var(--green)" strokeWidth="1" opacity="0.7" />
          <path d={area} fill="url(#tg)" />
          <path d={path} fill="none" stroke="var(--red)" strokeWidth="2" />
        </svg>
      </div>
    </div>
  );
}

export function TeamTyreOverlay({ data }: { data: TeamTyres }) {
  const teams = Object.entries(data.teams).map(([team, t]) => ({ team, ...t }));
  const sorted = [...teams].sort((a, b) => a.deg_multiplier - b.deg_multiplier);
  const [on, setOn] = useState<Set<string>>(() => new Set(sorted.slice(0, 1).concat(sorted.slice(-2)).map((t) => t.team)));
  const maxAge = 45;
  const toggle = (t: string) => setOn((s) => { const n = new Set(s); n.has(t) ? n.delete(t) : n.add(t); return n; });

  const curve = (mult: number) => Array.from({ length: maxAge + 1 }, (_, age) =>
    data.field_wear_rate_s_per_lap * mult * age + (1.0 * mult) / (1 + Math.exp(-(age - 30) * 0.6)));
  const allMax = Math.max(...sorted.map((t) => Math.max(...curve(t.deg_multiplier))), 0.001);
  const maxMult = Math.max(...sorted.map((t) => t.deg_multiplier));
  const w = 560, h = 230, pl = 36, pb = 24, pt = 12, pr = 8;
  const X = (i: number) => pl + (i / maxAge) * (w - pl - pr);
  const Y = (v: number) => pt + (1 - v / allMax) * (h - pt - pb);

  return (
    <div className="pw-panel pw-toolpanel">
      <div className="pw-phead"><h2>Per-team tyre management</h2><Interactive /></div>
      <p className="desc" style={{ marginBottom: 16 }}>Calibrated from real long runs. Tap teams to overlay their degradation curves — gentle to harsh.</p>
      <div className="pw-chips" style={{ marginBottom: 16 }}>
        {sorted.map((t) => (
          <button key={t.team} className={"pw-chip-btn" + (on.has(t.team) ? "" : " off")} onClick={() => toggle(t.team)}>
            <span className="sw" style={{ background: colorOf(t.team) }} />{shortOf(t.team)}
          </button>
        ))}
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto", marginBottom: 14 }}>
        {[0, 10, 20, 30, 40].map((l) => <text key={l} x={X(l)} y={h - 7} textAnchor="middle" fontSize="9" fill="var(--ink-3)" fontFamily="var(--font-mono)">{l}</text>)}
        {[0.5, 1].map((g) => <line key={g} x1={pl} x2={w - pr} y1={Y(g * allMax)} y2={Y(g * allMax)} stroke="var(--line-soft)" />)}
        {sorted.filter((t) => on.has(t.team)).map((t) => {
          const d = curve(t.deg_multiplier).map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
          return <path key={t.team} d={d} fill="none" stroke={colorOf(t.team)} strokeWidth="2" />;
        })}
      </svg>
      <div className="label" style={{ marginBottom: 8 }}>Wear multiplier · gentle → harsh</div>
      {sorted.map((t) => (
        <div className="pw-wearbar" key={t.team}>
          <span className="nm"><span style={{ width: 3, height: 12, background: colorOf(t.team), borderRadius: 2 }} />{t.team}</span>
          <div className="bar"><span style={{ width: `${(t.deg_multiplier / maxMult) * 100}%`, background: colorOf(t.team) }} /></div>
          <span className="v">{t.deg_multiplier.toFixed(2)}×</span>
        </div>
      ))}
    </div>
  );
}
