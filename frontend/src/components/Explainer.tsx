import { useState } from "react";
import { LapTimeBuilder } from "./LapTimeBuilder";
import { TeamTyreOverlay } from "./TeamTyreOverlay";
import { TyreSandbox } from "./TyreSandbox";

// ---------------------------------------------------------------------------
// Curated, self-contained explainer content. Sourced from docs/science/*.
// Each section pairs a plain-English blurb (the prominent part) with an
// optional "the math / the numbers" drill-down (equation + small param table).
// ---------------------------------------------------------------------------

type Param = { label: string; value: string; unit?: string };

type Section = {
  id: string;
  index: string;
  title: string;
  tag?: string;
  blurb: string;
  equation?: string;
  params?: Param[];
  note?: string;
};

const COMPOUND = {
  SOFT: "#ff3b3b",
  MEDIUM: "#ffd23b",
  HARD: "#e8e8ee",
} as const;

const SECTIONS: Section[] = [
  {
    id: "decomposition",
    index: "01",
    title: "How a lap time is built",
    tag: "physics + ML + noise",
    blurb:
      "A car's lap time is mostly predictable physics: heavy fuel and worn tyres make it slower in known ways. We model those directly, let a statistical layer learn the leftover patterns, then treat whatever remains as random execution noise. Stripping out the predictable parts is what lets us compare a driver's true pace fairly.",
    equation: "t_lap(driver d, lap k)  =  f_physics(state)  +  g_ML(features)  +  ε",
    params: [
      { label: "f_physics", value: "fuel mass, tyre trend, base pace" },
      { label: "g_ML", value: "LightGBM residual learner" },
      { label: "ε", value: "skewed execution noise" },
    ],
    note: "The physics-baseline + stochastic-noise split is the backbone of every published F1 simulator (Heilmeier / TUM). Inserting a learned residual between them is a gray-box / residual-learning pattern.",
  },
  {
    id: "fuel",
    index: "02",
    title: "Fuel-corrected pace",
    tag: "lighter = faster",
    blurb:
      "An F1 car starts a race carrying up to ~100 kg of fuel and burns it off, getting lighter and faster — worth roughly 0.03 seconds per lap per kilogram. To compare true pace fairly we fuel-correct lap times by adding back what the heavy fuel cost, revealing how the tyres are actually wearing.",
    equation:
      "fuel_mass(lap) ≈ fuel_start − burn_per_lap × lap\nt_corrected   = t_observed − k_fuel × fuel_mass(lap)",
    params: [
      { label: "Fuel sensitivity k_fuel", value: "0.030 (0.025–0.040)", unit: "s/kg" },
      { label: "Max race fuel", value: "110 (~70 in 2026)", unit: "kg" },
      { label: "Fuel burn per lap", value: "~1.6–1.8", unit: "kg/lap" },
      { label: "Total start penalty", value: "~3.0–3.3", unit: "s/lap" },
    ],
    note: "Correction: base lap, burn rate and k_fuel are fine as averages but should be circuit-specific (Spa burns far more than the Red Bull Ring).",
  },
  {
    id: "tyres",
    index: "03",
    title: "Three-phase tyre degradation",
    tag: "warm-up → linear → cliff",
    blurb:
      "New tyres start slightly slow until they heat into their grip window, then lose time steadily as they wear — about 0.05 s/lap for a hard — until they hit a cliff and fall apart over a couple of laps. Softer tyres are faster but cliff sooner; hotter tracks speed up the decline. We learn each tyre's wear curve from practice long runs.",
    equation:
      "t_deg(age) =  θ1·exp(−θ2·age)              # warm-up, decays away\n           +  θ3·age                        # linear wear\n           +  θ4 / (1 + exp(−θ5·(age−θ6)))  # logistic cliff",
    params: [
      { label: "Soft deg rate", value: "0.08–0.15+", unit: "s/lap" },
      { label: "Medium deg rate", value: "0.05–0.06", unit: "s/lap" },
      { label: "Hard deg rate (θ3)", value: "~0.05", unit: "s/lap" },
      { label: "Soft vs Hard pace", value: "~0.6–1.0", unit: "s/lap" },
      { label: "Optimal slick temp", value: "~90–110", unit: "°C" },
    ],
    note: "Correction: the 6-parameter form is over-parameterized — clean long-runs rarely reach the cliff, so θ4–θ6 are weakly identified. Fit with priors / bounds and fall back to linear when data is sparse.",
  },
  {
    id: "noise",
    index: "04",
    title: "Why driver noise is skewed",
    tag: "you can only lose time",
    blurb:
      "Drivers make mistakes, but the mistakes are lopsided — you can lose a second locking up a brake, but you can't gain a second over a perfect lap. So we add randomness that's positively skewed: small losses common, occasional big ones, almost never a freakishly fast lap.",
    equation: "ε ~ skewed-t(positive skew, df ≈ 2)   # short left tail, long slow tail",
    params: [
      { label: "Per-lap σ (clean)", value: "0.20–0.35", unit: "s" },
      { label: "Distribution", value: "skewed-t (df ≈ 2)" },
      { label: "Inflate in traffic / wet", value: "yes" },
    ],
    note: "Correction: the original spec used symmetric Gaussian noise, which overstates freakishly-fast laps. The skewed-t beats it empirically (CRPS 0.202 vs 0.324; RMSPE 1.082 vs 1.520).",
  },
  {
    id: "montecarlo",
    index: "05",
    title: "Monte Carlo race simulation",
    tag: "10,000 races, not one",
    blurb:
      "We don't predict a single race — we simulate it thousands of times, each with different tyre luck, mistakes, and safety cars drawn from their real distributions. Counting how often each driver wins, podiums, or scores points turns physics into honest probabilities, complete with uncertainty bands.",
    equation: "P(win_d) = (# sims where d finishes 1st) / N_sims      # N ≈ 10,000",
    params: [
      { label: "Iterations", value: "~10,000", unit: "sims" },
      { label: "Per-lap draws", value: "noise + events", unit: "" },
      { label: "Outputs", value: "win / podium / points + finish distribution" },
    ],
    note: "We score the probabilities themselves with proper scoring rules (Brier, log-loss, CRPS) on held-out past races — so something we call 30% likely happens about 30% of the time.",
  },
  {
    id: "pitstops",
    index: "06",
    title: "Pit stops, undercut & overcut",
    tag: "the ~20-second gamble",
    blurb:
      "Your total race time is just the sum of every lap plus a fixed ~20-second penalty each time you pit. An undercut means pitting a lap earlier than the car ahead: your fresh tyres are ~1–2 s/lap faster, so you bank time and leapfrog them when they finally stop. An overcut is the opposite — stay out while your warm tyres beat their cold ones. Undercuts win on high-wear tracks; overcuts win when tyres last.",
    equation:
      "T_race = Σ t_lap + Σ_stops (standstill + drive_in + drive_out)\nundercut works when:  Σ(fresh-tyre advantage)  >  gap_to_car_ahead",
    params: [
      { label: "Green pit loss (total)", value: "18–25", unit: "s" },
      { label: "Standstill change", value: "1.9–2.5 (+team)", unit: "s" },
      { label: "Fresh-tyre out-lap gain", value: "1.0–2.0", unit: "s/lap" },
      { label: "Required overtake gap", value: "~1.5–2.5", unit: "s" },
    ],
    note: "Correction: pit loss is not one constant — decompose it (standstill + in-lap + out-lap). TUM Catalunya 2019: ≈ 1.9 + 3.04 + 16.0 ⇒ ~21 s green.",
  },
  {
    id: "stackelberg",
    index: "07",
    title: "Stackelberg: cover vs extend",
    tag: "a leader-follower chess match",
    blurb:
      "When two cars fight on strategy it's a chess match: the leader must decide whether to cover by pitting the moment the chaser does, or gamble on staying out for fresher tyres later. We model this as a leader-follower (Stackelberg) game solved backwards from the finish — how real strategists actually think.",
    equation: "V(lap, state) = min_action { stage_cost(action) + V(lap+1, next_state) }",
    params: [
      { label: "Win probability", value: "+>15%", unit: "" },
      { label: "Avg race-time gain", value: "~2.3", unit: "s" },
      { label: "P(being undercut)", value: "−17.8%", unit: "" },
    ],
    note: "Correction: the original Nash-equilibrium / mixed-strategy framing is mislabeled. Pit moves are observed in real time — you see the rival enter the pit lane — so the leader genuinely moves first. (Aguad & Thraves, EJOR 2024.)",
  },
  {
    id: "safetycar",
    index: "08",
    title: "Safety-car modelling",
    tag: "random, but predictable in aggregate",
    blurb:
      "Safety cars are random but predictable in aggregate: about half of all races see at least one, they're most likely right after the start, and they usually last 2–4 laps (a Virtual Safety Car is shorter). Pitting under one costs far less because everyone else is slow too — a well-timed safety car is almost a free pit stop.",
    equation:
      "P(≥1 SC) ≈ 54.5%      start timing heavily front-loaded (36% on lap 1)\nSC pit loss ≈ 0.40–0.50× green   VSC ≈ 0.55–0.70× green",
    params: [
      { label: "SC count [0,1,2,3]", value: "0.455, 0.413, 0.099, 0.033" },
      { label: "SC duration peak", value: "2–4 (VSC 1–2)", unit: "laps" },
      { label: "VSC after failure", value: "0.227" },
    ],
    note: "Correction: a flat per-lap hazard misses the lap-1 spike and duration. Model three parts — count, front-loaded start timing, and duration — with a per-circuit base rate (Singapore / Baku / Monaco ≫ Paul Ricard).",
  },
];

