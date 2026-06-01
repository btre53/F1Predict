import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type TeamTyres } from "../api";
import { tyreDeg } from "./TyreSandbox";

// Team colours (hex without #). Falls back to a neutral grey if unknown.
const TEAM_COLOR: Record<string, string> = {
  "Red Bull Racing": "3671C6",
  Ferrari: "E8002D",
  Mercedes: "27F4D2",
  McLaren: "FF8000",
  "Aston Martin": "229971",
  Alpine: "0093CC",
  Williams: "64C4FF",
  RB: "6692FF",
  "Kick Sauber": "52E252",
  "Haas F1 Team": "B6BABD",
  AlphaTauri: "5E8FAA",
  "Alfa Romeo": "C92D4B",
};

function colorFor(team: string): string {
  return `#${TEAM_COLOR[team] ?? "9ca3af"}`;
}

// Baseline MEDIUM-tyre shape; deg_multiplier scales only the linear wear term θ3.
const BASE_T1 = 0.7;
const BASE_T2 = 0.5;
const BASE_T3 = 0.05;
const BASE_T4 = 3.0;
const BASE_T5 = 0.5;
const BASE_T6 = 28;
const MAX_AGE = 45;

function teamCurve(mult: number): { age: number; deg: number }[] {
  const rows: { age: number; deg: number }[] = [];
  for (let age = 0; age <= MAX_AGE; age++) {
    rows.push({
      age,
      deg: tyreDeg(age, BASE_T1, BASE_T2, BASE_T3 * mult, BASE_T4, BASE_T5, BASE_T6),
    });
  }
  return rows;
}

