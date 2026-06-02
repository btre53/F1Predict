// PIT WALL — Explorer tab. Wired to api.replayRaces() + api.replayRace().
// Leaderboard, compounds, tyre life and gaps come from the real Replay payload.
// Sector times are DERIVED from gap_s (see charts/deriveSectors.ts) — the payload has
// no sector splits. Track-map dot position is a cosmetic lap-fraction animation
// (Replay has no x/y); swap in OpenF1 /location coords for a true position map.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type RaceRef, type Replay } from "../api";
import { COMPOUND_COLOR } from "./charts/Charts";
import { TrackMap, SectorTower } from "./charts/TrackMap";
import { deriveSectorTable, type SectorTableEntry } from "./charts/deriveSectors";

const DEFAULT_BASE_LAP_S = 92; // fallback if the circuit isn't in /circuits

export function Explorer() {
  const [races, setRaces] = useState<RaceRef[]>([]);
  const [sel, setSel] = useState<RaceRef | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [baseLapS, setBaseLapS] = useState(DEFAULT_BASE_LAP_S);
  const [lapIdx, setLapIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [phase, setPhase] = useState(0);
  const [trackPath, setTrackPath] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const phaseRef = useRef(0), floorRef = useRef(0);

  // Load race list + circuit base lap times (for the physics anchor).
  const baseLaps = useRef<Record<string, number>>({});
  useEffect(() => {
    api.replayRaces().then((rs) => { setRaces(rs); if (rs.length) setSel(rs[0]); }).catch((e) => setErr(String(e)));
    api.circuits().then((cs) => { cs.forEach((c) => { baseLaps.current[c.name] = c.base_lap_ms / 1000; }); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!sel) return;
    setErr(null); reset();
    setBaseLapS(baseLaps.current[sel.circuit] ?? DEFAULT_BASE_LAP_S);
    api.replayRace(sel.circuit, sel.year).then(setReplay).catch((e) => setErr(String(e)));
    // Real FastF1 track outline if the /replay/track endpoint exists; else stylized fallback.
    setTrackPath(null);
    fetch(`/api/replay/track?circuit=${encodeURIComponent(sel.circuit)}&year=${sel.year}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setTrackPath(d?.path ?? null))
      .catch(() => {});
  }, [sel]);

  // Derive the full sector table once per replay load.
  const table: SectorTableEntry[] = useMemo(
    () => (replay ? deriveSectorTable(replay, baseLapS) : []),
    [replay, baseLapS]);

  useEffect(() => {
    if (!playing || !replay) return;
    let prev = performance.now();
    const speed = 0.4;
    const id = setInterval(() => {
      const now = performance.now();
      const dt = Math.min(0.5, (now - prev) / 1000); prev = now;
      phaseRef.current += dt * speed;
      const fl = Math.floor(phaseRef.current);
      if (fl !== floorRef.current) {
        floorRef.current = fl;
        setLapIdx((l) => { const nl = l + 1; if (nl >= replay.laps.length - 1) setPlaying(false); return Math.min(replay.laps.length - 1, nl); });
      }
      setPhase(phaseRef.current);
    }, 16);
    return () => clearInterval(id);
  }, [playing, replay]);

  const reset = () => { setPlaying(false); phaseRef.current = 0; floorRef.current = 0; setPhase(0); setLapIdx(0); };

  const colorOf = useMemo(() => {
    const m: Record<string, string> = {};
    replay?.drivers.forEach((d) => { m[d.driver] = `#${d.colour}`; });
    return (code: string) => m[code] ?? "#9aa0ab";
  }, [replay]);

  const lap = replay?.laps[lapIdx];
  const order = lap ? [...lap.order].sort((a, b) => a.position - b.position) : [];
  const leader = order[0]?.driver ?? "—";
  const f = ((phase % 1) + 1) % 1;
  const passed = f >= 0.70 ? 2 : f >= 0.38 ? 1 : 0;
  const sec = table[lapIdx];
  const status = lap?.track_status ?? "GREEN";

  return (
    <div className="pw-stack">
      <div className="pw-controls">
        <div className="pw-field"><span className="label">Race</span>
          <select className="pw-select" value={sel ? `${sel.year}|${sel.circuit}` : ""}
            onChange={(e) => { const [y, c] = e.target.value.split("|"); setSel(races.find((r) => r.year === +y && r.circuit === c) ?? null); }}>
            {races.map((r) => <option key={`${r.year}|${r.circuit}`} value={`${r.year}|${r.circuit}`}>{r.year} {r.circuit} GP</option>)}
          </select></div>
        <div className="pw-readouts">
          <div className="pw-readout"><div className="label">Lap</div><div className="v">{lapIdx + 1} / {replay?.total_laps ?? "—"}</div></div>
          <div className="pw-readout"><div className="label">Status</div><div className="v" style={{ color: status === "GREEN" ? "var(--green)" : "var(--amber)" }}>{status}</div></div>
        </div>
      </div>

      {err && <div className="pw-panel" style={{ borderColor: "var(--red)", color: "var(--red-bright)" }}>{err}</div>}

      {replay && sec && (
        <div className="pw-panel pw-toolpanel">
          <div className="pw-phead">
            <h2>Race replay · {replay.circuit} {replay.year}</h2>
            <div style={{ display: "flex", gap: 8 }}>
              <div className="pw-nav" style={{ display: "flex" }}>
                <button className="active" onClick={() => setPlaying((p) => !p)} style={{ minWidth: 88 }}>
                  <span className="dot" style={{ background: playing ? "var(--amber)" : "var(--green)" }} />{playing ? "PAUSE" : "PLAY"}
                </button>
              </div>
              <div className="pw-nav"><button onClick={reset}>RESET</button></div>
            </div>
          </div>

          <div className="pw-explorer-top">
            <div className="pw-trackmap">
              <div className="label" style={{ marginBottom: 8 }}>{replay.circuit} circuit</div>
              <TrackMap phase={phase} color={colorOf(leader)} circuit={replay.circuit} path={trackPath ?? undefined} />
            </div>
            <SectorTower leader={leader} color={colorOf(leader)} sec={{ ...sec, passed }} />
          </div>
          <div className="label" style={{ marginBottom: 4 }}>Sectors derived from gap_s deltas · physics-anchored lap time · purple = session best</div>

          <input type="range" className="pw-range" style={{ width: "100%", margin: "16px 0 20px" }}
            min={0} max={Math.max(0, replay.laps.length - 1)} value={lapIdx} onChange={(e) => setLapIdx(+e.target.value)} />

          <div className="pw-stack" style={{ gap: 4 }}>
            {order.map((s) => (
              <div key={s.driver} style={{ display: "grid", gridTemplateColumns: "26px 4px 64px 1fr 64px", gap: 12, alignItems: "center", padding: "9px 0", borderBottom: "1px solid var(--line-soft)", transition: "all .35s" }}>
                <span className="pw-pos tnum">{s.position}</span>
                <span style={{ width: 4, height: 22, background: colorOf(s.driver), borderRadius: 2 }} />
                <span className="pw-code">{s.driver}{s.pitting && <span className="mono" style={{ fontSize: 9, color: "var(--amber)", marginLeft: 5 }}>PIT</span>}</span>
                <div className="pw-track" style={{ maxWidth: 220 }}>
                  <div className="pw-fill" style={{ width: `${Math.max(3, 100 - s.tyre_life * 2.2)}%`, background: COMPOUND_COLOR[s.compound] ?? "#888" }} />
                </div>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)", textAlign: "right" }}>
                  {s.position === 1 ? "LEADER" : `+${s.gap_s.toFixed(1)}s`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