const SOURCES = [
  {
    label: "Heilmeier et al. 2020 — Monte Carlo race simulation (Applied Sciences)",
    url: "https://www.mdpi.com/2076-3417/10/12/4229",
  },
  {
    label: "TUMFTM/race-simulation — open-source code + calibrated parameter files",
    url: "https://github.com/TUMFTM/race-simulation",
  },
  {
    label: "State-Space Tyre Degradation (arXiv 2512.00640)",
    url: "https://arxiv.org/html/2512.00640v1",
  },
  {
    label: "Aguad & Thraves — Stackelberg pit-stop game (EJOR 2024)",
    url: "https://www.sciencedirect.com/science/article/abs/pii/S0377221724005484",
  },
];

export function Explainer() {
  return (
    <div className="space-y-8">
      {/* Intro */}
      <div className="rounded-xl border border-edge bg-gradient-to-br from-slate-panel to-graphite p-6">
        <div className="mb-2 text-xs uppercase tracking-[0.2em] text-zinc-500">
          How the engine thinks
        </div>
        <h2 className="text-2xl font-bold tracking-tight text-zinc-100">
          The science, in plain English
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-400">
          F1Predict simulates a Grand Prix thousands of times to turn physics and
          statistics into honest win probabilities and strategy calls. The core idea
          is simple:
        </p>
        <p className="mt-3 max-w-2xl text-base leading-relaxed text-zinc-200">
          a car's lap time is mostly{" "}
          <span className="font-semibold text-f1-redbright">predictable physics</span>{" "}
          + a <span className="font-semibold text-f1-redbright">learned residual</span>{" "}
          + <span className="font-semibold text-f1-redbright">skewed randomness</span>.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {(Object.keys(COMPOUND) as Array<keyof typeof COMPOUND>).map((c) => (
            <span
              key={c}
              className="inline-flex items-center gap-1.5 rounded-full border border-edge bg-carbon px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-zinc-400"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: COMPOUND[c] }}
              />
              {c}
            </span>
          ))}
        </div>
      </div>

      {/* Concept cards, with interactive widgets interleaved near their concept */}
      <div className="grid gap-4 lg:grid-cols-2">
        {SECTIONS.map((s) => (
          <ConceptCard key={s.id} section={s} />
        ))}
      </div>

      {/* Interactive: how a lap is composed (relates to concept 01) */}
      <div>
        <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-zinc-500">
          <span className="h-px w-6 bg-edge" />
          Play with the maths
        </div>
        <LapTimeBuilder />
      </div>

      {/* Interactive: tyre degradation (relates to concept 03) */}
      <div className="grid gap-4">
        <TyreSandbox />
        <TeamTyreOverlay />
      </div>

      {/* Sources */}
      <div className="rounded-xl border border-edge bg-graphite p-5">
        <h3 className="text-xs uppercase tracking-wider text-zinc-500">Sources</h3>
        <ul className="mt-3 space-y-2">
          {SOURCES.map((src) => (
            <li key={src.url}>
              <a
                href={src.url}
                target="_blank"
                rel="noreferrer noopener"
                className="group flex items-start gap-2 text-sm text-zinc-400 transition hover:text-f1-redbright"
              >
                <span className="mt-1.5 h-1 w-1 flex-shrink-0 rounded-full bg-edge group-hover:bg-f1-red" />
                <span className="leading-relaxed underline decoration-edge underline-offset-2 group-hover:decoration-f1-red">
                  {src.label}
                </span>
              </a>
            </li>
          ))}
        </ul>
        <p className="mt-4 border-t border-edge pt-3 text-[11px] leading-relaxed text-zinc-600">
          Every parameter is seeded from peer-reviewed work and real calibration
          files, then re-fit to data. Full derivations live in{" "}
          <span className="text-zinc-500">docs/science/</span>.
        </p>
      </div>
    </div>
  );
}