export function TeamTyreOverlay() {
  const [data, setData] = useState<TeamTyres | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    api
      .teamTyres()
      .then((d) => {
        setData(d);
        // Default selection: the two gentlest + the harshest, for contrast.
        const ranked = Object.entries(d.teams).sort(
          (a, b) => a[1].deg_multiplier - b[1].deg_multiplier,
        );
        if (ranked.length) {
          const picks = [ranked[0][0]];
          if (ranked.length > 1) picks.push(ranked[ranked.length - 1][0]);
          if (ranked.length > 2) picks.push(ranked[1][0]);
          setSelected(picks);
        }
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  // Teams ranked gentle → harsh.
  const ranked = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.teams).sort(
      (a, b) => a[1].deg_multiplier - b[1].deg_multiplier,
    );
  }, [data]);

  // Merge the selected teams' curves into one chart dataset keyed by age.
  const chartData = useMemo(() => {
    if (!data) return [];
    const rows: Record<string, number>[] = [];
    for (let age = 0; age <= MAX_AGE; age++) rows.push({ age });
    for (const team of selected) {
      const mult = data.teams[team]?.deg_multiplier ?? 1;
      const curve = teamCurve(mult);
      for (let age = 0; age <= MAX_AGE; age++) rows[age][team] = curve[age].deg;
    }
    return rows;
  }, [data, selected]);

  const multRange = useMemo(() => {
    if (!ranked.length) return { min: 0, max: 1 };
    const vals = ranked.map(([, t]) => t.deg_multiplier);
    return { min: Math.min(...vals), max: Math.max(...vals) };
  }, [ranked]);

  function toggle(team: string) {
    setSelected((cur) =>
      cur.includes(team)
        ? cur.filter((t) => t !== team)
        : cur.length >= 3
          ? [...cur.slice(1), team]
          : [...cur, team],
    );
  }

  const unavailable = loaded && (!data || ranked.length === 0);

  return (
    <div className="rounded-xl border border-edge bg-graphite p-5">
      <div className="mb-1 flex items-baseline gap-3">
        <span className="font-mono text-xs font-bold tabular text-f1-red">03·b</span>
        <h3 className="text-base font-semibold text-zinc-100">Per-team tyre management</h3>
      </div>
      <div className="mb-4 text-[10px] uppercase tracking-wider text-zinc-500">
        calibrated from real long runs · gentle vs harsh
      </div>

      {!loaded && (
        <div className="animate-pulse text-sm text-zinc-500">Loading team curves…</div>
      )}

      {unavailable && (
        <p className="text-xs leading-relaxed text-zinc-500">
          Per-team calibration isn't available yet — run the ETL to populate
          <span className="font-mono text-zinc-400"> /api/tyres/teams</span>. The overlay
          will appear automatically once data exists.
        </p>
      )}

      {!unavailable && data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          {/* Overlay curves */}
          <div className="min-w-0">
            <div className="mb-2 text-[11px] text-zinc-500">
              Pick up to 3 teams to overlay their degradation curves.
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                <CartesianGrid stroke="#2a2a35" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="age"
                  tick={{ fill: "#71717a", fontSize: 10 }}
                  stroke="#2a2a35"
                  interval="preserveStartEnd"
                  minTickGap={24}
                  label={{
                    value: "tyre age (laps)",
                    position: "insideBottom",
                    offset: -2,
                    fill: "#52525b",
                    fontSize: 10,
                  }}
                />
                <YAxis
                  domain={[0, "dataMax + 0.5"]}
                  tick={{ fill: "#71717a", fontSize: 10 }}
                  stroke="#2a2a35"
                  width={42}
                  tickFormatter={(v) => (v as number).toFixed(1)}
                />
                <Tooltip
                  contentStyle={{
                    background: "#1c1c24",
                    border: "1px solid #2a2a35",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "#a1a1aa" }}
                  formatter={(v, name) => [`+${(v as number).toFixed(2)}s`, name as string]}
                  labelFormatter={(l) => `Age ${l as number} laps`}
                />
                {selected.map((team) => (
                  <Line
                    key={team}
                    type="monotone"
                    dataKey={team}
                    stroke={colorFor(team)}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <div className="mt-2 flex flex-wrap gap-3">
              {selected.map((team) => (
                <span key={team} className="inline-flex items-center gap-1.5 text-[11px] text-zinc-400">
                  <span className="h-2 w-2 rounded-full" style={{ background: colorFor(team) }} />
                  {team}
                </span>
              ))}
            </div>
          </div>

          {/* Ranked bar */}
          <div>
            <div className="mb-2 text-[11px] uppercase tracking-wider text-zinc-500">
              Wear multiplier · gentle → harsh
            </div>
            <div className="space-y-1.5">
              {ranked.map(([team, t]) => {
                const isOn = selected.includes(team);
                // Normalize bar length across the observed multiplier spread.
                const span = multRange.max - multRange.min || 1;
                const frac = 0.25 + 0.75 * ((t.deg_multiplier - multRange.min) / span);
                // Hue: green (gentle) → red (harsh).
                const harsh = (t.deg_multiplier - multRange.min) / span;
                const hue = Math.round(140 - 140 * harsh);
                return (
                  <button
                    key={team}
                    onClick={() => toggle(team)}
                    className={`flex w-full items-center gap-2 rounded-md border px-2 py-1 text-left transition ${
                      isOn ? "border-zinc-500 bg-slate-panel" : "border-transparent hover:bg-slate-panel/50"
                    }`}
                  >
                    <span
                      className="h-2 w-2 flex-shrink-0 rounded-full"
                      style={{ background: colorFor(team), opacity: isOn ? 1 : 0.4 }}
                    />
                    <span className="w-28 flex-shrink-0 truncate text-[11px] text-zinc-300">
                      {team}
                    </span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-carbon">
                      <span
                        className="block h-full rounded-full"
                        style={{
                          width: `${frac * 100}%`,
                          background: `hsl(${hue} 70% 50%)`,
                        }}
                      />
                    </span>
                    <span className="w-9 flex-shrink-0 text-right font-mono text-[10px] tabular text-zinc-400">
                      {t.deg_multiplier.toFixed(2)}×
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="mt-3 border-t border-edge pt-2 text-[11px] leading-relaxed text-zinc-600">
              Field wear ≈ {data.field_wear_rate_s_per_lap.toFixed(4)} s/lap. Multiplier scales
              the linear wear term θ3; below 1× is gentle on tyres, above 1× is harsh.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
