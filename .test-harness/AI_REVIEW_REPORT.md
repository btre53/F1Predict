# AI Visual Review
**Generated:** 2026-06-02
**Screenshots reviewed:** 7
**Total findings:** 21
- 5★: 2 / 4★: 5 / 3★: 8 / 2★: 4 / 1★: 2

---

## Top findings (sorted by severity)

### ★★★★★ (5) — DATA INTEGRITY — Predictor
**Issue:** The screenshot captures the Predictor mid-simulation ("RUNNING 10,000 RACE SIMULATIONS…") with zero results rendered. The entire right two-thirds of the viewport is empty dark grid. No win-probability table, no podium distribution, no lap-time chart — nothing that demonstrates the app's core value proposition. A recruiter landing here sees a circuit dropdown and a loading string, not a prediction engine.
**Where:** Entire results area (roughly 75% of the page width) is blank. Only the circuit selector, the "NEXT: MONACO GP • 4D ✓" badge, and the loading text are visible.
**Suggested fix:** Either (a) pre-seed the screenshot after simulation completes so results are visible, or (b) add a skeleton/placeholder state that shows panel outlines so the layout intent is clear even while loading. The current state makes the page look broken rather than loading.

### ★★★★★ (5) — DATA INTEGRITY — Explorer
**Issue:** The live sector-timing panel shows "---" for all three sector times (S1, S2, S3) and "LAST LAP" displays as "–:–– .–––" (dashes). This is on Lap 1 / Status GREEN — the simulation is supposedly running, but no timing data is being fed through. The 404 console error likely points to a missing data asset that supplies this feed.
**Where:** Top-right timing panel inside the race replay card. S1/S2/S3 rows all read "---" or "---.----". LAST LAP row shows full dash placeholder.
**Suggested fix:** Investigate the 404 resource (likely the lap-data JSON or telemetry endpoint). If data is legitimately unavailable for lap 1 before the leader crosses S1, show a meaningful "waiting for sector data…" micro-label rather than raw dash placeholders, which look like broken state.

### ★★★★ (4) — DATA INTEGRITY — Explorer
**Issue:** The track map renders as a single large red dot with no car positions or multi-car dot cloud. Per the documented fallback this is the "uncached race" single-dot state, but it occupies the full map panel and looks indistinguishable from a rendering error to an external reviewer. There is no label, caption, or visual indicator explaining this is a fallback state.
**Where:** Left panel of the "Race replay · Australian 2026" card.
**Suggested fix:** Add a small overlay or caption on the map panel ("Track map loading — race not yet cached") so the fallback intent is legible. The racing line / circuit outline shows faintly, which is good, but the single dot still reads as broken.

### ★★★★ (4) — DATA INTEGRITY — Scenario
**Issue:** The "PIT NOW" comparison bar is visually shorter than the "STAY OUT" bar (PIT NOW shows roughly 65% of the bar width; STAY OUT fills 95%+), yet PIT NOW is the recommended faster option at 38.1 s vs STAY OUT at 47.9 s. The bar lengths are inverted relative to the time values — longer bar should mean longer/worse time if bars represent total time, but the layout implies the longer bar is better. This creates a confusing signal: the recommendation says "BOX NOW" but the bar graphic contradicts it.
**Where:** Right panel, "PIT NOW / STAY OUT" comparison rows with progress bars.
**Suggested fix:** Clarify bar encoding. If bars represent remaining race time (lower = better), the shorter PIT NOW bar is correct — but add axis labels or a legend ("lower = faster"). If bars represent something else, fix the length to match values proportionally.

### ★★★★ (4) — LAYOUT / LEGIBILITY — Markets
**Issue:** At 1440 × 900 the Markets page renders at a very compressed zoom. The two driver tables (Monaco Winners / Monaco Pole Position) have columns with values that are near-illegible — the text appears to be roughly 9–10 px rendered size. Column headers ("WIN%", "TOP 3%", etc.) and delta values are too small to read without zooming. For a portfolio piece aimed at recruiters viewing in a browser, this is a trust signal about production-readiness.
**Where:** Both driver probability tables at the top of the page.
**Suggested fix:** Either increase base font size for table rows, reduce column count (move lower-priority columns behind a toggle), or use a wider minimum row height. The "pit wall" aesthetic justifies density but not unreadable text.

