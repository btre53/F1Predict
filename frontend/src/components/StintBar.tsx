import { COMPOUND_COLOR } from "../api";

// Horizontal tyre-strategy timeline: one coloured segment per stint, with pit
// markers between them. Mirrors a broadcast strategy graphic.
export function StintBar({
  compounds,
  lengths,
  totalLaps,
}: {
  compounds: string[];
  lengths: number[];
  totalLaps: number;
}) {
  let cum = 0;
  return (
    <div className="flex h-7 w-full overflow-hidden rounded-md ring-1 ring-edge">
      {compounds.map((c, i) => {
        const w = (lengths[i] / totalLaps) * 100;
        cum += lengths[i];
        const showPit = i < compounds.length - 1;
        return (
          <div
            key={i}
            className="relative flex items-center justify-center border-r border-carbon/60 text-[10px] font-semibold tabular"
            style={{
              width: `${w}%`,
              background: `linear-gradient(180deg, ${COMPOUND_COLOR[c]}, ${COMPOUND_COLOR[c]}cc)`,
              color: c === "MEDIUM" || c === "HARD" ? "#0a0a0d" : "#fff",
            }}
            title={`${c} — ${lengths[i]} laps`}
          >
            {lengths[i]}
            {showPit && (
              <span className="absolute -right-[1px] top-0 h-full w-[2px] bg-carbon" />
            )}
            {showPit && (
              <span className="absolute -right-2 -top-4 text-[9px] text-zinc-500">
                L{cum}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
