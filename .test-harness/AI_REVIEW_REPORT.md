# AI Visual Review

**Generated:** 2026-06-04
**Screenshots reviewed:** 10
**Total findings:** 22
- 5★: 2
- 4★: 3
- 3★: 7
- 2★: 7
- 1★: 3

The app's core look is strong — the pit-wall aesthetic lands, the dense data panels (Companion, Markets order books, Explainer, Scenario) are genuinely impressive and the copy is sharp. The findings that matter are concentrated in a handful of **data-integrity and broken-layout** problems that a technical recruiter would notice immediately: an empty chart panel, a broken multi-column text wrap, unsorted standings tables, an implausible 106% vig, and the default Predictor route captured fully blank on a loader.

## Top 15 findings (sorted by severity)

### ★★★★★ (5) — dead-ui — StrategyLab (desktop)
**Issue:** The "Lap-time profile" panel is empty — only the header and legend ("Drift down = fuel burn-off · saw-tooth = tyre deg · dashed = pit stops") render, with no chart.
**Where:** Mid-page, between the strategy list and the Undercut/Cover panels.
**Suggested fix:** Render the lap-time line chart, or show an explicit empty state. Never ship a captioned chart panel that is blank.

### ★★★★★ (5) — broken — Findings (desktop)
**Issue:** The "KILLED" research cards render body copy 2-3 words per line ("Telemetry / style ≠ / racecraft", "edge / comes / from / data we / structurally / lack:"), creating a wall of single-word lines. It's a column-width collapse and the main reason the page is ~13,000px tall.
**Where:** The two-column "KILLED" card section in the lower half of the page.
**Suggested fix:** Fix the card/grid width so paragraphs wrap at a normal line length (45-75 chars). The cards are collapsing to a fraction of their intended width.

### ★★★★ (4) — dead-ui — Predictor (desktop)
**Issue:** The default route was captured stuck on the loading state — spinning track outline and "RUNNING 10,000 RACE SIMULATIONS…" with the entire results area blank. The landing page reads as empty.
**Where:** Center of viewport; everything below the CIRCUIT selector is empty.
**Suggested fix:** Paint from a cached/seeded result on first load, or show a results skeleton so the page is never visually empty.

### ★★★★ (4) — broken — Championship (desktop)
**Issue:** Driver standings are not sorted by points — OCO (1pt) is rank 9, BEA (17) rank 10, LAW (14) rank 11, GAS (19) rank 12. A standings table where 19pts ranks below 1pt reads as a data bug.
**Where:** Drivers' championship table, rows 8-12 (PTS column vs rank).
**Suggested fix:** Surface the sort key — if sorted by title odds (all <1% there), add a visible header sort indicator or secondary PTS sort so the order is explainable.

### ★★★★ (4) — broken — Markets (desktop)
**Issue:** "Monaco · Winner" shows "106% VIG" in red, with Gabriel Bortoleto at 48% implied on a PRICE of 0.997 (99.7% last-trade) tagged LAST. A 0.997 last de-vigged to 48%, plus a 106% vig, looks like a parsing error next to the clean 12%-vig Pole panel beside it.
**Where:** Monaco · Winner panel header (106% VIG) and the Bortoleto row.
**Suggested fix:** Verify the de-vig math and the 0.997 price source; flag/cap implausible books explicitly and reconcile the 106% vs 12% mismatch.

### ★★★ (3) — broken — Championship (desktop)
**Issue:** Constructors table order is also jumbled: Red Bull Racing (337 EXP PTS) is rank 8 while Haas (86), Racing Bulls (123) and Williams (49) rank above it.
**Where:** Constructors' championship table, EXP PTS column.
**Suggested fix:** Same as drivers — expose the sort key or add EXP-PTS sorting; the visible contradiction reads as broken.

### ★★★ (3) — content — StrategyLab (desktop)
**Issue:** All six ranked strategies show the identical "avg 90.9s/lap" while their deltas differ (+0.0/+0.1/+0.2s). The metric is rounded too coarsely to distinguish OPTIMAL from #6.
**Where:** Optimal strategies list, the per-row "avg 90.9s/lap" label.
**Suggested fix:** Show avg lap to enough precision to differentiate rows (90.91 vs 90.94), or drop the redundant avg and lean on the delta.

### ★★★ (3) — dead-ui — Explorer (desktop)
**Issue:** Captured at lap 1/57 with no telemetry — LAST LAP shows "—:—.—", S1/S2/S3 bars are empty, deltas static. The replay reads as idle/not-started.
**Where:** LEADER timing panel (S1/S2/S3, LAST LAP) and lap counter.
**Suggested fix:** Auto-advance the replay a few laps for the default state, or seed lap-1 sector times so the panel isn't full of dashes.

