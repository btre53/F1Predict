// PIT WALL — The Journey: how we built the model, start to finish, and the metrics that judged it.
// A visitor-facing story of the whole arc (docs/journey_notes.md). Static narrative, no API.

type Act = { n: number; title: string; body: string; take: string; kept?: boolean };

const ACTS: Act[] = [
  {
    n: 1,
    title: "The naive start — a physics simulator",
    body: "We began the obvious way: simulate every car's lap times — pace, fuel, tyre wear, pit stops — and rank by total race time. The intuitive, “physical” model.",
    take: "It lost badly (~32% top-pick vs the market's 36%). More physics ≠ better probabilities — a detailed sim compounds small per-lap errors and over-disperses.",
  },
  {
    n: 2,
    title: "The bake-off — let the data pick the model",
    body: "We built a forward-chained, leak-free harness: predict each race using only its past, score, fold the result in. Then we raced a grid+quali baseline, a Glicko rating, a Kalman pace filter, LightGBM, the mechanistic sim, and a team×circuit affinity.",
    take: "They all clustered ~63% top-pick and barely beat a 10-line baseline. The signal is qualifying. The Kalman filter won — best-calibrated, online, interpretable.",
    kept: true,
  },
  {
    n: 3,
    title: "The honest negatives",
    body: "We tested for edges and found none: no edge vs the pre-race market (it's efficient), no in-play edge (our live probability lags the market ~90s), no timing edge, and telemetry driving-style doesn't separate racecraft from the car.",
    take: "We keep every negative on the record. The honesty is the product — the “anti-AWS”, where every number is explainable.",
  },
  {
    n: 4,
    title: "Mechanistic, brand-agnostic features",
    body: "We added track physics, never brand bias: an overtaking-difficulty index, a structural safety-car prior, a hazard-based DNF model, corner-speed car-DNA, and weather. Each validated forward-chained.",
    take: "Weather was the surprise — rain doesn't raise retirements and the wet favourite is already calibrated; it scrambles WHO SCORES, so we widen only the points market in the wet.",
    kept: true,
  },
  {
    n: 5,
    title: "The bug that made the sim “very wrong”",
    body: "Re-investigating the sim, we found it double-counted tyre management: it re-applied a per-team tyre multiplier on top of the Kalman pace, which already includes how a car treats its tyres — so it crowned the gentle-tyre teams regardless of speed.",
    take: "Removing it + calibrating the pace scale flipped the result: the anchored, ensembled sim now beats the rank model on order accuracy.",
    kept: true,
  },
  {
    n: 6,
    title: "Decoupling the lump into measured parts",
    body: "A car's “strength” is a lump — pace, tyre wear, reliability, racecraft, all tangled. We pulled them apart into measured, traceable components: clean-air race pace, a measured non-linear dirty-air curve (worse the closer you are; slipstream tracks shrug it off, high-speed-corner tracks bite), per-car tyre deg from its own stints, the official starting grid, and reliability handled only by the hazard model.",
    take: "Every car/driver attribute now ties to a row of observed data — no “Team X is good on tyres” assumptions, no double-counts.",
    kept: true,
  },
  {
    n: 7,
    title: "A premise that failed — honestly",
    body: "We sourced Pirelli's real C1–C6 tyre nominations for 94 races to make degradation comparable across weekends. Expected: softer compound, faster wear. It backfired — the softest compounds show the LOWEST in-race wear, because they're only nominated at low-deg tracks and run in short, managed stints.",
    take: "The plain relative compound is the cleaner signal. We sourced it, tested it, understood WHY it failed, and shelved it. That's the method.",
  },
  {
    n: 8,
    title: "The final scorecard",
    body: "After all of it, the rank model and the physics sim split the trophies. The rank model is better-calibrated on win/podium/points; the sim is better at ordering the field, especially the midfield (best-of-rest). The ensemble tunes between them and can never do worse than the rank model.",
    take: "The physics never beat a calibrated rating model on probabilities — but it became genuinely better at ordering the midfield, with every number tied to data. Calibration + transparency over a false edge.",
    kept: true,
  },
];

const METRICS = [
  ["Forward-chained, leak-free", "Predict each race from only its past — the model never sees the future, not even future seasons."],
  ["Calibration-first", "A single temperature tuned on win log-loss; we report Brier + log-loss + reliability for win / podium / points."],
  ["Best-of-the-rest", "Predict P2 with the actual winner removed — the high-variance signal that matters when one car dominates."],
  ["Top-pick accuracy", "How often the favourite is the actual winner — the headline, near-trivial when there's a dominant car."],
  ["Per-race DNF log-loss", "The hazard DNF model vs a flat retirement rate."],
  ["vs the market", "Brier of our win probabilities against de-vigged Polymarket prices — the honest “do we have edge?” test."],
];

const SCORE = [
  { model: "Rank model (shipped)", win: "0.131", pod: "0.244", pts: "0.471", top: "0.333", bor: "0.378", best: "calibration" },
  { model: "Physics sim", win: "0.139", pod: "0.285", pts: "0.503", top: "0.356", bor: "0.489", best: "order accuracy" },
];

export function Journey() {
  return (
    <div className="pw-stack">
      <div className="pw-intro">
        <div className="pw-chip">▮ THE JOURNEY</div>
        <h2>How we built the model — and what it taught us</h2>
        <p>From a naive lap-time simulator to a forward-chained rating model, through honest dead
          ends, to a sim where every number ties back to observed data. The story, and the metrics
          that judged every step.</p>
      </div>

      <div className="pw-panel">
        <div className="pw-timeline">
          {ACTS.map((a) => (
            <div className={`pw-act${a.kept ? " kept" : ""}`} key={a.n}>
              <div className="num">{a.n}</div>
              <div>
                <div className="ttl">{a.title}</div>
                <div className="body">{a.body}</div>
                <div className="take">{a.take}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="pw-intro" style={{ paddingTop: 8 }}>
        <div className="pw-chip">▮ HOW WE KEPT SCORE</div>
        <h2 style={{ fontSize: 20 }}>The metrics behind every decision</h2>
      </div>
      <div className="pw-grid2">
        {METRICS.map(([k, v]) => (
          <div className="pw-sci" key={k}>
            <div>
              <h3 style={{ fontSize: 15 }}>{k}</h3>
              <div className="body">{v}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="pw-panel flush">
        <div style={{ padding: "18px 20px 0" }}>
          <div className="pw-phead">
            <h2>The final scorecard</h2>
            <span className="label">forward-chained · 45 recent races</span>
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="pw-table">
            <thead>
              <tr><th>Model</th><th className="num">win ll</th><th className="num">podium ll</th>
                <th className="num">points ll</th><th className="num">top-pick</th>
                <th className="num">best-of-rest</th><th>wins on</th></tr>
            </thead>
            <tbody>
              {SCORE.map((r) => (
                <tr key={r.model}>
                  <td><b>{r.model}</b></td>
                  <td className="num">{r.win}</td><td className="num">{r.pod}</td>
                  <td className="num">{r.pts}</td><td className="num">{r.top}</td>
                  <td className="num">{r.bor}</td>
                  <td style={{ color: "var(--red)" }}>{r.best}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="label" style={{ padding: "0 20px 16px" }}>
          Lower log-loss = better-calibrated; higher accuracy = picks the actual order more often.
          We ship the rank model for probabilities and use the sim for race texture and props.
          Full detail in docs/MODEL.md + docs/science/.
        </div>
      </div>
    </div>
  );
}
