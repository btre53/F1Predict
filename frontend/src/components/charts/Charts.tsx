// PIT WALL — typed presentational chart primitives.
// Pure components: no API calls. Probabilities are 0..1 floats (as the API returns).

export const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#FF3B3B", MEDIUM: "#FFD23B", HARD: "#E8E8EE", INTERMEDIATE: "#3BD07A", WET: "#3B8DFF",
};
export const COMPOUND_LABEL: Record<string, string> = {
  SOFT: "S", MEDIUM: "M", HARD: "H", INTERMEDIATE: "I", WET: "W",
};

export const pct = (x: number): string =>
  x >= 0.995 ? "100%" : x < 0.01 ? "<1%" : `${Math.round(x * 100)}%`;

export function ProbBar({ k, value, color }: { k: string; value: number; color: string }) {
  return (
    <div className="pw-barrow">
      <span className="k">{k}</span>
      <div className="pw-track"><div className="pw-fill" style={{ width: `${Math.max(2, value * 100)}%`, background: color }} /></div>
      <span className="pct tnum">{pct(value)}</span>
    </div>
  );
}

export function StintBar({ compounds, lengths }: { compounds: string[]; lengths: number[] }) {
  return (
    <div className="pw-stintbar">
      {lengths.map((n, i) => (
        <div key={i} className="pw-stint" title={`${compounds[i]} · ${n} laps`}
          style={{ flex: n, background: COMPOUND_COLOR[compounds[i]] ?? "#888" }}>{n}</div>
      ))}
    </div>
  );
}

export function DuelBar({ aLabel, a, bLabel, b, unit = "s", caption }: {
  aLabel: string; a: number; bLabel: string; b: number; unit?: string; caption?: string;
}) {
  const m = Math.max(a, b, 1) * 1.1;
  const net = +(b - a).toFixed(2);
  return (
    <div className="pw-duel">
      <div className="pw-duelrow"><span className="k">{aLabel}</span>
        <div className="bar"><span style={{ width: `${(a / m) * 100}%`, background: "var(--ink-3)" }} /></div>
        <span className="v">{a}{unit}</span></div>
      <div className="pw-duelrow"><span className="k">{bLabel}</span>
        <div className="bar"><span style={{ width: `${(b / m) * 100}%`, background: net >= 0 ? "var(--green)" : "var(--red)" }} /></div>
        <span className="v">{b}{unit}</span></div>
      {caption && <div className="label" style={{ fontSize: 10, marginTop: 6, color: "var(--ink-3)" }}>{caption}</div>}
    </div>
  );
}

export function Slider({ label, value, min, max, step = 1, unit = "", onChange }: {
  label: string; value: number; min: number; max: number; step?: number; unit?: string; onChange: (v: number) => void;
}) {
  return (
    <div className="pw-slider">
      <div className="top"><span className="label">{label}</span><span className="v tnum">{value}{unit}</span></div>
      <input type="range" className="pw-range" min={min} max={max} step={step}
        value={value} onChange={(e) => onChange(+e.target.value)} />
    </div>
  );
}

export function Interactive() {
  return <span className="pw-interactive"><span className="pulse" />Interactive</span>;
}

// SVG line chart for a lap-time / value series.
export function LineChart({ data, height = 200, pits = [], color = "var(--red)" }: {
  data: number[]; height?: number; pits?: number[]; color?: string;
}) {
  if (!data.length) return null;
  const w = 620, h = height, pl = 38, pb = 22, pt = 12, pr = 8;
  const min = Math.min(...data), max = Math.max(...data);
  const x = (i: number) => pl + (i / (data.length - 1)) * (w - pl - pr);
  const y = (v: number) => pt + (1 - (v - min) / (max - min || 1)) * (h - pt - pb);
  const path = data.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto" }}>
      {[min, (min + max) / 2, max].map((tk, i) => (
        <g key={i}>
          <line x1={pl} x2={w - pr} y1={y(tk)} y2={y(tk)} stroke="var(--line-soft)" />
          <text x={pl - 6} y={y(tk) + 3} textAnchor="end" fontSize="9" fill="var(--ink-3)" fontFamily="var(--font-mono)">{tk.toFixed(1)}</text>
        </g>
      ))}
      {pits.map((p, i) => <line key={i} x1={x(p - 1)} x2={x(p - 1)} y1={pt} y2={h - pb} stroke="var(--amber)" strokeWidth="1" strokeDasharray="3 3" opacity="0.6" />)}
      <path d={path} fill="none" stroke={color} strokeWidth="1.8" />
    </svg>
  );
}

// Calibration scatter — points are {predicted, observed} in 0..1.
export function Calibration({ points, height = 220 }: { points: { predicted: number; observed: number }[]; height?: number }) {
  const w = 280, h = height, p = 28;
  const X = (v: number) => p + v * (w - p * 1.4);
  const Y = (v: number) => h - p - v * (h - p * 1.6);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", maxWidth: 320 }}>
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}>
          <line x1={X(g)} x2={X(g)} y1={Y(0)} y2={Y(1)} stroke="var(--line-soft)" />
          <line x1={X(0)} x2={X(1)} y1={Y(g)} y2={Y(g)} stroke="var(--line-soft)" />
          <text x={X(g)} y={Y(0) + 12} textAnchor="middle" fontSize="8" fill="var(--ink-3)" fontFamily="var(--font-mono)">{g}</text>
        </g>
      ))}
      <line x1={X(0)} y1={Y(0)} x2={X(1)} y2={Y(1)} stroke="var(--ink-3)" strokeDasharray="4 4" />
      {points.map((pt, i) => <circle key={i} cx={X(pt.predicted)} cy={Y(pt.observed)} r="4.5" fill="var(--red)" opacity="0.85" />)}
    </svg>
  );
}

// Finishing-position heatmap. rows: [{ driver, colour(hex no #), dist[] }]
export function Heatmap({ rows }: { rows: { driver: string; colour: string; dist: number[] }[] }) {
  const n = rows.length;
  return (
    <div className="pw-heat">
      <div className="pw-heatgrid" style={{ gridTemplateColumns: `44px repeat(${n}, 1fr)` }}>
        <div />
        {Array.from({ length: n }, (_, j) => <div key={j} className="pw-heatlabel">{j + 1}</div>)}
        {rows.map((r, i) => {
          const tc = `#${r.colour}`;
          const max = Math.max(...r.dist, 0.0001);
          return (
            <div key={i} style={{ display: "contents" }}>
              <div className="pw-heatrowlab"><span style={{ width: 3, height: 12, background: tc, borderRadius: 2 }} />{r.driver}</div>
              {r.dist.map((v, j) => (
                <div key={j} className="pw-heatcell"
                  title={`${r.driver} · P${j + 1} · ${(v * 100).toFixed(1)}%`}
                  style={{ background: `color-mix(in srgb, ${tc} ${Math.pow(v / max, 0.6) * 100}%, var(--track))` }} />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