### ★★★ (3) — dead-ui — Markets (desktop)
**Issue:** The "Calibration — win probability" chart shows only two red points sitting near the corners of the dashed identity line — it doesn't read as a calibration curve.
**Where:** Calibration panel, lower-left.
**Suggested fix:** Plot the full set of binned calibration points (with counts), or state n if sparse; two corner dots look like a render failure.

### ★★★ (3) — content — Explainer (desktop)
**Issue:** The "Per-team tyre management" selector uses cryptic 2-letter chips (RP, A, AR, S, AM, FI, A, A, R, F, ARR, C, HFT, M, M, W, RBR, R, TR, KS, RB) with duplicates ("A" ×4, "M" ×2) and no legend.
**Where:** Per-team tyre management panel, chip row above the curves.
**Suggested fix:** Use recognizable team abbreviations (MER, FER, RBR, MCL…) with team-colour dots, or add labels on hover.

### ★★★ (3) — density — Predictor (desktop)
**Issue:** ~60% of the viewport is empty black — circuit selector top-left, loader floating mid-page. Padding-to-content ratio is far too high for a dense pit-wall look.
**Where:** Whole viewport.
**Suggested fix:** Tighten the layout so controls and (loaded) results fill the column; the loader should occupy the results panel, not the full page.

### ★★★ (3) — density — Findings (desktop)
**Issue:** Page is ~13,000px tall with no in-page navigation or anchors — a reviewer can't jump between Model Replay, KILLED findings and Research briefs.
**Where:** Whole page length.
**Suggested fix:** Add a sticky section nav / TOC and collapse the long research-brief lists behind expanders.

### ★★ (2) — broken — Predictor (desktop)
**Issue:** The theme toggle in the header is clipped — a stray "c" is cut off at the right edge next to the toggle.
**Where:** Top-right header, right of the dark/light toggle.
**Suggested fix:** Reserve width for the toggle's adjacent label or keep it inside the header bounds.

### ★★ (2) — content — Championship (desktop)
**Issue:** ANT at 87% model / 49% market (+38pp) on a season title market, while the page's own note says title markets are efficient and the sim carries "no edge". The headline number contradicts the methodology copy.
**Where:** Drivers table row 1 vs the "Reading the market column" note.
**Suggested fix:** Soften the leader's model probability or add an inline caveat next to the largest Δ.

### ★★ (2) — content — Companion (desktop)
**Issue:** The "MODEL ■ · MARKET |" legend repeats verbatim in the top-right of every panel (Podium, Pole, Race winner, Safety car).
**Where:** Top-right of each prop panel header.
**Suggested fix:** Show the legend once at the page top and drop it from the per-panel headers.

## Per-route detail

### Predictor (desktop) — /Predictor
> Captured fully blank on a loader with most of the viewport empty — the worst first impression of the set despite a clean header.

- **★★★★ (4) — dead-ui** — Default route stuck on "RUNNING 10,000 RACE SIMULATIONS…" with a blank results area.
  - Where: Center of viewport, below the CIRCUIT selector.
  - Fix: Paint from a cached/seeded result or show a results skeleton.
- **★★★ (3) — density** — ~60% of the viewport is empty black; padding-to-content ratio far too high.
  - Where: Whole viewport.
  - Fix: Tighten layout so controls and results fill the column; loader lives in the results panel.
- **★★ (2) — broken** — Theme toggle clipped, stray "c" cut off at the right edge.
  - Where: Top-right header.
  - Fix: Reserve width for the label or keep it inside the header bounds.

### Championship (desktop) — /Championship
> Dense and well-designed, but both standings tables appear unsorted relative to their points columns, which reads as a data bug.

- **★★★★ (4) — broken** — Driver standings not sorted by points (1pt above 19pts).
  - Where: Drivers table rows 8-12.
  - Fix: Expose the sort key or add a PTS sort indicator.
- **★★★ (3) — broken** — Constructors order jumbled vs EXP PTS (RBR 337 below Williams 49).
  - Where: Constructors table EXP PTS column.
  - Fix: Same — surface the sort key or add EXP-PTS sorting.
- **★★ (2) — content** — ANT +38pp model-vs-market edge contradicts the "no edge / efficient market" note.
  - Where: Drivers row 1 vs the market-column note.
  - Fix: Soften the probability or add an inline caveat.

### Companion (desktop) — /Companion
> One of the strongest pages — clean prop tables, honest framing, clear edge column. Only minor repetition to trim.

