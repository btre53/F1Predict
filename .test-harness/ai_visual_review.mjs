// Visual review — screenshot pass (adapted for a click-tab SPA).
//
// Reads ai_review_config.json. For each "route" it loads baseUrl once, clicks the tab's
// nav button (route.click), waits route.wait ms for data to fetch/render, then screenshots.
// Writes images + manifest.json to ./shots-ai-review/ for the review subagent.
//
// Usage:  node ai_visual_review.mjs  [--route=Markets] [--base=http://localhost:5173]

import { chromium } from "playwright";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CONFIG_PATH = resolve(HERE, "ai_review_config.json");
const SHOTS_DIR = resolve(HERE, "shots-ai-review");
mkdirSync(SHOTS_DIR, { recursive: true });

const ARGS = Object.fromEntries(
    process.argv.slice(2).map((a) => {
        const m = a.match(/^--([^=]+)=?(.*)$/);
        return m ? [m[1], m[2] || true] : [a, true];
    }),
);

const cfg = JSON.parse(readFileSync(CONFIG_PATH, "utf8"));
if (ARGS.base) cfg.baseUrl = ARGS.base;
const ROUTES = ARGS.route ? cfg.routes.filter((r) => r.label === ARGS.route) : cfg.routes;

async function main() {
    const browser = await chromium.launch();
    const taken = [];
    const consoleErrors = {};
    try {
        for (const mode of cfg.modes) {
            for (const vp of cfg.viewports) {
                const ctx = await browser.newContext({
                    colorScheme: mode,
                    viewport: { width: vp.width, height: vp.height },
                });
                const page = await ctx.newPage();
                await page.emulateMedia({ colorScheme: mode });
                for (const r of ROUTES) {
                    const errs = [];
                    page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
                    page.on("pageerror", (e) => errs.push(String(e)));
                    try {
                        await page.goto(cfg.baseUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
                        await page.waitForTimeout(500);
                        if (r.click) {
                            await page.getByRole("button", { name: r.click }).first()
                                .click({ timeout: 6000 });
                        }
                        await page.waitForTimeout(r.wait || 3000);
                    } catch (e) {
                        console.log(`  [skip] ${r.label} ${vp.name} ${mode}: ${e.message}`);
                        page.removeAllListeners("console");
                        page.removeAllListeners("pageerror");
                        continue;
                    }
                    const safe = `${r.label}_${vp.name}_${mode}`.replace(/[^a-z0-9_-]/gi, "_");
                    const file = resolve(SHOTS_DIR, safe + ".png");
                    await page.screenshot({ path: file, fullPage: true });
                    taken.push({
                        path: r.label, label: r.label, viewport: vp.name,
                        viewport_px: `${vp.width}x${vp.height}`, mode, file,
                        console_errors: [...new Set(errs)].slice(0, 10),
                    });
                    if (errs.length) consoleErrors[r.label] = [...new Set(errs)].slice(0, 10);
                    console.log(`  shot ${safe}${errs.length ? `  (${errs.length} console errors)` : ""}`);
                    page.removeAllListeners("console");
                    page.removeAllListeners("pageerror");
                }
                await ctx.close();
            }
        }
    } finally {
        await browser.close();
    }

    const manifestPath = resolve(SHOTS_DIR, "manifest.json");
    writeFileSync(manifestPath, JSON.stringify({
        baseUrl: cfg.baseUrl,
        projectContext: cfg.projectContext,
        ratingScale: cfg.ratingScale,
        maxFindingsPerScreen: cfg.maxFindingsPerScreen,
        consoleErrors,
        screenshots: taken,
    }, null, 2), "utf8");
    console.log(`\nWrote ${taken.length} screenshots.\nManifest -> ${manifestPath}`);
}

await main();
