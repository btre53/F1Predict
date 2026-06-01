import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Per-lap time across the race for an evaluated strategy. The shape tells the
// story: a gentle downward drift (fuel burn-off) sawtoothed by tyre deg, with
// sharp spikes on pit laps.
export function LapTimeChart({
  lapTimes,
  pitLaps,
}: {
  lapTimes: number[];
  pitLaps: number[];
}) {
  const data = lapTimes.map((t, i) => ({ lap: i + 1, time: t }));
  const pitSet = new Set(pitLaps);

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -8 }}>
        <XAxis
          dataKey="lap"
          tick={{ fill: "#71717a", fontSize: 10 }}
          stroke="#2a2a35"
          interval="preserveStartEnd"
          minTickGap={28}
        />
        <YAxis
          domain={["dataMin - 0.5", "dataMax + 0.5"]}
          tick={{ fill: "#71717a", fontSize: 10 }}
          stroke="#2a2a35"
          width={48}
          tickFormatter={(v: number) => v.toFixed(1)}
        />
        <Tooltip
          contentStyle={{
            background: "#1c1c24",
            border: "1px solid #2a2a35",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#a1a1aa" }}
          itemStyle={{ color: "#ff1e1e" }}
          formatter={(v) => [`${(v as number).toFixed(2)}s`, "Lap time"]}
          labelFormatter={(l) => {
            const lap = l as number;
            return pitSet.has(lap) ? `Lap ${lap} · PIT` : `Lap ${lap}`;
          }}
        />
        <Line
          type="monotone"
          dataKey="time"
          stroke="#e10600"
          strokeWidth={1.5}
          dot={(props: { cx?: number; cy?: number; payload?: { lap: number } }) => {
            const lap = props.payload?.lap ?? 0;
            if (!pitSet.has(lap) || props.cx == null || props.cy == null) {
              return <g key={lap} />;
            }
            return (
              <circle
                key={lap}
                cx={props.cx}
                cy={props.cy}
                r={3}
                fill="#ffd23b"
                stroke="#0a0a0d"
                strokeWidth={1}
              />
            );
          }}
          activeDot={{ r: 3, fill: "#ff1e1e" }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
