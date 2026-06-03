// PIT WALL — F1-circuit loading animation. A stylised Grand Prix circuit draws itself in while a
// glowing car runs laps (SMIL animateMotion, so it's self-contained and GPU-cheap — no JS timer,
// no layout thrash). Used as the buffering screen for the genuinely slow loads (Monte-Carlo
// predict, season sim, the network companion fetch) so the app never shows a bare "Loading…".
const TRACK =
  "M40,150 C18,120 22,70 55,58 C92,45 96,92 132,84 C168,76 150,40 182,44 " +
  "C214,48 206,96 176,108 C150,118 138,98 104,108 C70,118 70,150 50,156 C40,159 40,150 40,150 Z";

export function TrackLoader({ label = "Running the simulation…" }: { label?: string }) {
  return (
    <div className="pw-trackloader" role="status" aria-live="polite"
      style={{ display: "flex", flexDirection: "column", alignItems: "center",
               gap: 16, padding: "40px 0" }}>
      <svg viewBox="0 0 230 200" width="260" height="190" aria-hidden="true">
        {/* asphalt */}
        <path d={TRACK} fill="none" stroke="var(--line, #2a2e36)" strokeWidth="12"
          strokeLinecap="round" strokeLinejoin="round" opacity="0.45" />
        {/* racing line drawing itself in, on a loop */}
        <path d={TRACK} fill="none" stroke="var(--red, #ff2b2b)" strokeWidth="2.5"
          strokeLinecap="round" strokeDasharray="900" strokeDashoffset="900">
          <animate attributeName="stroke-dashoffset" from="900" to="0" dur="2.4s"
            repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.25;0.9;0.25" dur="2.4s"
            repeatCount="indefinite" />
        </path>
        {/* the car — a glowing dot doing laps */}
        <circle r="7" fill="var(--red, #ff2b2b)" opacity="0.25">
          <animateMotion dur="2.2s" repeatCount="indefinite" rotate="auto" path={TRACK} />
        </circle>
        <circle r="3.4" fill="#fff">
          <animateMotion dur="2.2s" repeatCount="indefinite" rotate="auto" path={TRACK} />
        </circle>
      </svg>
      <div className="label" style={{ letterSpacing: ".12em" }}>{label}</div>
    </div>
  );
}
