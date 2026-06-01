import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  api,
  COMPOUND_COLOR,
  type RaceRef,
  type Replay,
  type ReplayDriver,
} from "../api";

const STATUS_STYLE: Record<string, { label: string; colour: string }> = {
  GREEN: { label: "GREEN", colour: "#3bd07a" },
  YELLOW: { label: "YELLOW FLAG", colour: "#ffd23b" },
  SC: { label: "SAFETY CAR", colour: "#ff8000" },
  VSC: { label: "VIRTUAL SC", colour: "#ff8000" },
  RED: { label: "RED FLAG", colour: "#e10600" },
};

export function Explorer() {
  const [races, setRaces] = useState<RaceRef[]>([]);
  const [key, setKey] = useState<string>("");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [lap, setLap] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(450); // ms per lap
  const [err, setErr] = useState<string | null>(null);
  const lapRef = useRef(lap);
  lapRef.current = lap;

  useEffect(() => {
    api
      .replayRaces()
      .then((list) => {
        setRaces(list);
        if (list.length) setKey(`${list[0].circuit}|${list[0].year}`);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (!key) return;
    const [circuit, year] = key.split("|");
    setPlaying(false);
    setReplay(null);
    api
      .replayRace(circuit, Number(year))
      .then((r) => {
        setReplay(r);
        setLap(1);
        setPlaying(true);
      })
      .catch((e) => setErr(String(e)));
  }, [key]);

  // Wall-clock-driven playback: lap is computed from elapsed time, so even if
  // multiple timers were ever to run, they all compute the same value and the
  // pace can never exceed `speed` ms/lap. Excludes `lap` from deps on purpose
  // (start lap is captured via ref) so it isn't restarted on every tick.
  useEffect(() => {
    if (!playing || !replay) return;
    const startLap = lapRef.current;
    const t0 = Date.now();
    const id = window.setInterval(() => {
      const next = startLap + Math.floor((Date.now() - t0) / speed);
      if (next >= replay.total_laps) {
        setLap(replay.total_laps);
        setPlaying(false);
      } else if (next !== lapRef.current) {
        setLap(next);
      }
    }, 80);
    return () => window.clearInterval(id);
  }, [playing, replay, speed]);

  const driverMap: Record<string, ReplayDriver> = {};
  replay?.drivers.forEach((d) => (driverMap[d.driver] = d));
  const current = replay?.laps[lap - 1];
  const status = current ? STATUS_STYLE[current.track_status] ?? STATUS_STYLE.GREEN : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <select
          value={key}
          onChange={(e) => setKey(e.target.value)}
          className="rounded-md border border-edge bg-slate-panel px-3 py-2 text-sm outline-none focus:border-f1-red"
        >
          {races.map((r) => (
            <option key={`${r.circuit}|${r.year}`} value={`${r.circuit}|${r.year}`}>
              {r.year} {r.circuit} GP
            </option>
          ))}
        </select>

        {status && (
          <span
            className="flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-bold tracking-wide"
            style={{ background: `${status.colour}22`, color: status.colour }}
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: status.colour }}
            />
            {status.label}
          </span>
        )}

        {replay && (
          <div className="ml-auto font-mono text-sm tabular text-zinc-400">
            LAP <span className="text-lg font-bold text-white">{lap}</span>
            <span className="text-zinc-600"> / {replay.total_laps}</span>
          </div>
        )}
      </div>

      {err && (
        <div className="rounded-md border border-f1-red/40 bg-f1-red/10 px-4 py-3 text-sm text-f1-redbright">
          {err}
        </div>
      )}

      {replay && (
        <>
          {/* Transport controls */}
          <div className="flex items-center gap-3 rounded-lg border border-edge bg-graphite p-3">
            <button
              onClick={() => {
                if (lap >= replay.total_laps) setLap(1);
                setPlaying((p) => !p);
              }}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-f1-red text-white transition hover:bg-f1-redbright"
            >
              {playing ? "❚❚" : "▶"}
            </button>
            <input
              type="range"
              min={1}
              max={replay.total_laps}
              value={lap}
              onChange={(e) => {
                setPlaying(false);
                setLap(Number(e.target.value));
              }}
              className="flex-1 accent-f1-red"
            />
            <div className="flex overflow-hidden rounded-md border border-edge text-xs">
              {[
                { l: "0.5×", v: 800 },
                { l: "1×", v: 450 },
                { l: "2×", v: 200 },
              ].map((s) => (
                <button
                  key={s.v}
                  onClick={() => setSpeed(s.v)}
                  className={`px-2.5 py-1 ${
                    speed === s.v
                      ? "bg-f1-red text-white"
                      : "bg-slate-panel text-zinc-400 hover:bg-edge"
                  }`}
                >
                  {s.l}
                </button>
              ))}
            </div>
          </div>

          {/* Position tower */}
          <div className="relative rounded-xl border border-edge bg-graphite p-2">
            <div className="flex flex-col gap-1">
              {current?.order.map((slot) => {
                const d = driverMap[slot.driver];
                return (
                  <motion.div
                    key={slot.driver}
                    layout
                    transition={{ type: "spring", stiffness: 700, damping: 40 }}
                    className="flex items-center gap-3 rounded-md bg-slate-panel/60 px-3 py-1.5"
                  >
                    <span className="w-6 text-center font-mono text-sm font-bold tabular text-zinc-400">
                      {slot.position}
                    </span>
                    <span
                      className="h-5 w-1 rounded-full"
                      style={{ background: `#${d?.colour ?? "888"}` }}
                    />
                    <span className="w-12 font-semibold">{slot.driver}</span>
                    <span className="hidden w-32 text-xs text-zinc-500 sm:block">
                      {d?.team}
                    </span>
                    <span
                      className="flex items-center gap-1.5 text-[11px] tabular"
                      title={`${slot.compound} · ${slot.tyre_life} laps`}
                    >
                      <span
                        className="flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-bold"
                        style={{
                          border: `2px solid ${COMPOUND_COLOR[slot.compound] ?? "#888"}`,
                          color: COMPOUND_COLOR[slot.compound] ?? "#888",
                        }}
                      >
                        {slot.compound[0]}
                      </span>
                      <span className="text-zinc-500">{slot.tyre_life}</span>
                    </span>
                    {slot.pitting && (
                      <span className="rounded bg-f1-red/20 px-1.5 py-0.5 text-[9px] font-bold text-f1-redbright">
                        PIT
                      </span>
                    )}
                    <span className="ml-auto font-mono text-xs tabular text-zinc-400">
                      {slot.position === 1 ? "LEADER" : `+${slot.gap_s.toFixed(1)}s`}
                    </span>
                  </motion.div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