- **★★ (2) — content** — "MODEL ■ · MARKET |" legend repeated in every panel header.
  - Where: Top-right of each panel.
  - Fix: Show the legend once at the top.
- **★ (1) — hierarchy** — Safety-car panel has a single "Yes" row, leaving the panel under-filled.
  - Where: Safety car panel.
  - Fix: Add the "No" row or compress the panel height.

### StrategyLab (desktop) — /StrategyLab
> Good strategy comparison and interactive calculators, undercut by one empty chart panel and a non-differentiating avg-lap metric.

- **★★★★★ (5) — dead-ui** — "Lap-time profile" panel renders only header + legend, no chart.
  - Where: Between the strategy list and the calculators.
  - Fix: Render the chart or show an explicit empty state.
- **★★★ (3) — content** — All six strategies show identical "avg 90.9s/lap" despite differing deltas.
  - Where: Optimal strategies list.
  - Fix: Add precision to the avg lap or drop it in favour of the delta.

### Scenario (desktop) — /Scenario
> Excellent — clear narrative, readable bars, the "BOX NOW" recommendation card with reasoning is exactly the right level of polish. Slightly under-filled below the card.

- **★ (1) — hierarchy** — Single scenario card leaves the lower half of the page empty.
  - Where: Below the Safety-car card.
  - Fix: Optional summary/outcome strip below; not a blocker.

### Explorer (desktop) — /Explorer
> Handsome timing-screen layout, but captured idle at lap 1 with empty telemetry and a flat, hard-to-scan standings list.

- **★★★ (3) — dead-ui** — Replay at lap 1/57 with empty sectors and "—:—.—" last lap reads as not-started.
  - Where: LEADER timing panel and lap counter.
  - Fix: Auto-advance a few laps for the default state or seed lap-1 sector times.
- **★★ (2) — hierarchy** — 20-row standings has no grouping/striping and near-identical bar lengths.
  - Where: Standings rows 1-20.
  - Fix: Add row striping and scale the gap bars to the actual delta.

### Markets (desktop) — /Markets
> The order-book tables and Brier scoreboard are portfolio highlights — but a 106% vig and a near-empty calibration chart are exactly the data-integrity tells a recruiter looks for.

- **★★★★ (4) — broken** — "106% VIG" + Bortoleto 48% implied on a 0.997 last-trade price looks like a de-vig/parsing error.
  - Where: Monaco · Winner panel header and Bortoleto row.
  - Fix: Verify the de-vig math and price source; flag/cap implausible books; reconcile 106% vs 12%.
- **★★★ (3) — dead-ui** — Calibration chart shows only two corner points, not a curve.
  - Where: Calibration panel, lower-left.
  - Fix: Plot the full binned calibration set or state n if sparse.

### Explainer (desktop) — /Explainer
> Genuinely excellent — the numbered concept cards, interactive tyre-degradation sandbox and sourced references are recruiter-grade. Only the team-chip codes hurt.

- **★★★ (3) — content** — Per-team selector uses ambiguous duplicate 2-letter chips ("A" ×4) with no legend.
  - Where: Per-team tyre management chip row.
  - Fix: Use recognizable team abbreviations + colour dots or hover labels.

### Findings (desktop) — /Findings
> Strong content and an honest "we kept the negatives" stance, but a broken text-column wrap turns the KILLED section into a 13,000px wall of single-word lines.

- **★★★★★ (5) — broken** — "KILLED" cards wrap body copy 2-3 words per line (column width collapse).
  - Where: Two-column KILLED card section.
  - Fix: Fix card/grid width so text wraps at a normal line length.
- **★★★ (3) — density** — ~13,000px page with no anchors or section nav.
  - Where: Whole page.
  - Fix: Add sticky section nav and collapse long brief lists.
- **★★ (2) — content** — Actual-winner row not visually marked in the "who believed" table; equal-% bars look identical hit-or-miss.
  - Where: 2026 Canadian finish table, WIN PROBABILITY bars.
  - Fix: Tint/mark the actual winner's row.

### Journey (desktop) — /Journey
> Thoughtful build-narrative, but a long monotone scroll of similar cards and tiny metrics tables makes the key takeaways hard to find.

- **★★ (2) — density** — ~4,000px of dense paragraphs + small text-heavy metrics tables, hard to scan.
  - Where: Full page, especially the lower metrics grid.
  - Fix: Add anchors/sticky nav and a headline-numbers summary band up top.
- **★ (1) — hierarchy** — Numbered steps share near-identical styling; no signposting of the pivotal finding.
  - Where: Numbered story cards.
  - Fix: Accent the 1-2 key steps with colour.
