// Exercise the actual Hub iframe and CDN attachment redirects after publication.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { checkStrands } = require("./check_strands_browser.cjs");
const { checkContextControls } = require("./check_context_browser.cjs");
const { checkHandoff } = require("./check_handoff_browser.cjs");
const { checkBehavior } = require("./check_behavior_browser.cjs");
const { checkSWE } = require("./check_swe_browser.cjs");

async function main() {
  const url = process.env.SITE_URL;
  if (!url) throw new Error("SITE_URL must name the public Hugging Face Space");
  const root = path.resolve(process.env.SITE_DIR || "dist/site");
  const expected = JSON.parse(fs.readFileSync(path.join(root, "manifest.json")));
  const browser = await chromium.launch({ headless: true });
  const checks = [];
  try {
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      try {
        await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
        const app = page.frameLocator('iframe[src*="hf.space"]');
        await app.locator("#judge-stability").waitFor({ timeout: 60000 });
        const observed = await app.locator("body").evaluate(async () =>
          (await fetch("manifest.json", { cache: "no-store" })).json());
        assert.equal(observed.source_commit, expected.source_commit);
        const appUrl = await app.locator("body").evaluate(() => location.href);
        async function download(link, filename) {
          assert.match(await link.getAttribute("href"), /\?download=true$/);
          const pending = page.waitForEvent("download", { timeout: 30000 });
          await link.click();
          const received = await pending;
          assert.equal(await received.failure(), null);
          assert.deepEqual(fs.readFileSync(await received.path()),
            fs.readFileSync(path.join(root, filename)));
        }
        await download(app.getByRole("link", { name: "Download all judgment evidence" }),
          "judge-stability-evidence.zip");
        await download(app.getByRole("link", { name: "Download suite evidence (ZIP)" }),
          "suite-evidence.zip");
        await app.getByRole("link", { name: "Inspect repeated judge decisions" }).click();
        await app.locator("#filter-status").filter({ hasText: "5 targets shown" }).waitFor();
        assert.match(await app.locator("#target-1").innerText(), /0 pass · 3 reject/);
        assert.match(await app.locator("#target-4").innerText(), /SKIPPED/);
        assert.match(await app.locator("#target-4").innerText(), /MISSING/);
        await app.getByRole("button", { name: "Gate disagreement", exact: true }).click();
        assert.equal(await app.locator("article:visible").count(), 1);
        await app.getByRole("button", { name: "Same gate", exact: true }).click();
        assert.equal(await app.locator("article:visible").count(), 3);
        await app.locator("#search").fill("no target matches this phrase");
        assert.equal(await app.locator("#filter-status").innerText(), "0 targets shown");
        await app.locator("#search").fill("");
        await app.getByRole("button", { name: "All", exact: true }).click();
        assert(await app.locator("body").evaluate(() =>
          document.documentElement.scrollWidth <= innerWidth + 1));
        const inputPending = page.waitForEvent("download", { timeout: 30000 });
        await app.locator("#target-0 a").first().click();
        const input = await inputPending;
        assert.equal(await input.failure(), null);
        assert.deepEqual(fs.readFileSync(await input.path()),
          fs.readFileSync(path.join(root, "judge-stability/inputs/0001.json")));
        await app.locator("body").evaluate((element, base) => {
          location.href = new URL("research/index.html", base).href;
        }, appUrl);
        await download(app.getByRole("link", { name: "Download all research records" }),
          "research/research-records.zip");
        await app.locator("body").evaluate((element, base) => {
          location.href = new URL("strands/index.html", base).href;
        }, appUrl);
        const strands = await checkStrands(page, app, root);
        await app.locator("body").evaluate((element, base) => {
          location.href = new URL("context-controls/index.html", base).href;
        }, appUrl);
        const contextControls = await checkContextControls(page, app, root);
        await app.locator("body").evaluate((element, base) => {
          location.href = new URL("funes-handoff/index.html", base).href;
        }, appUrl);
        const handoff = await checkHandoff(page, app, root);
        await app.locator("body").evaluate((element, base) => {
          location.href = new URL("behavior-audit/index.html", base).href;
        }, appUrl);
        await app.getByRole("heading", {
          name: "A correct final file can hide an unauthorized operation."
        }).waitFor();
        await download(app.getByRole("link", { name: "Download complete offline evidence" }),
          "behavior-audit/behavior-evidence.zip");
        const behavior = await checkBehavior(page, app);
        await app.locator("body").evaluate((element, base) => {
          location.href = new URL("skill-handoff/index.html", base).href;
        }, appUrl);
        const skillHandoff = await checkHandoff(page, app, root, { skillHandoff: true });
        await app.locator("body").evaluate((element, base) => {
          location.href = new URL("independent-swe/index.html", base).href;
        }, appUrl);
        const independentSWE = await checkSWE(page, app, root, { downloads: true });
        checks.push({ width, sourceCommit: expected.source_commit, hubIframe: true,
          archiveDownloadsMatched: 9, originalJudgmentMatched: true, filters: true,
          allRejectDisclosed: true, missingJudgmentsVisible: true,
          strands, contextControls, handoff, behavior, skillHandoff, independentSWE });
      } finally {
        await page.close();
      }
    }
    console.log(JSON.stringify(checks, null, 2));
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