### ★★★★ (4) — DATA INTEGRITY — StrategyLab
**Issue:** The "Cover vs extend" panel in the bottom-right shows "Cover value: -39.3s". A negative cover value of nearly 40 seconds is a very large and unexpected number — it implies covering the undercut costs 39 seconds of net race time, which would only be coherent at the very end of a stint. Without more context this looks either correct-but-unexplained or a sign of a degenerate input state. Recruiters scanning the numbers will flag it as suspicious.
**Where:** Bottom-right "Cover vs extend" calculator, "Cover value" row.
**Suggested fix:** Add a brief inline tooltip or note explaining when negative cover values are expected (e.g., "negative = staying out costs more than boxing"). Alternatively, clamp the displayed range and add a "degenerate scenario" warning if inputs push into implausible territory.

### ★★★ (3) — INFORMATION HIERARCHY — Predictor
**Issue:** The footer text "MODELS DOCUMENTED IN docs/science/ · SEEDED FROM THE TUM HEILMEIER RACE SIMULATOR" sits in the lower third of an otherwise blank page. Because there is no results content, this isolated footer reads as the main content — which makes it look like a mostly-empty app rather than a data dashboard mid-load.
**Where:** Footer, approximately 330 px from top on an 867 px-tall content area.
**Suggested fix:** This resolves naturally if the simulation-complete state is what gets screenshotted (finding #1 above). No action needed beyond fixing the empty-panel issue.

### ★★★ (3) — INFORMATION HIERARCHY — StrategyLab
**Issue:** The page is very dense and small at 1440 × 900 — the strategy Gantt bars, lap-profile chart, and both calculators are all visible simultaneously but each section is at roughly 70% of a comfortable reading size. The "Optimal strategies" label and delta values (+0.8s, +0.3s, etc.) are readable, but the lap-time chart Y-axis tick labels and the calculator sub-labels require squinting. This is borderline acceptable for the "pit wall" aesthetic but approaches illegibility.
**Where:** Entire page — lap-time profile chart area and both bottom calculator panels.
**Suggested fix:** Increase the base content width or add a small amount of vertical breathing room between the strategy rows and the chart section. The data itself reads correctly; this is purely a density/sizing concern.

### ★★★ (3) — CONTENT / HIERARCHY — Explainer
**Issue:** The page is very long and the two interactive sandboxes (Tyre Degradation Sandbox and Per-team Tyre Management) are positioned well below the fold with no visual anchor from the top. At 1440 × 900, the eight numbered explanation cards are fully visible, but the charts below them are not visible without scrolling and the screenshot captures them only at very small size. The per-team bar chart is not readable at this zoom level (team labels appear to be ~7 px).
**Where:** Per-team tyre management section, lower third of the screenshot.
**Suggested fix:** Consider making the per-team chart slightly taller or giving it a minimum readable row height. Alternatively, a sticky "jump to interactive models" shortcut from the top of the page would help navigation.

### ★★★ (3) — DATA INTEGRITY — Markets
**Issue:** The "Calibration — win probability" scatter plot shows a tight cluster of points with a near-perfect diagonal line but contains only a small number of data points (roughly 8–12 visible dots). For a calibration plot, this sparse sample undermines the claim of "perfectly calibrated" — it could simply be too few observations to be meaningful. There is no N or confidence interval displayed.
**Where:** Bottom-left panel, "Calibration — win probability" section.
**Suggested fix:** Display the number of observations (n=X) on the chart, and optionally a confidence band. If the dataset is genuinely small, acknowledge it; if larger data underlies it, verify the plot is sampling correctly.

### ★★★ (3) — LAYOUT — Explorer
**Issue:** The driver table extends to 20 rows (VER is P16 with only a white bar, BOT P15 also white) which visually signals these drivers are on the same lap time, while everyone above them has coloured bars. The colour distinction (yellow = in-progress, white = no recent data?) is not explained by any legend on this screen.
**Where:** Driver timing table, rows 15–20 (BOT, VER, COL, LAW, PER, STR).
**Suggested fix:** Add a brief legend: coloured bar = live sector data, white/grey = lapped / no data. Without this, the white bars look like a render bug.

### ★★★ (3) — DATA INTEGRITY — Findings
**Issue:** The four column-tables in the top half of the Findings page (showing driver feature lists under headers like "fast qualifying", "efficient", etc.) contain many driver names in very small text (~9 px at this viewport). They are not readable in the screenshot. For a methodology page meant to demonstrate model quality to recruiters, these tables need to be legible.
**Where:** Feature attribution tables, upper half of the Findings page.
**Suggested fix:** Increase font size in these tables to at least 11 px rendered, or widen the columns. The information is valuable but invisible at this zoom.

### ★★★ (3) — LAYOUT — Findings
**Issue:** The bottom section "Research links" is compressed to a single barely-readable line of text in the footer area. It contains what appear to be academic citations but they are too small to parse (approximately 7–8 px). This is the most scholarly part of the portfolio piece and should be legible.
**Where:** Footer of the Findings page, "Research links" section.
**Suggested fix:** Either increase the font size to match the rest of the page body, or give each citation its own line with readable text.

### ★★ (2) — VISUAL POLISH — Scenario
**Issue:** The outer card containing the scenario controls has a faint top-left corner bracket (visible as a small "┌" glyph at the card's top-left). This appears to be a decorative ASCII-art border element that is only partially rendered — only the top-left corner is present with no matching bottom-right or horizontal/vertical lines extending from it.
**Where:** Top-left of the main scenario card border.
**Suggested fix:** Either complete the corner-bracket border treatment (if intentional) or remove the orphaned glyph.

### ★★ (2) — VISUAL POLISH — Explorer
**Issue:** The same orphaned "┌" corner bracket decoration appears at the top-left of the Explorer replay card. As with Scenario, only one corner is rendered.
**Where:** Top-left of the "Race replay · Australian 2026" card.
**Suggested fix:** Same as Scenario — complete the bracket or remove it.

### ★★ (2) — NAVIGATION — Predictor
**Issue:** The "LIVE SOON" navigation item has a muted colour and the word "SOON" is rendered very small. It reads as both a nav item and a status label simultaneously, which is slightly ambiguous — is it a page you can navigate to, or a coming-soon badge? The dot to its left is the same colour as active nav items.
**Where:** Navigation bar, rightmost item before the theme toggle.
**Suggested fix:** Style the LIVE badge distinctly from regular nav items (e.g., no navigation dot, different opacity, tooltip "Coming soon") so it's clear it's non-interactive.

### ★★ (2) — TYPOGRAPHY — Findings
**Issue:** The page title area uses two different copy treatments back-to-back: "Methodology & findings" in large serif/sans-serif body text, followed immediately by a paragraph of small monospaced text. The transition is slightly jarring — the mono paragraph sits too close to the title without a clear visual separation.
**Where:** Top of Findings page, title and introductory paragraph.
**Suggested fix:** Add slightly more margin between the page title and the first paragraph, or set the intro paragraph in the same font scale as the rest of the page prose.

### ★ (1) — COSMETIC — StrategyLab
**Issue:** The "OPTIONS" label in the top-right of the first strategy row is styled in a distinct red pill/badge. It works at this scale but at compressed viewport the pill clips slightly against the right edge of the card — it appears to be 1–2 px cut off at the right.
**Where:** Top-right of the "2-stop" optimal strategy row.
**Suggested fix:** Add 4 px right padding to the strategy card container.

### ★ (1) — COSMETIC — Markets
**Issue:** The "Model vs Polymarket" section headline uses an "39% 52%" percentage display with green colouring. The two numbers are visually close together and their meaning (model vs market accuracy?) is not labelled inline — the header reads "39% 52%" without clear axis labels at this zoom level.
**Where:** Bottom-right "Model vs Polymarket" panel.
**Suggested fix:** Add micro-labels ("model" and "market" or equivalent) directly adjacent to each percentage figure.

---

## Per-route detail

### Predictor (desktop/dark)
> The screenshot captures an in-progress simulation with all results panels empty, rendering the app's primary feature completely invisible.

- **★★★★★ (5) — DATA INTEGRITY** — All prediction results panels are blank; only the circuit selector and a "RUNNING 10,000 RACE SIMULATIONS…" string are visible. | Where: Entire right 75% of page | Fix: Re-capture after simulation completes, or show a skeleton layout while loading.
- **★★★ (3) — INFORMATION HIERARCHY** — The footer citation text is the only text below the loading string, making the page read as mostly empty. | Where: Footer area | Fix: Resolves with finding above.
- **★★ (2) — NAVIGATION** — "LIVE SOON" nav item is ambiguous — styled like a nav link with a dot, but is non-interactive. | Where: Nav bar right side | Fix: Differentiate visually from real nav items.

### StrategyLab (desktop/dark)
> Functionally well-populated with coherent strategy stacks and both calculators rendering, but density is high and one value raises a data-integrity question.

- **★★★★ (4) — DATA INTEGRITY** — Cover value shows -39.3s in the "Cover vs extend" panel, which is an unexplained large negative number. | Where: Bottom-right calculator, "Cover value" row | Fix: Add tooltip/note explaining when negative values occur; add range clamping for degenerate inputs.
- **★★★ (3) — INFORMATION HIERARCHY** — Page is very dense; lap-time chart Y-axis labels and calculator sub-labels are near the edge of legibility. | Where: Lap-time profile chart + calculator panels | Fix: Increase vertical spacing between major sections or bump base font size slightly.
- **★ (1) — COSMETIC** — "OPTIONS" badge clips slightly at card right edge. | Where: First strategy row, top-right | Fix: Add 4 px right padding to card container.

### Scenario (desktop/dark)
> One of the stronger screens — the safety car scenario is coherent and the layout is well-structured. One data-visualisation ambiguity undermines the bar comparison.

- **★★★★ (4) — DATA INTEGRITY** — PIT NOW bar is shorter than STAY OUT bar, but PIT NOW (38.1 s) is the faster/recommended option. Bar encoding contradicts the recommendation without a legend. | Where: Right panel comparison bars | Fix: Add axis label or legend; ensure bar lengths are proportionally consistent with what they represent.
- **★★ (2) — VISUAL POLISH** — Orphaned "┌" corner bracket decoration at card top-left. | Where: Top-left of main scenario card | Fix: Complete or remove the bracket.

### Explorer (desktop/dark)
> Race table is well-populated and the layout is functional, but the timing panel shows all-dashes and the track map is a single dot — both look broken without context.

- **★★★★★ (5) — DATA INTEGRITY** — All sector times (S1, S2, S3) and LAST LAP show dash placeholders. 404 console error is the likely root cause. | Where: Top-right timing panel | Fix: Resolve 404 resource; add "waiting for data…" label instead of raw dashes.
- **★★★★ (4) — DATA INTEGRITY** — Track map shows single red dot with no car positions or circuit context label; no explanation of fallback state. | Where: Track map panel inside replay card | Fix: Add "Track map loading" overlay caption on the fallback single-dot state.
- **★★★ (3) — LAYOUT** — White/grey bars for P15–P20 rows have no legend to distinguish from coloured timing bars. | Where: Driver timing table, lower rows | Fix: Add a brief legend for bar colours.
- **★★ (2) — VISUAL POLISH** — Orphaned "┌" corner bracket decoration at card top-left. | Where: Top-left of race replay card | Fix: Same as Scenario.

### Markets (desktop/dark)
> Data is present and the calibration + Polymarket comparison panels are a strong portfolio differentiator, but everything is rendered too small to be read at native resolution.

- **★★★★ (4) — LAYOUT / LEGIBILITY** — Driver probability tables use font size approximately 9–10 px rendered; values and column headers are illegible without zoom. | Where: Both driver tables at top of page | Fix: Increase font size or reduce column count.
- **★★★ (3) — DATA INTEGRITY** — Calibration scatter plot shows only ~10 data points; no n-value displayed, making the "perfectly calibrated" claim appear unsupported. | Where: Calibration scatter plot, bottom-left | Fix: Display n= count; add confidence band if possible.
- **★ (1) — COSMETIC** — "39% 52%" model vs market display lacks inline labels for which percentage belongs to which. | Where: Model vs Polymarket panel | Fix: Add "model" / "market" micro-labels.

### Explainer (desktop/dark)
> One of the most complete screens. Eight model explanation cards render clearly, two interactive charts are present. Main issue is legibility of the per-team chart at this viewport.

- **★★★ (3) — INFORMATION HIERARCHY** — Per-team tyre management chart team labels are approximately 7 px — effectively unreadable in the screenshot at this viewport. | Where: Per-team tyre management section, lower page | Fix: Increase minimum row height for bar chart; or make the chart taller.
- No other findings. The 8 numbered explanation cards are legible and well-structured. The tyre degradation sandbox renders correctly.

### Findings (desktop/dark)
> Content-rich methodology page, but multiple text elements are at sizes that undermine legibility. Feature tables and research links are near-invisible.

- **★★★ (3) — DATA INTEGRITY / LEGIBILITY** — Feature attribution tables (driver classification lists) render at ~9 px; content is not readable. | Where: Feature tables, upper half of page | Fix: Increase font size to minimum 11 px rendered.
- **★★★ (3) — LAYOUT** — Research links / citations at page bottom render at ~7–8 px, unreadable. | Where: "Research links" footer section | Fix: Match font size to body prose; give each citation its own line.
- **★★ (2) — TYPOGRAPHY** — Title and intro paragraph transition is abrupt — inadequate vertical margin between display heading and monospaced paragraph. | Where: Page title area | Fix: Increase margin-bottom on the page title.
