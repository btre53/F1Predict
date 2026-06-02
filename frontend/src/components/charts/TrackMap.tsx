// PIT WALL — race-replay track map + broadcast sector timing tower.
// TrackMap dot position is a cosmetic lap-fraction animation (the Replay API has no
// x/y coordinates). SectorTower needs sector splits — the current /replay/race payload
// has none, so pass synthesized splits or wire a future /replay/sectors endpoint. See README.
import { useEffect, useRef, useState } from "react";
import { circuitPath } from "./circuits";

export function TrackMap({ phase, color, circuit, path }: { phase: number; color: string; circuit?: string; path?: string }) {
  const TRACK_D = path || circuitPath(circuit);
  const ref = useRef<SVGPathElement | null>(null);
  const [L, setL] = useState(0);
  useEffect(() => { if (ref.current) setL(ref.current.getTotalLength()); }, [TRACK_D]);
  const f = ((phase % 1) + 1) % 1;
  let car = { x: 46, y: 158 }, b1 = { x: 0, y: 0 }, b2 = { x: 0, y: 0 }, sf = { x: 46, y: 158 };
  if (ref.current && L) {
    car = ref.current.getPointAtLength(f * L);
    b1 = ref.current.getPointAtLength(0.38 * L);
    b2 = ref.current.getPointAtLength(0.70 * L);
    sf = ref.current.getPointAtLength(0);
  }
  const trailLen = (f * L).toFixed(1);
  return (
    <svg viewBox="0 0 360 180" style={{ width: "100%", height: "auto" }}>
      <path ref={ref} d={TRACK_D} fill="none" stroke="var(--track)" strokeWidth="7" strokeLinejoin="round" strokeLinecap="round" />
      <path d={TRACK_D} fill="none" stroke="var(--line)" strokeWidth="1" strokeDasharray="2 5" opacity="0.7" />
      {L > 0 && (
        <path d={TRACK_D} fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round"
          pathLength={L} strokeDasharray={`${trailLen} ${L}`} style={{ transition: "stroke-dasharray .08s linear" }} />
      )}
      {L > 0 && <g transform={`translate(${sf.x},${sf.y})`}><rect x="-1.5" y="-7" width="3" height="14" rx="1" fill="var(--ink)" /></g>}
      {L > 0 && [b1, b2].map((p, i) => (
        <g key={i}><circle cx={p.x} cy={p.y} r="2.6" fill="var(--bg)" stroke="var(--ink-3)" strokeWidth="1.4" />
          <text x={p.x} y={p.y - 7} textAnchor="middle" fontSize="8" fontFamily="var(--font-mono)" fill="var(--ink-3)">S{i + 2}</text></g>
      ))}
      <circle cx={car.x} cy={car.y} r="6" fill={color} stroke="var(--bg)" strokeWidth="2" style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
    </svg>
  );
}

export type SectorState = {
  t: [number, number, number];
  colors: ("sbest" | "pbest" | "slower")[];
  passed: number;          // sectors completed this lap (0..3)
  last: number | null;     // last lap total seconds
  best: number | null;     // best lap total seconds
};

export function SectorTower({ leader, color, sec }: { leader: string; color: string; sec: SectorState }) {
  const names = ["S1", "S2", "S3"];
  const cmap: Record<string, string> = { sbest: "#b249ff", pbest: "var(--green)", slower: "var(--ink-2)" };
  const fmt = (v: number) => v.toFixed(3);
  const fmtLap = (s: number | null) => s ? `${Math.floor(s / 60)}:${(s % 60).toFixed(3).padStart(6, "0")}` : "—:——.———";
  return (
    <div>
      <div className="pw-secthead">
        <span className="label">Leader</span>
        <span className="pw-secdrv"><span className="sp" style={{ background: color }} />{leader}</span>
      </div>
      <div className="pw-sectors">
        {names.map((nm, i) => {
          const done = i < sec.passed;
          return (
            <div className={"pw-sectorcell" + (i === sec.passed ? " live" : "")} key={nm}>
              <span className="sn">{nm}</span>
              <span className="sbar"><span style={{ width: done ? "100%" : i === sec.passed ? "45%" : "0%", background: done ? cmap[sec.colors[i]] : "var(--ink-3)" }} /></span>
              <span className="st" style={{ color: done ? cmap[sec.colors[i]] : "var(--ink-3)" }}>{done ? fmt(sec.t[i]) : i === sec.passed ? "··· " : "—.———"}</span>
            </div>
          );
        })}
      </div>
      <div className="pw-laprow">
        <div><div className="label">Last lap</div><div className="pw-laptime">{fmtLap(sec.last)}</div></div>
        <div style={{ textAlign: "right" }}><div className="label">Best lap</div><div className="pw-laptime" style={{ color: "#b249ff" }}>{fmtLap(sec.best)}</div></div>
      </div>
    </div>
  );
}