function ConceptCard({ section }: { section: Section }) {
  const [open, setOpen] = useState(false);
  const hasDetail = Boolean(section.equation || section.params || section.note);

  return (
    <div className="flex flex-col rounded-xl border border-edge bg-graphite p-5 transition hover:border-zinc-600">
      <div className="mb-2 flex items-baseline gap-3">
        <span className="font-mono text-xs font-bold tabular text-f1-red">
          {section.index}
        </span>
        <h3 className="text-base font-semibold text-zinc-100">{section.title}</h3>
      </div>
      {section.tag && (
        <div className="mb-3 text-[10px] uppercase tracking-wider text-zinc-500">
          {section.tag}
        </div>
      )}
      <p className="text-sm leading-relaxed text-zinc-300">{section.blurb}</p>

      {hasDetail && (
        <div className="mt-4">
          <button
            onClick={() => setOpen((o) => !o)}
            className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500 transition hover:text-zinc-300"
          >
            <span
              className={`inline-block transition-transform ${
                open ? "rotate-90" : ""
              }`}
            >
              ▸
            </span>
            The math · the numbers
          </button>

          {open && (
            <div className="mt-3 space-y-3 border-t border-edge pt-3">
              {section.equation && (
                <pre className="overflow-x-auto rounded-lg border border-edge bg-carbon p-3 font-mono text-[11px] leading-relaxed text-zinc-300">
                  {section.equation}
                </pre>
              )}
              {section.params && (
                <table className="w-full text-xs">
                  <tbody>
                    {section.params.map((p) => (
                      <tr key={p.label} className="border-b border-edge/60 last:border-0">
                        <td className="py-1.5 pr-3 text-zinc-500">{p.label}</td>
                        <td className="py-1.5 text-right font-mono tabular text-zinc-200">
                          {p.value}
                          {p.unit ? (
                            <span className="ml-1 text-zinc-500">{p.unit}</span>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {section.note && (
                <p className="text-[11px] leading-relaxed text-zinc-500">
                  <span className="font-semibold text-amber-400/90">Note · </span>
                  {section.note}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
