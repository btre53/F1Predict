// PIT WALL — race-replay track map + broadcast sector timing tower.
// When the backend serves /replay/positions (real FastF1 GPS, see ReplayPositions), the
// map animates ALL cars as team-coloured dots at their true positions on the real outline.
// Otherwise it falls back to the cosmetic single-dot lap-fraction animation so the Explorer
// never breaks. SectorTower colouring uses real sectors when /replay/race surfaces them.
import { useEffect, useRef, useState } from "react";
import type { ReplayPositions } from "../../api";
import { circuitPath } from "./circuits";

// Linear-interp a car's [x,y] between adjacent frames at a fractional frame index.
function carAt(pts: ([number, number] | null)[], fi: number): [number, number] | null {
  if (pts.length === 0) return null;
  const i0 = Math.max(0, Math.min(pts.length - 1, Math.floor(fi)));
  const i1 = Math.min(pts.length - 1, i0 + 1);
  const a = pts[i0];
  const b = pts[i1];
  if (a && b) {
    const t = fi - i0;
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  }
  return a ?? b ?? null;
}

export function TrackMap({
  phase,
  color,
  circuit,
  path,
  positions,
  progress,
  colorOf,
  leader,
}: {
  phase: number;
  color: string;
  circuit?: string;
  path?: string;
  positions?: ReplayPositions | null;
  progress?: number;       // 0..1 race progress, drives the positional frame index
  colorOf?: (code: string) => string;
  leader?: string;
}) {
  const TRACK_D = path || circuitPath(circuit);
  const ref = useRef<SVGPathElement | null>(null);
  const [L, setL] = useState(0);
  useEffect(() => { if (ref.current) setL(ref.current.getTotalLength()); }, [TRACK_D]);
  const f = ((phase % 1) + 1) % 1;

  const multi = !!(positions && positions.n_frames > 0);
  let sf = { x: 46, y: 158 };
  let car = { x: 46, y: 158 }, b1 = { x: 0, y: 0 }, b2 = { x: 0, y: 0 };
  if (ref.current && L) {
    sf = ref.current.getPointAtLength(0);
    if (!multi) {
      car = ref.current.getPointAtLength(f * L);
      b1 = ref.current.getPointAtLength(0.38 * L);
      b2 = ref.current.getPointAtLength(0.70 * L);
    }
  }
  const trailLen = (f * L).toFixed(1);

  // Positional frame index from race progress (kept inside the cached frame range).
  const fi = multi
    ? Math.max(0, Math.min(positions!.n_frames - 1, (progress ?? 0) * (positions!.n_frames - 1)))
    : 0;
  const dots = multi
    ? Object.entries(positions!.cars)
        .map(([code, pts]) => ({ code, p: carAt(pts, fi) }))
        .filter((d): d is { code: string; p: [number, number] } => d.p != null)
    : [];

  return (
    <svg viewBox="0 0 360 180" style={{ width: "100%", height: "auto" }}>
      <path ref={ref} d={TRACK_D} fill="none" stroke="var(--track)" strokeWidth="7" strokeLinejoin="round" strokeLinecap="round" />
      <path d={TRACK_D} fill="none" stroke="var(--line)" strokeWidth="1" strokeDasharray="2 5" opacity="0.7" />
      {!multi && L > 0 && (
        <path d={TRACK_D} fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round"
          pathLength={L} strokeDasharray={`${trailLen} ${L}`} style={{ transition: "stroke-dasharray .08s linear" }} />
      )}
      {L > 0 && <g transform={`translate(${sf.x},${sf.y})`}><rect x="-1.5" y="-7" width="3" height="14" rx="1" fill="var(--ink)" /></g>}
      {!multi && L > 0 && [b1, b2].map((p, i) => (
        <g key={i}><circle cx={p.x} cy={p.y} r="2.6" fill="var(--bg)" stroke="var(--ink-3)" strokeWidth="1.4" />
          <text x={p.x} y={p.y - 7} textAnchor="middle" fontSize="8" fontFamily="var(--font-mono)" fill="var(--ink-3)">S{i + 2}</text></g>
      ))}
      {multi
        ? dots.map(({ code, p }) => {
            const c = colorOf ? colorOf(code) : color;
            const isLeader = code === leader;
            return (
              <g key={code} style={{ transition: "transform .12s linear" }} transform={`translate(${p[0]},${p[1]})`}>
                <circle r={isLeader ? 4.4 : 3.4} fill={c} stroke="var(--bg)" strokeWidth="1.4"
                  style={isLeader ? { filter: `drop-shadow(0 0 4px ${c})` } : undefined} />
              </g>
            );
          })
        : (
          <circle cx={car.x} cy={car.y} r="6" fill={color} stroke="var(--bg)" strokeWidth="2" style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
        )}
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
