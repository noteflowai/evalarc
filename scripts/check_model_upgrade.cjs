"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
  const root = path.resolve(process.env.SITE_DIR || "dist/site", "model-upgrade");
  const data = JSON.parse(await fs.readFile(path.join(root, "review.json"), "utf8"));
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  try {
    await fs.mkdir("artifacts/model-upgrade-browser", { recursive: true });
    for (const width of [1440, 390, 320]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: "reduce" });
      const requests = [];
      page.on("pageerror", error => errors.push(String(error)));
      page.on("request", request => requests.push(request.url()));
      await page.goto("file://" + path.join(root, "index.html"));
      assert.equal(await page.locator("#case option").count(), 8);
      assert.equal(await page.locator("#seed option").count(), 3);
      for (const item of data.protocol.cases) {
        await page.locator("#case").selectOption(item.id);
        for (const seed of data.protocol.seeds) {
          await page.locator("#seed").selectOption(String(seed));
          for (const label of ["baseline", "current"]) {
            assert.equal(await page.locator(`#${label}-text`).innerText(),
              data.records[label][`${item.id}-${seed}`].record.text);
          }
        }
      }
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.goto("file://" + path.join(root, "index.html") + "#case=already-closed&seed=29");
      assert.equal(await page.locator("#case").inputValue(), "already-closed");
      assert.equal(await page.locator("#seed").inputValue(), "29");
      await page.locator("#seed").selectOption("43");
      await page.reload();
      assert.equal(await page.locator("#seed").inputValue(), "43");
      assert.equal((await page.locator("#current-text").innerText()).trim(), "{}");
      assert(requests.every(url => url.startsWith("file:")), "Offline review made a network request");
      await page.screenshot({ path: `artifacts/model-upgrade-browser/${width}.png`, fullPage: true });
      await page.close();
    }
    assert.deepEqual(errors, []);
    console.log("Model upgrade review: all 48 original answers, case/seed controls, mobile, offline, no network.");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
